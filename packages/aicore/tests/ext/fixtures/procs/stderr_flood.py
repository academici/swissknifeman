"""Write about a megabyte to stderr, then a closing marker, and answer with an empty object."""
import sys

line = ("flood-" * 16 + "\n").encode()
for _ in range(11000):
    sys.stderr.buffer.write(line)
sys.stderr.buffer.write(b"END-OF-STDERR\n")
sys.stderr.flush()
print("{}")
