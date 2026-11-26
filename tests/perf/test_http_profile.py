"""Open-loop HTTP load and streaming upload against one local skm serve process."""

import asyncio
import hashlib
from collections import Counter
from pathlib import Path
from threading import Event, Thread
from time import perf_counter

import httpx
import pytest

from support.processes import Instance

pytestmark = [pytest.mark.perf, pytest.mark.pg]
MIB = 1024 * 1024


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server(tmp_path, pg_dsn):
    with Instance(tmp_path / "server", db_dsn=pg_dsn, serve=False, worker=False) as instance:
        process = instance.start("serve")
        children = Path(f"/proc/{process.process.pid}/task/{process.process.pid}/children")
        (pid,) = map(int, children.read_text().split())
        yield instance, pid


def http(instance, **options):
    return httpx.AsyncClient(
        base_url=instance.url,
        headers={"Authorization": f"Bearer {instance.owner_token}"},
        trust_env=False,
        timeout=30,
        **options,
    )


async def open_loop(rate, seconds, operation):
    loop = asyncio.get_running_loop()
    origin = loop.time()

    async def invoke(i):
        due = origin + i / rate
        await asyncio.sleep(max(0, due - loop.time()))
        start = loop.time()
        result = await operation(i)
        return (loop.time() - start) * 1000, (start - due) * 1000, result

    return await asyncio.gather(*(invoke(i) for i in range(rate * seconds)))


def response_outcome(response):
    if response.is_success:
        return response.status_code, "", "", False
    try:
        problem = response.json()
    except ValueError:
        problem = {}
    return (
        response.status_code,
        problem.get("code", ""),
        problem.get("details", {}).get("reason", ""),
        (problem.get("retryable") is True),
    )


@pytest.mark.anyio
async def test_api_30_rps_and_100_rps_burst(server, measure):
    instance, _ = server
    async with http(
        instance, limits=httpx.Limits(max_connections=128, max_keepalive_connections=32)
    ) as client:
        root = f"/api/v1/workspaces/{instance.workspace_id}"
        warm = await client.get(root)
        assert warm.status_code == 200, warm.text
        for rate, seconds in ((30, 10), (100, 3)):

            async def operation(i, rate=rate):
                try:
                    if i % 2 == 0:
                        response = await client.get(root)
                    else:
                        slug = f"perf-{rate}-{i}"
                        response = await client.post(root + "/projects", json={"slug": slug, "title": slug})
                    return response_outcome(response)
                except httpx.TransportError as error:
                    return 0, type(error).__name__, "", False

            results = await open_loop(rate, seconds, operation)
            pool_timeouts = sum(reason == "pool_timeout" for _, _, (_, _, reason, _) in results)
            failures = Counter(
                (status, code, reason, retry)
                for _, _, (status, code, reason, retry) in results
                if not 200 <= status < 300
            )
            facts = {
                "rps": rate,
                "seconds": seconds,
                "pool_timeouts": pool_timeouts,
                "failures": [(*key, n) for key, n in sorted(failures.items())],
            }
            for name, selected in (("http_query_ms", results[::2]), ("http_command_ms", results[1::2])):
                measure(name, [ms for ms, _, _ in selected], **facts)
            measure("dispatch_lateness_ms", [lateness for _, lateness, _ in results], **facts)
            if rate == 30:
                assert not failures
                assert pool_timeouts == 0
            else:
                assert all(retry for _, _, _, retry in failures)


def _memory(pid):
    status = Path(f"/proc/{pid}/status").read_text().splitlines()
    return tuple(
        int(next(line for line in status if line.startswith(key)).split()[1]) for key in ("VmRSS:", "VmHWM:")
    )


@pytest.mark.anyio
async def test_upload_100_mib_rss(server, measure):
    instance, pid = server
    assert pid > 0
    data = bytes(range(256)) * 256  # 64 KiB, reused throughout the upload.
    results = []
    async with http(instance) as client:
        url = f"/api/v1/workspaces/{instance.workspace_id}/blobs"
        for mib in (1, 10, 100, 10, 100, 10, 100):
            size = mib * MIB
            parts = size // len(data)
            digest = hashlib.sha256()
            for _ in range(parts):
                digest.update(data)

            async def content(parts=parts):
                for _ in range(parts):
                    yield data

            baseline, hwm_before = _memory(pid)
            rss = [baseline]
            done = Event()

            def sample(done=done, rss=rss):
                while not done.wait(0.005):
                    rss.append(_memory(pid)[0])

            sampler = Thread(target=sample)
            sampler.start()
            start = perf_counter()
            try:
                response = await client.post(
                    url,
                    content=content(),
                    headers={
                        "Content-Length": str(size),
                        "Content-Type": "application/octet-stream",
                        "Idempotency-Key": f"perf-upload-{len(results)}",
                        "SKM-Expected-Digest": f"sha256:{digest.hexdigest()}",
                    },
                )
            finally:
                elapsed = (perf_counter() - start) * 1000
                done.set()
                sampler.join()
            rss_after, hwm_after = _memory(pid)
            rss.append(rss_after)
            growth_mib = (max(*rss, hwm_after if hwm_after > hwm_before else baseline) - baseline) / 1024
            facts = {
                "size_mib": mib,
                "status": response.status_code,
                "elapsed_ms": round(elapsed, 3),
                "hwm_before_kib": hwm_before,
                "hwm_after_kib": hwm_after,
            }
            measure("upload_rss_kib", rss, **facts)
            assert response.status_code == 201, response.text
            assert response.json()["size"] == size
            assert response.json()["digest"] == f"sha256:{digest.hexdigest()}"
            results.append((mib, growth_mib, elapsed))
    for size in (10, 100):
        measure("upload_ms", [t for mib, _, t in results if mib == size], size_mib=size)
        measure("upload_peak_growth_mib", [delta for mib, delta, _ in results if mib == size], size_mib=size)
    # A full payload copy would increase RSS by about 90 MiB over the 10 MiB probe.
    assert max(delta for mib, delta, _ in results if mib == 100) < 25
