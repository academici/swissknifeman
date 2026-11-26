"""Path patterns as the write-scope fence reads them (planning §5.7; fence: adapters §3.5).

Port of legacy ``check.globs_overlap`` and ``parallel._bare``. The dialect itself lives in
``skm.kernel.path_globs`` because execution admission must judge overlaps exactly as planning validation does;
this module keeps planning's import path for it.
"""

from skm.kernel.path_globs import bare, covers, globs_overlap

__all__ = ["bare", "covers", "globs_overlap"]
