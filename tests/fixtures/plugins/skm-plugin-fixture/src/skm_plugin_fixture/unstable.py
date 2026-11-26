"""Deliberately imports an unstable surface: the negative example of ``skm plugins lint``; never imported."""

from skm.modules.runtimes.public import RuntimeId

FIXTURE_RUNTIME = RuntimeId("fixture_rt")
