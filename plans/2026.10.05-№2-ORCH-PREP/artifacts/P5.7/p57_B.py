import ast
import json
import re
from pathlib import Path
from p57_audit import ART,ROOT,PLAN

MAPPING={
 'R1':[('packages/task/bridges/orch/brief.py','def verify'),('packages/orch/tests/test_roles_text.py','def test_')],
 'R2':[('packages/orch/lib/orch/port.py','TERMINAL'),('packages/orch/tests/test_runstate.py','def test_')],
 'R3':[('packages/task/bridges/orch/register.py','def main'),('packages/task/lib/task/plan/scout.py','def _argv')],
 'R4':[('packages/orch/lib/orch/launch.py','--bare'),('packages/orch/tests/test_launch.py','def test_catalog_names_no_model')],
 'R5':[('packages/orch/lib/orch/bindings/__init__.py','def prepare_common'),('packages/orch/tests/test_prepare.py','def test_dry_run_prints_a_valid_plan')],
 'R6':[('packages/orch/schemas/exec/v1/run-policy.schema.json','"scout"'),('packages/orch/tests/test_role_manifests.py','def test_')],
 'R7':[('packages/orch/lib/orch/bindings/__init__.py','stage_provider ='),('packages/orch/tests/test_prepare.py','def test_optional_review_on_the_primary_provider_is_dropped')],
 'R8':[('packages/orch/schemas/exec/v1/run-event.schema.json','"raw_ref"'),('packages/orch/lib/orch/port.py','def close')],
 'R9':[('packages/orch/bridges/skiller/role-skills.json','quality'),('packages/orch/bridges/skiller/resolve_role.py','def run_skiller'),('packages/orch/bridges/skiller/tests/test_review_prompt.py','def test_')],
 'R10':[('orch/DECISIONS.md','^#')],
 'R11':[('packages/orch/docs/architecture.md','^#'),('packages/orch/lib/orch/port.py','class EnginePort')],
 'R12':[('packages/orch/docs/adding-an-engine.md','^#'),('packages/orch/docs/engine-port.md','^#')],
 'R13':[('packages/orch/lib/orch/adhoc.py','def build'),('packages/orch/tests/test_portability.py','INPUTS =')],
 'R14':[('packages/orch/tests/test_portability.py','def test_launch_plan_is_valid_or_the_expected_refusal')],
 'R15':[('orch/DECISIONS.md','^## 0')],
 'R16':[('packages/orch/bindings/matrix.json','"cao"'),('packages/orch/tests/test_capability_seeds.py','def test_')],
 'R17':[('packages/task/references/executor-handoff.md','^#'),('packages/task/tests/test_boundary.py','def test_core_names_no_other_package')],
 'R18':[('packages/orch/tests/test_schema_profile.py','def test_'),('packages/orch/tests/test_contracts_input.py','def test_')],
 'R19':[('packages/harness/lib/harness/run/task_paths.py','def task_root'),('packages/skiller/tests/test_boundary.py','def test_package_boundary_and_allowlist')],
 'R20':[('packages/orch/lib/orch/bindings/__init__.py','NOT_IMPLEMENTED'),('packages/orch/docs/architecture.md','future')],
 'R21':[('CHANGELOG.md','never released'),('core/config_paths.py','def shared_config_path')],
 'R22':[('plans/2026.10.05-№2-ORCH-PREP/research/Q19.json','"')],
 'R23':[('plans/2026.10.05-№2-ORCH-PREP/plan.json','"phases"')],
 'R24':[('packages/task/lib/task/plan/lifecycle.py','ROUTE_MODEL_UNKNOWN')],
 'R25':[('plans/2026.10.05-№2-ORCH-PREP/knowledge/conclusion.json','"id": "coverage"')],
 'R26':[('plans/2026.10.05-№2-ORCH-PREP/brief.json','новой сессии')],
 'R27':[('packages/task/bridges/orch/tests/test_record_parity.py','def test_')],
 'R28':[('plans/2026.10.05-№2-ORCH-PREP/knowledge/conclusion.json','"id"')],
 'I1':[('packages/task/bridges/orch/brief.py','BRIEF_INCOMPLETE'),('packages/task/bridges/orch/tests/test_brief.py','def test_large_item_is_not_truncated')],
 'I2':[('packages/orch/docs/engine-port.md','owner'),('packages/orch/lib/orch/bindings/__init__.py','self.binding')],
 'I3':[('packages/orch/lib/orch/contracts.py','INPUT_AUTHORITY'),('packages/task/bridges/orch/register.py','plan.py')],
 'I4':[('packages/task/lib/task/plan/lifecycle.py','def '),('packages/task/tests/engine/test_evidence.py','def test_')],
 'I5':[('packages/orch/lib/orch/bindings/__init__.py','ROUTE_UNDERSHOOT'),('packages/task/tests/engine/test_actors_attempts.py','def test_')],
 'I6':[('packages/task/lib/task/plan/lifecycle.py','already_registered=True'),('packages/task/tests/engine/test_actors_attempts.py','def test_')],
 'I7':[('packages/orch/lib/orch/bindings/__init__.py','CAPABILITY_UNSUPPORTED'),('packages/orch/tests/test_portability.py','CAPABILITY_UNSUPPORTED')],
 'I8':[('packages/orch/lib/orch/catalog.py','def resolve_model'),('packages/task/bridges/orch/launch.py','resolve_model')],
 'I9':[('scripts/sync-managed-blocks.py','^def '),('packages/task/references/reviewer-selection.md','^#')],
 'I10':[('packages/orch/lib/orch/contracts.py','POLICY_REVIEW_LIMIT'),('packages/task/commands/plan-run.md','at most one re-review')],
 'I11':[('packages/orch/tests/test_boundaries.py','def test_runtime_imports_are_stdlib_or_orch')],
 'I12':[('packages/orch/lib/orch/launch.py','--bare'),('packages/orch/tests/test_launch.py','def test_bare_is_forbidden')],
 'I13':[('packages/harness/lib/harness/run/task_paths.py','def task_root'),('packages/orch/bridges/task/discovery.py','def task_root')],
 'I14':[('packages/orch/lib/orch/port.py','usage'),('packages/orch/tests/test_runstate.py','quota')],
 'I15':[('packages/harness/lib/harness/run/task_paths.py','monorepo_root')],
 'B44':[('packages/task/tests/test_boundary.py','def test_core_names_no_other_package'),('packages/task/skills/plan-protocol/references/review-mode.md','^#')],
 'B45':[('packages/orch/tests/test_boundaries.py','def test_core_names_no_other_package')],
 'B46':[('packages/task/lib/task/plan/bridges.py','bridge.json'),('packages/task/tests/engine/test_bridges.py','partner-x')],
 'B47':[('scripts/skiller-standalone-check.sh','Standalone Skiller'),('configs/skiller-host.json','bootstrap')],
 'B48':[('packages/task/lib/task/plan/gitops.py','def commit'),('packages/task/commands/plan-run.md','scoped commit')],
 'B49':[('packages/orch/configs/launch-catalog.json','codex'),('packages/task/bridges/orch/launch.py','def main')],
 'B50':[('configs/config-inventory.json','profile-catalog'),('scripts/test-config-inventory.py','^def '),('packages/task/tests/test_command_routing_capabilities.py','def test_')],
 'B51':[('packages/task/lib/task/plan/parallel.py','def '),('packages/orch/schemas/exec/v1/run-policy.schema.json','isolation')],
 'B52':[('packages/task/lib/task/plan/context.py','included'),('packages/task/skills/plan-protocol/SKILL.md','context')],
}

anchors={}
for iid,checks in MAPPING.items():
    print('\n### '+iid)
    anchors[iid]=[]
    for file,pattern in checks:
        path=ROOT/file
        if not path.exists():print('MISSING',file);continue
        lines=path.read_text().splitlines()
        found=[n for n,line in enumerate(lines) if re.search(pattern,line)]
        if not found:print('NO MATCH',file,pattern);continue
        for n in found[:2]:
            anchors[iid].append(file+':'+str(n+1))
            for k in range(max(0,n-1),min(len(lines),n+11)):
                print(file+':'+str(k+1)+': '+lines[k])
    for file,_ in checks:
        if 'tests/' in file and file.endswith('.py') and (ROOT/file).exists():
            tree=ast.parse((ROOT/file).read_text())
            tests=[{'name':n.name,'line':n.lineno,'assertions':sum(isinstance(c,ast.Call) and isinstance(c.func,ast.Attribute) and c.func.attr.startswith('assert') for c in ast.walk(n))}
                   for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
            print('TESTS',file,json.dumps(tests))
(ART/'B-anchors.json').write_text(json.dumps(anchors,ensure_ascii=False,indent=2)+'\n')
