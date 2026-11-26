"""Start a grandchild `sleep 60` in the same group, record its pid in argv[1], then sleep."""
import subprocess
import sys
import time

grandchild = subprocess.Popen(["sleep", "60"])
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    handle.write(f"{grandchild.pid}\n")
time.sleep(60)
