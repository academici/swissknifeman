"""Read-only inventory for this audit; writes reports only beside this script.

Counts are filesystem/config candidates, not an attested provider skills/list.
Token estimates reuse Skiller math and are not provider usage measurements.
"""
from pathlib import Path
import collections
import hashlib
import json
import re
import subprocess
import sys
import tomllib

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path[:0] = [str(ROOT / 'packages/skiller/lib'), str(ROOT)]
from skiller.common import parse_frontmatter
from skiller.budget import skill_budget, estimate_tokens

HOME_DIR = Path.home()
PROJECTS = [HOME_DIR / 'projects/edufy', HOME_DIR / 'projects/flexcrm',
            HOME_DIR / 'projects/packages/corex']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path, origin):
    fm = parse_frontmatter(path)
    text = path.read_text()
    description = str(fm.get('description', ''))
    name = fm.get('name', path.parent.name)
    return dict(path=str(path), origin=origin, name=name, description=description,
                description_chars=len(description), bytes=len(path.read_bytes()), sha256=sha(path),
                listing_chars=len(f'- {name}: {description} (file: {path})\n'),
                budget_estimate=skill_budget(path.parent),
                constraint_signals=[dict(line=i, text=line[:600])
                    for i, line in enumerate(text.splitlines(), 1)
                    if re.search(r'\b(must|mandatory|forbidden|always|never|approval|ask|stop)\b|обяз|подтверж|чистое', line, re.I)])


