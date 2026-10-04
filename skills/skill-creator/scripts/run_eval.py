"""Trigger evaluation with bounded transport and explicit incomplete results."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

from scripts.claude_process import claude_command, model_args, run_process, isolation_args, model_environment
from scripts.call_budget import CallBudget, DEFAULT_MAX_CALLS
from scripts.structured_logging import ErrorCategory, QueryOutcome, StructuredLogger
from scripts.tests_loader import normalize_cases
from scripts.utils import parse_skill_md


def validate_options(num_workers, timeout, runs_per_query, trigger_threshold, max_retries=0):
    for name,value in [('workers',num_workers),('runs',runs_per_query)]:
        if type(value) is not int or value < 1:
            raise ValueError(f'{name} must be a positive integer')
    if type(max_retries) is not int or max_retries < 0:
        raise ValueError('retries must be a nonnegative integer')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be positive and finite')
    if not math.isfinite(trigger_threshold) or not 0 < trigger_threshold <= 1:
        raise ValueError('trigger threshold must be in (0, 1]')


def run_single_query(query, skill_name, skill_description, timeout, project_root,
                     model=None, max_retries=0, logger=None, transcript_dir=None, budget=None):
    validate_options(1,timeout,1,0.5,max_retries)
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', skill_name) or len(skill_name)>64:
        raise ValueError('Invalid skill name for evaluation')
    budget = budget if budget is not None else CallBudget()
    clean_name = f'{skill_name}-skill-{uuid.uuid4().hex[:8]}'
    command_file = Path(project_root) / '.claude' / 'commands' / f'{clean_name}.md'
    last = QueryOutcome.failure(ErrorCategory.UNKNOWN, 'No attempt completed')
    for attempt in range(max_retries+1):
        state = {'triggered':False,'completed':False,'error':None,'blocks':{}}
        def handle_line(line):
            if not line.strip():
                return False
            try:
                event=json.loads(line)
                if not isinstance(event,dict):
                    raise ValueError('event must be an object')
                kind=event.get('type')
                if kind=='result':
                    if event.get('is_error') or str(event.get('subtype','')).startswith('error'):
                        detail=json.dumps(event).lower()
                        category=ErrorCategory.AUTHENTICATION if any(s in detail for s in ('auth','quota','usage limit','credit','rate limit')) else ErrorCategory.SUBPROCESS_CRASH
                        state['error']=QueryOutcome.failure(category,'Claude result reported an error')
                    elif event.get('subtype')=='success':
                        state['completed']=True
                    else:
                        raise ValueError('result lacks successful completion subtype')
                elif kind=='assistant':
                    for block in event.get('message',{}).get('content',[]):
                        if block.get('type')=='tool_use':
                            tool=block.get('name'); inputs=block.get('input',{})
                            value=inputs.get('skill' if tool=='Skill' else 'file_path','')
                            if tool in ('Skill','Read') and isinstance(value,str) and clean_name in value:
                                state['triggered']=True
                elif kind=='stream_event':
                    e=event.get('event',{}); idx=e.get('index',0); typ=e.get('type')
                    if typ=='content_block_start':
                        b=e.get('content_block',{})
                        state['blocks'][idx]={'name':b.get('name'),'text':''} if b.get('type')=='tool_use' else {'name':None,'text':''}
                    elif typ=='content_block_delta' and idx in state['blocks']:
                        b=state['blocks'][idx]; d=e.get('delta',{})
                        if d.get('type')=='input_json_delta':
                            b['text']+=d.get('partial_json','')
                            try:
                                inputs=json.loads(b['text'])
                            except json.JSONDecodeError:
                                inputs={}
                            if b['name'] in ('Skill','Read') and isinstance(inputs,dict):
                                val=inputs.get('skill' if b['name']=='Skill' else 'file_path','')
                                if isinstance(val,str) and clean_name in val:
                                    state['triggered']=True
                    elif typ=='content_block_stop':
                        state['blocks'].pop(idx,None)
            except (ValueError,TypeError,AttributeError):
                state['error']=QueryOutcome.failure(ErrorCategory.PARSING,'Malformed stream event')
            return state['triggered'] and state['error'] is None
        try:
            command_file.parent.mkdir(parents=True,exist_ok=True)
            import yaml
            command_file.write_text('---\n'+yaml.safe_dump({'description':skill_description},allow_unicode=True)+'---\n# '+skill_name+'\n',encoding='utf-8')
            transcript=None
            if transcript_dir:
                Path(transcript_dir).mkdir(parents=True,exist_ok=True)
                transcript=Path(transcript_dir)/f'{clean_name}-{attempt}.jsonl'
            with model_environment() as (env, _):
                cmd=claude_command('-p','--output-format','stream-json','--verbose','--include-partial-messages',
                                   *isolation_args('Skill'),*model_args(model))
                budget.consume()
                proc=run_process(cmd,query,cwd=Path(project_root),timeout=timeout,on_line=handle_line,
                                 capture_stdout=False,transcript=transcript,env=env)
            if proc.timed_out:
                last=QueryOutcome.failure(ErrorCategory.TIMEOUT,'Request exceeded its deadline')
            elif proc.transport_error:
                last=QueryOutcome.failure(ErrorCategory.IO,proc.transport_error)
            elif state['error']:
                last=state['error']
            elif state['triggered']:
                return QueryOutcome.triggered_ok()
            elif state['completed'] and proc.returncode==0:
                return QueryOutcome.not_triggered_ok()
            elif any(s in proc.stderr.lower() for s in ('not logged in','authentication','unauthorized','invalid api key','quota','usage limit','credit balance','rate limit')):
                last=QueryOutcome.failure(ErrorCategory.AUTHENTICATION,'Check Claude authentication and allowance')
            elif proc.returncode not in (0,None):
                last=QueryOutcome.failure(ErrorCategory.SUBPROCESS_CRASH,f'Claude exited {proc.returncode}')
            else:
                last=QueryOutcome.failure(ErrorCategory.PARSING,'Missing successful completion event')
        except FileNotFoundError:
            return QueryOutcome.failure(ErrorCategory.SUBPROCESS_CRASH,'Claude CLI is missing; run doctor')
        except (OSError,ValueError) as exc:
            last=QueryOutcome.failure(ErrorCategory.IO,str(exc))
        finally:
            command_file.unlink(missing_ok=True)
        if last.category not in (ErrorCategory.TIMEOUT,ErrorCategory.SUBPROCESS_CRASH):
            break
    return last


def _aggregate_results(query_outcomes,query_items,trigger_threshold):
    rows=[]
    for query,item in query_items.items():
        outcomes=query_outcomes.get(query,[])
        clean=[o for o in outcomes if o.ok]; failed=[o for o in outcomes if not o.ok]
        rate=sum(o.triggered for o in clean)/len(clean) if clean else 0.0
        incomplete=bool(failed) or not clean
        passed=not incomplete and (rate>=trigger_threshold if item['should_trigger'] else rate<trigger_threshold)
        row={'query':query,'should_trigger':item['should_trigger'],'trigger_rate':rate,
             'triggers':sum(o.triggered for o in clean),'runs':len(outcomes),'ok_runs':len(clean),
             'failed_runs':len(failed),'pass':passed,'status':'incomplete' if incomplete else 'passed' if passed else 'failed'}
        if incomplete:
            row['execution_error']=failed[0].category.value if failed else 'missing_run'
            row['errors']=[o.category.value for o in failed]
        rows.append(row)
    errored=sum(r['status']=='incomplete' for r in rows)
    passed=sum(r['pass'] for r in rows)
    return rows,{'total':len(rows),'passed':passed,'failed':len(rows)-passed,'errored':errored,
                 'infrastructure_failed':bool(errored),'status':'incomplete' if errored else 'passed' if passed==len(rows) else 'failed'}


def run_eval(eval_set,skill_name,description,num_workers,timeout,runs_per_query=1,
             trigger_threshold=0.5,model=None,logger=None,max_retries=0,max_calls=DEFAULT_MAX_CALLS,transcript_dir=None,budget=None):
    validate_options(num_workers,timeout,runs_per_query,trigger_threshold,max_retries)
    eval_set=normalize_cases(eval_set)
    if not eval_set:
        raise ValueError('Evaluation requires at least one test case')
    calls=len(eval_set)*runs_per_query*(max_retries+1)
    budget = budget if budget is not None else CallBudget(max_calls)
    budget.require(calls)
    if type(max_calls) is not int or max_calls<1 or calls>max_calls:
        raise ValueError(f'Evaluation needs at most {calls} calls, exceeding or invalidating max_calls={max_calls}')
    items={e['query']:e for e in eval_set}
    outcomes={q:[] for q in items}
    # Each query gets an isolated project so concurrent synthetic commands cannot
    # alter another query's available skill list or the caller's configuration.
    with tempfile.TemporaryDirectory(prefix='bsc-eval-') as temp:
        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            futures={}
            for i,item in enumerate(eval_set):
                for run in range(runs_per_query):
                    work=Path(temp)/f'{i}-{run}'
                    work.mkdir()
                    f=pool.submit(run_single_query,item['query'],skill_name,description,timeout,str(work),
                                  model,max_retries,None,transcript_dir,budget)
                    futures[f]=item['query']
            for f in as_completed(futures):
                try:
                    outcomes[futures[f]].append(f.result())
                except Exception as exc:
                    outcomes[futures[f]].append(QueryOutcome.failure(ErrorCategory.UNKNOWN,type(exc).__name__))
    rows,summary=_aggregate_results(outcomes,items,trigger_threshold)
    return {'skill_name':skill_name,'description':description,'results':rows,'summary':summary,'max_calls':calls,
            'behavior_status':'not_tested','model':model or 'configured default','call_budget':budget.report()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eval-set',required=True);p.add_argument('--skill-path',required=True)
    p.add_argument('--description');p.add_argument('--model');p.add_argument('--log-file')
    p.add_argument('--num-workers',type=int,default=1);p.add_argument('--timeout',type=float,default=60)
    p.add_argument('--runs-per-query',type=int,default=1);p.add_argument('--max-retries',type=int,default=0)
    p.add_argument('--max-calls',type=int,default=DEFAULT_MAX_CALLS);p.add_argument('--trigger-threshold',type=float,default=0.5)
    p.add_argument('--verbose',action='store_true')
    args=p.parse_args()
    try:
        cases=json.loads(Path(args.eval_set).read_text(encoding='utf-8'))
        name,desc,_=parse_skill_md(Path(args.skill_path))
        result=run_eval(cases,name,args.description or desc,args.num_workers,args.timeout,
                        args.runs_per_query,args.trigger_threshold,args.model,max_retries=args.max_retries,max_calls=args.max_calls)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if args.log_file:
            dest=Path(args.log_file);dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(json.dumps({'summary':result['summary']})+'\n',encoding='utf-8')
        return 1 if result['summary']['infrastructure_failed'] else 0 if result['summary']['failed']==0 else 2
    except (OSError,ValueError) as exc:
        print(f'Error: {exc}',file=sys.stderr);return 1

if __name__=='__main__':
    sys.exit(main())
