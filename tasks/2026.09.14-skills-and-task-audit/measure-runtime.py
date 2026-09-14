"""Capture native startup metadata without sending a model request or saving prompts."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'packages/skiller/lib'), str(ROOT)]
from skiller.common import parse_frontmatter

PROJECTS = [Path.home() / 'projects/edufy', Path.home() / 'projects/flexcrm',
            Path.home() / 'projects/packages/corex']


def capture(pair):
    project, model = pair
    command = ['codex', '-C', str(project), '-m', model, '-a', 'never', '-s',
               'danger-full-access', 'debug', 'prompt-input']
    result = subprocess.run(command, text=True, capture_output=True, timeout=60)
    if result.returncode:
        return dict(project=str(project), model=model, exit=result.returncode, error=result.stderr)
    messages = json.loads(result.stdout)
    text = '\n'.join(c.get('text', '') for m in messages for c in m.get('content', []))
    match = re.search(r'<skills_instructions>(.*?)</skills_instructions>', text, re.S)
    if not match:
        raise ValueError('Native skills instructions missing')
    skill_text = match.group(1)
    roots = dict(re.findall(r'^- `(r\d+)` = `([^`]+)`$', skill_text, re.M))
    skills = []
    for name, description, ref in re.findall(r'^- (.+?): (.*?) \(file: (\S+)\)$', skill_text, re.M):
        alias, _, rest = ref.partition('/')
        path = Path(roots[alias]) / rest if alias in roots else Path(ref)
        fm = parse_frontmatter(path)
        expected = str(fm.get('description', ''))
        skills.append(dict(name=name, path=str(path), description=description,
                           shortened=len(description.strip()) < len(expected.strip()),
                           source_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return dict(project=str(project), model=model, exit=0, native_skill_count=len(skills),
                shortened_descriptions=sum(s['shortened'] for s in skills),
                skills_section_chars=len(skill_text), prompt_chars=len(text),
                skills_section_sha256=hashlib.sha256(skill_text.encode()).hexdigest(), skills=skills)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(capture, [(p, m) for p in PROJECTS
                                     for m in ['gpt-6-astra', 'gpt-5.6-sol']]))
    out = Path(__file__).parent / f'runtime-{args.label}.json'
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n')
    for row in rows:
        print(json.dumps({k:v for k,v in row.items() if k != 'skills'},ensure_ascii=False))
