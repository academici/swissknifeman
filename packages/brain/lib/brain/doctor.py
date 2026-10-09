"""brain doctor: check-result/v1 documents about the vault, the configuration and the notes folder."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from aicore.config import ConfigError

from . import errors, settings as _settings, vault as _vault

RESULT_SCHEMA = "urn:swissknifeman:aicore:check-result:v1"
SET_REMEDIATION = _vault.SET_HINT


def _result(check_id: str, status: str, observed: str, *, evidence: Optional[List[str]] = None,
            remediation: Optional[str] = None, category: str = "config") -> Dict[str, Any]:
    doc: Dict[str, Any] = {"$schema": RESULT_SCHEMA, "check_id": check_id, "status": status,
                           "category": category, "observed": observed}
    if evidence:
        doc["evidence"] = evidence
    if remediation:
        doc["remediation"] = remediation
    return doc


def _vault_check(config: _settings.BrainSettings, env: Mapping[str, str], home: Optional[Path]) -> Dict[str, Any]:
    info = _vault.resolve_vault(config, env=env, home=home)
    if info.path is None:
        return _result("brain.vault", "warn", "no vault is configured on this machine",
                       remediation=SET_REMEDIATION)
    evidence = [f"path: {info.path}", f"source: {info.source}"]  # warnings belong to brain.config
    if not info.exists:
        return _result("brain.vault", "fail", f"vault directory {info.path} does not exist", evidence=evidence,
                       remediation=f"Create the directory or point brain.vault_path elsewhere: {SET_REMEDIATION}")
    if not info.obsidian:
        return _result("brain.vault", "warn", f"vault {info.path} has no .obsidian folder", evidence=evidence,
                       remediation="Open the directory once in Obsidian, or set brain.vault_path to the real vault.")
    return _result("brain.vault", "ok", f"vault {info.path}", evidence=evidence)


def run_checks(project: Optional[Path] = None, *, env: Optional[Mapping[str, str]] = None,
               home: Optional[Path] = None, config_file: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The doctor checks as ``check-result/v1`` documents: ``brain.vault``, ``brain.config``, ``brain.notes-folder``.

    A machine without a vault is normal, so a missing vault is a warning. A configuration that cannot be
    loaded fails ``brain.config`` (or ``brain.notes-folder`` when that is the cause) and skips the others.
    """
    environment = os.environ if env is None else env
    try:
        config = _settings.load(project, env=environment, home=home, config_file=config_file)
    except ConfigError as exc:
        reason = f"configuration is invalid: {exc}"
        if exc.code == errors.CONFIG_NOTES_FOLDER:
            return [_result("brain.vault", "skip", "configuration is invalid, the vault was not looked up"),
                    _result("brain.config", "ok", "configuration loads apart from notes.folder"),
                    _result("brain.notes-folder", "fail", reason,
                            remediation="Set notes.folder to a folder outside docs, docs-public and plans.")]
        return [_result("brain.vault", "skip", "configuration is invalid, the vault was not looked up"),
                _result("brain.config", "fail", reason, evidence=[exc.code],
                        remediation="Fix the named layer file or run: aicore config explain brain"),
                _result("brain.notes-folder", "skip", "configuration is invalid")]
    info = _vault.resolve_vault(config, env=environment, home=home)
    notices = list(dict.fromkeys(list(config.warnings) + list(info.warnings)))
    if notices:
        config_check = _result("brain.config", "warn", "configuration has warnings (deprecated sources or ignored settings)",
                               evidence=notices,
                               remediation="Move deprecated values into the brain configuration "
                                           "(aicore config set brain.vault_path <dir> --machine) and fix ignored settings.")
    else:
        config_check = _result("brain.config", "ok", "configuration loads and uses no deprecated sources")
    notes_check = _result("brain.notes-folder", "ok",
                          f"notes folder {config.notes_folder!r} is outside the synchronized folders")
    return [_vault_check(config, environment, home), config_check, notes_check]
