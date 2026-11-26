"""Native host observations independently of CLI operation registration."""

import json
from dataclasses import replace
from unittest.mock import Mock
from uuid import UUID

import pytest

from skm.adapters.checkout_fs.local import LocalCheckoutFs
from skm.adapters.checkout_fs.user_home import LocalUserHomeReader
from skm.adapters.integrations.claude_code.hooks import build_hook_command as claude_hook_command
from skm.adapters.integrations.claude_code.target import ClaudeCodeTarget
from skm.adapters.integrations.cursor.hooks import build_hook_command as cursor_hook_command
from skm.adapters.integrations.cursor.target import CursorTarget
from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext
from skm.kernel.cancel import CancelSource
from skm.kernel.errors import BackendUnavailable
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, ProjectId
from skm.modules.integrations.domain.budget import estimate_tokens
from skm.modules.integrations.domain.checks.projections import subscriptions_valid
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.events import ProjectionDriftDetected
from skm.modules.integrations.domain.hook_events import HookSurfaceId
from skm.modules.integrations.domain.hook_subscriptions import parse_subscriptions, validate_subscription
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.generated.queries import ListHookSubscriptions
from skm.modules.integrations.generated.results import ListHookSubscriptionsResult
from skm.modules.integrations.generated.views import HookSubscriptionView
from skm.modules.integrations.host import doctor
from skm.modules.integrations.host import first_turn_budget as budget
from skm.modules.integrations.ports import UserHomeReader


def test_checkout_state_operations_require_a_configured_directory(tmp_path):
    fs = LocalCheckoutFs(tmp_path / "checkout", state_dir=None)

    with (
        pytest.raises(BackendUnavailable, match="Checkout host state is unavailable"),
        fs.hold_binding_lock("binding"),
    ):
        pytest.fail("acquired a lock without checkout state")
    with pytest.raises(BackendUnavailable):
        fs.write_journal("binding", "journal", b"{}")
    with pytest.raises(BackendUnavailable):
        fs.list_journals("binding")
    with pytest.raises(BackendUnavailable):
        fs.remove_journal("binding", "journal")

    assert not list(tmp_path.iterdir())


@pytest.fixture
def native_budget(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    fs = LocalCheckoutFs(root, state_dir=tmp_path / "state")
    target = TargetId.CLAUDE_CODE
    project_id = ProjectId(UUID(int=1))
    documents = [
        (Surface.INSTRUCTIONS, "CLAUDE.md", "managed and unmanaged instructions\n"),
        (
            Surface.SKILLS,
            ".claude/skills/test/SKILL.md",
            "---\nname: test\ndescription: Skill card\n---\nlarge body",
        ),
        (Surface.AGENTS, ".claude/agents/test.md", "---\ndescription: Agent card\n---\nlarge body"),
        (Surface.MCP, ".mcp.json", '{"mcpServers":{"docs":{"tool_count":3}}}'),
        (
            Surface.PERMISSIONS,
            ".claude/settings.json",
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": claude_hook_command(
                                            "SessionStart", HookSurfaceId.SESSION_CONTEXT, project_id
                                        ),
                                    }
                                ]
                            }
                        ]
                    }
                }
            ),
        ),
    ]
    files = []
    for surface, path, content in documents:
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)
        raw = content.encode()
        files.append(
            DesiredFile(
                target,
                surface,
                path,
                ManagedBoundary(Ownership.MANAGED_FILE),
                raw,
                sha256_tagged(raw),
                (),
                "test@1",
            )
        )
    inputs = ProjectionInputs(
        project_id,
        target,
        {"session_start_template": "Project context preview"},
        {},
        (),
        {},
        PermissionProfile.OBSERVE,
        {},
        (),
        {"docs": {"command": "docs", "tool_count": 3}},
        (),
        "sha256:" + "0" * 64,
        0,
        (),
    )
    client = Mock(spec_set=SkmClient)
    ctx = HostContext(
        client=client,
        gateways=GatewayTable(
            {UserHomeReader: LocalUserHomeReader(home, managed_root=tmp_path / "managed")}, "host_gateway"
        ),
        host_id=HostId(UUID(int=2)),
        config={},
        log=None,
        cancel=CancelSource().token,
    )

    def observed(_ctx, _project, _mount, _target):
        return fs, ClaudeCodeTarget(), inputs, tuple(files)

    monkeypatch.setattr(budget, "native_inputs", observed)
    monkeypatch.setattr(doctor, "native_inputs", observed)
    yield ctx, project_id, root, home
    assert not client.mock_calls


