"""Deterministic child-process cuts for recovery verification."""
from __future__ import annotations
import multiprocessing
import os
from dataclasses import dataclass

CUT_POINTS = ("before_admission", "after_admission", "before_intent_append", "after_intent_append", "before_intent_reopen", "after_intent_reopen", "before_activity", "after_activity", "before_observation_append", "after_observation_append", "before_validation", "after_validation", "before_snapshot_replace", "after_snapshot_replace", "before_directory_fsync", "after_directory_fsync")

class FaultRefusal(ValueError): pass
@dataclass(frozen=True)
class CrashObservation: cut_id: str; reached: bool; exit_code: int

def crash_at(cut_id: str, timeout: float = 2.0) -> CrashObservation:
    if cut_id not in CUT_POINTS: raise FaultRefusal(f"unknown cut point: {cut_id}")
    receive, send = multiprocessing.Pipe(False)
    def child(): send.send(cut_id); send.close(); os._exit(97)
    process = multiprocessing.Process(target=child); process.start()
    reached = receive.poll(timeout) and receive.recv() == cut_id
    process.join(timeout)
    if process.is_alive(): process.kill(); process.join(timeout); raise RuntimeError("child process exceeded its time limit")
    return CrashObservation(cut_id, bool(reached), process.exitcode or 0)
