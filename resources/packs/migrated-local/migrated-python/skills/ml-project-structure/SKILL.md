---
name: ml-project-structure
description: "Use when structuring an ML/Data Science project per Cookiecutter Data Science."
---

# Python ML Project Structure

Use Cookiecutter Data Science layout for ML/DS projects.

## Directory Layout

```text
my_ml_project/
├── data/
│   ├── raw/            # Source, immutable data (never commit to git!)
│   ├── interim/        # Intermediate data (after initial cleaning)
│   └── processed/      # Final data, ready for model training
├── models/             # Trained models and serialized objects (pickle, onnx)
├── notebooks/          # Jupyter notebooks. Naming: 1.0-jdoe-initial_exploration.ipynb
├── src/                # Project source code (core modules)
│   ├── __init__.py
│   ├── data/           # Scripts to load and generate data
│   ├── features/       # Scripts to transform features (Feature Engineering)
│   ├── models/         # Scripts to train and infer (predict.py, train.py)
│   └── visualization/  # Scripts to build plots
├── requirements.txt    # Dependencies file (or pyproject.toml / poetry.lock)
├── .env                # Local env vars (DB passwords, API keys)
├── .gitignore
└── README.md
```

## Rules

- **Data is immutable:** never modify `data/raw`. Scripts read from there, write results to `data/interim` or `data/processed`.
- **Notebooks = research, scripts = production:**
  - Jupyter notebooks for EDA and prototyping.
  - Once code stabilizes (e.g. a data-cleaning function), move it to Python modules under `src/`.
  - From notebooks call imported functions from `src/`; do not write long code blobs in the notebook.
- **Logging:** use `logging` module, not many `print()`.
- **Config:** put hyperparameters, file paths, settings in config files (YAML, JSON, or `.env`); do not hardcode in scripts.

## Related skills

- `python/venv-dependencies` — dependency/environment management for the folder this structure defines (`requirements.txt` / `pyproject.toml`, linters).
- `php/laravel-structure` — analogous structure canon for Laravel projects.
- `oss-dev/oss-development` — OSS-repo structure (README, ADR, CI) on top of project code.
