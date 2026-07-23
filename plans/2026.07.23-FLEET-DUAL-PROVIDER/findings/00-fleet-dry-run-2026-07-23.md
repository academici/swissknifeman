# Fleet dry-run — 2026-07-23

Команда: `./packages/maind/bin/maind sync --all --mode auto --dry-run --json`.

Наблюдения:

- четыре временных `local-repo` в реестре указывают на отсутствующие `/tmp` пути;
- vendor-проекции корректно отказались перезаписывать managed-drift без `--repair`;
- connect-проекции с Codex для внешнего проекта завершаются
  `SPUB_PATH_UNCONTAINED`, потому что
  `skiller.publication.build_connect_distribution_plan()` разрешает Codex
  marketplace только для self-host корня;
- ни один проект не был изменён: это dry-run, процесс завершился до JSON-отчёта
  из-за fail-closed ошибок.

Источник: локальный воспроизводимый запуск в корне swissknifeman. RAG:—
(repo-grounded: packages/skiller/lib/skiller/publication.py:571).
