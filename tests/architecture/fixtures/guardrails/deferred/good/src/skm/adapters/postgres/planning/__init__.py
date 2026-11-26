from skm.modules.planning.ports import PlanRepository
from .repositories import PostgresPlanRepository

REPOSITORIES = {PlanRepository: PostgresPlanRepository}
