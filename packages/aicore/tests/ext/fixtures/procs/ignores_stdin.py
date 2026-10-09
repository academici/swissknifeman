"""Close stdin without reading it and answer at once."""
import os
import sys

os.close(0)
print('{"ok": true}')
sys.stdout.flush()
