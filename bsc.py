#!/usr/bin/env python3
"""Better Skill Creator: check your setup, try an example, and package a skill."""
from __future__ import annotations
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent
TOOLKIT = ROOT / 'skills' / 'skill-creator'
VERSION = '3.2.0'
sys.path.insert(0, str(TOOLKIT))


class InputError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError(message)


def fingerprint(root):
    """Return SHA-256 digests for reviewable source files, excluding review.yaml."""
    from scripts.file_policy import source_manifest
    return source_manifest(root)


def checks(target):
    """Return structure, analysis, review, and dependency check results for a skill."""
    from scripts.quick_validate import validate_skill
    from scripts.skill_ir import Skill
    from scripts.lint import lint
    from scripts.static_analysis import analyze
    from scripts.semantic_analysis import semantic_analyze
    from scripts.review_gate import analyze as review, review_applies
    from scripts.dependency_graph import SkillGraph
    valid, message = validate_skill(target)
    rows: list[dict] = [{'check':'structure','status':'passed' if valid else 'failed','message':message}]
    if not valid:
        return rows
    skill=Skill.from_path(target)
    for name,fn in [('lint',lint),('static',analyze),('semantic',semantic_analyze),('review',review)]:
        if name=='review' and not review_applies(skill):
            rows.append({'check':name,'status':'skipped','message':'Independent review process not declared by this skill.'})
            continue
        findings=fn(skill)
        rows.append({'check':name,'status':'failed' if any(f.severity=='error' for f in findings) else 'passed',
                     'message':f'{len(findings)} finding(s)',
                     'findings':[{'severity':f.severity,'rule':f.rule,'message':f.message} for f in findings]})
    graph=SkillGraph(skill);graph.build()
    # The static analyzer distinguishes runtime artifacts from dependencies;
    # quick_validate checks the declared dependencies. Graph cycles add a check.
    cycles=graph.detect_cycles()
    rows.append({'check':'dependencies','status':'failed' if cycles else 'passed',
                 'message':f'{len(graph.nodes)} nodes; {len(cycles)} cycles; declared paths checked by structure validation.'})
    return rows


def doctor():
    rows=[]
    rows.append({'check':'python','status':'passed' if sys.version_info >= (3,12) else 'failed',
                 'message':sys.version.split()[0], 'remedy':'Use Python 3.12 or newer; 3.12 is the tested baseline.'})
    available=importlib.util.find_spec('yaml') is not None
    rows.append({'check':'PyYAML','status':'passed' if available else 'failed',
                 'message':'Available' if available else 'Missing','remedy':f'Run {sys.executable} -m pip install -r "{ROOT / "requirements.txt"}"'})
    from scripts.claude_process import claude_command, run_process
    try:
        cmd=claude_command('--version')
        info=run_process(cmd,'',cwd=ROOT,timeout=15)
        if info.returncode!=0 or info.timed_out:
            raise OSError('Claude version check failed')
        rows.append({'check':'claude','status':'passed','message':info.stdout.strip()})
        for file in ['.claude-plugin/plugin.json','.claude-plugin/marketplace.json']:
            result=run_process(claude_command('plugin','validate',str(ROOT/file)),'',cwd=ROOT,timeout=20)
            rows.append({'check':file,'status':'passed' if result.returncode==0 and not result.timed_out else 'failed',
                         'message':result.stdout.strip() or result.stderr[-500:]})
    except (OSError,ValueError) as exc:
        rows.append({'check':'claude','status':'skipped','message':str(exc),'remedy':'Install Claude Code before live evaluation; local checks remain available.'})
        for file in ['.claude-plugin/plugin.json','.claude-plugin/marketplace.json']:
            data=json.loads((ROOT/file).read_text(encoding='utf-8'))
            rows.append({'check':file,'status':'passed' if data.get('name') else 'failed',
                         'message':'JSON checked locally; Claude schema validation skipped.'})
    rows.append({'check':'authentication and billing','status':'skipped',
                 'message':'No model calls or account-setting changes. Confirm subscription and overage settings before --live.'})
    return rows


def build_parser():
    parser=Parser(description=__doc__)
    parser.add_argument('--version',action='version',version=VERSION)
    sub=parser.add_subparsers(dest='command',required=True,parser_class=Parser)
    for name in ('doctor','new','check','eval','package'):
        p=sub.add_parser(name)
        p.add_argument('--runs-dir',type=Path,default=Path('runs'),help='Report directory relative to your current directory')
        if name=='new':
            p.add_argument('name');p.add_argument('--example',choices=['release-notes'],required=True)
            p.add_argument('--output',type=Path,default=Path('.'),help='Parent directory for the new skill')
        elif name!='doctor':
            p.add_argument('path',type=Path)
        if name=='package':
            p.add_argument('--output',type=Path,default=Path('dist'))
        if name=='eval':
            p.add_argument('--live',action='store_true');p.add_argument('--model')
            p.add_argument('--models',help='Comma-separated models to run the trigger eval on, e.g. haiku,sonnet,opus')
            p.add_argument('--workers',type=int,default=1);p.add_argument('--runs',type=int,default=1)
            p.add_argument('--retries',type=int,default=0);p.add_argument('--timeout',type=float,default=60)
            p.add_argument('--max-calls',type=int,default=20);p.add_argument('--threshold',type=float,default=0.5)
            p.add_argument('--save-transcripts',action='store_true')
            p.add_argument('--grade-transcript',type=Path);p.add_argument('--outputs-dir',type=Path)
            p.add_argument('--grade-timeout',type=float,default=600,help='Timeout in seconds for the grading call (default 600)')
    return parser


