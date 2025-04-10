import math
from bdr_calculator import BDRCalculator

class BDRInterfaceOptimizer:
    def __init__(self, tasks, algorithm, budget, period, max_t):
        self.tasks = tasks
        self.algorithm = algorithm
        self.budget = budget
        self.period = period
        self.max_t = max_t

    def find_min_delta(self):
        """核心修复：基于预算/周期模型计算资源供给"""
        for delta in range(1, self.max_t + 1):
            # 计算资源供给量（预算/周期模型）
            supply = (delta // self.period) * self.budget + min(delta % self.period, self.budget)
            
            # 计算需求函数（根据调度算法）
            if self.algorithm == 'EDF':
                demand = BDRCalculator.dbf_edf(self.tasks, delta)
            else:
                demand = max(BDRCalculator.dbf_fps(self.tasks, delta, i) for i in range(len(self.tasks)))
            
            if supply >= demand:
                alpha = demand / supply
                return alpha, delta
        return None, None