def test_host_observes_five_native_sources_and_template_without_hook_execution(native_budget):
    ctx, project_id, root, _ = native_budget
    report = budget.first_turn_budget(ctx, project_id=project_id, target=TargetId.CLAUDE_CODE)
    assert report.verdict == "ok"
    assert len(report.sources) == 5
    assert report.sources[3].tokens == estimate_tokens("Project context preview")
    assert report.sources[4].tokens == 3 * 150 + 40
    tokens = [source.tokens for source in report.sources]
    assert None not in tokens
    assert report.total == sum(count for count in tokens if count is not None)
    (root / "CLAUDE.md").write_text("a much larger unmanaged instruction " * 100)
    changed = budget.first_turn_budget(ctx, project_id=project_id, target=TargetId.CLAUDE_CODE)
    original_tokens, changed_tokens = report.sources[2].tokens, changed.sources[2].tokens
    assert original_tokens is not None
    assert changed_tokens is not None
    assert changed_tokens > original_tokens
    assert changed.sources[2].detail["digests"] != report.sources[2].detail["digests"]


@pytest.mark.parametrize(
    "path", ["CLAUDE.md", ".claude/skills/test/SKILL.md", ".claude/agents/test.md", ".mcp.json"]
)
def test_partial_native_observation_is_never_reported_as_actual_usage(native_budget, path):
    ctx, project_id, root, _ = native_budget
    (root / path).unlink()
    report = budget.run(
        ctx, {"project_id": str(project_id), "target": "claude_code", "include_plugins": False}
    )
    assert report["total"] is None
    assert report["verdict"] == "incomplete"
    assert all("usage" not in source for source in report["sources"])


def test_deferred_search_and_unobserved_plugins(native_budget):
    ctx, project_id, _, home = native_budget
    (home / ".claude").mkdir()
    (home / ".claude/settings.json").write_text(json.dumps({"env": {"ENABLE_TOOL_SEARCH": "auto:5"}}))
    report = budget.first_turn_budget(ctx, project_id=project_id, target=TargetId.CLAUDE_CODE)
    assert report.sources[4].tokens == 3 * 24 + 40
    report = budget.first_turn_budget(
        ctx, project_id=project_id, target=TargetId.CLAUDE_CODE, include_plugins=True
    )
    assert report.verdict == "incomplete"
    assert report.sources[0].tokens is None


def test_invalid_effective_order_fails_before_observation(native_budget):
    ctx, project_id, _, _ = native_budget
    ctx = replace(ctx, config={"integrations.budget.first_turn.target": 24000})
    with pytest.raises(ValueError, match=r"integrations\.budget_order"):
        budget.first_turn_budget(ctx, project_id=project_id, target=TargetId.CLAUDE_CODE)