def recommendation(key):
    explicit = {
        'general/anti-drift': ('rewrite', 'Убрать ASK/точные filenames как общий gate; удалить устаревшие restart/tool-specific хвосты.'),
        'general/context-economy': ('keep', 'Короткий полезный контракт замеров и continuity; сохранить.'),
        'general/compact-responses': ('opt-in', 'Личная настройка стиля; кандидат на исключение из обязательного CORE.'),
        'general/mcp-advisor': ('opt-in', 'Onboarding/MCP setup; исключить из повседневного CORE, сохранить capability.'),
        'research/query-craft': ('opt-in', 'Исследовательский профиль; убрать из обязательного CORE после проверки зависимостей.'),
        'oss-dev/gh-review': ('opt-in', 'GitHub review профиль; не нужен в каждой локальной задаче.'),
        'general/plan-protocol': ('split-body', 'Task-owned short executor entry; layout/authoring/reference по роли, без нового набора резидентных скиллов.'),
        'general/skills-ssot': ('rewrite', 'Устранить универсальное предписание Boost ownership; учитывать существующий канал/генератор.'),
        'general/complex-task-orchestrator': ('merge', 'Сохранить краткую организацию прямой задачи; убрать параллельный process canon рядом с Task.'),
        'general/implement': ('opt-in', 'Явная standalone команда; не вызывать автоматически поверх task:dev.'),
        'general/task-brief-template': ('reference', 'Шаблон по запросу; поля не должны становиться обязательным планом для обычной задачи.'),
        'general/naming-conventions': ('merge', 'Общие банальности убрать; необычные проектные правила объединить со style entry.'),
        'general/writing-style': ('opt-in', 'Языковые предпочтения проекта; не глобальное требование для всех артефактов.'),
        'quality/tdd-discipline': ('rewrite', 'Удалить повторное user approval при уже согласованном scope; test-first только по релевантному запросу.'),
        'quality/test-strategy': ('rewrite', 'Проценты и запреты сделать примерами стратегии, не gates любой разработки.'),
        'quality/code-review': ('opt-in', 'Командный процесс/SLA отдельно от проверки конкретного diff; устранить разночтение severity.'),
        'quality/artifact-review': ('rewrite', 'Не отправлять всякий plan/spec review в phase audit; severity по воздействию, не вкусу скилла.'),
        'quality/diagnosing-bugs': ('rewrite', 'Не блокировать статически доказуемую ошибку отсутствием live reproducer; сузить auto trigger.'),
        'quality/testing-safety-report': ('merge', 'Использовать один итоговый отчёт Task; шаблон рисков оставить reference.'),
        'architect/package-contribution-protocol': ('rewrite', 'Различать несогласованное расширение dependency и разрешённый bugfix; устранить 2/3-consumer и SemVer противоречия.'),
        'architect/engineering': ('opt-in', 'Обзорный navigator; не подключать вместе со всеми granular skills по умолчанию.'),
        'architect/domain-modeling': ('rewrite', 'Глоссарий/ADR только для реального изменения модели; убрать обязательную запись при каждом уточнении.'),
        'architect/architecture': ('rewrite', 'ADR/BRD как выбор по решению и риску, не обязательный этап любой локальной архитектурной правки.'),
        'architect/api-design': ('rewrite', 'Versioning/матрицы как policy проекта; не универсальный gate с первого дня.'),
        'architect/agent-design': ('rewrite', 'Четыре budget limits и запрет любых параллельных writes не универсальны; привязать к tool/resource риску.'),
        'architect/security-design': ('rewrite', 'Сохранить threat/auth/secrets проверки; manual review только по реальному security boundary.'),
        'php/named-arguments': ('merge', 'Сохранить выбранную проектом конвенцию в php style; убрать отдельный auto-trigger почти каждого вызова.'),
        'php/naming-conventions': ('merge', 'Сохранить необычные naming conventions в одном style/structure entry, без отдельного широкого триггера.'),
        'php/dependency-injection': ('reference', 'Матрица DI в references Laravel architecture; не отдельная обязательная остановка.'),
        'php/php-patterns': ('reference', 'Справочник выбора паттерна; не автоматическое требование новой абстракции.'),
        'php/laravel': ('rewrite', 'Сохранить проектные инварианты; разъяснить conditional repository, consistency first.'),
        'php/repositories': ('rewrite', 'Уточнить условие применения выбранной CQRS схемы; не навязывать фасад/visibility каждому проекту.'),
        'php/laravel-best-practices': ('deduplicate', 'В Boost-проекте выбрать одну версионную поставку; fallback оставить другим проектам.'),
        'frontend-vue/vueuse-functions': ('split-body', 'Перенести каталог функций в references; узкий navigator, API установленной версии.'),
        'frontend-vue/vue-best-practices': ('deduplicate', 'Согласовать с vue entry; убрать повторный auto-trigger всего Vue-кода.'),
        'devops/docker': ('keep', 'Один entry для Docker с выбором предметного reference.'),
        'devops/gitops': ('opt-in', 'Только настройка git strategy, не каждодневная разработка.'),
        'ai/performance': ('opt-in', 'Perplexity-specific стиль, не глобальная сессия Codex.'),
    }
    if key in explicit:
        return explicit[key]
    bucket, name = key.split('/', 1)
    if bucket == 'repository-bootstrap':
        return ('private-only', 'Сохранить внутренним; сузить trigger/читать канон по конкретной операции.')
    if bucket == 'system':
        return ('opt-in', 'Environment/navigation профиль; не добавлять весь bucket каждому consumer.')
    if bucket == 'devops' and name.startswith('docker-'):
        return ('reference', 'Кандидат в references единого Docker entry; проверить доставку ресурсов и обратные ссылки.')
    if bucket in {'finance','founder','creative','legal','marketing','sales','pm','roles','operator',
                  'blender','blender-modeling','voice-ai','ai','python','dart','mobile','security'}:
        return ('specialized', 'Сохранить для профильного запроса; не включать в default этих трёх PHP-проектов.')
    return ('keep-scoped', 'Сохранить по стеку/риску; по скринингу нет основания удалять. Точечный trigger вместо загрузки всего bucket.')


