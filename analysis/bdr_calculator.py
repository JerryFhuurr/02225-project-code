# bdr_calculator.py
import math

class BDRCalculator:
    @staticmethod
    def dbf_edf(tasks, t):
        """精确的EDF需求函数计算"""
        return sum(
            (math.floor((t - task.period) / task.period) + 1) * task.adjusted_wcet
            for task in tasks
            if t >= task.period
        )

    @staticmethod
    def dbf_fps(tasks, t, task_index):
        """改进的固定优先级需求计算"""
        task = tasks[task_index]
        interference = 0.0
        for hp_task in tasks[:task_index]:
            if hp_task.priority > task.priority:
                interference += math.ceil(t / hp_task.period) * hp_task.adjusted_wcet
        return task.adjusted_wcet + interference

    @staticmethod
    def sbf_bdr(alpha, delta, t):
        """修正后的供给函数（移除速度因子错误应用）"""
        return max(0.0, alpha * (t - delta))