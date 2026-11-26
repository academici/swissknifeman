import pytest

from security.api.harness import make_world
from skm import __version__


@pytest.mark.parametrize("version", ["0.0.9", "0.1.0-alpha", "0.1.0-rc.1"])
def test_old_client_is_rejected_before_authentication(tmp_path, version):
    world = make_world(tmp_path)
    with world.client() as client:
        response = client.get("/api/v1/me", headers={"SKM-Client-Version": version})
    assert response.status_code == 426
    assert response.json()["code"] == "CLIENT_TOO_OLD"
    assert response.json()["details"] == {"client_version": version, "min_version": "0.1.0"}
    assert response.headers["SKM-Api-Version"] == "1.0"


@pytest.mark.parametrize("version", [None, "0.1", __version__, "0.1.0+build", "0.2.0-alpha", "10.0.0"])
def test_current_or_unspecified_version_reaches_auth(tmp_path, version):
    headers = {} if version is None else {"SKM-Client-Version": version}
    with make_world(tmp_path).client() as client:
        assert client.get("/api/v1/me", headers=headers).status_code == 401


@pytest.mark.parametrize("version", ["garbage", "", "02.0.0", "2.0.0-01"])
def test_malformed_client_version_is_structured(tmp_path, version):
    with make_world(tmp_path).client() as client:
        result = client.get("/api/v1/me", headers={"SKM-Client-Version": version})
    assert result.status_code == 422
    assert result.json()["code"] == "SCHEMA_INVALID"
