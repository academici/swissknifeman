"""Host-provided buckets: skills carried by host module plugins (connect, vendor, sync, budget,
status, doctor, registry) on a synthetic host with neutral module names."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore.content.budget import skill_budget
from skiller.budget import resolve_active_set
from skiller.common import Env
from skiller.config import all_buckets, library_buckets, selectable_buckets
from skiller.connect import do_connect, prepare_connect_selection
from skiller.host import clear_host_cache, load_host
from skiller.module_skills import (
    check_collisions, expand_bucket, host_bucket_plugins, host_provided_buckets, module_skills,
    module_skill_sources, registry_entries, reset_warnings)
from skiller.registry import build_registry, render_index
from skiller.skillset import do_sync, resolve_skillset
from skiller.status import channel_overlap, registry_skill_names
from skiller.vendor import build_requires_index, collect_skills, do_vendor, resolve_requires
from aicore.delivery.materialize import load_lock

from tests.fixtures import make_registry, write_skill

MARKETPLACE = "swissknifeman"


def _json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")


class HostCase(unittest.TestCase):
    """A host repository: the library as a package folder, plugins mod-a and mod-b, bucket
    `env-skills` provided by the host and mapped to both plugins."""

    ALIASES = {"env-skills": ["mod-a", "mod-b"]}

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        (self.repo / ".git").mkdir()
        registry_root, _ = make_registry(self.repo)
        self.root = self.repo / "packages" / "skiller"
        self.root.parent.mkdir()
        registry_root.rename(self.root)
        self.home = self.repo / "home"
        self.env = Env(self.root, home=self.home)
        patch = mock.patch.dict(os.environ, {}, clear=False)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("SKILLER_HOST_CONFIG", None)
        clear_host_cache()
        reset_warnings()
        self.addCleanup(clear_host_cache)
        self.addCleanup(reset_warnings)

        write_skill(self.root / "skills" / "lib-a" / "sk-lib", "sk-lib")
        meta = json.loads((self.root / "buckets.json").read_text(encoding="utf-8"))
        meta["lib-a"] = {"description": "Library A", "category": "engineering", "tags": ["a"]}
        meta["env-skills"] = {"description": "Provided by the host", "category": "meta",
                              "tags": ["env"], "provided_by": "host"}
        _json(self.root / "buckets.json", meta)
        _json(self.root / "profiles" / "p1.json",
              {"name": "p1", "description": "P1", "buckets": ["env-skills", "lib-a"],
               "include_meta": False})
        self.module("mod-a", {"sk-a": ["sk-b"]})
        self.module("mod-b", {"sk-b": []})
        self.host(self.ALIASES)
        self.marketplace(["mod-a", "mod-b", "lib-a"])

    def module(self, name, skills, *, manifest=None):
        package = self.repo / "packages" / name
        _json(package / ".claude-plugin" / "plugin.json",
              manifest or {"name": name, "description": name, "skills": ["./skills"]})
        for skill, requires in skills.items():
            write_skill(package / "skills" / skill, skill, requires=requires,
                        description=f"{skill} description")
        return package

    def host(self, aliases=None, *, plugin_dirs=("packages/*",)):
        data = {"schema_version": 1, "plugin_dirs": list(plugin_dirs)}
        if aliases is not None:
            data["bucket_aliases"] = aliases
        _json(self.repo / "configs" / "skiller-host.json", data)
        clear_host_cache()

    def marketplace(self, names):
        _json(self.repo / ".claude-plugin" / "marketplace.json",
              {"name": MARKETPLACE, "plugins": [{"name": n, "source": f"./{n}"} for n in names]})

    def project(self, name="proj"):
        proj = self.repo / name
        proj.mkdir(exist_ok=True)
        (proj / ".git").mkdir(exist_ok=True)
        return proj

    def settings(self, proj):
        return json.loads((proj / ".claude" / "settings.local.json").read_text(encoding="utf-8"))

    def run_quiet(self, fn, *args, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = fn(*args, **kwargs)
        return result, out.getvalue(), err.getvalue()


class HostConfigTests(HostCase):
    def test_bucket_aliases_are_parsed(self):
        self.assertEqual(dict(load_host(self.root).bucket_aliases),
                         {"env-skills": ("mod-a", "mod-b")})

    def test_host_without_aliases_has_none(self):
        self.host(None)
        self.assertEqual(dict(load_host(self.root).bucket_aliases), {})

    def test_malformed_aliases_stop_with_the_field(self):
        for bad, field in (([], "bucket_aliases"),
                           ({"env-skills": "mod-a"}, "bucket_aliases.env-skills"),
                           ({"env-skills": []}, "bucket_aliases.env-skills"),
                           ({"env-skills": ["a", "a"]}, "bucket_aliases.env-skills"),
                           ({"env-skills": [1]}, "bucket_aliases.env-skills[0]"),
                           ({"bad name": ["a"]}, "bucket_aliases.bad name")):
            with self.subTest(bad=bad):
                self.host(bad)
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                    load_host(self.root)
                self.assertIn(f"HOST_CONFIG_INVALID: {field}", err.getvalue())


class BucketTests(HostCase):
    def test_all_buckets_include_the_host_bucket_without_a_catalog(self):
        self.assertIn("env-skills", all_buckets(self.env))
        self.assertNotIn("env-skills", library_buckets(self.env))
        self.assertEqual(host_provided_buckets(self.env), frozenset({"env-skills"}))
        self.assertIn("mod-a", selectable_buckets(self.env))

    def test_sources_and_expansion(self):
        self.assertEqual(sorted(module_skill_sources(self.env)), ["mod-a", "mod-b"])
        self.assertEqual(expand_bucket(self.env, "env-skills"), ("mod-a", "mod-b"))
        self.assertEqual(expand_bucket(self.env, "mod-a"), ("mod-a",))
        self.assertEqual(expand_bucket(self.env, "lib-a"), ())
        self.assertEqual(host_bucket_plugins(self.env), {"env-skills": ("mod-a", "mod-b")})
        self.assertEqual([(s.plugin, s.rel, s.name, s.requires)
                          for s in module_skills(self.env)],
                         [("mod-a", "sk-a", "sk-a", ("sk-b",)), ("mod-b", "sk-b", "sk-b", ())])
        self.assertEqual(module_skills(self.env)[0].path, "packages/mod-a/skills/sk-a/SKILL.md")

    def test_plugin_without_skills_is_not_a_source(self):
        self.module("mod-c", {}, manifest={"name": "mod-c", "description": "commands only"})
        self.assertNotIn("mod-c", module_skill_sources(self.env))

    def test_skills_path_outside_the_plugin_is_skipped(self):
        self.module("mod-c", {}, manifest={"name": "mod-c", "skills": ["./missing"]})
        _, _, err = self.run_quiet(module_skill_sources, self.env)
        self.assertNotIn("mod-c", module_skill_sources(self.env))
        self.assertIn("skills path './missing' not found", err)

    def test_no_host_file_warns_and_gives_nothing(self):
        (self.repo / "configs" / "skiller-host.json").unlink()
        clear_host_cache()
        self.assertEqual(module_skill_sources(self.env), {})
        names, _, err = self.run_quiet(expand_bucket, self.env, "env-skills")
        self.assertEqual(names, ())
        self.assertIn("bucket 'env-skills' is provided by the host; no host modules here; "
                      "skipped", err)
        # once per process
        _, _, again = self.run_quiet(expand_bucket, self.env, "env-skills")
        self.assertEqual(again, "")

    def test_host_without_aliases_warns_and_gives_nothing(self):
        self.host(None)
        names, _, err = self.run_quiet(expand_bucket, self.env, "env-skills")
        self.assertEqual(names, ())
        self.assertIn("no host modules here", err)

    def test_alias_plugin_not_found_warns(self):
        self.host({"env-skills": ["mod-a", "mod-gone"]})
        names, _, err = self.run_quiet(expand_bucket, self.env, "env-skills")
        self.assertEqual(names, ("mod-a",))
        self.assertIn("bucket 'env-skills': host plugin 'mod-gone' not found; skipped", err)

    def test_library_bucket_named_like_a_plugin_is_refused(self):
        write_skill(self.root / "skills" / "mod-a" / "x", "x")
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
            check_collisions(self.env)
        self.assertIn("bucket name 'mod-a' is both a library bucket and a host module plugin",
                      err.getvalue())

    def test_library_directory_for_a_host_bucket_is_refused(self):
        write_skill(self.root / "skills" / "env-skills" / "x", "x")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            check_collisions(self.env)


class ConnectTests(HostCase):
    OPTS = {"profile": "p1", "no_core": True, "no_permissions": True}

    def test_resident_estimate_counts_direct_and_host_bucket_module_selections(self):
        for source in ("flag", "legacy", "toml", "host-bucket"):
            with self.subTest(source=source):
                proj = self.project(source)
                opts = {"no_core": True, "no_permissions": True, "list": True}
                if source == "legacy":
                    _json(proj / ".swissknife.json", {"plugins": ["mod-a"]})
                elif source == "toml":
                    path = proj / ".swissknifeman" / "config.toml"
                    path.parent.mkdir()
                    path.write_text('schema_version = 1\n[skiller]\nplugins = ["mod-a"]\n',
                                    encoding="utf-8")
                else:
                    opts["plugins"] = "env-skills" if source == "host-bucket" else "mod-a"
                selected = [("mod-a", "sk-a")]
                if source == "host-bucket":
                    selected.append(("mod-b", "sk-b"))
                tokens = sum(skill_budget(self.repo / "packages" / plugin / "skills" / skill)["tier0"]
                             for plugin, skill in selected)
                _, out, _ = self.run_quiet(do_connect, self.env, proj, opts, register=False)
                self.assertIn(f"Resident: ~{tokens} current ⊕ tier-0 ({len(selected)} skills,", out)
                self.assertFalse((proj / ".claude" / "settings.local.json").exists())

    def test_selection_expands_the_host_bucket_into_module_plugins(self):
        prepared = prepare_connect_selection(self.env, self.project(), self.OPTS, {})
        self.assertGreaterEqual(set(prepared["plugins"]), {"mod-a", "mod-b", "lib-a"})
        self.assertNotIn("env-skills", prepared["plugins"])
        self.assertEqual(prepared["host_buckets"], ("env-skills",))

    def test_exact_plugin_list_accepts_host_bucket_and_plugin_names(self):
        prepared = prepare_connect_selection(
            self.env, self.project(), {"plugins": "env-skills,lib-a", "no_core": True}, {})
        self.assertEqual(set(prepared["plugins"]), {"mod-a", "mod-b", "lib-a"})
        prepared = prepare_connect_selection(
            self.env, self.project(), {"plugins": "mod-a", "no_core": True}, {})
        self.assertEqual(prepared["plugins"], ("mod-a",))
        self.assertEqual(prepared["host_buckets"], ())

    def test_undeclared_module_plugin_is_skipped_with_a_warning(self):
        self.marketplace(["mod-a", "lib-a"])
        prepared, _, err = self.run_quiet(
            prepare_connect_selection, self.env, self.project(), self.OPTS, {})
        self.assertEqual(set(prepared["plugins"]), {"mod-a", "lib-a"})
        self.assertIn("does not declare the plugin 'mod-b'", err)

    def test_unknown_plugin_still_stops(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            prepare_connect_selection(
                self.env, self.project(), {"plugins": "nope", "no_core": True}, {})

    def test_old_bucket_key_is_replaced_by_the_module_plugins(self):
        proj = self.project()
        _json(proj / ".claude" / "settings.local.json",
              {"enabledPlugins": {f"env-skills@{MARKETPLACE}": True,
                                  "other@elsewhere": True}, "model": "keep"})
        _, out, _ = self.run_quiet(do_connect, self.env, proj, self.OPTS)
        enabled = self.settings(proj)["enabledPlugins"]
        self.assertNotIn(f"env-skills@{MARKETPLACE}", enabled)
        self.assertTrue(enabled[f"mod-a@{MARKETPLACE}"])
        self.assertTrue(enabled[f"mod-b@{MARKETPLACE}"])
        self.assertTrue(enabled[f"lib-a@{MARKETPLACE}"])
        self.assertTrue(enabled["other@elsewhere"])
        self.assertEqual(self.settings(proj)["model"], "keep")
        self.assertIn(f"Replaced:  env-skills@{MARKETPLACE} -> mod-a@{MARKETPLACE}, "
                      f"mod-b@{MARKETPLACE}", out)

    def test_dry_run_prints_the_replacement_and_writes_nothing(self):
        proj = self.project()
        path = proj / ".claude" / "settings.local.json"
        _json(path, {"enabledPlugins": {f"env-skills@{MARKETPLACE}": True}})
        before = path.read_bytes()
        _, out, _ = self.run_quiet(do_connect, self.env, proj, {**self.OPTS, "dry_run": True})
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(Path(f"{path}.bak").exists())
        self.assertIn(f"[dry-run] Replaced:  env-skills@{MARKETPLACE} -> ", out)

    def test_explicit_false_is_respected(self):
        proj = self.project()
        _json(proj / ".claude" / "settings.local.json",
              {"enabledPlugins": {f"env-skills@{MARKETPLACE}": False}})
        _, out, _ = self.run_quiet(do_connect, self.env, proj, self.OPTS)
        enabled = self.settings(proj)["enabledPlugins"]
        self.assertIs(enabled[f"env-skills@{MARKETPLACE}"], False)
        self.assertNotIn(f"mod-a@{MARKETPLACE}", enabled)
        self.assertTrue(enabled[f"lib-a@{MARKETPLACE}"])
        self.assertIn("Skipped (explicit false)", out)
        self.assertNotIn("Replaced:", out)

    def test_key_stays_when_the_marketplace_still_declares_the_bucket(self):
        self.marketplace(["mod-a", "mod-b", "lib-a", "env-skills"])
        proj = self.project()
        _json(proj / ".claude" / "settings.local.json",
              {"enabledPlugins": {f"env-skills@{MARKETPLACE}": True}})
        _, out, _ = self.run_quiet(do_connect, self.env, proj, self.OPTS)
        self.assertIn(f"env-skills@{MARKETPLACE}", self.settings(proj)["enabledPlugins"])
        self.assertNotIn("Replaced:", out)

    def test_without_a_host_the_bucket_is_empty_and_connect_goes_on(self):
        (self.repo / "configs" / "skiller-host.json").unlink()
        clear_host_cache()
        prepared, _, err = self.run_quiet(
            prepare_connect_selection, self.env, self.project(), self.OPTS, {})
        self.assertEqual(prepared["plugins"], ("lib-a",))
        self.assertIn("no host modules here", err)


class VendorTests(HostCase):
    def test_collect_skills_reads_module_plugins(self):
        skills, rels = collect_skills(self.env, ["env-skills"], set())
        self.assertEqual([(b, r, n) for b, r, _d, n in skills],
                         [("mod-a", "sk-a", "sk-a"), ("mod-b", "sk-b", "sk-b")])
        self.assertEqual(rels, {"mod-a": ["sk-a"], "mod-b": ["sk-b"]})

    def test_exclude_by_name_directory_plugin_path_and_host_bucket_path(self):
        for token in ("sk-b", "mod-b/sk-b", "env-skills/sk-b"):
            with self.subTest(token=token):
                skills, _ = collect_skills(self.env, ["env-skills"], {token})
                self.assertEqual([n for _b, _r, _d, n in skills], ["sk-a"])

    def test_plugin_name_selects_exactly_that_plugin(self):
        skills, _ = collect_skills(self.env, ["mod-b"], set())
        self.assertEqual([n for _b, _r, _d, n in skills], ["sk-b"])

    def test_requires_pulls_across_plugins(self):
        skills, _ = collect_skills(self.env, ["mod-a"], set())
        pulled = resolve_requires(skills, build_requires_index(self.env), set())
        self.assertEqual(pulled, {"sk-b": "sk-a"})
        self.assertEqual(sorted((b, n) for b, _r, _d, n in skills),
                         [("mod-a", "sk-a"), ("mod-b", "sk-b")])

    def test_exclude_beats_requires(self):
        skills, _ = collect_skills(self.env, ["mod-a"], {"sk-b"})
        self.assertEqual(resolve_requires(skills, build_requires_index(self.env), {"sk-b"}), {})
        self.assertEqual([n for _b, _r, _d, n in skills], ["sk-a"])

    def test_library_wins_a_name_clash(self):
        write_skill(self.root / "skills" / "lib-a" / "sk-b", "sk-b")
        index = build_requires_index(self.env)
        self.assertEqual(index["sk-b"][0], "lib-a")

    def test_clash_warns(self):
        write_skill(self.root / "skills" / "lib-a" / "sk-b", "sk-b")
        _, _, err = self.run_quiet(build_requires_index, self.env)
        self.assertIn("skill name 'sk-b' exists in the library and in host plugin 'mod-b'; "
                      "the library copy is used", err)

    def test_do_vendor_copies_module_skills_in_bucket_layout(self):
        proj = self.project()
        self.run_quiet(do_vendor, self.env, proj, {
            "agent": "generic", "buckets": "env-skills", "no_core": True,
            "no_permissions": True})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "mod-a" / "sk-a" / "SKILL.md").is_file())
        self.assertTrue((dest / "mod-b" / "sk-b" / "SKILL.md").is_file())
        manifest = json.loads((dest / ".swissknifeman-manifest.json").read_text())
        self.assertEqual(sorted(e["source_path"] for e in manifest["skills"]),
                         ["packages/mod-a/skills/sk-a", "packages/mod-b/skills/sk-b"])

    def test_host_bucket_path_exclude_beats_requires_through_do_vendor(self):
        proj = self.project()
        self.run_quiet(do_vendor, self.env, proj, {
            "agent": "generic", "buckets": "env-skills", "exclude": "env-skills/sk-b",
            "no_core": True, "no_permissions": True})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "mod-a" / "sk-a").is_dir())
        self.assertFalse((dest / "mod-b").exists())

    def test_do_vendor_profile_with_the_host_bucket(self):
        proj = self.project()
        self.run_quiet(do_vendor, self.env, proj, {
            "agent": "generic", "profile": "p1", "no_core": True, "no_permissions": True})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "mod-a" / "sk-a").is_dir())
        self.assertTrue((dest / "lib-a" / "sk-lib").is_dir())

    def test_do_vendor_without_a_host_installs_the_library_only(self):
        (self.repo / "configs" / "skiller-host.json").unlink()
        clear_host_cache()
        proj = self.project()
        _, _, err = self.run_quiet(do_vendor, self.env, proj, {
            "agent": "generic", "profile": "p1", "no_core": True, "no_permissions": True})
        dest = proj / ".ai" / "skills"
        self.assertTrue((dest / "lib-a" / "sk-lib").is_dir())
        self.assertFalse((dest / "mod-a").exists())
        self.assertIn("no host modules here", err)


class SyncTests(HostCase):
    def setUp(self):
        super().setUp()
        reg, *_ = build_registry(self.env)
        (self.root / "skills.json").write_text(json.dumps(reg), encoding="utf-8")

    def names(self, cfg, **kwargs):
        entries, skipped = resolve_skillset(self.env, cfg, **kwargs)
        return sorted(e["name"] for e in entries), skipped

    def test_registry_index_carries_module_entries(self):
        entries = {e["name"]: e for e in registry_entries(self.env)}
        self.assertEqual(entries["sk-a"]["origin"], "host")
        self.assertEqual(entries["sk-a"]["path"], "packages/mod-a/skills/sk-a/SKILL.md")
        self.assertEqual(entries["sk-a"]["requires"], ["sk-b"])
        self.assertEqual(len(entries["sk-a"]["sha256"]), 64)

    def test_bucket_token_expands_to_module_skills(self):
        self.assertEqual(self.names({"buckets": ["env-skills"]})[0], ["sk-a", "sk-b"])

    def test_plugin_name_is_a_bucket(self):
        # sk-a requires sk-b, so selecting mod-b alone gives sk-b only
        self.assertEqual(self.names({"buckets": ["mod-b"]})[0], ["sk-b"])

    def test_include_by_host_bucket_path_name_and_full_key(self):
        for token in ("env-skills/sk-a", "sk-a", "mod-a/sk-a"):
            with self.subTest(token=token):
                names, skipped = self.names({"include": [token]})
                self.assertEqual(names, ["sk-a", "sk-b"])
                self.assertEqual(skipped, [])

    def test_host_bucket_include_does_not_warn_about_a_moved_skill(self):
        _, _, err = self.run_quiet(resolve_skillset, self.env, {"include": ["env-skills/sk-a"]})
        self.assertNotIn("moved", err)

    def test_exclude_removes_a_skill_and_beats_requires(self):
        names, _ = self.names({"buckets": ["env-skills"], "exclude": ["sk-b"]})
        self.assertEqual(names, ["sk-a"])
        names, _ = self.names({"buckets": ["env-skills"], "exclude": ["env-skills/sk-b"]})
        self.assertEqual(names, ["sk-a"])

    def test_default_exclude_applies_by_name(self):
        names, _ = self.names({"buckets": ["env-skills"]}, include_core=True)
        self.assertEqual(names, ["sk-a", "sk-b"])
        with mock.patch("skiller.skillset.DEFAULT_EXCLUDE", ["sk-b"]):
            names, _ = self.names({"buckets": ["env-skills"]}, include_core=True)
        self.assertEqual(names, ["sk-a"])

    def test_library_skill_wins_a_name_clash_in_either_bucket_order(self):
        write_skill(self.root / "skills" / "lib-a" / "sk-a", "sk-a", body="FROM LIBRARY\n")
        write_skill(self.repo / "packages" / "mod-a" / "skills" / "sk-a", "sk-a",
                    requires=["sk-b"], body="FROM HOST\n")
        reg, *_ = build_registry(self.env)
        (self.root / "skills.json").write_text(json.dumps(reg), encoding="utf-8")
        for buckets in (["lib-a", "env-skills"], ["env-skills", "lib-a"]):
            with self.subTest(buckets=buckets):
                (entries, _), _, err = self.run_quiet(resolve_skillset, self.env,
                                                      {"buckets": buckets})
                chosen = {e["name"]: e for e in entries}["sk-a"]
                self.assertNotEqual(chosen.get("origin"), "host")
                self.assertEqual(chosen["bucket"], "lib-a")
                self.assertIn("the library copy is used", err)

    def test_without_a_host_the_bucket_is_empty(self):
        (self.repo / "configs" / "skiller-host.json").unlink()
        clear_host_cache()
        (names, _), _, err = self.run_quiet(self.names, {"buckets": ["env-skills", "lib-a"]})
        self.assertEqual(names, ["sk-lib"])
        self.assertIn("no host modules here", err)

    def test_do_sync_installs_module_skills_and_records_them(self):
        proj = self.project()
        cfg = proj / ".swissknifeman" / "config.json"
        _json(cfg, {"version": 1, "mode": "vendor", "buckets": ["env-skills"]})
        self.run_quiet(do_sync, self.env, proj, {"no_core": True, "no_permissions": True,
                                                 "provider_ids": ["claude-code"]})
        for name in ("sk-a", "sk-b"):
            self.assertTrue((proj / ".claude" / "skills" / name / "SKILL.md").is_file())
        lock = load_lock(proj)["skills"]
        self.assertEqual({n: lock[n]["bucket"] for n in ("sk-a", "sk-b")},
                         {"sk-a": "mod-a", "sk-b": "mod-b"})
        self.assertTrue(all(lock[n]["managed"] for n in ("sk-a", "sk-b")))
        manifest = json.loads((proj / ".claude" / "skills" / ".swissknifeman-manifest.json")
                              .read_text())
        self.assertEqual(sorted(e["source_path"] for e in manifest["skills"]),
                         ["packages/mod-a/skills/sk-a", "packages/mod-b/skills/sk-b"])
        # a second sync keeps the managed copies and the lock verifies
        self.run_quiet(do_sync, self.env, proj, {
            "no_core": True, "no_permissions": True, "provider_ids": ["claude-code"]})
        self.assertEqual(load_lock(proj)["skills"], lock)


class ReportTests(HostCase):
    def test_budget_counts_module_skills(self):
        skills, meta = resolve_active_set(self.env, self.project(), {}, profile="p1",
                                          no_core=True)
        self.assertEqual(sorted(n for _b, _r, _d, n in skills), ["sk-a", "sk-b", "sk-lib"])
        self.assertEqual(meta["pulled"], {})

    def test_channel_overlap_expands_a_host_bucket_on_either_side(self):
        # a stale host bucket key in enabledPlugins against a vendored module skill
        self.assertEqual(channel_overlap({"env-skills", "keep"}, {"mod-a"}, self.env), ["mod-a"])
        self.assertEqual(channel_overlap({"mod-b"}, {"env-skills"}, self.env), ["mod-b"])
        self.assertEqual(channel_overlap({"lib-a"}, {"lib-a"}, self.env), ["lib-a"])
        self.assertEqual(channel_overlap({"env-skills"}, {"lib-a"}, self.env), [])
        # without env the plain intersection is unchanged
        self.assertEqual(channel_overlap({"env-skills"}, {"mod-a"}), [])

    def test_status_registry_names_include_module_skills(self):
        names = registry_skill_names(self.env)
        self.assertEqual(names["sk-a"], ["mod-a"])
        self.assertEqual(names["sk-lib"], ["lib-a"])

    def test_registry_builds_without_a_catalog_for_the_host_bucket(self):
        registry, meta, dirs = build_registry(self.env)
        self.assertNotIn("env-skills", dirs)
        self.assertNotIn("env-skills", registry["buckets"])
        self.assertIn("env-skills", meta)

    def test_index_has_one_line_for_the_host_bucket(self):
        registry, meta, _dirs = build_registry(self.env)
        index = render_index(registry, meta, host_bucket_plugins(self.env))
        self.assertIn("### env-skills — provided by host modules: mod-a, mod-b\n", index)
        self.assertNotIn("sk-a", index)
        bare = render_index(registry, meta)
        self.assertIn("### env-skills — provided by the host\n", bare)

    def test_index_without_host_buckets_is_unchanged(self):
        registry, meta, _dirs = build_registry(self.env)
        meta = {k: v for k, v in meta.items() if k != "env-skills"}
        self.assertNotIn("provided by", render_index(registry, meta, {}))

    def test_registry_refuses_a_name_clash(self):
        write_skill(self.root / "skills" / "mod-a" / "x", "x")
        meta = json.loads((self.root / "buckets.json").read_text())
        meta["mod-a"] = {"description": "clash", "category": "x", "tags": []}
        _json(self.root / "buckets.json", meta)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_registry(self.env)


if __name__ == "__main__":
    unittest.main()
