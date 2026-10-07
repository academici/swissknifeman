import ast
import json
import re
import subprocess
from pathlib import Path
from p57_audit import ROOT, PLAN, ART, TASK, SCRATCH, run

# Narrow the two failed broad checks without running either broad suite again.
run('F','command -v skiller; readlink -f "$(command -v skiller)"','skiller-path')
run('F','SKM_SKILLER_ROOT='+str(ROOT/'packages/skiller')+' python3 -m unittest discover -s packages/orch/bridges/skiller/tests -t packages/orch/bridges/skiller/tests -p "test_*.py"','skiller-bridge-local')
run('F','bash '+str(Path(SCRATCH)/'head/scripts/docs-sync.sh')+' --check','docs-sync-tracked-head')
run('F',['git','check-ignore','docs/skiller','docs/harness','docs/task'],'docs-ignored')

run('G',['git','ls-tree','-r','--name-only','v0.28.6','packages/task/scripts','packages/task/lib/task/plan'],'released-task-layout')
run('G',['rg','-n','profile-catalog|Repository bootstrap|14 canonical|publication-lock|repository-bootstrap-skills','CHANGELOG.md'],'changelog-removed')
_,schema=run('G',TASK+['schema','--verbs'],'current-verbs',quiet=True)
verbs=json.loads(schema)['data']['verbs']
for verb in verbs:run('G',TASK+[verb['name'],'--help'],'current-help-'+verb['name'],quiet=True)

# Independent scan, using tracked paths and the documented exceptions, not boundary functions.
tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
hits=[];bridge_imports=[]
names={'task','orch','skiller','harness','maind','analyst','artifex'}
for f in tracked:
    parts=Path(f).parts
    if len(parts)<3 or parts[0]!='packages' or parts[1] not in ('task','orch','skiller'):continue
    owner=parts[1]
    if Path(f).suffix not in ('.py','.md','.json','.sh'):continue
    if 'bridges' in parts:
        if Path(f).suffix=='.py':
            for node in ast.walk(ast.parse((ROOT/f).read_text())):
                imports=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.level==0 else []
                for module in imports:
                    bridge_imports.append({'file':f,'line':node.lineno,'module':module,
                                           'foreign_package':module.split('.')[0] in names-{owner}})
        continue
    if ('fixtures' in f or 'CHANGELOG' in f or 'docs/audits/' in f
        or Path(f).name in ('test_boundary.py','test_boundaries.py')):continue
    for n,line in enumerate((ROOT/f).read_text().splitlines(),1):
        found=re.findall(r'packages/(task|orch|skiller|harness|maind|analyst|artifex)\b|(?:from|import)\s+(task|orch|skiller|harness|maind|analyst|artifex)\b',line)
        for match in found:
            partner=next(p for p in match if p)
            if partner!=owner:hits.append({'file':f,'line':n,'partner':partner})
(ART/'E-scan.json').write_text(json.dumps({'outside_bridge':hits,'bridge_imports':bridge_imports},indent=2)+'\n')
print('E independent scan:',hits,'foreign bridge imports:',[i for i in bridge_imports if i['foreign_package']])

# Recording: only this candidate's history may witness a PLAN2 item.
done=[json.loads(p.read_text()) for p in PLAN.glob('phases/*/P*.json')
      if json.loads(p.read_text())['status'] in ('done','done_with_deviations')]
git_log=(ART/'H-candidate-git-log.log').read_text()
commits=json.loads((ART/'H-commits.log').read_text())['data']['commits']
unlinked=[];links={}
for item in done:
    iid=item['id']
    hits=[line for line in git_log.splitlines() if re.search(r'(?<![0-9])'+re.escape(iid)+r'(?![0-9])',line)]
    hits.extend(c['sha']+' '+c['subject'] for c in commits if c['ref']==iid)
    if hits:links[iid]=list(dict.fromkeys(hits))
    else:
        code,text=run('H',['git','log',Path(SCRATCH,'base-sha').read_text()+'..HEAD','--format=%H%x09%s','--',
                          str(PLAN.relative_to(ROOT)/'phases'/iid.split('.')[0]/(iid+'.json'))],'path-history-'+iid,quiet=True)
        unlinked.append({'item':iid,'path_history':text})
(ART/'H-commit-links.json').write_text(json.dumps({'trailer_count':len(commits),'subject_links':links,'unlinked':unlinked},ensure_ascii=False,indent=2)+'\n')
print('H trailers',len(commits),'items',len(set(c['ref'] for c in commits)),'unlinked',unlinked)
print('I decision graph')
for path in sorted((PLAN/'decisions').glob('D*.json'),key=lambda p:int(p.stem[1:])):
    d=json.loads(path.read_text());links=json.loads((ART/('I-links-'+d['id']+'.log')).read_text())['data']['edges']
    consumers=[e for e in links if e.get('kind') in ('applies_to','decision')]
    superseded=[i for i in d.get('supersedes',[]) if not (PLAN/'decisions'/str(i+'.json')).is_file()]
    print(d['id'],d['status'],'consumers',len(consumers),'missing supersedes',superseded)

# Documentation commands described as bare CLI verbs in architecture.md are still checked.
for argv,label in ((['input','adhoc','--help'],'input-adhoc'),(['render-prompt','--help'],'render-prompt'),
                   (['launch','list','--help'],'launch-list'),(['launch','show','--help'],'launch-show'),
                   (['launch','argv','--help'],'launch-argv')):
    run('J',['python3','packages/orch/scripts/orch.py']+argv,'extra-help-'+label)
run('J',['rg','-n','orch.discovery|supersede','packages/orch/docs/architecture.md','packages/task/docs'],'stale-doc-locations')

run('K',['git','diff','--check',Path(SCRATCH,'base-sha').read_text()+'..HEAD','--','packages','configs','scripts'],'product-whitespace')
changed=set(subprocess.check_output(['git','diff','--name-only',Path(SCRATCH,'base-sha').read_text()+'..HEAD'],cwd=ROOT,text=True).splitlines())
base_lines=set((ART/'K-hygiene-base.log').read_text().splitlines())
new=[l for l in (ART/'K-hygiene-head.log').read_text().splitlines()
     if l not in base_lines and l.split(' (',1)[0] in changed]
(ART/'K-hygiene-delta.json').write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n')
print('K new hygiene rows on changed files',len(new))
