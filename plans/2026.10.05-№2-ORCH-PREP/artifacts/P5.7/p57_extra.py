import json
import subprocess
import sys
from pathlib import Path
from p57_audit import ROOT, PLAN, ART, SCRATCH, TASK, ORCH, run

run('B',['python3','scripts/test-config-inventory.py'],'config-inventory')
run('B',['python3','scripts/sync-managed-blocks.py','--check'],'managed-blocks')
run('B',TASK+['context','PLAN2','P5.6','--budget'],'conclusion-context-budget')
run('B',['git','log',Path(SCRATCH,'base-sha').read_text()+'..HEAD','--format=%H %s','--','packages/artifex'],'artifex-history')
run('B',['git','diff','--name-only',Path(SCRATCH,'base-sha').read_text()+'..HEAD','--','packages/harness/lib/harness/run'],'harness-run-paths')

# Preserve the first results; qualify lexical refusals as facts, not a change to a decision.
run('D',TASK+['bridge','orch','brief','PLAN2','P4.4','--out',SCRATCH+'/p44.json'],'negative-role-input')
run('D',['rg','-n','report_api','packages/orch/roles/executor.json'],'negative-role-literal')

run('G',['git','cat-file','-e','v0.28.6:configs/profile-catalog.json'],'profile-released')
run('G',['git','show','v0.28.6:core/config_paths.py'],'released-config-resolver')
# In scratch, exercise the released API with a supported root-only layout.
source=subprocess.check_output(['git','show','v0.28.6:core/config_paths.py'],cwd=ROOT,text=True)
source=source.replace('from .repo import find_monorepo_root','find_monorepo_root = lambda _: None')
old={};exec(compile(source,'v0.28.6:core/config_paths.py','exec'),old)
sys.path.insert(0,str(ROOT))
from core.config_paths import shared_config_path
fixture=Path(SCRATCH)/'legacy-config-layout'
(fixture/'configs').mkdir(parents=True,exist_ok=True)
(fixture/'configs/profile-catalog.json').write_text('{}\n')
released=old['shared_config_path']('profile-catalog',repo_root=fixture)
current=shared_config_path('profile-catalog',repo_root=fixture)
print('G config behavior: released='+str(released.relative_to(fixture))+' exists='+str(released.exists()))
print('G config behavior: current='+str(current.relative_to(fixture))+' exists='+str(current.exists()))

run('I',['rg','-n','^#|^def |schemas/plan/v1|core|prepare_common|role-skills|bridges','packages/task/skills/plan-protocol/references/review-mode.md','packages/task/lib/task/plan/bridges.py','packages/task/lib/task/plan/lifecycle.py','packages/task/lib/task/plan/gitops.py','packages/task/lib/task/plan/parallel.py','packages/orch/bridges/skiller/resolve_role.py','packages/orch/lib/orch/launch.py','packages/skiller/lib/skiller/host.py','scripts/skiller-standalone-check.sh'],'implementation-locations')
