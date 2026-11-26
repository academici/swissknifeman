from skm.modules.planning.ports import PlanRepository
from .repositories import MemoryPlanRepository

REPOSITORIES = {PlanRepository: MemoryPlanRepository}
