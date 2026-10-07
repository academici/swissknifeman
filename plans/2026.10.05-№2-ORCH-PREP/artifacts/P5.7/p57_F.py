from p57_audit import run

checks = [
    ('orch-validate', 'bash packages/orch/scripts/validate.sh'),
    ('task-validate', 'bash packages/task/scripts/validate.sh'),
    ('skiller-validate-test', 'bash packages/skiller/scripts/validate.sh && bash packages/skiller/scripts/test.sh'),
    ('harness-validate-test', 'bash packages/harness/scripts/validate.sh && bash packages/harness/scripts/test.sh'),
    ('provider-render', 'python3 packages/task/scripts/render-provider-commands.py --check --root .'),
    ('registry', 'packages/skiller/bin/skiller registry --check'),
    ('docs-sync', 'bash scripts/docs-sync.sh --check'),
    ('standalone', 'bash scripts/skiller-standalone-check.sh'),
]
for label, command in checks:
    run('F', command, label)
