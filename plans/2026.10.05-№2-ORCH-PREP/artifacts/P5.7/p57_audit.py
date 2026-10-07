import fcntl
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/home/vostrikov/projects/packages/swissknifeman')
PLAN = ROOT / 'plans/2026.10.05-№2-ORCH-PREP'
ART = PLAN / 'artifacts/P5.7'
SCRATCH = Path('/tmp/plan2-p57-scratch').read_text().strip()
TASK = ['python3', 'packages/task/scripts/plan.py']
ORCH = ['python3', 'packages/orch/scripts/orch.py']

def run(block, command, label, *, quiet=False):
    cmd = shlex.join(command) if isinstance(command, list) else command
    log = ART / (block + '-' + label + '.log')
    started = time.monotonic()
    with log.open('w') as out:
        result = subprocess.run(command if isinstance(command, list) else ['bash', '-c', command],
                                cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, text=True)
    output = log.read_text(errors='replace')
    record = {'block': block, 'cmd': cmd, 'exit': result.returncode,
              'log': str(log.relative_to(ROOT)), 'seconds': round(time.monotonic()-started, 3)}
    with (ART / 'validation.json').open('r+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        records = json.load(f)
        records.append(record)
        f.seek(0)
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.truncate()
        with (ART / 'commands.log').open('a') as commands:
            commands.write('$ ' + cmd + '\nexit=' + str(result.returncode) + '\n')
            commands.write('\n'.join(output.splitlines()[-20:]) + '\n\n')
    if not quiet:
        print(f'{block}/{label}: exit={result.returncode} ({record["seconds"]}s) -> {log.name}', flush=True)
        if result.returncode:
            print('\n'.join(output.splitlines()[-12:]), flush=True)
    return result.returncode, output

if __name__ == '__main__':
    block, label = sys.argv[1:3]
    code, _ = run(block, sys.argv[3:], label)
    sys.exit(code)
