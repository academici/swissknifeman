"""skiller select (P8.2): the pure function on synthetic entries, the dependency readers, the policy from the project
configuration and the golden answers of five tasks on the real library."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from skiller import select as sel
from skiller.common import Env

PKG_ROOT = Path(__file__).resolve().parents[1]


def entry(bucket, name, **selection):
    row = {"name": name, "bucket": bucket, "path": f"skills/{bucket}/{name}/SKILL.md"}
    if selection:
        row["selection"] = selection
    return row


ENTRIES = [
    entry("php", "database", kind="contract", triggers={"paths": ["database/migrations/**"]}),
    entry("php", "laravel", kind="router", triggers={"deps": ["composer:laravel/framework"]}),
    entry("php", "repositories", kind="domain", triggers={"deps": ["composer:laravel/framework"]},
          exclusive_group="arch"),
    entry("php", "php-patterns", kind="domain", triggers={"deps": ["composer:laravel/framework"]},
          exclusive_group="arch"),
    entry("blender", "mcp-blender", kind="tool", requires_tools=["blender-mcp"],
          triggers={"paths": ["*.blend"]}),
    entry("general", "implement", kind="procedure", replaced_by="the-role-contract.md",
          triggers={"paths": ["**"]}),
    entry("quality", "code-review", kind="procedure", roles=["reviewer"]),
    entry("devops", "docker", kind="router", exclusive_group="docker"),
    entry("devops", "docker-php", kind="domain", exclusive_group="docker", triggers={"paths": ["Dockerfile"]}),
    entry("devops", "makefile", kind="domain", triggers={"paths": ["Makefile"]}),
]
GROUPS = {"arch": {"max": 1, "members": ["php/repositories", "php/php-patterns"]},
          "docker": {"router": "devops/docker", "members": ["devops/docker", "devops/docker-php"]}}


def run(request, tokens=lambda sid: 100):
    return sel.select(ENTRIES, dict({"role": "executor", "policy": "auto"}, **request), GROUPS, tokens)


def ids(result):
    return [row["id"] for row in result["included"]]


def reasons(result):
    return {row["id"]: row["reason"] for row in result["excluded"]}


class PureSelectCase(unittest.TestCase):
    def test_path_trigger_and_nothing_else(self):
        out = run({"paths": ["database/migrations/2026_create_x.php"]})
        self.assertEqual(ids(out), ["php/database"])
        self.assertEqual(out["included"][0]["reason"], "trigger_path")
        self.assertEqual(out["tokens"], 100)

    def test_explicit_policy_skips_triggers_but_keeps_include(self):
        out = run({"policy": "explicit", "paths": ["database/migrations/x.php"], "include": ["quality/code-review"]})
        self.assertEqual(ids(out), ["quality/code-review"])
        self.assertEqual(out["explain"]["trace"][1], {"step": "triggers", "skipped": "policy explicit"})

    def test_include_by_name_and_unknown_include(self):
        out = run({"include": ["makefile", "no-such-skill"]})
        self.assertEqual(ids(out), ["devops/makefile"])
        self.assertEqual(reasons(out), {"no-such-skill": "unknown_skill"})

    def test_exclude_wins_over_include(self):
        out = run({"include": ["devops/makefile"], "exclude": ["makefile"]})
        self.assertEqual(ids(out), [])
        self.assertEqual(reasons(out), {"devops/makefile": "excluded"})

    def test_router_is_discoverable_not_preloaded(self):
        out = run({"deps": ["composer:laravel/framework"]})
        self.assertNotIn("php/laravel", ids(out))
        self.assertEqual(reasons(out)["php/laravel"], "kind_not_preloaded")
        self.assertEqual(out["discoverable"], ["php/laravel"])

    def test_explicit_router_is_preloaded(self):
        self.assertEqual(ids(run({"include": ["php/laravel"]})), ["php/laravel"])

    def test_exclusive_group_keeps_the_first_candidate_in_a_stable_order(self):
        out = run({"deps": ["composer:laravel/framework"]})
        self.assertEqual(ids(out), ["php/php-patterns"])
        self.assertEqual(reasons(out)["php/repositories"], "exclusive_group")
        self.assertEqual([r["detail"] for r in out["excluded"] if r["id"] == "php/repositories"], ["arch"])

    def test_a_group_member_removed_by_a_filter_does_not_take_the_slot(self):
        out = run({"deps": ["composer:laravel/framework"], "exclude": ["php/php-patterns"]})
        self.assertEqual(ids(out), ["php/repositories"])

    def test_a_router_group_gives_the_child_not_the_router(self):
        self.assertEqual(ids(run({"paths": ["Dockerfile"]})), ["devops/docker-php"])
        # only an explicit include takes the router, and then it stays next to the child
        self.assertEqual(ids(run({"include": ["devops/docker"], "paths": ["Dockerfile"]})),
                         ["devops/docker", "devops/docker-php"])

    def test_tool_missing_and_tool_present(self):
        self.assertEqual(reasons(run({"paths": ["a.blend"]}))["blender/mcp-blender"], "tool_missing")
        self.assertEqual(ids(run({"paths": ["a.blend"], "tools": ["blender-mcp"]})), ["blender/mcp-blender"])

    def test_skill_replaced_by_the_role_contract_is_not_preloaded(self):
        out = run({"paths": ["src/app.py"]})
        self.assertEqual(reasons(out)["general/implement"], "duplicated_by_role_contract")
        self.assertEqual(ids(run({"include": ["general/implement"]})), ["general/implement"])

    def test_role_not_allowed(self):
        self.assertEqual(ids(run({"role": "reviewer", "include": ["quality/code-review"]})), ["quality/code-review"])
        out = run({"role": "executor", "include": ["quality/code-review"]})
        self.assertEqual(ids(out), ["quality/code-review"])  # explicit is exempt
        entries = [dict(e) for e in ENTRIES]
        out = sel.select(entries, {"role": "executor", "policy": "auto", "paths": [], "deps": []}, GROUPS, lambda s: 1)
        self.assertNotIn("quality/code-review", ids(out))

    def test_budget_excludes_without_cutting_and_never_drops_an_explicit_skill(self):
        out = run({"paths": ["database/migrations/x.php", "Makefile"], "budget": 150,
                   "include": ["devops/makefile"]}, tokens=lambda sid: 100)
        self.assertEqual(ids(out), ["devops/makefile"])
        out = run({"paths": ["database/migrations/x.php", "Makefile"], "budget": 150})
        self.assertEqual(ids(out), ["devops/makefile"])
        self.assertEqual(reasons(out), {"php/database": "over_budget", "general/implement": "duplicated_by_role_contract"})
        self.assertEqual(out["tokens"], 100)

    def test_the_same_request_gives_the_same_answer(self):
        request = {"paths": ["database/migrations/x.php", "Makefile"], "deps": ["composer:laravel/framework"]}
        self.assertEqual(json.dumps(run(request)), json.dumps(run(request)))


class GlobAndDepsCase(unittest.TestCase):
    def test_path_matching(self):
        for pattern, path, expected in [
            ("database/migrations/**", "database/migrations/a/b.php", True),
            ("database/migrations/**", "app/database/migrations/a.php", False),
            ("**/*.vue", "resources/js/A.vue", True), ("**/*.vue", "A.vue", True),
            ("Makefile", "sub/dir/Makefile", True), ("*.blend", "x/y/a.blend", True),
            ("requirements*.txt", "requirements-dev.txt", True), ("src/*.py", "src/a/b.py", False),
            ("pyproject.toml", "./pyproject.toml", True)]:
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(sel.path_matches(pattern, path), expected)

    def test_project_deps_are_read_from_the_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "composer.json").write_text(json.dumps(
                {"require": {"php": "^8.2", "laravel/framework": "^11"}, "require-dev": {"pestphp/pest": "^3"}}))
            (root / "package.json").write_text(json.dumps(
                {"dependencies": {"vue": "^3"}, "devDependencies": {"vite": "^5"}}))
            (root / "pyproject.toml").write_text('[project]\nname = "x"\ndependencies = ["click>=8", "rich"]\n')
            self.assertEqual(sel.project_deps(root), [
                "composer:laravel/framework", "composer:pestphp/pest", "npm:vite", "npm:vue", "pip:click", "pip:rich"])
            self.assertEqual(sel.project_deps(root / "missing"), [])

    def test_broken_manifests_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "composer.json").write_text("{")
            (Path(tmp) / "pyproject.toml").write_text("[")
            self.assertEqual(sel.project_deps(tmp), [])


class PolicyAndCliCase(unittest.TestCase):
    def test_policy_comes_from_the_project_config_unless_given(self):
        env = Env(PKG_ROOT, "select")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sel._policy(env, Path(tmp), None), "explicit")
            (Path(tmp) / ".swissknifeman").mkdir()
            (Path(tmp) / ".swissknifeman" / "config.toml").write_text(
                'schema_version = 1\n\n[skiller.selection]\npolicy = "auto"\n')
            self.assertEqual(sel._policy(env, Path(tmp), None), "auto")
            self.assertEqual(sel._policy(env, Path(tmp), "explicit"), "explicit")

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sel.cmd_select(Env(PKG_ROOT, "select"), list(args))
        return out.getvalue()

    def test_json_output_has_the_documented_shape(self):
        doc = json.loads(self.cli("--role", "executor", "--policy", "auto", "--paths", "database/migrations/x.php",
                                  "--provider", "claude-code", "--json"))
        self.assertEqual(sorted(doc), ["discoverable", "excluded", "included", "request", "tokens"])
        row = doc["included"][0]
        self.assertEqual(sorted(row), ["id", "name", "path", "reason", "tokens"])
        self.assertTrue(Path(row["path"]).is_file())
        self.assertEqual(doc["request"]["policy"], "auto")

    def test_explain_adds_the_trace_and_text_output_lists_the_skills(self):
        doc = json.loads(self.cli("--role", "executor", "--policy", "auto", "--paths", "Makefile", "--json", "--explain"))
        self.assertEqual([step["step"] for step in doc["explain"]["trace"]],
                         ["include", "triggers", "filters", "exclusive_group", "budget"])
        text = self.cli("--role", "executor", "--policy", "auto", "--paths", "Makefile")
        self.assertIn("+ devops/makefile  trigger_path", text)


class GoldenTasksCase(unittest.TestCase):
    """Five tasks of the audit on the real library: the skills the executor gets, in order, with the reason."""

    def select(self, paths, deps=(), role="executor"):
        out = json.loads(self._run(role, paths, deps))
        return [(row["id"], row["reason"]) for row in out["included"]], out

    def _run(self, role, paths, deps):
        args = ["--role", role, "--policy", "auto", "--json", "--paths", *paths]
        if deps:
            args += ["--deps", *deps]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sel.cmd_select(Env(PKG_ROOT, "select"), args)
        return out.getvalue()

    def test_laravel_migration(self):
        got, out = self.select(["database/migrations/2026_create_orders.php"], ["composer:laravel/framework"])
        self.assertEqual(got, [("laravel-testing/test-isolation-guard", "trigger_path"), ("php/database", "trigger_path")])
        self.assertEqual(out["excluded"], [])

    def test_vue_component(self):
        got, _ = self.select(["resources/js/Components/OrderList.vue"], ["npm:vue"])
        self.assertEqual(got, [("frontend-vue/vue-best-practices", "trigger_path")])

    def test_python_cli(self):
        got, _ = self.select(["src/tool/cli.py", "pyproject.toml"], ["pip:click"])
        self.assertEqual(got, [("python/venv-dependencies", "trigger_path")])

    def test_docs_only(self):
        got, out = self.select(["docs/guide.md", "README.md"])
        self.assertEqual((got, out["excluded"], out["tokens"]), ([], [], 0))

    def test_schema_change(self):
        got, _ = self.select(["schemas/order/v1/order.schema.json"])
        self.assertEqual(got, [("architect/data-schema", "trigger_path")])

    def test_no_router_reference_or_persona_is_preloaded_in_any_task(self):
        registry = json.loads((PKG_ROOT / "skills.json").read_text(encoding="utf-8"))
        kinds = {sel.skill_id(e): (e.get("selection") or {}).get("kind") for e in registry["skills"]}
        for paths in (["database/migrations/a.php"], ["a.vue"], ["pyproject.toml"], ["docs/a.md"], ["a.schema.json"]):
            _, out = self.select(paths)
            for row in out["included"]:
                self.assertNotIn(kinds[row["id"]], sel.NOT_PRELOADED_KINDS)


if __name__ == "__main__":
    unittest.main()
