"""Entry point of the frozen backend ``gui-backend`` (PyInstaller) and of ``python3 sidecar/entry.py`` in development.

The desktop shell starts it without arguments and writes the handshake line to its stdin (decision D28); it is the
same as ``gui serve --sidecar``. The secret never comes through argv or the environment.
"""
import os
import sys

if getattr(sys, "frozen", False):  # gui-backend.spec ships both source trees under src/ in the repository layout
    for _path in ("src/aicore/lib", "src/gui/lib"):
        sys.path.insert(0, os.path.join(sys._MEIPASS, _path))  # type: ignore[attr-defined]
else:  # development: the sources of this checkout and of the foundation
    _MODULE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _AICORE = os.environ.get("AICORE_ROOT") or os.path.join(os.path.dirname(os.path.dirname(_MODULE)), "aicore")
    for _path in (os.path.join(_AICORE, "lib"), os.path.join(_MODULE, "lib")):
        if _path not in sys.path:
            sys.path.insert(0, _path)

from gui.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["serve", "--sidecar", *sys.argv[1:]]))
