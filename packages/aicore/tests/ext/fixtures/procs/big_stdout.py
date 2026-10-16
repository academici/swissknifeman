"""Write far more than the stdout limit; argv[1] is the size in bytes."""
import sys

size = int(sys.argv[1])
chunk = "x" * 65536
written = 0
try:
    while written < size:
        sys.stdout.write(chunk)
        written += len(chunk)
    sys.stdout.flush()
except BrokenPipeError:
    pass
