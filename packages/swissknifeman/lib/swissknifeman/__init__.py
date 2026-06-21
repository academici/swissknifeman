"""swissknifeman — CLI реестра скиллов.

Логика вынесена из bin/swissknifeman (раньше — Python-heredoc внутри bash).
Бинарник теперь тонкий лаунчер: проверяет окружение и вызывает
`python3 -m swissknifeman <repo_root> <cmd> [args...]`.

Модули:
  common    — die/warn/now_iso/confirm, парсинг frontmatter и flag'ов
  config    — .swissknife.json, профили, autodetect, resolve_selection
  state     — ~/.swissknifeman/projects.json, registry_git_state
  hub       — генерация корневого хаба, обнаружение артефактов
  boost     — синк boost.json::skills для Laravel Boost
  connect   — канал plugin marketplace
  vendor    — канал вендоринга
  update    — обновление подключения/вендоринга (диск — источник истины)
  status    — read-only отчёт
  projects  — list зарегистрированных проектов
  registry  — регенерация skills.json + манифестов (мейнтейнер)
  doctor    — диагностика окружения
  cli       — диспетчер команд (точка входа __main__)

Точка входа для тестов: импортируй нужные функции напрямую, окружение
передаётся через объект Env (common.Env), без модульных глобалей.
"""
