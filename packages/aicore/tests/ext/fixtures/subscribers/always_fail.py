"""Fail every attempt: a message on stderr and exit code 1."""
import sys

sys.stdin.read()
sys.stderr.write("boom\n")
sys.exit(1)
