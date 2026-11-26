"""The conductor: a deterministic driver that takes pieces of work from the work source and runs each one through a
chain of roles (context, scout, executor, checks, review, triage, correction, registration, commit) until it is green
or stops honestly. It branches only on exit codes, on the verdicts of the closed role results and on the limits of the
run options; models are used for the narrow roles only (docs/conductor.md).
"""
from __future__ import annotations

CONTRACT_URN = "urn:swissknifeman:orch:conductor"
