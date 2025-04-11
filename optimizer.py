# optimizer.py
import numpy as np
import math
from bdr_calculator import BDRCalculator

class BDRInterfaceOptimizer:
    def __init__(self, component, core_speed_factor):
        self.component = component
        self.speed = core_speed_factor
        self.max_t = self._safe_max_t()

    def _safe_max_t(self):
        """安全计算最大分析时间"""
        if self.component.period <= 0:
            raise ValueError(f"组件 {self.component.component_id} 周期无效: {self.component.period}")
        return min(3 * self.component.period, 1000.0)

    def find_min_delta(self):
        """安全参数优化"""
        if self.component.budget >= self.component.period:
            return float('inf'), self.component.period

        best_alpha = float('inf')
        best_delta = self.component.period
        step = 0.1

        try:
            for delta in np.arange(self.component.period, self.max_t + step, step):
                supply = (delta // self.component.period) * self.component.budget + min(delta % self.component.period, self.component.budget)
                if supply <= 0:
                    continue

                # 需求计算
                if self.component.scheduler == 'EDF':
                    demand = BDRCalculator.dbf_edf(self.component.tasks, delta)
                else:
                    demand = max(BDRCalculator.dbf_fps(self.component.tasks, delta, i) for i in range(len(self.component.tasks)))

                current_alpha = demand / supply
                if current_alpha < best_alpha:
                    best_alpha = current_alpha
                    best_delta = delta

            return best_alpha, best_delta
        except Exception as e:
            raise RuntimeError(f"参数优化失败: {str(e)}")