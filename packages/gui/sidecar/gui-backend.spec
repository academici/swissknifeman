# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir spec of the desktop sidecar `gui-backend` (decisions D9, D28). Paths are relative to this file.
# Build with `bash sidecar/build.sh`; the locked third-party packages must be installed (`gui deps ensure`).
import os
import sys

SPEC_DIR = os.path.abspath(SPECPATH)  # noqa: F821 - provided by PyInstaller
MODULE = os.path.dirname(SPEC_DIR)
AICORE = os.environ.get("AICORE_ROOT") or os.path.join(os.path.dirname(MODULE), "aicore")

sys.path[:0] = [os.path.join(MODULE, "lib"), os.path.join(AICORE, "lib")]
from gui import deps  # noqa: E402

SITE = str(deps.site_dir())  # the locked packages: starlette, uvicorn, wsproto, anyio, ...

# gui and aicore compute their data folders from their own file (lib/<pkg>/../..), which a frozen PYZ module cannot
# satisfy. Both therefore travel as source trees in the layout of the repository under src/ and entry.py puts their
# lib/ folders on sys.path; only the third-party packages and the standard library come from the frozen archive.
# UNVERIFIED on this machine (no PyInstaller, decision D26): the first build of the owner confirms the layout.
datas = [
    (os.path.join(MODULE, "lib", "gui"), "src/gui/lib/gui"),
    (os.path.join(MODULE, "schemas"), "src/gui/schemas"),
    (os.path.join(MODULE, "configs"), "src/gui/configs"),
    (os.path.join(MODULE, "unit.json"), "src/gui"),
    (os.path.join(MODULE, "requirements.lock"), "src/gui"),
    (os.path.join(AICORE, "lib", "aicore"), "src/aicore/lib/aicore"),
    (os.path.join(AICORE, "schemas"), "src/aicore/schemas"),
    (os.path.join(AICORE, "configs"), "src/aicore/configs"),
    (os.path.join(AICORE, "unit.json"), "src/aicore"),
]

hiddenimports = [
    "uvicorn", "uvicorn.config", "uvicorn.main", "uvicorn.server", "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    "uvicorn.loops.asyncio", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto", "uvicorn.protocols.websockets.wsproto_impl",
    "wsproto", "wsproto.extensions", "starlette", "starlette.routing", "starlette.responses", "starlette.testclient",
    "anyio", "anyio._backends._asyncio", "sniffio",
    # imported lazily inside functions of gui and aicore
    "sqlite3", "fcntl", "http.cookies", "webbrowser", "logging.config",
]

a = Analysis(  # noqa: F821
    [os.path.join(SPEC_DIR, "entry.py")],
    pathex=[os.path.join(MODULE, "lib"), os.path.join(AICORE, "lib"), SITE],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
# Analysis followed the imports of gui and aicore (their third-party and stdlib needs); the modules themselves are
# data under src/, not archive members.
a.pure[:] = [entry for entry in a.pure if entry[0].split(".")[0] not in ("gui", "aicore")]
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="gui-backend",
    debug=False,
    strip=False,
    upx=False,
    console=True,  # stdin/stdout/stderr carry the sidecar protocol
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="gui-backend")  # noqa: F821
