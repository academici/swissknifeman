import ast
import collections
import json
import re
import subprocess
from pathlib import Path
from p57_audit import ART, PLAN, ROOT, SCRATCH, TASK, ORCH, run

base=subprocess.check_output(['git','rev-parse','58025e3a4^'],cwd=ROOT,text=True).strip()
Path(SCRATCH,'base-sha').write_text(base)
run('G',['git','tag','--sort=-creatordate'],'tags')
run('G',['git','merge-base','--is-ancestor','58025e3a4','v0.28.6'],'release-ancestor')
run('G',['git','diff','--stat','--diff-filter=DR',base+'..HEAD','--','packages/task','packages/skiller','packages/harness','configs'],'deleted-stat')
_,removed=run('G',['git','diff','--name-status','--diff-filter=DR',base+'..HEAD','--','packages/task','packages/skiller','packages/harness','configs'],'deleted-paths')
removed_status=[]
for row in removed.splitlines():
    parts=row.split('\t');path=parts[1]
    code,_=run('G',['git','cat-file','-e','v0.28.6:'+path],'released-path-'+str(len(removed_status)),quiet=True)
    removed_status.append({'path':path,'release_exit':code,'change':parts[0]})
_,old=run('G',['git','show','v0.28.6:packages/task/lib/task/plan/cli.py'],'released-cli')
verbs=sorted(set(re.findall(r'add_parser\("([a-z-]+)"',old)))
verb_checks={}
for verb in verbs:
    code,_=run('G',TASK+[verb,'--help'],'old-help-'+verb,quiet=True);verb_checks[verb]=code
for argv,label in ((['packages/skiller/bin/skiller','--help'],'skiller'),*[( ['packages/skiller/bin/skiller',verb,'--help'],verb) for verb in ('connect','vendor','sync')]):
    run('G',argv,'help-'+label)
(ART/'G-results.json').write_text(json.dumps({'base':base,'removed':removed_status,'old_verbs':verb_checks},ensure_ascii=False,indent=2)+'\n')
print('G',len(removed_status),'removed paths;',len(verbs),'old verbs',verb_checks,flush=True)

run('H',['git','log',base+'..HEAD','--format=%H%x09%s'],'candidate-git-log')
for dpath in sorted((PLAN/'decisions').glob('D*.json'),key=lambda p:int(p.stem[1:])):
    d=json.loads(dpath.read_text());run('I',TASK+['--output','json','links','PLAN2',d['id']],'links-'+d['id'],quiet=True)
print('I links complete',flush=True)

docs=[ROOT/'packages/orch/README.md',*sorted((ROOT/'packages/orch/docs').glob('*.md'))]
commands={}
for path in docs:
    for line_no,line in enumerate(path.read_text().splitlines(),1):
        for match in re.finditer(r'orch\.py\s+([a-z][a-z-]*)(?:\s+(adhoc))?',line):
            argv=tuple(ORCH+[match[1]]+([match[2]] if match[2] else [])+['--help'])
            commands.setdefault(argv,[]).append(str(path.relative_to(ROOT))+':'+str(line_no))
        for match in re.finditer(r'plan\.py\s+bridge\s+orch\s+([a-z][a-z-]*)',line):
            argv=tuple(TASK+['bridge','orch',match[1],'--help'])
            commands.setdefault(argv,[]).append(str(path.relative_to(ROOT))+':'+str(line_no))
doc_commands=[]
for index,(argv,locations) in enumerate(commands.items()):
    code,_=run('J',list(argv),'help-'+str(index),quiet=True)
    doc_commands.append({'cmd':list(argv),'exit':code,'locations':locations})
_,schema=run('J',TASK+['schema','--verbs'],'schema-verbs',quiet=True)
doc_text='\n'.join(p.read_text() for p in (ROOT/'packages/task/docs').glob('*.md'))
schema=json.loads(schema)['data']['verbs']
missing_docs=[v['name'] for v in schema if not re.search(r'(?<![a-z-])'+re.escape(v['name'])+r'(?![a-z-])',doc_text)]
(ART/'J-results.json').write_text(json.dumps({'commands':doc_commands,'verb_count':len(schema),'verbs_missing_in_docs':missing_docs},ensure_ascii=False,indent=2)+'\n')
print('J',doc_commands,'missing docs',missing_docs,flush=True)

run('K',['git','diff','--check',base+'..HEAD'],'diff-check')
run('K',['rg','-n','--','--bare','packages/orch/configs','packages/task/bridges'],'bare')
pattern=re.compile(r'''(api[_-]?key|token|secret)\s*[:=]\s*['"][A-Za-z0-9]{16,}''',re.I)
found=[]
for directory in ('packages/orch','packages/task/bridges'):
    for path in (ROOT/directory).rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:continue
        try:lines=path.read_text().splitlines()
        except (UnicodeDecodeError,OSError):continue
        for number,line in enumerate(lines,1):
            if pattern.search(line):found.append(str(path.relative_to(ROOT))+':'+str(number))
(ART/'K-secret-scan.json').write_text(json.dumps(found)+'\n')
print('K secret scan paths only:',found,flush=True)
run('K',['python3','scripts/public-hygiene.py'],'hygiene-head')
scratch=Path(SCRATCH);(scratch/'base').mkdir(exist_ok=True)
run('K','git archive '+base+' | tar -x -C '+str(scratch/'base'),'archive-base')
run('K','cd '+str(scratch/'base')+' && python3 scripts/public-hygiene.py','hygiene-base')
