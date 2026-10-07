import collections
import json
import re
import subprocess
from pathlib import Path
from p57_audit import ART, PLAN, ROOT

items={}
for path in sorted(PLAN.glob('phases/*/P*.json')):
    doc=json.loads(path.read_text());items[doc['id']]=doc
done={i:d for i,d in items.items() if d['status'] in ('done','done_with_deviations')}
missing=[];red=[];bad_deviations=[];bad_skipped=[];actors=collections.Counter()
for iid,d in items.items():
    r=d.get('result') or {}
    if iid in done:
        expected={v['id'] for v in d.get('validation',[]) if v['kind']=='acceptance'}
        recorded={v['id'] for v in r.get('checks',[])}
        if not r.get('notes') or expected-recorded:missing.append({'item':iid,'missing_ids':sorted(expected-recorded)})
        executor=r.get('executor') or {};actors[(executor.get('provider'),executor.get('model'))]+=1
    for check in r.get('checks',[]):
        if check.get('exit',0)!=0:red.append({'item':iid,'status':d['status'],'check':check,'deviations':r.get('deviations',[])})
    if d['status']=='done_with_deviations' and not r.get('deviations'):bad_deviations.append(iid)
    if d['status']=='skipped' and not r.get('notes'):bad_skipped.append(iid)

tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT,text=True).split('\0'))
prefix=PLAN.relative_to(ROOT).as_posix()+'/'
references=collections.defaultdict(list)
unparsed=[]
source_count=0
def strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for v in value.values():yield from strings(v)
    elif isinstance(value,list):
        for v in value:yield from strings(v)
for filename in sorted(tracked):
    if not filename.startswith(prefix) or not filename.endswith('.json') or '/views/' in filename:continue
    source_count+=1
    raw=(ROOT/filename).read_text()
    try:document=json.loads(raw)
    except json.JSONDecodeError as error:
        unparsed.append({'file':filename,'error':str(error)})
        document=raw
    for text in strings(document):
        for hit in re.finditer(r'@plan/([A-Za-z0-9_./*?-]+)|\b(decisions/D[0-9]+|knowledge/[a-z][a-z0-9-]*|research/Q[0-9]+[a-z]?(?:\.json|\.md)?)',text):
            token=(hit.group(1) or hit.group(2)).rstrip('.,')
            if token.endswith('/'):
                tail=text[hit.end():hit.end()+1]
                if tail in ('<','{'):continue
            if any(c in token for c in '*?'):
                import fnmatch
                exists=any(fnmatch.fnmatch(f,prefix+token) for f in tracked)
            else:
                exists=any(f in tracked for f in (prefix+token,prefix+token+'.json',prefix+token+'.md'))
                exists=exists or any(f.startswith(prefix+token.rstrip('/')+'/') for f in tracked)
            if token.startswith(('context/','artifacts/P5.7')):continue
            if not exists:references[token].append(filename)

commits=json.loads((ART/'H-commits.log').read_text())['data']['commits']
git_log=(ART/'H-candidate-git-log.log').read_text()
unlinked=[];links={}
for iid in done:
    matches=[line for line in git_log.splitlines() if re.search(r'(?<![0-9])'+re.escape(iid)+r'(?![0-9])',line)]
    if matches:links[iid]=matches
    else:unlinked.append(iid)
events=json.loads((ART/'H-events.log').read_text()).get('data',[])
if isinstance(events,dict):events=events.get('events',[])
absent_events=[]
for iid in done:
    types={e.get('type') for e in events if e.get('item')==iid}
    if not {'start','finish'}<=types:absent_events.append({'item':iid,'types':sorted(types)})
review_notes={ref:[e for e in events if e.get('type')=='note' and ref in e.get('summary','')]
              for ref in ('review-p1','review-p2','review-p6','conclusion')}
out={'item_count':len(items),'statuses':dict(collections.Counter(d['status'] for d in items.values())),
     'missing_notes_checks':missing,'red_checks':red,'deviations_without_reason':bad_deviations,
     'skipped_without_reason':bad_skipped,'untracked_reference_candidates':dict(references),
     'tracked_json_scanned':source_count,'non_json_artifacts':unparsed,'commit_count':len(commits),'items_without_subject_link':unlinked,'subject_links':links,
     'missing_events':absent_events,'review_note_count':{k:len(v) for k,v in review_notes.items()},
     'actor_identities':[{'provider':k[0],'model':k[1],'items':n} for k,n in actors.items()]}
(ART/'H-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
for key,value in out.items():
    if key!='subject_links':print(key,json.dumps(value,ensure_ascii=False))
