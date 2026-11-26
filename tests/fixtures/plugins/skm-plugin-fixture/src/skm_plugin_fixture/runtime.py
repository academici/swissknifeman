"""A runtime that implements the AgentRuntime surface by shape only; its behaviour is never exercised."""

from skm.plugin_api import PluginContext


class FixtureRuntime:
    runtime_id = "fixture_rt"

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def capabilities(self):
        raise NotImplementedError

    def detect(self, probe):
        raise NotImplementedError

    def self_loaded_context(self, request):
        return ()

    def start(self, request):
        raise NotImplementedError

    def events(self, handle):
        raise NotImplementedError

    def cancel(self, handle, *, grace_seconds):
        raise NotImplementedError

    def result(self, handle):
        raise NotImplementedError
