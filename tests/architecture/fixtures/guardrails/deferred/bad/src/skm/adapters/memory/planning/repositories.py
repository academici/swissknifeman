from skm.modules.planning.ports import PlanRepository

class MemoryPlanRepository(PlanRepository):
    def get(self, identity):
        return identity
