"""Close stdout and stderr, then keep running."""
import os
import time

os.close(1)
os.close(2)
time.sleep(60)
