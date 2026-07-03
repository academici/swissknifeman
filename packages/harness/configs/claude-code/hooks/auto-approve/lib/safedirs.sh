#!/usr/bin/env bash
# safe-dirs: точечное разрешение rm/rmdir внутри доверенных директорий.
# Вердикт считает lib/safedirs.py по MACHINE-OWNED конфигу safe-dirs.json
# ($SKM_SAFE_DIRS_CONFIG → корень монорепо swissknifeman → legacy ~/.swissknifeman/;
# резолв — в python). Project-override .claude/auto-approve.config.json сюда не
# влияет — враждебный репозиторий не должен разрешать себе rm. Fail-closed: нет
# python3/конфига/любой сбой => вердикта нет => deny_hard работает как раньше.
# Источать после common.sh.

# safedirs_applicable <scan>: 0 если есть слово rm|rmdir — пре-фильтр, чтобы не
# спавнить python3 на каждую команду (git rm к этому моменту уже замаскирован).
safedirs_applicable() {
  printf '%s' "$1" | grep -Eq '(^|[^[:alnum:]_/.-])(rm|rmdir)([[:space:]]|$)'
}

# safedirs_verdict: 0 если ВСЕ rm/rmdir команды валидированы против allowlist.
# Работает по сырому HOOK_INPUT (оригинальная команда с кавычками + cwd).
safedirs_verdict() {
  command -v python3 >/dev/null 2>&1 || return 1
  [ "$(printf '%s' "$HOOK_INPUT" | python3 "$HOOK_DIR/lib/safedirs.py" 2>/dev/null)" = "safe" ]
}

# safedirs_mask <text>: rm|rmdir как слово → safe-rm|safe-rmdir. Только ПОСЛЕ
# вердикта: маскированные головы deny_hard не ловит, strict принимает.
safedirs_mask() {
  printf '%s' "$1" | sed -E \
    -e 's/(^|[^[:alnum:]_/.-])rm([[:space:]]|$)/\1safe-rm\2/g' \
    -e 's/(^|[^[:alnum:]_/.-])rmdir([[:space:]]|$)/\1safe-rmdir\2/g'
}
