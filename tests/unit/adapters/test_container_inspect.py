"""Typed readers over docker inspect documents (adapters §7.2)."""

import json

import pytest

from skm.adapters.sandbox.container import DockerResult
from skm.adapters.sandbox.container_inspect import (
    ABSENT,
    CONTAINER_ID,
    PROBE_COMMAND,
    PROBE_LABEL,
    as_flag,
    as_mapping,
    as_number,
    as_strings,
    as_text,
    dig,
    effective_mounts,
    has_writable_mount,
    image_entrypoint,
    inspected_one,
    merged_env,
    probe_volumes,
    requested_mounts,
    returned_id,
    verified_probe_id,
)

PROBE_ID = "a" * 64


def test_dig_walks_nested_keys_and_signals_absence() -> None:
    document = {"HostConfig": {"LogConfig": {"Config": {"max-size": "1m"}}}}
    assert dig(document, "HostConfig.LogConfig.Config") == {"max-size": "1m"}
    assert dig(document, "HostConfig.Missing") is ABSENT
    assert dig(document, "HostConfig.LogConfig.Config.max-size.extra") is ABSENT
    assert dig("not-a-mapping", "HostConfig") is ABSENT


def test_scalar_converters_reject_wrong_shapes() -> None:
    assert as_text("created") == "created"
    assert as_flag(False) is False
    assert as_number(64) == 64
    assert as_strings(None) == ()
    assert as_strings(["a", "b"]) == ("a", "b")
    with pytest.raises(ValueError, match=r"^$"):
        as_text(1)
    with pytest.raises(ValueError, match=r"^$"):
        as_flag("false")
    with pytest.raises(ValueError, match=r"^$"):
        as_number(True)
    with pytest.raises(ValueError, match=r"^$"):
        as_number(1.5)
    with pytest.raises(ValueError, match=r"^$"):
        as_strings("one")
    with pytest.raises(ValueError, match=r"^$"):
        as_strings([1])


def test_image_entrypoint_treats_a_blank_vector_as_empty() -> None:
    assert image_entrypoint(["/bin/sh", "-c"]) == ("/bin/sh", "-c")
    assert image_entrypoint([""]) == ()
    assert image_entrypoint(None) == ()


def test_merged_env_lets_the_request_override_the_image() -> None:
    assert merged_env(
        {"PATH": "/opt/bin", "HOME": "/home/dev"}, ("PATH=/usr/bin", "TERM=xterm")
    ) == frozenset({"PATH=/opt/bin", "HOME=/home/dev", "TERM=xterm"})


def test_as_mapping_accepts_none_unless_forbidden() -> None:
    assert as_mapping(None) == {}
    assert as_mapping({"k": "v"}) == {"k": "v"}
    with pytest.raises(ValueError, match=r"^$"):
        as_mapping(None, allow_none=False)
    with pytest.raises(ValueError, match=r"^$"):
        as_mapping(["x"])


def test_requested_mounts_record_type_source_target_and_extra_options() -> None:
    mounts = requested_mounts(
        [
            {"Type": "bind", "Source": "/host/src", "Target": "/src", "ReadOnly": True},
            {
                "Type": "bind",
                "Source": "/host/worktmp",
                "Target": "/worktmp",
                "BindOptions": {"Propagation": "rprivate"},
            },
        ]
    )
    assert ("bind", "/host/src", "/src", "ro") in mounts
    assert ("bind", "/host/worktmp", "/worktmp", "rw") in mounts
    assert ("option", "BindOptions") in mounts
    assert requested_mounts(None) == frozenset()
    with pytest.raises(ValueError, match=r"^$"):
        requested_mounts({"Type": "bind"})
    with pytest.raises(ValueError, match=r"^$"):
        requested_mounts(["not-a-mount"])


