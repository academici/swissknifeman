#!/usr/bin/env bash
# Режим off — память выключена (база для A/B). Источается memory.sh.

mode_remember() { echo "memory(off): режим выключен — ничего не сохранено"; }
mode_recall()   { echo "memory(off): режим выключен"; }
mode_members()  { brain_members "$1"; }
mode_status()   { echo "brain=$1 mode=off (память выключена)"; }
mode_sync()     { :; }
