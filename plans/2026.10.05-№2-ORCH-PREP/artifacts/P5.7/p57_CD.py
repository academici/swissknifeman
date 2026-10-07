import json
import shutil
from pathlib import Path
from p57_audit import ART, ROOT, PLAN, SCRATCH, TASK, ORCH, run

s = Path(SCRATCH)
copy = s/'plans'/PLAN.name
# Copy tracked product files: Task deliberately rejects symlinks escaping its repo root.
for child in s.iterdir():
    if child.is_symlink():child.unlink()
(s/'head').mkdir(exist_ok=True)
run('C', 'git archive HEAD | tar -x -C '+str(s/'head'), 'archive-head')
for child in (s/'head').iterdir():
    if child.name == 'plans':continue
    if child.is_dir():shutil.copytree(child,s/child.name,dirs_exist_ok=True)
    else:shutil.copy2(child,s/child.name)

text=(ART/'A-items.log').read_text()
items = json.loads(text)
if isinstance(items, dict):
    items=items.get('items',items.get('data',[]))
print('items',type(items).__name__,len(items),flush=True)

f=s/'p55-settings.json'
run('C', TASK+['bridge','orch','brief',str(copy),'P5.5','--out',str(f)], 'fc2-brief-with-tracked-reads')
run('C', ORCH+['validate','execution-input',str(f)], 'fc2-validate-with-tracked-reads')

rows=[]
for item in items:
    if item['status'] not in ('done','done_with_deviations'): continue
    iid=item['ref']; f=s/(iid+'.json')
    code,_=run('D',TASK+['bridge','orch','brief','PLAN2',iid,'--out',str(f)],'brief-'+iid,quiet=True)
    result={'item':iid,'brief_exit':code}
    if not code:
        code,text=run('D',ORCH+['validate','execution-input',str(f)],'validate-'+iid,quiet=True)
        result['validate_exit']=code
        try:result['validation']=json.loads(text.splitlines()[-1])
        except ValueError:result['output']=text
    rows.append(result)
    print(iid, 'brief='+str(result['brief_exit']), 'validate='+str(result.get('validate_exit','not-run')), flush=True)

demo=s/'plans/2026.10.05-№7-DEMO'
shutil.copytree(ROOT/'packages/task/tests/engine/fixtures/demo-plan',demo)
(s/'lib/pkg').mkdir(parents=True,exist_ok=True)
(s/'lib/pkg/config.py').write_text('DEFAULT = 1\n')
for source in sorted(demo.glob('phases/*/P*.json')):
    item=json.loads(source.read_text()); iid=item['id']; f=s/('DEMO-'+iid+'.json')
    code,_=run('D',TASK+['bridge','orch','brief',str(demo),iid,'--out',str(f)],'demo-brief-'+iid,quiet=True)
    result={'item':'DEMO.'+iid,'brief_exit':code}
    if not code:
        code,text=run('D',ORCH+['validate','execution-input',str(f)],'demo-validate-'+iid,quiet=True)
        result['validate_exit']=code
        try:result['validation']=json.loads(text.splitlines()[-1])
        except ValueError:result['output']=text
    rows.append(result)
    print(result['item'],result,flush=True)

(ART/'D-results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
# Only a scratch copy is normalized. Keep its original failure in the audit.
source=s/'DEMO-P1.2.json'
if not source.exists():source=s/'P5.5.json'
doc=json.loads(source.read_text())
for r in doc.get('reads',[]):r.pop('included',None)
doc.get('route',{}).get('minimum',{}).pop('settings',None)
import sys
sys.path.insert(0,str(ROOT/'packages/orch/lib'))
from orch.contracts import canonical_digest
doc['digest']=canonical_digest(doc)
doc['input_id']=doc['input_id'].split('@')[0]+'@'+doc['digest'][:12]
normalized=s/'normalized.json'
normalized.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
run('D',ORCH+['validate','execution-input',str(normalized)],'normalized-validate')
for binding in ('native','cao','claude-only'):
    out=s/('prepare-'+binding)
    code,text=run('D',ORCH+['prepare','--binding',binding,'--provider','claude-code',
                         '--input',str(normalized),'--policy','packages/orch/fixtures/exec/v1/valid/run-policy/solo.json',
                         '--out',str(out),'--dry-run'],'prepare-'+binding)
    if not code:
        launch=s/('launch-'+binding+'.json'); launch.write_text(text)
        run('D',ORCH+['validate','launch-plan',str(launch)],'launch-validate-'+binding)