@pytest.mark.parametrize("kind", ["webhook", "event_sink"])
@pytest.mark.parametrize("valid", [True, False])
def test_doctor_preserves_server_validation_for_local_subscriptions(native_budget, monkeypatch, kind, valid):
    ctx, project_id, _, _ = native_budget
    fs, adapter, inputs, files = doctor.native_inputs(ctx, project_id, None, TargetId.CLAUDE_CODE)
    raw = {
        "drift-audit": {
            "class": "observation",
            "kind": kind,
            "execution_location": "control_plane",
            "event_types": [ProjectionDriftDetected.event_type],
            "timeout_ms": 5000 if valid else 999999,
            "target": {"url": "https://example.test/hooks", "secret": "secret://env/DRIFT_SECRET"}
            if kind == "webhook"
            else {"sink_id": "test-sink", "config": {}},
        }
    }
    subscriptions, problems = parse_subscriptions(raw, {})
    assert not problems
    sub = subscriptions[0]
    problems = validate_subscription(
        sub, hookable_types=frozenset({ProjectionDriftDetected.event_type}), sink_ids=frozenset({"test-sink"})
    )
    assert bool(problems) is not valid
    assert all(problem.reason == "timeout_out_of_range" for problem in problems)
    view = HookSubscriptionView(
        id=sub.id,
        class_=sub.hook_class.value,
        kind=sub.kind.value,
        execution_location=sub.execution_location.value,
        event_types=sub.event_types,
        target_summary="registered endpoint",
        enabled=sub.enabled,
        valid=not problems,
        violations=tuple(
            {"key": item.key, "reason": item.reason, "message": item.message} for item in problems
        ),
        defined_at=sub.defined_at,
        digest=sub.digest,
    )

    class Client:
        def ask(self, query):
            assert isinstance(query, ListHookSubscriptions)
            return ListHookSubscriptionsResult(items=(view,))

    ctx = replace(ctx, client=Client(), config={"hooks.subscriptions": raw})
    monkeypatch.setattr(doctor, "resolve_project_workspace_id", lambda *_args: UUID(int=3))
    observed = doctor.doctor_context(ctx, fs, adapter, inputs, files, repository_id=UUID(int=5), mount="main")
    assert observed.subscriptions == ()
    assert len(observed.subscription_facts) == 1
    assert subscriptions_valid(observed)[0].level == ("ok" if valid else "error")


def test_missing_cursor_hooks_stays_incomplete_despite_known_template(native_budget, monkeypatch):
    ctx, project_id, root, _ = native_budget
    fs, _, inputs, files = doctor.native_inputs(ctx, project_id, None, TargetId.CLAUDE_CODE)
    (root / ".claude/settings.json").unlink()
    adapter = CursorTarget()
    inputs = replace(inputs, target=TargetId.CURSOR)
    for path in adapter.instruction_paths():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("Native cursor instructions\n")
    raw = json.dumps(
        {
            "hooks": {
                "sessionStart": [
                    {
                        "command": cursor_hook_command(
                            "sessionStart", HookSurfaceId.SESSION_CONTEXT, project_id
                        )
                    }
                ]
            }
        }
    ).encode()
    hook = replace(
        files[0],
        target=TargetId.CURSOR,
        surface=Surface.HOOKS,
        relative_path=".cursor/hooks.json",
        managed_bytes=raw,
        managed_digest=sha256_tagged(raw),
    )
    files = (*(replace(file, target=TargetId.CURSOR) for file in files), hook)
    monkeypatch.setattr(budget, "native_inputs", lambda *_args: (fs, adapter, inputs, files))
    report = budget.first_turn_budget(ctx, project_id=project_id, target=TargetId.CURSOR)
    assert report.sources[3].tokens is None
    assert report.total is None
    assert report.verdict == "incomplete"
    assert all(source.tokens is not None for source in report.sources if source.kind != "hooks")
    (root / ".cursor/hooks.json").write_bytes(raw)
    complete = budget.first_turn_budget(ctx, project_id=project_id, target=TargetId.CURSOR)
    assert complete.sources[3].tokens == estimate_tokens("Project context preview")
    assert complete.total is not None
    assert complete.verdict == "ok"


@pytest.mark.parametrize(
    "extra",
    [{"type": "command", "command": "touch forbidden"}, {"type": "prompt", "prompt": "Unmeasurable context"}],
)
def test_extra_session_hook_stays_incomplete_despite_known_template(native_budget, extra):
    ctx, project_id, root, _ = native_budget
    path = root / ".claude/settings.json"
    settings = json.loads(path.read_text())
    settings["hooks"]["SessionStart"].append({"hooks": [extra]})
    path.write_text(json.dumps(settings))
    report = budget.first_turn_budget(ctx, project_id=project_id, target=TargetId.CLAUDE_CODE)
    assert report.sources[3].tokens is None
    assert report.total is None
    assert report.verdict == "incomplete"
    assert all(source.tokens is not None for source in report.sources if source.kind != "hooks")
    assert not (root / "forbidden").exists()