def write_report(run, result):
    (run/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=[f'# {result["command"]}: {result["status"].upper()}', '',
           f'Better Skill Creator {VERSION} | {result["created_at"]}', '', result['next_action'], '']
    for row in result.get('checks',[]):
        lines.append(f'- **{row["check"]} — {row["status"]}:** {row.get("message", "")}')
        if row.get('status')=='failed' and row.get('remedy'):
            lines.append('  '+row['remedy'])
        for f in row.get('findings',[]):
            lines.append(f'  - {f["severity"]}: {f["message"]}')
    blocks=[('Trigger evaluation',result['trigger'])] if 'trigger' in result else []
    blocks+=[(f'Trigger evaluation: {m}',d) for m,d in result.get('trigger_by_model',{}).items()]
    for title,data in blocks:
        lines+=['',f'## {title}','',json.dumps(data['summary'])]
        for r in data['results']:
            lines.append(f'- {r["status"]}: {r["ok_runs"]}/{r["runs"]} valid runs; {r["failed_runs"]} execution failures; {r["query"]}')
    lines+=['','## Behavior grading','',result.get('behavior_status','not_tested')]
    if result.get('artifact'):
        lines+=['','Artifact: '+result['artifact']]
    if result.get('repairs'):
        lines+=['','Changes made to the packaging copy only:',*[f'- {x}' for x in result['repairs']]]
    (run/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main(argv=None):
    """Run a CLI subcommand, write its reports, and return its exit status."""
    try:
        args=build_parser().parse_args(argv)
    except InputError as exc:
        print(f'Input error: {exc}\nRun python bsc.py --help.',file=sys.stderr);return 1
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
    run=args.runs_dir.resolve()/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    try:
        run.mkdir(parents=True)
    except OSError as exc:
        print(f'Cannot create report directory {run}: {exc}',file=sys.stderr);return 1
    result={'schema_version':1,'version':VERSION,'command':args.command,'created_at':datetime.now(timezone.utc).isoformat(),
            'status':'passed','checks':[],'behavior_status':'not_tested','next_action':'Read the report for details.'}
    code=0
    try:
        if args.command=='doctor':
            result['checks']=doctor()
            code=1 if any(x['status']=='failed' for x in result['checks']) else 0
            result['next_action']='Fix failed prerequisites; otherwise create the release-notes example. Skipped authentication is not live readiness.'
        else:
            if sys.version_info<(3,12) or importlib.util.find_spec('yaml') is None:
                raise InputError('Run doctor and fix Python/PyYAML prerequisites first.')
            if args.command=='new':
                if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',args.name) or len(args.name)>64:
                    raise InputError('Use a skill name of up to 64 lowercase letters, digits, and single hyphens.')
                target=(args.output/args.name).resolve()
                try:
                    target.mkdir(parents=True,exist_ok=False)
                except FileExistsError:
                    raise InputError(f'Directory already exists: {target}. Choose a different name or parent directory.')
                try:
                    shutil.copytree(ROOT/'examples/release-notes',target,dirs_exist_ok=True)
                    p=target/'SKILL.md'
                    p.write_text(p.read_text(encoding='utf-8').replace('name: release-note-draft','name: '+args.name),encoding='utf-8')
                except Exception:
                    shutil.rmtree(target,ignore_errors=True);raise
                result['artifact']=str(target);result['checks']=checks(target)
                result['next_action']=f'Edit {target / "SKILL.md"}, then run check on this directory.'
            else:
                target=args.path.resolve()
                source_files={}
                if args.command=='package':
                    from scripts.file_policy import snapshot
                    source_files=snapshot(target,review=True)
                if not (target/'SKILL.md').is_file():
                    raise InputError('Target must be a skill directory containing SKILL.md.')
                result['target']=str(target)
                result['source_sha256']=hashlib.sha256(source_files['SKILL.md'].data if args.command=='package' else (target/'SKILL.md').read_bytes()).hexdigest()
                if args.command=='check':
                    result['checks']=checks(target)
                    result['next_action']='Fix error findings, inspect warnings, then package or preview eval.'
                elif args.command=='package':
                    from scripts.package_skill import _package_snapshot as package_skill
                    from scripts.file_policy import snapshot, copy_snapshot
                    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
                    dest=out/(target.name+'.skill')
                    if dest.exists():
                        raise InputError(f'Archive already exists: {dest}. Choose another output directory.')
                    before={name:hashlib.sha256(item.data).hexdigest() for name,item in source_files.items() if name!='review.yaml'}
                    with tempfile.TemporaryDirectory(prefix='bsc-package-') as tmp:
                        copy=Path(tmp)/target.name
                        copy_snapshot(source_files,copy)
                        with contextlib.redirect_stdout(io.StringIO()) as output:
                            artifact=package_skill(copy,Path(tmp)/'out')
                        result['checks']=checks(copy)
                        after=fingerprint(copy)
                        result['repairs']=[p for p in sorted(set(before)|set(after)) if before.get(p)!=after.get(p)]
                        artifact_bytes = b""
                        if not artifact:
                            result['status']='failed';code=2
                            result['next_action']='Fix packaging errors shown in the report and retry.'
                            result['packager_output']=output.getvalue()
                        else:
                            artifact_bytes=Path(artifact).read_bytes()
                            result['artifact_sha256']=hashlib.sha256(artifact_bytes).hexdigest()
                            result['next_action']='Inspect the archive and any repairs listed below; the original skill was not modified.'
                    if fingerprint(target)!=before:
                        raise RuntimeError('Source changed during packaging; inspect concurrent changes before accepting the archive.')
                    if result.get('artifact_sha256') and code==0:
                        with dest.open('xb') as f:
                            f.write(artifact_bytes)
                        result['artifact']=str(dest)
                else:
                    from scripts.tests_loader import load_trigger_suite
                    from scripts.run_eval import run_eval,validate_options
                    from scripts.claude_process import model_args
                    cases=load_trigger_suite(target/'tests')
                    validate_options(args.workers,args.timeout,args.runs,args.threshold,args.retries)
                    if args.models and args.model:
                        raise InputError('Use --model or --models, not both.')
                    models=[m.strip() for m in args.models.split(',') if m.strip()] if args.models else [args.model]
                    if args.models and not models:
                        raise InputError('--models needs at least one model name.')
                    if len(models) != len(set(models)):
                        raise InputError('--models must not contain duplicate model names.')
                    for m in models:
                        model_args(m)
                    if not cases:
                        raise InputError('Add positive and negative YAML cases under tests/.')
                    calls=len(cases)*args.runs*(args.retries+1)*len(models)+(1 if args.grade_transcript else 0)
                    if args.max_calls<1 or calls>args.max_calls:
                        raise InputError(f'At most {calls} calls requested; --max-calls is {args.max_calls}. Reduce the tests/repetitions or explicitly raise the limit.')
                    result.update({'max_calls':calls,'live':args.live,'test_count':len(cases)})
                    result['checks']=[{'check':'test inputs','status':'passed','message':f'{len(cases)} cases; at most {calls} calls, {args.workers} worker(s), {args.retries} retries.'}]
                    print(result['checks'][0]['message'],flush=True)
                    if not args.live:
                        result['status']='preview';result['next_action']='No model calls made. Verify account allowance and paid-overage settings, then add --live if you want to run these checks.'
                    else:
                        from scripts.skill_ir import Skill as _Skill
                        skill_desc=_Skill.from_path(target).description or ''
                        from scripts.call_budget import CallBudget
                        budget=CallBudget(args.max_calls)
                        by_model={}
                        for m in models:
                            tdir=None
                            if args.save_transcripts:
                                safe_m=re.sub(r'[<>:"/\\|?*]','-',m or 'default')
                                tdir=run/'transcripts'/safe_m if len(models)>1 else run/'transcripts'
                            by_model[m or 'default']=run_eval(cases,target.name,skill_desc,args.workers,args.timeout,args.runs,args.threshold,m,
                                      max_retries=args.retries,max_calls=args.max_calls,transcript_dir=tdir,budget=budget)
                        if len(models)==1:
                            result['trigger']=next(iter(by_model.values()))
                        else:
                            result['trigger_by_model']=by_model
                        summaries=[d['summary'] for d in by_model.values()]
                        code=1 if any(x['infrastructure_failed'] for x in summaries) else 2 if any(x['failed'] for x in summaries) else 0
                        if args.grade_transcript and code!=1:
                            from scripts.skill_test import grade_behavior
                            grade_code=grade_behavior(target,args.grade_transcript,args.outputs_dir,run/'grading.json',timeout=args.grade_timeout,model=args.model,budget=budget)
                            result['behavior_status']={0:'passed',1:'incomplete',2:'failed'}[grade_code]
                            code=1 if 1 in (code,grade_code) else max(code,grade_code)
                        result['call_budget']=budget.report()
                        result['next_action']='Inspect trigger and behavior results separately. Resolve incomplete runs before tuning descriptions.'
            if any(r['status']=='failed' for r in result['checks']) and code==0:
                code=2
    except Exception as exc:
        code=1;result['error']=str(exc);result['next_action']=f'{type(exc).__name__}: {exc}. Correct this issue and retry; use doctor for environment problems.'
    if code:
        result['status']='incomplete' if code==1 else 'failed'
    result['exit_code']=code
    write_report(run,result)
    print(f'{args.command}: {result["status"].upper()}\n{result["next_action"]}\nReport: {run / "report.md"}')
    return code


if __name__=='__main__':
    sys.exit(main())
