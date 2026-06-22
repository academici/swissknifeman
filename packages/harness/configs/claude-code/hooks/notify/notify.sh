#!/usr/bin/env bash
# Notification hook: ОС-уведомление, когда Claude Code ждёт человека —
# запрос разрешения на инструмент или утверждение плана (ExitPlanMode),
# а также простой промпта дольше ~60 сек.
#
# Регистрируется на событие "Notification". Никогда не блокирует — exit 0.
# Кросс-платформенно: Linux (notify-send), macOS (osascript/terminal-notifier),
# WSL/Windows (powershell toast / msg.exe). Если бэкенда нет — тихо выходит.

input=$(cat)

# .message — текст уведомления от Claude Code (напр. "Claude needs your
# permission to use Bash"). cwd — каталог проекта для контекста заголовка.
msg=$(printf '%s' "$input" | jq -r '.message // "Claude Code ждёт ввода"' 2>/dev/null)
cwd=$(printf '%s' "$input" | jq -r '.cwd // ""' 2>/dev/null)
[[ -n "$msg" ]] || msg="Claude Code ждёт ввода"

project=""
[[ -n "$cwd" ]] && project="$(basename "$cwd")"
title="Claude Code"
[[ -n "$project" ]] && title="Claude Code — $project"

notify_linux() {
  command -v notify-send >/dev/null 2>&1 || return 1
  # -a имя приложения, -u critical чтобы не авто-исчезало мгновенно
  notify-send -a "Claude Code" -u critical "$title" "$msg" >/dev/null 2>&1
}

notify_macos() {
  if command -v terminal-notifier >/dev/null 2>&1; then
    terminal-notifier -title "$title" -message "$msg" -sound default >/dev/null 2>&1
    return 0
  fi
  command -v osascript >/dev/null 2>&1 || return 1
  # экранируем двойные кавычки для AppleScript-строки
  local m="${msg//\"/\\\"}" t="${title//\"/\\\"}"
  osascript -e "display notification \"$m\" with title \"$t\" sound name \"Submarine\"" >/dev/null 2>&1
}

notify_windows() {
  # WSL/Git-Bash: пробуем toast через PowerShell, иначе msg.exe
  local ps
  ps=$(command -v powershell.exe || command -v pwsh.exe) || ps=""
  if [[ -n "$ps" ]]; then
    local m="${msg//\'/\'\'}" t="${title//\'/\'\'}"
    "$ps" -NoProfile -NonInteractive -Command "
      \$ErrorActionPreference='SilentlyContinue';
      [Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null;
      \$xml=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);
      \$t=\$xml.GetElementsByTagName('text'); \$t[0].AppendChild(\$xml.CreateTextNode('$t')) | Out-Null;
      \$t[1].AppendChild(\$xml.CreateTextNode('$m')) | Out-Null;
      \$n=[Windows.UI.Notifications.ToastNotification]::new(\$xml);
      [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Claude Code').Show(\$n);
    " >/dev/null 2>&1 && return 0
    "$ps" -NoProfile -NonInteractive -Command "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; [System.Windows.Forms.MessageBox]::Show('$m','$t')" >/dev/null 2>&1
    return 0
  fi
  command -v msg.exe >/dev/null 2>&1 || return 1
  msg.exe "*" "/TIME:10" "$title: $msg" >/dev/null 2>&1
}

case "$(uname -s)" in
  Linux*)
    # WSL опознаём по микроядру; иначе обычный Linux desktop
    if grep -qi microsoft /proc/version 2>/dev/null; then
      notify_windows || notify_linux
    else
      notify_linux
    fi
    ;;
  Darwin*) notify_macos ;;
  CYGWIN*|MINGW*|MSYS*) notify_windows ;;
esac

exit 0
