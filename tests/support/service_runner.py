"""Production background services in threads, bounded process supervision, no timing sleeps."""

import subprocess
from contextlib import AbstractContextManager
from threading import Event
from time import monotonic
from typing import override

from skm.adapters.secrets.env import EnvSecretResolver
from skm.application_bus.subscribers import DeliverySettings, OutboxRelayPass
from skm.background.lease_sweeper import LeaseSweeper
from skm.background.outbox_relay import OutboxRelayService
from skm.background.scheduler import Scheduler
from skm.background.service_runner import BackgroundService
from skm.background.service_runner import ServiceRunner as ProductionServiceRunner
from skm.background.timeout_enforcer import TimeoutEnforcer
from skm.modules.access.public import SYSTEM_ACTOR
from skm.platform.logging.logger import get_logger


class Instance:
    """Bounded observation with process diagnostics; all owned children are reaped on exit."""

    @staticmethod
    def wait_until(predicate, *, timeout=20, description="condition"):
        deadline, wake = monotonic() + timeout, Event()
        while True:
            value = predicate()
            if value:
                return value
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise AssertionError(f"timed out waiting for {description}")
            wake.wait(min(0.02, remaining))

    @staticmethod
    def kill(process):
        process.kill()
        process.wait(timeout=10)

    @staticmethod
    def stop(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                Instance.kill(process)


class ServiceRunner(AbstractContextManager):
    """Each restart constructs fresh services against the same committed database."""

    def __init__(self, side):
        app = side.app
        log = get_logger("tests.m3.services")
        registry = app.bus._registry
        services: list[BackgroundService] = [
            factory(app.bus, registry=registry, clock=side.clock, ids=app.bus._ids)
            for factory in (Scheduler, LeaseSweeper, TimeoutEnforcer)
        ]
        relay = OutboxRelayPass(
            registry=registry,
            uow_factory=app.uow_factory,
            config=app.config,
            settings=lambda: DeliverySettings(max_attempts=3, backoff_seconds=1, backoff_max_seconds=2),
            clock=side.clock,
            ids=app.bus._ids,
            gateways=app.gateways,
            log=log,
            relay_id=f"m3-{side.new_id()}",
            batch_size=100,
            secrets=EnvSecretResolver({}),
            dispatcher=app.bus,
            actor=SYSTEM_ACTOR,
        )
        services.append(OutboxRelayService(relay))
        self.runner = ProductionServiceRunner(
            services,
            intervals={service.name: 0.1 for service in services},
            clock=side.clock,
            log=log,
        )

    @override
    def __enter__(self):
        self.runner.start()
        return self

    def healthy(self):
        health = self.runner.health()
        failed = {name: item.last_error for name, item in health.items() if item.consecutive_failures >= 3}
        assert not failed, failed
        return all(item.last_ok_at is not None and item.last_error is None for item in health.values())

    @override
    def __exit__(self, *exc):
        self.runner.stop(timeout_seconds=15)
