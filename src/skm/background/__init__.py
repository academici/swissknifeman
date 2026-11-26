"""Background services: periodic ticks of outbox relay, lease, stall, timeout, janitor and autopilot work.

``service_runner.py`` owns the threaded lifecycle. Services hold no domain logic: they dispatch fresh
system bus commands or run tasks that bootstrap built for them, and import modules only through facades.
"""

__all__: list[str] = []
