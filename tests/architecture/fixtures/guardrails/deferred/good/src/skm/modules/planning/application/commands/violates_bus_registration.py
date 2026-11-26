from skm.application_bus.registry import CommandSpec

SPEC = CommandSpec(name='planning.sample', permission='plan.read')

def handle(ctx, cmd):
    return cmd
