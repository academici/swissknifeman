"""Start a background grandchild `sleep 60` that keeps stdout open, record its pid in argv[1], and exit."""
import subprocess
import sys

grandchild = subprocess.Popen(["sleep", "60"])
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    handle.write(f"{grandchild.pid}\n")
print("{}")
sys.stdout.flush()