def main():
    source = []
    for path in sorted((ROOT / 'packages/skiller/skills').glob('*/*/SKILL.md')):
        key = '/'.join(path.parts[-3:-1])
        row = record(path, 'canonical')
        row.update(key=key, action=recommendation(key)[0], reason=recommendation(key)[1])
        source.append(row)
    global_path = HOME_DIR / '.codex/config.toml'
    global_config = tomllib.loads(global_path.read_text())
    by_name = collections.defaultdict(list)
    for row in source:
        by_name[row['name']].append(row)
    projects = []
    for root in PROJECTS:
        config_path = root / '.codex/config.toml'
        local = tomllib.loads(config_path.read_text()) if config_path.exists() else {}
        merged = {**global_config.get('plugins', {}), **local.get('plugins', {})}
        entries, unresolved = [], []
        for key, value in sorted(merged.items()):
            if not value.get('enabled', False):
                continue
            name, marketplace = key.split('@')
            base = HOME_DIR / '.codex/plugins/cache' / marketplace / name
            versions = list(base.iterdir()) if base.exists() else []
            if len(versions) != 1:
                unresolved.append(dict(plugin=key, versions=[p.name for p in versions]))
                continue
            version = versions[0]
            manifest = version / '.codex-plugin/plugin.json'
            metadata = json.loads(manifest.read_text())
            paths = set()
            for entry in metadata.get('skills', []):
                folder = version / entry
                if (folder / 'SKILL.md').exists():
                    paths.add(folder / 'SKILL.md')
                else:
                    paths.update(folder.rglob('SKILL.md'))
            # Codex auto-migrated commands are a separate observed discovery surface.
            paths.update((version / '.codex-plugin/migrated-command-skills').glob('*/SKILL.md'))
            entries += [record(p, key) for p in sorted(paths)]
        for p in sorted((root / '.agents/skills').glob('*/SKILL.md')):
            row = record(p, 'project-local')
            candidates = by_name[row['name']]
            if len(candidates) == 1:
                row['canonical_key'] = candidates[0]['key']
                row['canonical_sha_matches'] = candidates[0]['sha256'] == row['sha256']
            entries.append(row)
        # These scopes are visible in the active session; curated plugin enablement is
        # not inferred from mere cache presence and is deliberately not counted here.
        globals_seen = set()
        for base in [HOME_DIR / '.codex/skills', HOME_DIR / '.agents/skills']:
            for p in sorted(base.rglob('SKILL.md')):
                if p.resolve() not in globals_seen:
                    entries.append(record(p, 'user-or-system'))
                    globals_seen.add(p.resolve())
        duplicate_names = {name: [r['path'] for r in entries if r['name'] == name]
                           for name, n in collections.Counter(r['name'] for r in entries).items() if n > 1}
        doc = root / 'AGENTS.md'
        projects.append(dict(project=str(root), config_sha256=sha(config_path) if config_path.exists() else None,
            enabled_plugins=[k for k,v in merged.items() if v.get('enabled')], unresolved=unresolved,
            candidates=len(entries), description_chars=sum(r['description_chars'] for r in entries),
            listing_chars_proxy=sum(r['listing_chars'] for r in entries),
            tier0_name_description_estimate=sum(r['budget_estimate']['tier0'] for r in entries),
            agents_md_bytes=len(doc.read_bytes()), agents_md_sha256=sha(doc),
            duplicates=duplicate_names, entries=entries))
    roads = [dict(path=str(p.relative_to(ROOT)), sha256=sha(p)) for p in sorted((ROOT / 'roadmap').glob('2026.09.14-*.md'))]
    report = dict(method='Static candidate inventory; no provider enumeration, no model A/B, no runtime writes.',
        git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        global_config_sha256=sha(global_path), source=source, projects=projects, roadmap=roads)
    (OUT / 'inventory.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    lines = ['# Полный каталог: 232 canonical SKILL.md', '',
        'Автоматический скрининг всех тел/описаний + адресный содержательный аудит проблемных семейств. '
        'Это рекомендации, не разрешение массово удалять скиллы. References и scripts не прошли полный API/security аудит.', '',
        'Числа T0/T1 — оценка Skiller, не usage Codex. T1 не резидентен до чтения скилла.', '',
        '| Скилл | T0 / T1 estimate | Решение | Обоснование |', '|---|---:|---|---|']
    for r in source:
        b = r['budget_estimate']
        link = '../../'+str(Path(r['path']).relative_to(ROOT))
        lines.append(f'| [{r["key"]}]({link}) | {b["tier0"]} / {b["tier1"]} | {r["action"]} | {r["reason"]} |')
    (OUT / 'skills-matrix.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(source_count=len(source), actions=dict(collections.Counter(r['action'] for r in source)),
        projects=[{k:p[k] for k in ['project','candidates','description_chars','listing_chars_proxy','agents_md_bytes']} |
                  {'duplicate_names':len(p['duplicates'])} for p in projects]),ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
