"""Bounded new-file content for review; never follow an untracked symlink into host files."""
import json
import os
from pathlib import Path
import stat


def new_files(project: Path, names: list, limit: int) -> str:
    parts, remaining = [], max(0, limit)
    for name in names:
        if remaining <= 0:
            parts.append("\n# … new-file diff cut; read the remaining candidate files\n")
            break
        path = project / name
        shown = json.dumps(name, ensure_ascii=False)
        header = f"\ndiff --git {shown} {shown}\nnew file\n--- /dev/null\n+++ {shown}\n"
        try:
            # git lists symlinks as files: show their targets, not the contents they point to.
            if path.is_symlink():
                data = os.readlink(path).encode("utf-8", "surrogateescape")
            else:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise OSError("not a regular file")
                    data = stream.read(remaining + 1)
            if b"\0" in data:
                body = "# binary content omitted; inspect the candidate file\n"
            else:
                decoded = data.decode("utf-8", "strict")
                body = "@@ new file @@\n" + "".join("+" + line + "\n" for line in decoded.splitlines())
                if decoded and not decoded.endswith("\n"):
                    body += "\\ No newline at end of file\n"
                if len(data) > remaining:
                    body += "# … new-file content cut; read the file for the rest\n"
        except (OSError, UnicodeError):
            body = "# content unavailable as text; inspect the candidate file\n"
        block = header + body
        if len(block) > remaining:
            block = block[:remaining] + "\n# … new-file diff cut; read the files for the rest\n"
        parts.append(block)
        remaining -= len(block)
    return "".join(parts)


def diff(project: Path, base: str, limit: int = 200_000, paths: list | None = None, *, git, untracked) -> str:
    """The diff of the working tree against ``base``, plus the untracked files; cut at ``limit`` characters. ``paths``
    (names relative to the project) limits both to those paths and what lies under them; no path gives no diff."""
    if paths is None:
        text = git(project, "diff", base)
        extra = untracked(project)
    elif not paths:
        return ""
    else:
        text = git(project, "diff", base, "--", *[f":(literal){name}" for name in paths])
        extra = [name for name in untracked(project) if any(name == folder or name.startswith(folder.rstrip("/") + "/") for folder in paths)]
    if extra:
        text += new_files(project, extra, max(0, limit - len(text)))
    if len(text) > limit:
        text = text[:limit] + f"\n# … diff cut at {limit} characters; read the files for the rest\n"
    return text

