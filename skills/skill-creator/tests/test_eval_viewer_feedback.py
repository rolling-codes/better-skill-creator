"""The eval viewer must not accept cross-origin feedback writes."""
from __future__ import annotations

from functools import partial
from http.server import HTTPServer
import http.client
import importlib.util
import io
import json
from pathlib import Path
import threading

import pytest

SKILL = Path(__file__).resolve().parent.parent
VIEWER = SKILL / "eval-viewer" / "generate_review.py"


def _load_viewer():
    spec = importlib.util.spec_from_file_location("generate_review", VIEWER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def viewer(tmp_path, monkeypatch):
    module = _load_viewer()
    monkeypatch.setattr(module, "MAX_FEEDBACK_BYTES", 64)
    feedback = tmp_path / "feedback.json"
    handler = partial(module.ReviewHandler, tmp_path, "demo", feedback, {}, None)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield module, port, feedback
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _post(port, body, headers):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", "/api/feedback", body=body, headers=headers)
    response = conn.getresponse()
    payload = response.read()
    conn.close()
    return response.status, payload


def test_feedback_rejects_cross_origin_and_non_json(viewer):
    _module, port, feedback = viewer
    body = json.dumps({"reviews": []}).encode("utf-8")
    status, _payload = _post(port, body, {
        "Origin": "http://evil.example",
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    })
    assert status == 403
    assert not feedback.exists()

    status, _payload = _post(port, body, {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    })
    assert status == 403
    assert not feedback.exists()

    status, _payload = _post(port, body, {
        "Origin": f"http://127.0.0.1:{port}",
        "Content-Type": "text/plain",
        "Content-Length": str(len(body)),
    })
    assert status == 415
    assert not feedback.exists()

    status, _payload = _post(port, body, {
        "Origin": "http://127.0.0.1:1",
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    })
    assert status == 403
    assert not feedback.exists()


def test_feedback_rejects_a_short_body():
    module = _load_viewer()
    responses = []
    handler = module.ReviewHandler.__new__(module.ReviewHandler)
    handler.path = "/api/feedback"
    handler.headers = {
        "Origin": "http://127.0.0.1:9",
        "Content-Type": "application/json",
        "Content-Length": "20",
    }
    handler.rfile = io.BytesIO(b"{}")
    handler.server = type("Server", (), {"server_address": ("127.0.0.1", 9)})()
    handler.feedback_path = Path("/tmp/eval-viewer-should-not-write-feedback.json")
    handler._json_response = lambda status, payload: responses.append((status, payload))
    handler.do_POST()
    assert responses == [(400, {"error": "Incomplete request body"})]
    assert module.ReviewHandler.timeout == 10


def test_feedback_rejects_oversized_declared_length(viewer):
    _module, port, feedback = viewer
    status, _payload = _post(port, b"{}", {
        "Origin": f"http://localhost:{port}",
        "Content-Type": "application/json",
        "Content-Length": "999999",
    })
    assert status == 413
    assert not feedback.exists()


def test_feedback_accepts_loopback_json_and_writes_utf8(viewer):
    _module, port, feedback = viewer
    body = json.dumps({"reviews": [{"feedback": "café"}]}).encode("utf-8")
    for origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
        feedback.unlink(missing_ok=True)
        status, payload = _post(port, body, {
            "Origin": origin,
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": str(len(body)),
        })
        assert status == 200, payload
        assert json.loads(payload) == {"ok": True}
        written = feedback.read_text(encoding="utf-8")
        assert "café" in written
        assert "\\u" not in written


def test_early_rejections_do_not_reset_the_connection(viewer):
    """Replying 403/415 without reading the body reset the socket; on Windows that raised
    ConnectionAbortedError in roughly 1 of 6 runs of the test above. Repeat to make a race visible."""
    _module, port, _feedback = viewer
    body = json.dumps({"reviews": []}).encode("utf-8")
    for _ in range(60):
        status, _payload = _post(port, body, {
            "Origin": "http://evil.example",
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        })
        assert status == 403
        status, _payload = _post(port, body, {
            "Origin": f"http://127.0.0.1:{port}",
            "Content-Type": "text/plain",
            "Content-Length": str(len(body)),
        })
        assert status == 415


def test_a_client_that_never_sends_the_declared_body_cannot_stall_the_viewer(viewer, monkeypatch):
    """The drain has its own deadline: a declared-but-never-sent body still gets its 403 promptly."""
    import socket
    import time

    module, port, _feedback = viewer
    monkeypatch.setattr(module, "DRAIN_SECONDS", 0.5)
    started = time.monotonic()
    with socket.create_connection(("127.0.0.1", port), timeout=8) as sock:
        sock.sendall(
            b"POST /api/feedback HTTP/1.1\r\nHost: x\r\nOrigin: http://evil.example\r\n"
            b"Content-Type: application/json\r\nContent-Length: 10\r\n\r\n"
        )  # headers only; the 10 declared body bytes never arrive
        reply = sock.recv(4096)
    assert b" 403 " in reply.split(b"\r\n", 1)[0]
    assert time.monotonic() - started < 4
