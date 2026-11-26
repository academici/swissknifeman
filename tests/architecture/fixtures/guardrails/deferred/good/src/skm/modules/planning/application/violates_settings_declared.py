from ..generated.settings import PlanningSettings as View

def run(ctx):
    ctx.config.get('planning.depth')
    return ctx.config.section(View)
