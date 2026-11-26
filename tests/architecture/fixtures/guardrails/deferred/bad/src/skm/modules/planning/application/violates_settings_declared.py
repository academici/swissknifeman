from ..generated.settings import WrongView as View

def run(ctx):
    ctx.config.get('planning.typo')
    return ctx.config.section(View)
