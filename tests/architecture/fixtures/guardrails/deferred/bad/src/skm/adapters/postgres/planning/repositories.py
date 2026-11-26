from skm.modules.planning.ports import PlanRepository

class PostgresPlanRepository(PlanRepository):
    def get(self, identity):
        return identity
