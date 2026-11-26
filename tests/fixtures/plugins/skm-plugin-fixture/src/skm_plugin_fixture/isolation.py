"""A sandbox profile ``acme.fixture:jail`` with the Isolation surface by shape only."""


class FixtureIsolation:
    profile = "acme.fixture:jail"

    def available(self, host):
        raise NotImplementedError

    def wrap(self, argv, spec):
        raise NotImplementedError
