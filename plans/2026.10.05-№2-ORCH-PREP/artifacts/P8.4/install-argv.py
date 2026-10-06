"""Record install.sh argv (fake codex/grok) for monorepo scenarios; stdout to a log."""
import os, subprocess, sys, tempfile
from pathlib import Path

MONO = Path(sys.argv[1]).resolve()
INSTALLER = MONO / "packages/skiller/install.sh"
SCEN = [
    ("default", [], {}),
    ("no-codex", ["--no-codex-plugins"], {}),
    ("no-grok", ["--no-grok-plugins"], {}),
    ("explicit-ai", ["--no-codex-plugins", "--codex-plugin", "ai"], {}),
    ("extra-ai", ["--codex-plugin", "ai"], {}),
    ("grok-already", ["--no-codex-plugins"], {"GROK_STUB_FAIL": "1"}),
]
out = []
for name, args, extra in SCEN:
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); fb = root / "fb"; fb.mkdir(); (root / "home").mkdir()
        (fb / "codex").write_text('#!/usr/bin/env bash\nprintf "codex %s\\n" "$*" >> "$STUB_LOG"\n'); (fb / "codex").chmod(0o755)
        (fb / "grok").write_text('#!/usr/bin/env bash\nprintf "grok %s\\n" "$*" >> "$STUB_LOG"\n'
            'if [[ "${GROK_STUB_FAIL:-}" == 1 ]]; then echo "Error: already installed" >&2; exit 1; fi\n'); (fb / "grok").chmod(0o755)
        env = {k: v for k, v in os.environ.items() if k != "SKILLER_HOST_CONFIG"}
        env.update(HOME=str(root / "home"), PATH=f"{fb}:{env['PATH']}", STUB_LOG=str(root / "log"), **extra)
        r = subprocess.run(["bash", str(INSTALLER), "--bin-dir", str(root / "bin"), *args], cwd=MONO,
                           env=env, capture_output=True, text=True)
        log = (root / "log").read_text() if (root / "log").exists() else ""
        norm = lambda s: s.replace(str(root), "<TMP>").replace(str(MONO), "<ROOT>")
        out.append(f"## {name} rc={r.returncode}")
        out += ["argv: " + l for l in norm(log).splitlines()]
        out += ["stdout: " + l for l in norm(r.stdout).splitlines()]
print("\n".join(out))
