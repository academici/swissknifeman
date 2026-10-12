"""Tests package. Machine state follows SKM_HOME and the XDG variables over a test Env's home;
drop them so every test's temporary home owns its registry (a sandbox exports SKM_HOME)."""
import os

for _name in ("SKM_HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
    os.environ.pop(_name, None)
