import math

class BDRCalculator:
    @staticmethod
    def dbf_edf(tasks, t):
        """EDF需求边界函数（公式2）"""
        return sum(
            ( (t - task.deadline) // task.period + 1 ) * task.wcet
            for task in tasks
            if t >= task.deadline
        )

    @staticmethod
    def dbf_fps(tasks, t, task_index):
        """FPS需求边界函数（公式4）"""
        task = tasks[task_index]
        interference = sum(
            math.ceil(t / hp_task.period) * hp_task.wcet
            for hp_task in tasks[:task_index]
        )
        return task.wcet + interference

    @staticmethod
    def sbf_bdr(alpha, delta, t):
        """BDR资源供给函数(公式6)"""
        return max(0, alpha * (t - delta))