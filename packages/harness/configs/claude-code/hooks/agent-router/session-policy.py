#!/usr/bin/env python3
"""Compatibility entrypoint for installed SessionStart registrations.

Task is explicitly invoked through native commands/skills. Session startup must
not inject a routing policy, including for legacy propose/auto_dispatch settings.
"""


def main():
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
