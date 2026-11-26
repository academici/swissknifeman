"""Pick a runtime route through the shared routing query."""

from skm.entrypoints.cli.commands import CommandGroup, SubParsers

from .runtime import register_route_args, route_pick

__all__ = ["GROUP"]


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("route", help="inspect runtime routing")
    verbs = parser.add_subparsers(dest="route_verb", required=True)
    pick = verbs.add_parser("pick", help="pick and explain a runtime route")
    register_route_args(pick)
    pick.set_defaults(run=route_pick, command_name="runtimes.explain_routing")


GROUP = CommandGroup("route", "inspect runtime routing", register, module="runtimes", order=66)
