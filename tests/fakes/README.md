# Deterministic test doubles

These are test-only implementations of ports. [clock.py](clock.py) provides
`FrozenClock` and `FakeMonotonic`; [ids.py](ids.py) provides `SequentialIds`,
and [entropy.py](entropy.py) provides deterministic entropy. Construct new mutable
instances for each test. Never import donor packages or substitute a passing
dummy for behavior under test.

[app.py](app.py) builds a real in-memory bus, seeded UoW and embedded client around
the [demo module](demo_module/__init__.py), with controllable authorization/config:

```python
from fakes.app import build_harness
from fakes.demo_module import Echo, EchoResult

harness = build_harness()
result = harness.client.dispatch(Echo(harness.seed.workspace_id, "hello"))
assert result == EchoResult("hello")
```

This core harness is for bus contracts; module behavior belongs in
`tests/contracts/<owner>/harness.py`. For memory/PostgreSQL parity use
[support.backend](../support/README.md). Production composition has its own
authorization; a fake's configurable permission set does not validate that path.
