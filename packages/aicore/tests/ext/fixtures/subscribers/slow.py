"""Take argv[1] seconds (longer than the deadline of the test) before answering."""
import sys
import time

sys.stdin.read()
time.sleep(float(sys.argv[1]))
