---
name: venv-dependencies
bucket: python
version: 0.1.0
description: "Use when managing Python dependencies and virtual environments for project reproducibility."
risk: write
persona: oss-dev
tags: [python, venv, dependencies, tooling, quality, conventions]
requires: [ml-project-structure]
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Dependency & Environment Management (Python)

## Virtual environments
- Always use a venv. NEVER install packages globally into the system.
- Standard `venv` (simple projects):
  ```bash
  python3 -m venv .venv
  ```
  Activate (Linux/macOS):
  ```bash
  source .venv/bin/activate
  ```
  Activate (Windows):
  ```bash
  .venv\Scripts\activate
  ```
- Alternatives (complex projects):
  - Poetry: complex deps + package builds. Uses `pyproject.toml` + `poetry.lock`.
  - Conda: Data Science with binary deps (e.g. specific CUDA for TensorFlow/PyTorch) hard to build via plain `pip`.

## Dependencies (`requirements.txt`) — with `pip`+`venv`
- Pin exact versions:
  ```bash
  pip freeze > requirements.txt
  ```
- Split deps (optional): prod vs dev.
  - `requirements.txt` — core (pandas, scikit-learn, fastapi)
  - `requirements-dev.txt` — testing/linters/notebooks (pytest, black, jupyter)

## .gitignore — must include venvs + compiled bytecode
```gitignore
# Virtual Environments
.env/
.venv/
env/
venv/
ENV/
env.bak/
venv.bak/

# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# Jupyter
.ipynb_checkpoints

# Local environment variables
.env
```

## Linters & formatters
- Black: uncompromising formatter (`black .`).
- Ruff: fast Rust linter (replaces Flake8, Isort, others).
- Mypy: static type checker (optional; useful for complex logic and Python backends).

## Related skills
- `python/ml-project-structure` — project layout deciding where `requirements.txt`/`pyproject.toml` go and what enters `.gitignore`.
- `php/static-analysis` — PHP analog of Black/Ruff/Mypy (Pint, PHPStan, Rector) locally and in CI.
- `oss-dev/dependency-audit` — dependency audit (vuln scan, licenses, supply-chain, SBOM) on top of pinned versions.
