# bdr_calculator.py
import math

class BDRCalculator:
    @staticmethod
    def dbf_edf(tasks, t):
        """EDF demand calculation"""
        return sum(
            (math.floor((t - task.period) / task.period) + 1) * task.adjusted_wcet
            for task in tasks
            if t >= task.period
        )

    @staticmethod
    def dbf_fps(tasks, t, task_index):
        """Fixed-priority calculation"""
        task = tasks[task_index]
        interference = 0.0
        for hp_task in tasks[:task_index]:
            if hp_task.priority > task.priority:
                interference += math.ceil(t / hp_task.period) * hp_task.adjusted_wcet
        return task.adjusted_wcet + interference

    @staticmethod
    def sbf_bdr(alpha, delta, t):
        return max(0.0, alpha * (t - delta))