def test_effective_mounts_skip_declared_image_volumes() -> None:
    read = effective_mounts({"/var/data": {}, "/tmp": {}})  # noqa: S108
    found = read(
        [
            {"Type": "volume", "Source": "anon", "Destination": "/var/data", "RW": True},
            {"Type": "bind", "Source": "/host/src", "Destination": "/src", "RW": False},
        ]
    )
    assert found == frozenset({("bind", "/host/src", "/src", "ro")})
    with pytest.raises(ValueError, match=r"^$"):
        read("not-a-list")


def test_probe_volumes_accept_only_anonymous_volumes_for_declared_targets() -> None:
    names = probe_volumes(
        {
            "Config": {"Volumes": {"/var/data": {}, "/tmp": {}}},  # noqa: S108
            "Mounts": [
                {
                    "Type": "volume",
                    "Name": PROBE_ID,
                    "Destination": "/var/data",
                }
            ],
        }
    )
    assert names == (PROBE_ID,)
    with pytest.raises(ValueError, match=r"^$"):
        probe_volumes({"Config": {"Volumes": {"/var/data": {}}}, "Mounts": "bad"})
    with pytest.raises(ValueError, match=r"^$"):
        probe_volumes(
            {
                "Config": {"Volumes": {"/var/data": {}, "/extra": {}}},
                "Mounts": [{"Type": "volume", "Name": PROBE_ID, "Destination": "/var/data"}],
            }
        )
    with pytest.raises(ValueError, match=r"^$"):
        probe_volumes(
            {
                "Config": {"Volumes": {"/var/data": {}}},
                "Mounts": [{"Type": "bind", "Name": PROBE_ID, "Destination": "/var/data"}],
            }
        )


def test_returned_id_requires_a_successful_64_hex_line() -> None:
    ok = DockerResult(exit_code=0, stdout=f"created\n{PROBE_ID}\n")
    assert returned_id(ok) == PROBE_ID
    assert returned_id(DockerResult(exit_code=1, stdout=PROBE_ID)) is None
    assert returned_id(DockerResult(exit_code=0, stdout="short\n")) is None
    assert returned_id(DockerResult(exit_code=0, stdout="")) is None


def test_inspected_one_reads_a_single_object_document() -> None:
    report = {"Id": PROBE_ID, "Name": "/probe"}
    result = DockerResult(exit_code=0, stdout=json.dumps([report]))
    assert inspected_one(result) == report
    assert inspected_one(DockerResult(exit_code=1, stdout=json.dumps([report]))) is None
    assert inspected_one(DockerResult(exit_code=0, stdout="not-json")) is None
    assert inspected_one(DockerResult(exit_code=0, stdout=json.dumps([report, report]))) is None
    assert inspected_one(DockerResult(exit_code=0, stdout=json.dumps(["x"]))) is None


def test_verified_probe_id_matches_the_unstarted_baseline_probe() -> None:
    report = {
        "Id": PROBE_ID,
        "Name": "/probe",
        "State": {"Status": "created"},
        "Config": {"Labels": {PROBE_LABEL: "true"}, "Cmd": [PROBE_COMMAND]},
    }
    assert verified_probe_id(report, PROBE_ID, "probe") == PROBE_ID
    assert verified_probe_id(None, PROBE_ID, "probe") == PROBE_ID
    assert verified_probe_id(report, "b" * 64, "probe") is None
    assert verified_probe_id({**report, "Name": "/other"}, PROBE_ID, "probe") is None
    assert verified_probe_id({**report, "State": {"Status": "running"}}, PROBE_ID, "probe") is None
    assert CONTAINER_ID.fullmatch(PROBE_ID)


def test_has_writable_mount_treats_unknown_shapes_as_writable() -> None:
    assert has_writable_mount({"Mounts": [{"Type": "bind", "RW": False}]}) is False
    assert has_writable_mount({"Mounts": [{"Type": "bind", "RW": True}]}) is True
    assert has_writable_mount({"Mounts": [{"Type": "volume", "RW": True}]}) is False
    assert has_writable_mount({"Mounts": "bad"}) is True
    assert has_writable_mount({"Mounts": [None]}) is True
    assert has_writable_mount({}) is True
