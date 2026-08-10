#     говорит first-party док: «Description **not** in context»
#     (<https://code.claude.com/docs/en/skills> §«Control who invokes a skill»);
#   • `paths:` — ось A −88, ТА ЖЕ величина (там же §3.1/§4). Доку это
#     противоречит («The listing always contains every skill name»), поэтому
#     основание — наблюдение. Дозамер P3.6 назвал механизм: (C) условная
#     загрузка с условием «сессия ПРОЧЛА совпавший файл», а НЕ «файл лежит в
#     дереве» (`findings/P3-paths-mechanism.md` §2). Условие по ДЕРЕВУ в модель
#     не вносится: плечо A1 дозамера («совпавший файл лежит») дало
#     «неразличимо» в обоих прогонах — запись не возвращается (там же §3), а
#     недоказанное занижение хуже известного завышения (Implementation Rules
#     P3.2 §2). На ПЕРВОМ ходу прочитанных файлов нет по построению, поэтому для
#     first-turn-модели исключение безусловно.
# Поля НЕ измерены для Codex (стенд гонял только Claude Code — версия клиента
# первой строкой файла-вердикта), поэтому исключение применяется ТОЛЬКО к
# provider `claude-code`; codex-ветка сознательно продолжает завышать.
LISTING_EXCLUDED_BY_FIELDS = ("disable-model-invocation", "paths")
LISTING_EXCLUSION_PROVIDERS = ("claude-code",)
