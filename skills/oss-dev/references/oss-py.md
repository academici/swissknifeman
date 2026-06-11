---
name: oss-py
description: Python-специфика для OSS-проектов: pyproject.toml, uv/poetry, ruff, mypy, pytest, PyPI, tox/nox
type: reference
parent: oss-development
---

# Reference: OSS Python

Загружается дополнительно к `.ai/skills/oss-dev/oss-development.md` когда язык проекта — Python (CLI-инструменты, библиотеки на PyPI, ML-пакеты).

---

### pyproject.toml минимум (PEP 621)

```toml
[project]
name = "package-name"
version = "0.1.0"
description = "Одна строка (для PyPI листинга)"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "Vendor", email = "user@example.com" }]
keywords = []
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "License :: OSI Approved :: MIT License",
]
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1",
    "ruff>=0.4",
    "mypy>=1.10",
]

[project.urls]
Homepage = "https://github.com/vendor/repo"
Repository = "https://github.com/vendor/repo"
Issues = "https://github.com/vendor/repo/issues"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Naming convention:** PyPI имя — `kebab-case` или `snake_case`, латиница, глобально уникально на pypi.org. Импортируемое имя пакета (`src/<name>/`) — строго `snake_case`.

### Package Manager / Build Backend

| Инструмент | Когда | Lockfile |
|:---|:---|:---|
| **uv** | По умолчанию для новых проектов (быстрее всех, Rust-based, унифицирует pip + venv + lock) | `uv.lock` |
| poetry | Если уже на poetry или нужны фичи групп зависимостей | `poetry.lock` |
| pip + pip-tools | Минимализм / CI-only сценарии | `requirements.txt` (compiled) |
| hatch / pdm | Альтернативные modern build backends | свои |

**Build backend** в `[build-system]`: `hatchling` (по умолчанию для новых), `setuptools` (легаси/совместимость), `poetry-core` (если уже на poetry).

Один lockfile в репо. Коммитить **обязательно**.

### src/ layout (обязательно для библиотек)

```
package_name/
├── src/
│   └── package_name/
│       ├── __init__.py
│       └── core.py
├── tests/
├── pyproject.toml
└── README.md
```

`src/` layout предотвращает случайный импорт из cwd вместо установленного пакета — критично для тестов.

### Static Analysis & Lint

```bash
# Ruff — lint + format в одном tool (заменяет flake8 + isort + black)
uvx ruff check src tests
uvx ruff format src tests

# mypy — strict обязательно для public API
uvx mypy --strict src
```

`pyproject.toml` секция:

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF"]
# E/F: pycodestyle/pyflakes, I: isort, N: naming, UP: pyupgrade, B: bugbear, SIM: simplify

[tool.mypy]
python_version = "3.10"
strict = true
warn_unreachable = true
```

### Python Version Support Matrix

```
Python 3.10 — minimum (match statements, parametrized generics в stdlib)
Python 3.11 — recommended (exception groups, faster)
Python 3.12 — latest stable (type parameter syntax)
Python 3.13 — latest

Правило: поддерживать 3 активные минорные версии Python (Python sunset schedule — 5 лет, 1 версия в год).
```

### pytest структура

```
tests/
├── unit/           # Чистая логика без IO
├── integration/    # С реальными зависимостями
└── conftest.py     # Общие fixtures
```

```toml
[tool.pytest.ini_options]
minversion = "8.0"
addopts = "-ra -q --strict-markers --strict-config"
testpaths = ["tests"]

[tool.coverage.run]
source = ["src"]
branch = true

[tool.coverage.report]
fail_under = 80
exclude_lines = ["pragma: no cover", "raise NotImplementedError"]
```

```bash
uvx pytest --cov=src --cov-report=term-missing
```

### tox / nox для multi-version testing

`nox` (рекомендуется — конфиг в Python) для прогона тестов на нескольких версиях Python:

```python
# noxfile.py
import nox

@nox.session(python=["3.10", "3.11", "3.12", "3.13"])
def tests(session):
    session.install(".[dev]")
    session.run("pytest", "--cov=src")
```

`tox` (легаси, INI-конфиг) — только если уже используется.

### PyPI Publishing

```bash
# 1. Build (создаёт wheel + sdist в dist/)
uv build  # или python -m build

# 2. Проверить пакет (metadata sanity)
uvx twine check dist/*

# 3. Upload на TestPyPI (рекомендуется первый раз)
uvx twine upload --repository testpypi dist/*

# 4. Реальная публикация на PyPI
uvx twine upload dist/*
```

**Trusted Publishing (предпочтительно):** настроить OIDC в GitHub Actions → PyPI без хранения API токенов. См. PyPI docs «Trusted Publishers».

### .github/workflows/ci.yml для Python

```yaml
- Python versions: ["3.10", "3.11", "3.12", "3.13"]
- OS: [ubuntu-latest] (+ macos/windows если есть platform-specific код)
- uv sync --all-extras --dev
- uvx ruff check src tests
- uvx ruff format --check src tests
- uvx mypy --strict src
- uvx pytest --cov=src --cov-report=xml
- uv build  # проверка что пакет собирается
```

### Type stubs / py.typed

Для библиотеки с type hints — добавить пустой маркер `src/package_name/py.typed` и в `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/package_name"]

[tool.hatch.build]
include = ["src/package_name/py.typed"]
```

Без `py.typed` mypy в downstream-проектах **не увидит** твои аннотации.

---
