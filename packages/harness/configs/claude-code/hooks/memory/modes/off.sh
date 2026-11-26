#!/usr/bin/env bash

mode_remember() { echo "memory(off): mode off - nothing saved"; }
mode_recall()   { echo "memory(off): mode disabled"; }
mode_members()  { brain_members "$1"; }
mode_status()   { echo "brain=$1 mode=off (memory disabled)"; }
mode_sync()     { :; }
