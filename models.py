class Task:
    def __init__(self, task_id, wcet, period, component, priority=0):
        """严格匹配 CSV 列名（移除 deadline 参数）"""
        if not isinstance(wcet, int) or wcet <= 0:
            raise ValueError(f"任务 {task_id} 的 WCET 必须为正整数")
        if not isinstance(period, int) or period <= 0:
            raise ValueError(f"任务 {task_id} 的周期必须为正整数")
        
        self.id = task_id
        self.wcet = wcet
        self.period = period
        self.deadline = period  # 关键修复：默认 deadline=period
        self.component = component
        self.priority = priority

class Component:
    def __init__(self, comp_id, algorithm, core_id, budget, period, priority=0):

        if not isinstance(budget, int) or budget <= 0:
            raise ValueError(f"组件 {comp_id} 的 budget 必须为正整数")
        if not isinstance(period, int) or period <= 0:
            raise ValueError(f"组件 {comp_id} 的 period 必须为正整数")
        
        algorithm = algorithm.strip().upper()
        if algorithm not in {'EDF', 'RM'}:
            raise ValueError(f"组件 {comp_id} 的调度算法无效: {algorithm}")
        
        self.id = comp_id
        self.algorithm = algorithm
        self.core_id = core_id
        self.budget = int(budget)
        self.period = int(period)
        self.priority = int(priority)
        self.tasks = []  # 从图片数据推断tasks需后续关联

class Core:
    def __init__(self, core_id, speed_factor, global_algorithm):
        """适配图片中的核心配置"""
        # 处理速度因子的小数精度（如图片中的1.49）
        self.speed_factor = round(float(speed_factor), 2)
        if self.speed_factor <= 0:
            raise ValueError(f"核心 {core_id} 速度因子必须>0，实际值: {speed_factor}")
        
        # 统一算法名称大小写（如"edf" → "EDF"）
        self.global_algorithm = global_algorithm.strip().upper()
        if self.global_algorithm not in {'EDF', 'RM'}:
            raise ValueError(f"核心 {core_id} 调度算法无效: {global_algorithm}")
        
        self.id = core_id
        self.components = []