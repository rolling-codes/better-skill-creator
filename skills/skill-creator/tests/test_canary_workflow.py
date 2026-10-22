"""Offline contracts for the scheduled trigger matrix; no model calls."""
from pathlib import Path
import json
import os
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/test.yml').read_text())
JOB = WORKFLOW['jobs']['trigger-canary']


def test_canary_matrix_budget_and_isolation():
    assert WORKFLOW['permissions'] == {'contents': 'read'}
    assert JOB['strategy'] == {'fail-fast': False, 'matrix': {'model': ['haiku', 'sonnet']}}
    assert JOB['timeout-minutes'] == 15
    assert JOB['concurrency']['cancel-in-progress'] is False
    assert '${{ matrix.model }}' in JOB['concurrency']['group']
    run = next(s['run'] for s in JOB['steps'] if s.get('id') == 'canary')
    for option in ('--max-calls 5', '--workers 1', '--runs 1', '--retries 0'):
        assert option in run
    fixture = ROOT / '.github/fixtures/trigger-canary'
    for name, expected in [('should_trigger.yaml', True), ('should_not_trigger.yaml', False)]:
        cases = yaml.safe_load((fixture / name).read_text())
        assert len(cases) == 2
        assert all(c['expected'] is expected and c['prompt'] for c in cases)
    upload = JOB['steps'][-1]
    assert upload['if'] == 'always()'
    assert upload['with']['path'] == 'canary-results/'
    assert '${{ matrix.model }}' in upload['with']['name']


@pytest.mark.parametrize('credentials,code,outcome,status', [
    ('false', None, 'skipped', 'skipped_missing_credentials'),
    ('true', None, 'skipped', 'infrastructure_failed'),
    ('true', 0, 'success', 'passed'),
    ('true', 1, 'failure', 'infrastructure_failed'),
    ('true', 2, 'failure', 'expectations_failed'),
    ('true', 137, 'failure', 'infrastructure_failed'),
])
def test_summary_preserves_reports_after_each_outcome(tmp_path, credentials, code, outcome, status):
    summary_step = next(s for s in JOB['steps'] if s.get('name') == 'Summarize canary status')
    assert summary_step['if'] == 'always()'
    code_text = summary_step['run'].split("python3 - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
    reports = tmp_path / 'canary-results'
    reports.mkdir()
    original = reports / 'results.json'
    original.write_text('{"original": true}')
    if code is not None:
        (reports / 'exit-code').write_text(str(code))
    summary = tmp_path / 'summary.md'
    env = {**os.environ, 'HAS_OAUTH_TOKEN': credentials, 'CANARY_MODEL': 'haiku',
           'CANARY_OUTCOME': outcome, 'GITHUB_STEP_SUMMARY': str(summary)}
    result = subprocess.run([sys.executable, '-c', code_text], cwd=tmp_path, env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads((reports / 'status.json').read_text()) == {
        'model': 'haiku', 'status': status, 'exit_code': code, 'max_calls': 5}
    assert status in summary.read_text()
    assert (reports / 'status.md').read_text() == summary.read_text()
    assert original.read_text() == '{"original": true}'


def test_fixture_loads_as_exactly_four_eval_cases(tmp_path):
    import shutil
    sys.path.insert(0, str(ROOT / 'skills/skill-creator'))
    from scripts.tests_loader import load_trigger_suite

    shutil.copytree(ROOT / '.github/fixtures/trigger-canary', tmp_path / 'tests')
    cases = load_trigger_suite(tmp_path / "tests")
    assert len(cases) == 4
    assert sum(case['should_trigger'] for case in cases) == 2
