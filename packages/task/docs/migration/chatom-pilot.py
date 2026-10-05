#!/usr/bin/env python3
"""Temporary, explicit Chatom RC1 mapping. Not imported by Task runtime."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

TASK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TASK / 'lib'))
from task.plan import context, schema, snapshot, store

URN = 'urn:swissknifeman:task:plan:'
EMPTY = {'—', '-', 'no', ''}
STATUS = {'Not started': 'todo', 'In progress': 'in_progress', 'Done with deviations': 'done_with_deviations',
          'Done': 'done', 'Blocked': 'blocked', 'Skipped by decision': 'skipped'}


def sections(text, headings=False):
    pattern = r'^#{2,6}\s+(.+)$' if headings else r'^\*\*([^*\n]+):\*\*\s*'
    matches = list(re.finditer(pattern, text, re.M))
    return {m[1].strip(): text[m.end():matches[i+1].start() if i+1 < len(matches) else len(text)].strip()
            for i,m in enumerate(matches)}


def title(text):
    match = re.search(r'^#{1,6}\s+(?:[PD]\d+(?:\.\d+)?\s+[—-]\s+)?(.+)$', text, re.M)
    return match[1].strip() if match else 'Imported source'


def chunks(text):
    if text.strip() in EMPTY:return []
    return [s.strip() for s in re.split(r'\n(?=- |\d+\. )',text) if s.strip()]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('plan',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.plan.resolve();repo=root.parent.parent
    consumed={}
    def read(path):
        p=root/path;t=p.read_text();consumed[path]=hashlib.sha256(p.read_bytes()).hexdigest();return t
    journal=[json.loads(l) for l in read('journal.jsonl').splitlines() if l.strip()]
    current={};terminal={};starts={};actors={}
    for e in journal:
        current[e['item_id']]=e
        if e['result']=='closed-green':terminal[e['item_id']]=e
        if e['result']=='in-progress':starts.setdefault(e['item_id'],e['ts'])
        receipt=((e.get('decision') or {}).get('route_receipt') or {}).get('evidence') or {}
        if receipt.get('model'):actors[e['item_id']]={k:receipt[k] for k in ['model','effort'] if receipt.get(k)}|{'provider':e.get('actor','recorded')}
    now=store.now();actor={'provider':'claude-code','model':'claude-opus-5-5','effort':'high'}
    plan_text=read('plan.md');ps=sections(plan_text,True)
    route={};batch={};review={}
    for line in plan_text.splitlines():
        cells=[c.strip().strip('`') for c in line.strip().strip('|').split('|')]
        if len(cells)>=6 and re.fullmatch(r'P\d+\.\d+',cells[1]) and '/' in cells[2]:
            iid=cells[1];cl,effort=cells[2].split('/',1);route[iid]={'class':cl,'effort':effort};batch[iid]=cells[0];review[iid]=cells[4]
    file_map={}
    for p in root.glob('phases/*/P*.md'):
        rel=p.relative_to(root).as_posix()
        if re.fullmatch(r'P\d+(?:\.closed)?',p.stem):file_map[rel]=f'phases/{p.stem.removesuffix(".closed")}/phase.json'
        elif re.fullmatch(r'P\d+\.\d+(?:\.state)?',p.stem):file_map[rel]=f'phases/{p.parent.name}/{p.stem.removesuffix(".state")}.json'
    for p in root.glob('decisions/D[0-9]*.md'):file_map[p.relative_to(root).as_posix()]=f'decisions/{p.name.split("-")[0]}.json'
    for p in root.glob('research/**/*.md'):
        file_map[p.relative_to(root).as_posix()]='knowledge/'+re.sub(r'[^A-Za-z0-9._-]','-',p.relative_to(root).as_posix().removesuffix('.md'))+'.json'
    file_map.update({'plan.md':'plan.json','roadmap.md':'plan.json','status.md':'plan.json','handoff.md':'plan.json',
                     'session-routing.md':'knowledge/routing.json','open-questions.md':'plan.json','brief/00-brief.md':'brief.json'})
    def normalize(text):
        prefix=f'plans/{root.name}/'
        for old,new in sorted(file_map.items(),key=lambda x:len(x[0]),reverse=True):
            text=text.replace(prefix+old,'@plan/'+new)
            text=re.sub(r'(?<![A-Za-z0-9_/@.-])'+re.escape(old)+r'(?![A-Za-z0-9_.-])','@plan/'+new,text)
        return text
    def path(value):
        value=value.strip().strip('`').split('#')[0]
        if value.startswith('@plan/'):return value
        if value.startswith(('phases/','decisions/','research/','artifacts/','findings/','backlog/','brief/')):
            return '@plan/'+file_map.get(value,value)
        return value
    def records(values):
        return [{'id':f'S{n}','title':k,'text':normalize(v)} for n,(k,v) in enumerate(values.items(),1)]
    def timestamp(iid):return terminal.get(iid,current.get(iid,{})).get('ts',now)
    def safe_note(t):return normalize(t) if t and t.strip() not in EMPTY else ''
    goal=ps.get('1. Overview',next(iter(ps.values()),plan_text))
    rules=ps.get('2. Execution Rules','')
    # Product contracts remain; obsolete carriers, fixed read boundaries and launch bookkeeping do not.
    paragraphs=re.split(r'\n(?=- )',rules)
    omit=('Generated carriers','Эстафета между агентами','Canonical statuses','Маршрут запуска','Review `full`',
          'Каждая фаза при `task:plan-design`')
    rules=[normalize(p.strip()) for p in paragraphs if p.strip() and not any(k in p for k in omit)]
    rules=[r.replace('без поиска по репозиторию сверх Required Reads и без\n  собственных решений','с достаточным контекстом и явными решениями') for r in rules]
    roadmap=sections(read('roadmap.md'),True)
    risks=roadmap.get('Критический путь и риски','').split('| Admission |')[0]
    for name in ['index.md','status.md','handoff.md','open-questions.md']:read(name)
    data={'$schema':URN+'snapshot:v1','plan':{'$schema':URN+'plan:v1','id':root.name,'short_id':'PLAN3',
        'title':'Plan №1 — Chatom 1.0.0-rc.1','status':'active','created':'2026-09-27','updated_at':now,
        'repository':repo.name,'owner':'repository owner','authoring':actor,'goal':normalize(goal),
        'context':'RC1 successor to PLAN2. P08–P10 completed; P11–P14 await phase design. Migration preserves the existing product contract.',
        'rules':rules,'phases':[],'settings':{'design_audit':'none','scout':'off','language':'ru'},
        'links':{'predecessor':'PLAN2'},'orchestration':{'strategy':'dag'},
        'sections':records({**{k:v for k,v in ps.items() if k in ['7. Contracts','Exported','Consumed']},'Risks':risks})},
        'brief':{'$schema':URN+'brief:v1','messages':[],'requirements':[]},
        'phases':[],'items':[],'units':[],'decisions':[],'documents':[],'events':[]}
    bt=read('brief/00-brief.md');bs=sections(bt,True)
    data['brief']['messages']=[{'id':'M1','date':'2026-09-27','text':'я полагаюсь на тебя, если ты считаешь, что это улучшит разработку','kind':'owner'},
        {'id':'M2','date':'2026-09-27','text':normalize(bs.get('№2 — постановка сессии разделения (2026-09-27, owner session prompt)',bt)),'kind':'record','channel':'brief source record; paraphrased'}]
    data['brief']['sections']=records({'Inherited brief':bt.split('## ')[0]})
    for n,t in enumerate(re.findall(r'^\d+\. (.+(?:\n(?!\d+\. ).+)*)',data['brief']['messages'][1]['text'],re.M),1):
        data['brief']['requirements'].append({'id':f'B{n}','text':t.strip(),'source':'M2','owners':['P08','P09','P10','P11','P12','P13','P14']})
    for phase_file in sorted(root.glob('phases/*/P*.md')):
        if not re.fullmatch(r'P\d+',phase_file.stem):continue
        pid=phase_file.stem;pt=read(phase_file.relative_to(root).as_posix());phs=sections(pt,True)
        phase={'$schema':URN+'phase:v1','id':pid,'title':title(pt),'design':'skeleton' if 'top-layer skeleton' in pt else 'detailed',
            'goal':normalize(phs.get('Phase Context',title(pt))), 'context':normalize(phs.get('Phase Context',title(pt))),
            'scope':{'include':[normalize(x) for x in chunks(phs.get('Scope Included',''))],
                     'exclude':[normalize(x) for x in chunks(phs.get('Scope Excluded',''))]},
            'depends_on':{'P08':[],'P09':['P08'],'P10':['P08'],'P11':['P09','P10'],'P12':['P11'],'P13':['P12'],'P14':['P13']}[pid],
            'items':[],'batches':[],'sections':records({k:v for k,v in phs.items() if k not in ['Items','Phase Handoff']})}
        data['plan']['phases'].append(pid)
        if (root/f'phases/{pid}/{pid}.closed.md').exists():read(f'phases/{pid}/{pid}.closed.md')
        groups={}
        for item_file in sorted(phase_file.parent.glob('P*.md'),key=lambda p:[int(n) for n in re.findall(r'\d+',p.stem)]):
            iid=item_file.stem
            if not re.fullmatch(r'P\d+\.\d+',iid):continue
            it=read(item_file.relative_to(root).as_posix());fields=sections(it);state_text=read(f'phases/{pid}/{iid}.state.md');state=sections(state_text)
            status=next((v for k,v in STATUS.items() if k in state.get('Status','')),None)
            if status is None:raise ValueError(f'Unrecognized source status: {iid}')
            item={'$schema':URN+'item:v1','id':iid,'title':title(it),'status':status,
                'summary':normalize(fields['Intent']),'why':normalize(fields['Why']) if fields['Why'] not in EMPTY else 'Pending phase design.',
                'scope':{'include':[normalize(x) for x in chunks(fields['Scope Included'])], 'exclude':[normalize(x) for x in chunks(fields['Scope Excluded'])]},
                'route':route[iid], 'review':{'mode':{'full':'requested','light':'self','none':'none'}[review[iid]]},'authority':{'kind':'routine'},'rag':{'need':'none','status':'not_needed'},
                'updated_at':timestamp(iid),'guidance':normalize(fields['Code Guidance']) if fields['Code Guidance'] not in EMPTY else 'Pending phase design.',
                'deliverables':[normalize(x) for x in chunks(fields['Deliverables'])], 'rules':[normalize(x) for x in chunks(fields['Implementation Rules'])],
                'sections':records(fields),'validation':[], 'reads':[], 'task_files':[]}
            if iid=='P14.5':item['authority']={'kind':'owner_gate','gate':'PUBLISH-1.0-RC','scope':'Publication only after the owner explicitly grants it.'}
            for v in dict.fromkeys(re.findall(r'`([^`\n]+)`',fields['Files'])):
                if not re.search(r'\s',v) and ('/' in v or '.' in v) and not v.startswith(('->','::')):
                    item['task_files'].append({'path':path(v),'change':'any'})
            for v in dict.fromkeys(re.findall(r'`([^`\n]+)`',fields['Required Reads']+'\n'+fields['Inputs'])):
                if not re.search(r'\s',v) and ((repo/path(v)).exists() or v in file_map):
                    item['reads'].append({'path':path(v),'why':'Source item input; complete detail preserved in sections.',
                                          'required':v in re.findall(r'`([^`\n]+)`',fields['Required Reads'])})
            for n,(cmd,expect) in enumerate(re.findall(r'`([^`\n]+)`\s*→\s*([^\n;]+)',fields['Validation']),1):
                item['validation'].append({'id':f'V{n}','cmd':cmd,'expect':expect.strip(),'kind':'acceptance'})
            event=terminal.get(iid,current.get(iid,{}))
            proof=((event.get('decision') or {}).get('terminal_evidence') or {}).get('validation',[])
            checks=[];evidence=[]
            # Actual recorded validation carriers replace ambiguous historic shorthand.
            if proof:
                item['validation']=[]
                for n,v in enumerate(proof,1):
                    item['validation'].append({'id':f'V{n}','cmd':v['carrier'],'expect':'Source evidence: '+v['status'],'kind':'acceptance'})
                    if v['status']=='green':checks.append({'id':f'V{n}','exit':0,'at':event['ts']})
                    for e in v.get('evidence_ids',[]):
                        if e.startswith(str(root)+'/'):evidence.append('@plan/'+e[len(str(root))+1:])
            if status in {'done','done_with_deviations','in_progress','blocked','skipped'}:
                result={'started_at':starts.get(iid,timestamp(iid)),'executor':actors.get(iid,actor),
                        'notes':safe_note(state.get('Completion Notes','')) or safe_note(event.get('note')) or 'Source state retained.',
                        'checks':checks,'evidence':list(dict.fromkeys(evidence)),
                        'deviations':[safe_note(x) for x in chunks(state.get('Known Deviations',''))],
                        'pending':[safe_note(x) for x in chunks(state.get('Pending Work',''))]}
                if status!='in_progress':result['finished_at']=timestamp(iid)
                if status=='blocked':result['escalation']=safe_note(state.get('Escalation Needed','')) or 'Source reports blocked.'
                item['result']=result
            phase['items'].append(iid);data['items'].append(item)
            bid=batch.get(iid,'solo');bid=bid if bid!='solo' else f'B{pid}-{iid.split(".")[1]}'
            if bid not in groups:groups[bid]={'id':bid,'items':[],'mode':'recommended'}
            groups[bid]['items'].append(iid)
        phase['batches']=list(groups.values())
        members=[i for i in data['items'] if i['id'] in phase['items']]
        if members and all(i['status'] in {'done','done_with_deviations','skipped'} for i in members):
            closure=current.get(pid,{})
            phase['closed']={'at':closure.get('ts',max(i['result']['finished_at'] for i in members)),
                             'result':'done_with_deviations' if any(i['status']=='done_with_deviations' for i in members) else 'done',
                             'summary':safe_note(closure.get('note')) or 'Derived from existing terminal item states during migration; no new phase checks claimed.'}
        data['phases'].append(phase)
    for p in sorted(root.glob('decisions/D[0-9]*.md')):
        t=read(p.relative_to(root).as_posix());front=t.split('---',2)[1];meta={}
        for line in front.splitlines():
            if ':' in line:
                k,v=line.split(':',1);meta[k]=v.strip()
        ds=sections(t,True);did=meta['id'];doc={'$schema':URN+'decision:v1','id':did,'title':title(t),'date':meta['date'],
            'status':meta['status'],'actor':actor,'sections':records(ds),'context':normalize(t.split('---',2)[-1].split('## ')[0]),
            'decision':normalize(context.extract_section(t,'Solution') or t),'rationale':normalize(ds.get('Why',ds.get('Rationale','Recorded in the source decision.'))),
            'consequences':[normalize(x) for x in chunks(ds.get('Consequences',''))],
            'applies_to':re.findall(r'P\d+(?:\.\d+)?',meta.get('items',meta.get('item',''))),
            'supersedes':re.findall(r'D\d+',meta.get('supersedes',''))}
        if meta.get('superseded_by') not in {'null',None}:doc['superseded_by']=meta['superseded_by']
        data['decisions'].append(doc)
    for p in sorted(root.glob('research/**/*.md')):
        rel=p.relative_to(root).as_posix();t=read(rel);did=Path(file_map[rel]).stem
        applies=list(dict.fromkeys(re.findall(r'P\d+(?:\.\d+)?',p.name)))
        data['documents'].append({'$schema':URN+'document:v1','id':did,'title':title(t),'sections':records(sections(t,True) or {'Content':t}),
            'applies_to':applies,'provenance':{'path':rel,'sha256':consumed[rel]}})
    rt=read('session-routing.md');rs=sections(rt,True)
    data['documents'].append({'$schema':URN+'document:v1','id':'routing','title':'Source provider model selections',
        'sections':records({k:v for k,v in rs.items() if k.startswith('Пины классов')}),
        'provenance':{'path':'session-routing.md','sha256':consumed['session-routing.md']}})
    for n,e in enumerate(journal,1):
        target=e['item_id'];kind='start' if e['result']=='in-progress' else 'finish' if e['result']=='closed-green' and '.' in target else 'note'
        ev={'v':1,'ts':e['ts'],'type':kind,'summary':safe_note(e.get('note')) or f'Source event {n}: {e["result"]}',
            'actor':actors.get(target,actor),'phase':target.split('.')[0], 'data':{'source_line':n,'source_result':e['result'],'source_record':e}}
        if '.' in target:ev['item']=target
        data['events'].append(ev)
    data['events'].append(store.new_event('migrated','Current JSON snapshot preserves RC1 identities, states and source evidence; archived plans untouched.',
                                         {'provider':'codex','model':'gpt-6'},data={'source_files':consumed,'previous_next':'design-phase P11'}))
    issues=schema.validate(data,'snapshot')
    if issues:raise ValueError('\n'.join(map(str,issues)))
    snapshot._graph(root,data)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    report={'plan':root.name,'source_files':consumed,'file_mapping':file_map,'items':{i['id']:i['status'] for i in data['items']},
            'phase_designs':{p['id']:p['design'] for p in data['phases']},'decisions':[d['id'] for d in data['decisions']],
            'source_next':'design-phase P11','snapshot':str(args.output)}
    args.output.with_name('source-map.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'items':len(data['items']),'decisions':len(data['decisions']),'documents':len(data['documents']),'snapshot':str(args.output)}))

if __name__=='__main__':main()
