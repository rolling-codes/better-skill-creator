"""Regression tests at the public packaging, process, and review boundaries."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

SKILL = Path(__file__).resolve().parent.parent
REPO = SKILL.parent.parent
sys.path.insert(0, str(SKILL))
from scripts.call_budget import CallBudget
from scripts import claude_process as CP
from scripts import run_eval as RE
from scripts import run_loop as RL
from scripts import improve_description as ID
from scripts.file_policy import snapshot, source_manifest
from scripts.package_skill import package_skill
from scripts.review import ReviewRecord, REQUIRED_ROLES
from scripts.review_gate import analyze, REVIEW_AGENTS
from scripts.skill_ir import Skill


@pytest.fixture
def source(tmp_path):
    """Copy the release-notes example into an isolated, writable skill directory."""
    root = tmp_path/'release-note-draft'
    shutil.copytree(REPO/'examples/release-notes', root)
    return root


def link(path, target, directory=False):
    """Create a test symlink, skipping when the operating system refuses it."""
    try:
        path.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f'OS does not permit test symlink creation: {exc}')


@pytest.mark.parametrize('kind', ['file', 'directory', 'broken', 'SKILL.md', 'review.yaml'])
def test_public_package_rejects_links_before_reading(source, tmp_path, kind):
    """Verify the packaging API rejects source links without producing an archive."""
    outside = tmp_path/'outside'
    outside.mkdir()
    secret = outside/'private.txt'
    secret.write_text('SYNTHETIC-PRIVATE')
    if kind == 'SKILL.md':
        (source/'SKILL.md').unlink()
        link(source/'SKILL.md', secret)
    elif kind == 'review.yaml':
        link(source/'review.yaml', secret)
    elif kind == 'directory':
        link(source/'reference-link', outside, True)
    else:
        link(source/'linked.txt', secret if kind == 'file' else outside/'missing')
    assert package_skill(source, tmp_path/'dist') is None
    assert not list((tmp_path/'dist').glob('*.skill'))


def test_cli_package_rejects_outside_symlink(source, tmp_path):
    """Verify CLI packaging fails when a source link points outside the skill."""
    outside = tmp_path/'outside.txt'
    outside.write_text('SYNTHETIC-PRIVATE')
    link(source/'linked.txt', outside)
    run = subprocess.run([sys.executable, str(REPO/'bsc.py'), 'package', str(source),
                          '--output', str(tmp_path/'dist'), '--runs-dir', str(tmp_path/'runs')],
                         capture_output=True, text=True)
    assert run.returncode != 0
    assert not list((tmp_path/'dist').glob('*.skill'))


@pytest.mark.parametrize('launcher', [False, True])
def test_package_excludes_secrets_and_keeps_source_unchanged(source, tmp_path, launcher):
    """Verify API and CLI packaging omit secrets and leave source bytes unchanged."""
    for name in ('.env', '.env.local', 'private.pem', 'client.key', '.npmrc'):
        (source/name).write_text('SYNTHETIC-PRIVATE')
    (source/'.git').mkdir()
    (source/'.git/config').write_text('SYNTHETIC-PRIVATE')
    before = {str(p.relative_to(source)):p.read_bytes() for p in source.rglob('*') if p.is_file()}
    if launcher:
        run = subprocess.run([sys.executable, str(REPO/'bsc.py'), 'package', str(source),
                              '--output', str(tmp_path/'dist'), '--runs-dir', str(tmp_path/'runs')],
                             capture_output=True, text=True)
        assert run.returncode == 0, run.stdout + run.stderr
        artifact = tmp_path/'dist'/f'{source.name}.skill'
    else:
        artifact = package_skill(source, tmp_path/'dist')
    assert artifact
    with zipfile.ZipFile(artifact) as archive:
        assert f'{source.name}/SKILL.md' in archive.namelist()
        assert not any(b'SYNTHETIC-PRIVATE' in archive.read(n) for n in archive.namelist())
    assert before == {str(p.relative_to(source)):p.read_bytes() for p in source.rglob('*') if p.is_file()}


def test_package_never_overwrites_existing_archive(source, tmp_path):
    """Verify packaging preserves an existing archive and reports failure."""
    out = tmp_path/'dist'
    out.mkdir()
    artifact = out/f'{source.name}.skill'
    artifact.write_bytes(b'KEEP')
    assert package_skill(source, out) is None
    assert artifact.read_bytes() == b'KEEP'


@pytest.mark.skipif(os.name != 'posix', reason='POSIX descriptors and permission bits')
def test_snapshot_rejects_directory_swap(source, tmp_path, monkeypatch):
    """Verify descriptor traversal rejects a directory replaced by an outside symlink."""
    directory = source/'references'
    directory.mkdir()
    (directory/'original.txt').write_text('original')
    outside = tmp_path/'outside';outside.mkdir()
    (outside/'private.txt').write_text('SYNTHETIC-PRIVATE')
    real_open = os.open
    def swap(path, flags, *args, **kwargs):
        """Replace the selected directory with a symlink just before its descriptor is opened."""
        if path == 'references' and kwargs.get('dir_fd') is not None:
            directory.rename(source/'saved')
            directory.symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)
    # Preserve supports_dir_fd identity detection while instrumenting open.
    monkeypatch.setattr(os, 'supports_dir_fd', os.supports_dir_fd | {swap})
    monkeypatch.setattr(os, 'open', swap)
    with pytest.raises(OSError):
        snapshot(source)


@pytest.mark.skipif(os.name != 'posix', reason='POSIX executable mode')
def test_package_preserves_executable_mode(source, tmp_path):
    """Verify packaging retains executable permission bits in ZIP metadata."""
    script = source/'helper.sh';script.write_text('#!/bin/sh\nexit 0\n');script.chmod(0o755)
    artifact=package_skill(source, tmp_path/'dist')
    assert artifact is not None
    with zipfile.ZipFile(artifact) as archive:
        assert archive.getinfo(f'{source.name}/helper.sh').external_attr >> 16 & 0o777 == 0o755


def test_model_profile_forwards_only_explicit_auth(monkeypatch, tmp_path):
    """Verify disposable profiles forward explicit auth and filter unrelated settings."""
    monkeypatch.setenv('UNRELATED_SECRET', 'synthetic-secret')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic-provider-key')
    monkeypatch.setenv('ANTHROPIC_BASE_URL', 'https://untrusted.invalid')
    monkeypatch.setenv('NODE_OPTIONS', '--require unwanted.js')
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path/'user-config'))
    with CP.model_environment() as (env, work):
        assert env['ANTHROPIC_API_KEY'] == 'synthetic-provider-key'
        assert not {'UNRELATED_SECRET','NODE_OPTIONS','ANTHROPIC_BASE_URL','CLAUDECODE'} & env.keys()
        assert env['CLAUDE_CONFIG_DIR'] != str(tmp_path/'user-config')
        assert Path(env['HOME']).is_dir() and work.is_dir()
        isolated_home=Path(env['HOME'])
    assert not isolated_home.exists()


def test_text_request_uses_empty_tools_and_disposable_cwd(monkeypatch, tmp_path):
    """Verify text calls use isolated settings and stop when their shared budget is spent."""
    calls=[]
    monkeypatch.setattr(CP, 'claude_command', lambda *a: ['fake', *a])
    def run(cmd,prompt,**kwargs):
        """Record a text call and assert its working directory and profile are disposable."""
        calls.append((cmd,kwargs))
        assert kwargs['cwd'] != tmp_path
        assert Path(kwargs['env']['CLAUDE_CONFIG_DIR']).is_dir()
        return CP.ProcessResult(stdout='result',returncode=0)
    monkeypatch.setattr(CP,'run_process',run)
    budget=CallBudget(1)
    assert CP.call_claude_text('data',cwd=tmp_path,budget=budget)=='result'
    cmd=calls[0][0]
    assert cmd[cmd.index('--tools')+1]==''
    assert cmd[cmd.index('--setting-sources')+1]==''
    assert cmd[cmd.index('--permission-mode')+1]=='dontAsk'
    assert '--strict-mcp-config' in cmd
    assert json.loads(cmd[cmd.index('--settings')+1])['disableAllHooks'] is True
    with pytest.raises(ValueError,match='budget exhausted'):
        CP.call_claude_text('data',cwd=tmp_path,budget=budget)
    assert len(calls)==1


def test_trigger_retries_share_budget_and_only_expose_skill(monkeypatch,tmp_path):
    """Verify timed-out trigger retries share an allowance and expose only the Skill tool."""
    seen=[]
    monkeypatch.setattr(RE,'claude_command',lambda *a:['fake',*a])
    def run(cmd,prompt,**kwargs):
        """Record an isolated Skill-only request and simulate a timeout."""
        seen.append(cmd)
        assert cmd[cmd.index('--tools')+1]=='Skill'
        assert '--strict-mcp-config' in cmd
        assert 'env' in kwargs
        return CP.ProcessResult(timed_out=True)
    monkeypatch.setattr(RE,'run_process',run)
    budget=CallBudget(2)
    out=RE.run_single_query('q','demo','desc',1,str(tmp_path),max_retries=5,budget=budget)
    assert out.failed
    assert len(seen)==2
    assert budget.report()=={'limit':2,'used':2,'remaining':0}


@pytest.mark.parametrize('name',['../outside','/absolute','..','bad/name','bad\\name'])
def test_trigger_names_cannot_escape_project(tmp_path,name):
    """Verify unsafe skill names are rejected before creating project files."""
    with pytest.raises(ValueError,match='Invalid skill name'):
        RE.run_single_query('q',name,'desc',1,str(tmp_path))
    assert list(tmp_path.iterdir())==[]


def test_shared_budget_is_atomic():
    """Verify concurrent consumers cannot spend more than the shared allowance."""
    budget=CallBudget(7)
    def consume(_):
        """Return one for a charged attempt or zero when the allowance is exhausted."""
        try: budget.consume();return 1
        except ValueError:return 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(consume,range(100)))==7
    assert budget.report()['remaining']==0


def test_loop_rejects_over_budget_before_any_call(monkeypatch,tmp_path):
    """Verify optimization rejects insufficient allowance before evaluating any queries."""
    monkeypatch.setattr(RL,'run_eval',lambda **k:pytest.fail('unexpected eval'))
    with pytest.raises(ValueError,match='needs up to 7 calls'):
        RL.run_loop([{'query':'q','should_trigger':True}],tmp_path,None,1,1,3,1,0.5,0,'haiku',False,max_calls=6)


def test_optimizer_shortening_uses_same_budget(monkeypatch):
    """Verify the initial description and its shortening request charge the same budget."""
    seen=[]
    def request(prompt,model,timeout=300,budget=None):
        """Charge the supplied budget and return an overlong proposal followed by a short one."""
        assert budget is not None
        seen.append(budget);budget.consume()
        return 'x'*1025 if len(seen)==1 else 'short'
    monkeypatch.setattr(ID,'_call_claude',request)
    budget=CallBudget(2)
    assert ID.improve_description('demo','body','desc',{'results':[],'summary':{'passed':0,'total':1}},[],'haiku',budget=budget)=='short'
    assert seen==[budget,budget] and budget.report()['used']==2


def reviewed_source(source):
    """Attach review agents and a passing source-bound record, then return the record."""
    for rel in REVIEW_AGENTS:
        path=source/rel;path.parent.mkdir(exist_ok=True);path.write_text('review instructions')
    record=ReviewRecord(source_manifest=source_manifest(source),activation_required=True,
                        activation_reason='test',consolidated_decision={'scope':'test'},
                        independent_findings=[{'role':role,'findings':[]} for role in REQUIRED_ROLES],
                        completion_adversary_report={'role':'completion-adversary','verdict':'complete'},
                        completion_gate_status='passed')
    record.write(source)
    assert not [f for f in analyze(Skill.from_path(source)) if f.severity=='error']
    return record


@pytest.mark.parametrize('change',['edit','add','delete','test','eval'])
def test_review_rejects_changes_since_approval(source,change):
    """Verify edits, additions, and deletions invalidate a source-bound review."""
    reviewed_source(source)
    if change=='edit':
        with (source/'SKILL.md').open('a') as f:f.write('\nNew behavior\n')
    elif change=='delete':(source/REVIEW_AGENTS[0]).unlink()
    elif change=='test':(source/'tests/expected_behavior.yaml').write_text('- altered')
    elif change=='eval':
        (source/'evals').mkdir();(source/'evals/evals.json').write_text('[]')
    else:(source/'new.txt').write_text('new')
    assert 'review-stale' in {f.rule for f in analyze(Skill.from_path(source))}


def test_review_legacy_record_blocks_and_restart_clears_approval(source):
    """Verify unbound reviews are blocked and restart clears approval while binding sources."""
    record=reviewed_source(source)
    record.source_manifest={};record.write(source)
    assert 'review-unbound' in {f.rule for f in analyze(Skill.from_path(source))}
    result=subprocess.run([sys.executable,'-m','scripts.review','restart',str(source)],cwd=SKILL,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    restarted=ReviewRecord.from_skill_path(source)
    assert restarted.source_manifest==source_manifest(source)
    assert restarted.completion_gate_status=='not_run'
    assert restarted.independent_findings==[]
    assert 'review-gate-not-passed' in {f.rule for f in analyze(Skill.from_path(source))}


def test_explicit_package_manifest_restricts_distribution(source,tmp_path):
    """Verify an explicit file list omits private notes and retains listed resources."""
    (source/'private-notes.txt').write_text('not for distribution')
    (source/'package-manifest.json').write_text(json.dumps({'files':['SKILL.md','tests/expected_behavior.yaml']}))
    artifact=package_skill(source,tmp_path/'dist')
    assert artifact
    with zipfile.ZipFile(artifact) as archive:
        assert f'{source.name}/private-notes.txt' not in archive.namelist()
        assert f'{source.name}/package-manifest.json' in archive.namelist()
        assert f'{source.name}/tests/expected_behavior.yaml' in archive.namelist()


@pytest.mark.parametrize('entry',['../outside.txt','.env','missing.txt'])
def test_package_manifest_cannot_override_security_policy(source,tmp_path,entry):
    """Verify a file list cannot include outside, secret, or nonexistent source files."""
    (source/'.env').write_text('SYNTHETIC-PRIVATE')
    (source/'package-manifest.json').write_text(json.dumps({'files':['SKILL.md',entry]}))
    assert package_skill(source,tmp_path/'dist') is None
    assert not list((tmp_path/'dist').glob('*.skill'))


def test_loop_shares_allowance_with_every_optimizer_call(monkeypatch,tmp_path):
    """Verify all evaluation and rewrite calls in the loop consume the same allowance."""
    seen=[]
    monkeypatch.setattr(RL,'parse_skill_md',lambda p:('demo','desc','body'))
    def evaluate(**kw):
        """Charge one evaluation attempt and return a completed trigger mismatch."""
        budget=kw['budget'];seen.append(budget);budget.consume()
        return {'results':[{'query':'q','should_trigger':True,'pass':False,'triggers':0,'runs':1}],
                'summary':{'infrastructure_failed':False}}
    def improve(**kw):
        """Charge two rewrite attempts and return a replacement description."""
        budget=kw['budget'];seen.append(budget);budget.consume();budget.consume()
        return 'new description'
    monkeypatch.setattr(RL,'run_eval',evaluate)
    monkeypatch.setattr(RL,'improve_description',improve)
    result=RL.run_loop([{'query':'q','should_trigger':True}],tmp_path,None,1,1,3,1,0.5,0,'haiku',False,max_calls=7)
    assert result['call_budget']=={'limit':7,'used':7,'remaining':0}
    assert result['planned_max_calls']==7
    assert all(b is seen[0] for b in seen)


def test_package_manifest_cannot_omit_referenced_resource(source,tmp_path):
    """Verify packaging rejects a file list that omits a referenced skill resource."""
    (source/'package-manifest.json').write_text(json.dumps({'files':['SKILL.md']}))
    assert package_skill(source,tmp_path/'dist') is None
    assert not list((tmp_path/'dist').glob('*.skill'))
