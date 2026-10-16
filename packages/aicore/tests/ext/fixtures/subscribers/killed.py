"""Die by SIGKILL while handling the event: no answer, no exit code."""
import os
import signal
import sys

sys.stdin.read()
os.kill(os.getpid(), signal.SIGKILL)
