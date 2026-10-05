#!/usr/bin/env python3
"""Temporary migration inventory and automatic removal after verified fleet completion."""
import argparse
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'lib'))
from task.plan import check, store, views

MANIFEST = HERE / 'inventory.json'


def scan(projects_root):
    projects = [p for p in projects_root.iterdir() if p.is_dir() and not p.name.startswith('.')]
    for group in ('packages', 'libs'):
        parent = projects_root / group
        if parent.is_dir():projects += [p for p in parent.iterdir() if p.is_dir()]
    found = []
    for project in projects:
        plans = project / 'plans'
        if not plans.is_dir():continue
        for plan in plans.iterdir():
            if plan.is_dir() and plan.name != 'archive' and not plan.name.startswith('.') and any((plan/f).is_file() for f in ('plan.json','plan.md')):
                found.append({'project':project.relative_to(projects_root).as_posix(),'plan':plan.name,'status':'pending'})
    return sorted(found,key=lambda e:(e['project'],e['plan']))


def verify(base, project, identity):
    root = (base / project / 'plans' / identity).resolve()
    root.relative_to(base)
    plan = store.load_plan(root)
    errors = [i for i in check.check(plan) if i.level == 'error']
    if errors:
        raise ValueError(errors)
    if views.render_all(plan, check=True):
        raise ValueError(f'{identity}: human views are stale')
    names = ('index.md', 'plan.md', 'roadmap.md', 'status.md', 'handoff.md', 'open-questions.md',
             'session-routing.md', 'journal.jsonl', 'AGENTS.md', 'CLAUDE.md')
    carriers = [root / name for name in names]
    for folder in ('phases', 'brief', 'decisions'):
        carriers += list((root / folder).glob('**/*.md'))
    if any(f.exists() for f in carriers):
        raise ValueError(f'{identity}: old active carriers still exist')


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['discover','complete']);p.add_argument('projects_root',type=Path)
    p.add_argument('project',nargs='?');p.add_argument('plan',nargs='?');a=p.parse_args();base=a.projects_root.resolve()
    old=json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {'plans':[]}
    statuses={(v['project'],v['plan']):v['status'] for v in old['plans']}
    entries=scan(base)
    for e in entries:e['status']=statuses.get((e['project'],e['plan']),'pending')
    present={(e['project'],e['plan']) for e in entries}
    # A vanished inventoried plan is not evidence of a completed conversion. Archives are out of scope.
    for e in old['plans']:
        if (e['project'],e['plan']) not in present:
            archived=base/e['project']/'plans'/'archive'/e['plan']
            if not archived.is_dir():entries.append({**e,'status':'missing'})
    entries.sort(key=lambda e:(e['project'],e['plan']))
    if a.action=='complete':
        if not a.project or not a.plan:p.error('complete needs project and plan')
        verify(base,a.project,a.plan)
        matched=False
        for e in entries:
            if (e['project'],e['plan'])==(a.project,a.plan):e['status']='done';matched=True
        if not matched:raise ValueError('plan is outside the live inventory')
    MANIFEST.write_text(json.dumps({'format':'task-json-migration/v1','plans':entries},ensure_ascii=False,indent=2)+'\n')
    pending=sum(e['status']!='done' for e in entries)
    print(json.dumps({'plans':len(entries),'pending':pending}))
    if entries and pending==0 and a.action=='complete':
        for e in entries:verify(base,e['project'],e['plan'])
        if HERE.name!='migration' or HERE.parent.name!='docs':raise ValueError('unexpected cleanup location')
        shutil.rmtree(HERE)
        print('All active plans verified; temporary migration instructions and adapters removed.')

if __name__=='__main__':main()
