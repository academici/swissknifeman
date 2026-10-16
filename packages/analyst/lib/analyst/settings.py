"""analyst settings: the thresholds of the lesson state machine and of the recurrence rule.

Values come from ``aicore.config`` (schema ``configs/config.schema.json``: defaults, machine file,
project file, environment, ``--config``); without any file the defaults below apply. The model
parameters of analyst (priors, decay, tiers) are not settings and stay in the code.
"""
from dataclasses import dataclass
from pathlib import Path

from aicore.config import resolve

UNIT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Thresholds:
    """The nine user-tunable thresholds; the field defaults equal ``default`` in the config schema."""

    candidate_min_n: int = 15
    candidate_min_conf: float = 0.6
    curated_min_n: int = 50
    curated_min_conf: float = 0.8
    curated_min_passrate: float = 0.95
    deprecate_conf: float = 0.6
    candidate_min_n_floor: int = 3
    pathology_window: int = 5
    pathology_min_hits: int = 2


DEFAULT_THRESHOLDS = Thresholds()

_KEYS = {
    "candidate_min_n": "recompute.candidate_min_n",
    "candidate_min_conf": "recompute.candidate_min_conf",
    "curated_min_n": "recompute.curated_min_n",
    "curated_min_conf": "recompute.curated_min_conf",
    "curated_min_passrate": "recompute.curated_min_passrate",
    "deprecate_conf": "recompute.deprecate_conf",
    "candidate_min_n_floor": "recompute.candidate_min_n_floor",
    "pathology_window": "digest.pathology_window",
    "pathology_min_hits": "digest.pathology_min_hits",
}


def load_thresholds(project_path=None, *, config_file=None, env=None, home=None):
    """Resolve the thresholds for a project (``None``: machine, environment and ``config_file`` layers only).

    Raises :class:`aicore.config.ConfigError` (with file and line) when a layer is invalid.
    """
    config = resolve("analyst", unit_root=UNIT_ROOT, project=project_path, config_file=config_file,
                     env=env, home=home)
    fields = {field: config.get(key) for field, key in _KEYS.items()}
    return Thresholds(**fields)
