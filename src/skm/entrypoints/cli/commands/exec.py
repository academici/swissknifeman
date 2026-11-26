"""Start an ad hoc task with the default workflow."""

from skm.entrypoints.cli.commands import CommandGroup, SubParsers

from ._adhoc import register_args, start

__all__ = ["GROUP"]


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("exec", help="start an ad hoc task")
    register_args(parser)
    parser.set_defaults(run=start, command_name="execution.run_adhoc")


GROUP = CommandGroup("exec", "start an ad hoc task", register, module="execution", order=62)
