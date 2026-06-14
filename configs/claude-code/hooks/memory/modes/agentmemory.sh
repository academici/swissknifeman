#!/usr/bin/env bash
# Режим agentmemory — прокси в сторонний AgentMemory (демон на Brain).
# Источается memory.sh.
#
# ВНИМАНИЕ: точная форма HTTP-API AgentMemory (пути, поля) зависит от версии
# (@agentmemory/agentmemory). Ниже — разумные дефолты; при первом реальном
# прогоне сверь с `curl <url>` и поправь пути/jq-выборку под свой инстанс.
# Любая недоступность демона → честное сообщение, без падения сессии.

_am_up() { # brain → 0 если демон отвечает
  local url; url="$(brain_am_url "$1")"; [ -n "$url" ] || return 1
  curl -fsS -m 2 "$url/health" >/dev/null 2>&1 || curl -fsS -m 2 "$url" >/dev/null 2>&1
}

mode_remember() { # brain type text
  local url ns; url="$(brain_am_url "$1")"; ns="$(brain_am_ns "$1")"
  _am_up "$1" || { echo "memory(agentmemory): демон недоступен ($url) — факт не сохранён"; return 1; }
  curl -fsS -m 5 -X POST "$url/memories" -H 'Content-Type: application/json' \
       -d "$(jq -cn --arg t "$3" --arg ns "$ns" --arg ty "$2" '{namespace:$ns,type:$ty,text:$t}')" \
       >/dev/null 2>&1 \
    && echo "memory(agentmemory): отправлено в namespace=$ns" \
    || echo "memory(agentmemory): POST не прошёл — сверь API ($url)"
}

mode_recall() { # brain query
  local url ns q; url="$(brain_am_url "$1")"; ns="$(brain_am_ns "$1")"
  _am_up "$1" || { echo "memory(agentmemory): демон недоступен ($url)"; return 1; }
  q="$(jq -rn --arg q "$2" '$q|@uri')"
  curl -fsS -m 5 "$url/search?namespace=$ns&q=$q" 2>/dev/null \
    | jq -r '.results[]? | "— [\(.score // "?")] \(.text)"' 2>/dev/null \
    || echo "memory(agentmemory): пустой/неожиданный ответ — сверь API ($url)"
}

mode_members() { brain_members "$1"; }

mode_status() {
  local url; url="$(brain_am_url "$1")"
  if _am_up "$1"; then
    echo "brain=$1 mode=agentmemory url=$url статус=доступен ns=$(brain_am_ns "$1")"
  else
    echo "brain=$1 mode=agentmemory url=$url статус=НЕДОСТУПЕН (подними: cd ~/Vaults/Brain && npm run memory:start)"
  fi
}

mode_sync() { mode_status "$1"; }
