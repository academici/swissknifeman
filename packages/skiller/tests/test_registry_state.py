"""Kernel tests CLI: registry-generation, state (projects.json), doctor, status.

Racing against a synthetic registry (tests/fixtures) in temporary directories,
without network and subprocess. registry is tested via build_registry/
write_plugin_manifests/render_graph directly (cmd_registry calls write_graph
in-process, without subprocess — used to be separate shell-script)."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from aicore.delivery import MARKETPLACE
from skiller.registry import build_registry, write_plugin_manifests
from skiller.state import (db_records, load_db, save_db, upsert_project)
from skiller.doctor import cmd_doctor
from skiller.host import clear_host_cache
from skiller.status import cmd_status
from skiller.connect import do_connect
import tests.fixtures as fx


def _schema_prop(pytype, json_type):
    """Collect schema-property under Python-type from CONFIG_KEYS. Tuple of types
    (memory_brain = (str, dict)) → oneOf-members; single type → {"type": ...}."""
    if isinstance(pytype, tuple):
        return {"oneOf": [{"type": json_type[t]} for t in pytype]}
    return {"type": json_type[pytype]}


def capture(fn, *a, **kw):
    """Execute fn, return (result, stdout-text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*a, **kw)
    return result, buf.getvalue()


class RegistryBuildCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_build_registry_shape(self):
        reg, bucket_meta, bucket_dirs = build_registry(self.env)
        self.assertEqual(reg["version"], 5)
        self.assertEqual(reg["name"], "swissknifeman")
        names = {s["name"] for s in reg["skills"]}
        # 4 skill from fixtures (generate-skill lives outside skills/, does not go to the registry)
        self.assertEqual(
            names, {"laravel-conventions", "code-style", "test-writer", "docker"})
        # bucket counters
        self.assertEqual(reg["buckets"]["php"]["count"], 2)
        self.assertEqual(reg["buckets"]["devops"]["count"], 1)
        self.assertEqual(sorted(bucket_dirs), ["devops", "php", "quality"])

    def test_local_skill_has_source_local(self):
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        self.assertEqual(docker["source"], "local")
        self.assertNotIn("upstream", docker)

    def test_marketplace_emits_curated_core_plugin(self):
        # Smart connection: registry issues a supervised plugin `core` (source:"./" + skills[]
        # from existing CORE_SKILLS), loading EXACTLY these skills instead of whole buckets.
        from skiller.config import CORE_PLUGIN
        skills = self.root / "skills"
        fx.write_skill(skills / "general" / "context-economy", "context-economy")
        fx.write_skill(skills / "oss-dev" / "gh-review", "gh-review")
        bj = json.loads((self.root / "buckets.json").read_text())
        bj["general"] = {"description": "General", "category": "eng", "tags": []}
        bj["oss-dev"] = {"description": "OSS", "category": "eng", "tags": []}
        (self.root / "buckets.json").write_text(json.dumps(bj))
        _reg, meta, dirs = build_registry(self.env)
        write_plugin_manifests(self.env, meta, dirs)
        mp = json.loads(
            (self.root / ".claude-plugin" / "marketplace.json").read_text())
        core = next((p for p in mp["plugins"] if p["name"] == CORE_PLUGIN), None)
        self.assertIsNotNone(core, "marketplace must contain a curated core-plugin")
        self.assertEqual(core["source"], "./")
        self.assertIn("./skills/general/context-economy", core["skills"])
        self.assertEqual(core["skills"], ["./skills/general/context-economy"])
        self.assertNotIn("./skills/oss-dev/gh-review", core["skills"])
        self.assertTrue(any(plugin["name"] == "oss-dev" for plugin in mp["plugins"]))
        # supervised core does not have a plugin directory on disk (links, not copies)
        self.assertFalse((skills / CORE_PLUGIN).exists())

    def test_upstream_skill_carries_provenance(self):
        fx.write_upstream(self.root / "skills" / "devops" / "docker",
                          source="github",
                          url="https://raw.example/SKILL.md",
                          fetched_at="2026-02-02")
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        self.assertEqual(docker["source"], "github")
        self.assertEqual(docker["upstream"], "https://raw.example/SKILL.md")
        self.assertEqual(docker["fetched_at"], "2026-02-02")

    def test_fork_skill_provenance_via_non_skill_path(self):
        # fork: files[].path points to the mirror (references/source.md), and not on
        # SKILL.md → registry should take provenance from files[0] (fallback).
        fx.write_upstream(self.root / "skills" / "devops" / "docker",
                          source="github", strategy="fork",
                          path="references/source.md",
                          url="https://raw.example/SKILL.md",
                          fetched_at="2026-03-03")
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        self.assertEqual(docker["source"], "github")
        self.assertEqual(docker["upstream"], "https://raw.example/SKILL.md")
        self.assertEqual(docker["fetched_at"], "2026-03-03")

    def test_body_path_provenance_preferred_over_skill_md_entry(self):
        # P7.3 thin-navigator: body_path explicitly calls files[]-recording with real
        # upstream body - registry should take provenance from HER, not from the first one
        # found entry with path=="SKILL.md" (even if this is for some reason
        # is also tracked) and not from files[0] (order in files[] shouldn't solve).
        fx.write_upstream(
            self.root / "skills" / "devops" / "docker",
            source="github", strategy="notify",
            path="SKILL.md", url="https://raw.example/SKILL.md", sha256="stale",
            fetched_at="2026-01-01",
            body_path="references/full.md",
            extra_files=[{"path": "references/full.md",
                         "url": "https://raw.example/references/full.md",
                         "sha256": "fresh", "fetched_at": "2026-07-01"}])
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        self.assertEqual(docker["source"], "github")
        self.assertEqual(docker["upstream"], "https://raw.example/references/full.md")
        self.assertEqual(docker["fetched_at"], "2026-07-01")

    def test_broken_upstream_json_dies_with_path(self):
        # Broken upstream.json → clear error with the path, not naked traceback
        # halfway through generation and not a silent failure in source="local".
        skill_dir = self.root / "skills" / "devops" / "docker"
        (skill_dir / "upstream.json").write_text("{ this is not json",
                                                 encoding="utf-8")
        with self.assertRaises(SystemExit):
            build_registry(self.env)

    def test_requires_only_when_present(self):
        reg, *_ = build_registry(self.env)
        conv = next(s for s in reg["skills"] if s["name"] == "laravel-conventions")
        style = next(s for s in reg["skills"] if s["name"] == "code-style")
        self.assertEqual(conv["requires"], ["code-style"])
        # for a skill without requires field is missing, not an empty list
        self.assertNotIn("requires", style)

    def test_level_only_when_present(self):
        # opt. field level: is written in skills.json if available, otherwise there is no key
        (self.root / "skills" / "devops" / "docker" / "SKILL.md").write_text(
            "---\nname: docker\nversion: 0.1.0\ndescription: Docker\n"
            "level: foundation\n---\n\nBody.\n", encoding="utf-8")
        reg, *_ = build_registry(self.env)
        docker = next(s for s in reg["skills"] if s["name"] == "docker")
        style = next(s for s in reg["skills"] if s["name"] == "code-style")
        self.assertEqual(docker["level"], "foundation")
        self.assertNotIn("level", style)  # omit-when-empty

    def test_content_sha256_covers_whole_dir(self):
        # content_sha256 wider sha256 (by SKILL.md): catches edits snippets/references
        docker = self.root / "skills" / "devops" / "docker"
        reg1, *_ = build_registry(self.env)
        e1 = next(s for s in reg1["skills"] if s["name"] == "docker")
        self.assertTrue(e1["content_sha256"])
        self.assertNotEqual(e1["content_sha256"], e1["sha256"])  # different coverage
        # edit ONLY snippet (SKILL.md do not touch)
        (docker / "snippets").mkdir(exist_ok=True)
        (docker / "snippets" / "ex.md").write_text("v1", encoding="utf-8")
        reg2, *_ = build_registry(self.env)
        e2 = next(s for s in reg2["skills"] if s["name"] == "docker")
        self.assertEqual(e2["sha256"], e1["sha256"])  # SKILL.md did not change
        self.assertNotEqual(e2["content_sha256"], e1["content_sha256"])  # dir other

    def test_content_sha256_ignores_ru_alternate(self):
        # SKILL.ru.md (language alternative) is not included content_sha256
        docker = self.root / "skills" / "devops" / "docker"
        e1 = next(s for s in build_registry(self.env)[0]["skills"]
                  if s["name"] == "docker")
        (docker / "SKILL.ru.md").write_text("full Russian source\n",
                                            encoding="utf-8")
        e2 = next(s for s in build_registry(self.env)[0]["skills"]
                  if s["name"] == "docker")
        self.assertEqual(e2["content_sha256"], e1["content_sha256"])

    def test_missing_buckets_json_dies(self):
        (self.root / "buckets.json").unlink()
        with self.assertRaises(SystemExit):
            build_registry(self.env)

    def test_write_plugin_manifests(self):
        _, bucket_meta, bucket_dirs = build_registry(self.env)
        n = write_plugin_manifests(self.env, bucket_meta, bucket_dirs)
        # 3 bucket + generate-skill
        self.assertEqual(n, 4)
        # per-bucket manifest
        php_plugin = json.loads(
            (self.root / "skills" / "php" / ".claude-plugin" / "plugin.json")
            .read_text())
        self.assertEqual(php_plugin["name"], "php")
        # root marketplace
        mk = json.loads(
            (self.root / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(mk["name"], MARKETPLACE)
        plugin_names = {p["name"] for p in mk["plugins"]}
        self.assertIn("generate-skill", plugin_names)
        self.assertIn("php", plugin_names)


class StateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_db_default_when_absent(self):
        self.assertFalse(self.env.db_file.exists())
        db = load_db(self.env)
        self.assertEqual(db["projects"], [])
        self.assertIn("version", db)

    def test_upsert_insert_then_update_preserves_first_connected(self):
        upsert_project(self.env, {"path": "/p", "channel": "vendor",
                                  "buckets": ["php"]})
        rec1 = load_db(self.env)["projects"][0]
        first = rec1["first_connected_at"]
        self.assertEqual(rec1["buckets"], ["php"])
        # update the same (path, channel) — first_connected_at is saved
        upsert_project(self.env, {"path": "/p", "channel": "vendor",
                                  "buckets": ["php", "devops"]})
        db = load_db(self.env)
        self.assertEqual(len(db["projects"]), 1)
        rec2 = db["projects"][0]
        self.assertEqual(rec2["buckets"], ["php", "devops"])
        self.assertEqual(rec2["first_connected_at"], first)

    def test_upsert_distinct_channels_coexist(self):
        upsert_project(self.env, {"path": "/p", "channel": "vendor"})
        upsert_project(self.env, {"path": "/p", "channel": "marketplace"})
        recs = db_records(self.env, "/p")
        self.assertEqual({r["channel"] for r in recs}, {"vendor", "marketplace"})

    def test_upsert_normalizes_path_dedupes(self):
        # different repr one way (./, ..) → one entry (normalization resolve())
        upsert_project(self.env, {"path": "/p", "channel": "vendor"})
        upsert_project(self.env, {"path": "/p/.", "channel": "vendor"})
        db = load_db(self.env)
        self.assertEqual(len(db["projects"]), 1)
        self.assertEqual(db["projects"][0]["path"], "/p")
        # lookup also normalizes - finds the record by «dirty» repr
        self.assertEqual(len(db_records(self.env, "/p/.")), 1)

    def test_save_load_round_trip_no_tmp_left(self):
        save_db(self.env, {"version": 1, "projects": [{"path": "/x",
                                                       "channel": "vendor"}]})
        self.assertEqual(load_db(self.env)["projects"][0]["path"], "/x")
        # atomic write leaves no temporary file
        leftovers = list(self.env.state_dir.glob("*.tmp"))
        self.assertEqual(leftovers, [])


class DoctorCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_doctor_runs_and_reports(self):
        # doctor may return code 1 (no symlink/not git-repo in tmp) — is normal;
        # important that it does not crash with an exception and prints diagnostics.
        try:
            _, out = capture(cmd_doctor, self.env, [])
        except SystemExit:
            # issues>0 -> sys.exit(1); intercept the output again without exit-sensitivity
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with contextlib.suppress(SystemExit):
                    cmd_doctor(self.env, [])
            out = buf.getvalue()
        self.assertIn("skiller doctor", out)
        self.assertIn("python3", out)
        self.assertIn("profiles are loading", out)
        # Doc-1: the environment command is not installed in the synthetic tmp-registry
        # (empty host) — an optional dependency and should NOT be considered FAIL.
        self.assertIn("environment command not configured - optional", out)
        self.assertNotIn("FAIL] environment", out)

    def test_doctor_help(self):
        _, out = capture(cmd_doctor, self.env, ["--help"])
        self.assertIn("skiller doctor", out)

    def test_doctor_flags_broken_environment_command_not_missing(self):
        """Doc-1: environment command INSTALLED (host `environment_doctor`, env override
        points to an executable file), but BROKEN (non-zero exit) — doctor should
        distinguish this from «not installed» and report FAIL, and not silent 'ok'. The
        only file test, really calling subprocess (the essence of the check cannot be
        verified otherwise)."""
        broken = self.tmp / "broken-env-tool.sh"
        broken.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
        broken.chmod(0o755)
        host = self.tmp / "host.json"
        host.write_text(json.dumps({"schema_version": 1, "commands": {"environment_doctor": {
            "argv": ["env-tool", "--help"], "env_override": "SKM_ENV_TOOL_BIN"}}}),
            encoding="utf-8")
        clear_host_cache()
        self.addCleanup(clear_host_cache)
        saved = {k: os.environ.get(k) for k in ("SKM_ENV_TOOL_BIN", "SKILLER_HOST_CONFIG")}
        os.environ["SKM_ENV_TOOL_BIN"] = str(broken)
        os.environ["SKILLER_HOST_CONFIG"] = str(host)
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with contextlib.suppress(SystemExit):
                    cmd_doctor(self.env, [])
            out = buf.getvalue()
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertIn("FAIL] environment command is being executed", out)
        self.assertNotIn("not configured", out)

    def test_doctor_flags_schema_type_mismatch_not_just_key_names(self):
        """Doc-2: before doctor checked ONLY the schema key names (⇄ keys) — when
        property TYPE discrepancy (e.g. schema says array, CONFIG_KEYS — str)
        printed false "OK". Diagram below: names 1:1 with CONFIG_KEYS, but
        'project_type' type 'array' instead of expected 'string'."""
        from skiller.common import CONFIG_KEYS
        json_type = {str: "string", list: "array", int: "integer",
                    dict: "object", bool: "boolean"}
        props = {k: _schema_prop(t, json_type) for k, t in CONFIG_KEYS.items()}
        props["project_type"]["type"] = "array"  # intentional discrepancy
        schema_dir = self.root / "schema"
        schema_dir.mkdir(parents=True, exist_ok=True)
        (schema_dir / "swissknife.schema.json").write_text(
            json.dumps({"properties": props}), encoding="utf-8")
        # second diagram (SKILLSET_KEYS) — the doctor reads it too, put it as valid
        from skiller.skillset import SKILLSET_KEYS
        props2 = {k: _schema_prop(t, json_type) for k, t in SKILLSET_KEYS.items()}
        (schema_dir / "swissknifeman-config.schema.json").write_text(
            json.dumps({"properties": props2}), encoding="utf-8")

        buf = io.StringIO()
        with contextlib.suppress(SystemExit):
            with contextlib.redirect_stdout(buf):
                cmd_doctor(self.env, [])
        out = buf.getvalue()
        self.assertIn("⇄ keys .swissknife.json", out)   # names matched - OK
        self.assertIn("FAIL] diagram swissknife.schema.json ⇄ types", out)
        self.assertIn("project_type", out)


def _run_doctor(env, argv):
    """doctor may sys.exit(1) on synthetic tmp-registry (no symlink/git) — this
    normal (see test_doctor_runs_and_reports); catch to read the output."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        with contextlib.suppress(SystemExit):
            cmd_doctor(env, argv)
    return buf.getvalue()


class VendorDriftCase(unittest.TestCase):
    """doctor --vendor-drift: drift managed-skills registered vendor-projects
    from the current registry (dry plan_sync — see doctor._vendor_drift)."""
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        reg, *_ = build_registry(self.env)
        (self.root / "skills.json").write_text(
            json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _register_vendor_project(self, buckets):
        proj = self.tmp / "proj"
        proj.mkdir(parents=True, exist_ok=True)
        cfg_dir = proj / ".swissknifeman"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "config.json").write_text(
            json.dumps({"mode": "vendor", "buckets": buckets}), encoding="utf-8")
        upsert_project(self.env, {"path": str(proj), "channel": "vendor"})
        return proj

    def test_summary_ok_when_no_vendor_projects(self):
        out = _run_doctor(self.env, [])
        self.assertIn("vendor-skills: no drift from the registry", out)

    def test_non_green_plan_states_are_never_ignored(self):
        from skiller.doctor import _vendor_plan_has_drift
        for field, value in (
                ("managed_drift", ["test-writer"]),
                ("provenance_invalid", "bad-lock"),
                ("relocated", {"test-writer": ".claude/skills/test-writer"}),
                ("errors", ["planning failed"])):
            with self.subTest(field=field):
                self.assertTrue(_vendor_plan_has_drift({field: value}))

    def test_summary_warns_when_project_behind(self):
        self._register_vendor_project(["quality"])
        out = _run_doctor(self.env, [])
        self.assertIn("vendor-skills: 1 project(ov) behind the registry", out)

    def test_detail_flag_reports_missing_skill(self):
        self._register_vendor_project(["quality"])
        out = _run_doctor(self.env, ["--vendor-drift"])
        self.assertIn("proj: +1 new", out)

    def test_detail_flag_clean_after_sync(self):
        from skiller.skillset import load_skillset_config, sync_skillset
        proj = self._register_vendor_project(["quality"])
        cfg = load_skillset_config(proj)
        sync_skillset(self.env, proj, cfg)
        out = _run_doctor(self.env, ["--vendor-drift"])
        self.assertIn("(all vendor-projects are synchronized with the registry)", out)

    def test_detail_flag_reports_managed_drift(self):
        from skiller.skillset import load_skillset_config, sync_skillset
        proj = self._register_vendor_project(["quality"])
        cfg = load_skillset_config(proj)
        sync_skillset(self.env, proj, cfg)
        installed = proj / ".claude/skills/test-writer/SKILL.md"
        installed.write_text(installed.read_text(encoding="utf-8") + "\nlocal edit\n",
                             encoding="utf-8")

        out = _run_doctor(self.env, ["--vendor-drift"])

        self.assertIn("proj: !1 managed drift", out)

    def test_detail_flag_checks_each_enabled_vendor_provider(self):
        from skiller.skillset import load_skillset_config, sync_skillset
        proj = self._register_vendor_project(["quality"])
        (proj / ".swissknife.json").write_text(json.dumps({
            "providers": {"contract_version": "1.0.0", "selection": {
                "claude-code": {"enabled": True},
                "codex": {"enabled": True},
            }},
        }), encoding="utf-8")
        cfg = load_skillset_config(proj)
        sync_skillset(self.env, proj, cfg, provider="claude-code")
        codex_cfg = {**cfg, "skills_path": ".agents/skills", "agent": "codex"}
        sync_skillset(self.env, proj, codex_cfg, provider="codex")
        installed = proj / ".agents/skills/test-writer/SKILL.md"
        installed.write_text(installed.read_text(encoding="utf-8") + "\nlocal edit\n",
                             encoding="utf-8")

        out = _run_doctor(self.env, ["--vendor-drift"])

        self.assertIn("proj [codex]: !1 managed drift", out)

    def test_connect_only_project_ignored(self):
        # project without .swissknifeman/config.json (only connect) — does not participate in drift
        proj = self.tmp / "connectonly"
        proj.mkdir(parents=True, exist_ok=True)
        upsert_project(self.env, {"path": str(proj), "channel": "connect"})
        out = _run_doctor(self.env, [])
        self.assertIn("vendor-skills: no drift from the registry", out)


class StatusCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_status_on_connected_project(self):
        proj = fx.make_laravel_project(self.tmp)
        do_connect(self.env, proj, {})
        _, out = capture(cmd_status, self.env, ["--target", str(proj)])
        self.assertIn(str(proj), out)
        self.assertIn("marketplace", out)
        self.assertIn("Profile", out)

    def test_status_on_unconnected_project(self):
        proj = fx.make_laravel_project(self.tmp)
        _, out = capture(cmd_status, self.env, ["--target", str(proj)])
        self.assertIn("not connected", out)


class DownstreamAuditCase(unittest.TestCase):
    """skiller doctor --downstream: hygiene publish-surface onboarded projects."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_project(self, name, *, claude_lines, scoped, unscoped, deny):
        pdir = self.tmp / name
        (pdir / ".claude" / "rules").mkdir(parents=True, exist_ok=True)
        (pdir / "CLAUDE.md").write_text(
            "\n".join(f"line {i}" for i in range(claude_lines)), encoding="utf-8")
        for i in range(scoped):
            (pdir / ".claude" / "rules" / f"s{i}.md").write_text(
                '---\npaths:\n  - "app/**"\n---\nscoped rule\n', encoding="utf-8")
        for i in range(unscoped):
            (pdir / ".claude" / "rules" / f"u{i}.md").write_text(
                "unscoped rule, no frontmatter\n", encoding="utf-8")
        perms = {"deny": ["Read(storage/logs/**)"]} if deny else {}
        (pdir / ".claude" / "settings.json").write_text(
            json.dumps({"permissions": perms}), encoding="utf-8")
        return pdir

    def test_audit_flags_oversize_unscoped_and_missing_deny(self):
        big = self._make_project("bigproj", claude_lines=300, scoped=1,
                                  unscoped=2, deny=False)
        lean = self._make_project("leanproj", claude_lines=50, scoped=2,
                                   unscoped=0, deny=True)
        save_db(self.env, {"projects": [
            {"id": "bigproj", "path": str(big)},
            {"id": "leanproj", "path": str(lean)},
        ]})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with contextlib.suppress(SystemExit):
                cmd_doctor(self.env, ["--downstream"])
        out = buf.getvalue()
        self.assertIn("Downstream publish-surface", out)
        # over-budget project flagged on all three axes
        self.assertIn("CLAUDE.md 300>200", out)
        self.assertIn("2 unscoped-rules", out)
        self.assertIn("no deny", out)
        # lean project is clean
        self.assertRegex(out, r"\[ok \] leanproj:")


if __name__ == "__main__":
    unittest.main()
