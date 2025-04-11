# models.py
import pandas as pd


class Task:
    def __init__(self, task_name, wcet, period, component_id, priority=None):
        self._validate_input(task_name, wcet, period, component_id)

        self.task_name = str(task_name)
        self.nominal_wcet = float(wcet)
        self.period = float(period)
        self.component_id = str(component_id)
        self.priority = self._parse_priority(priority)

        # 运行时属性
        self.adjusted_wcet = None
        self.wcrt = 0.0
        self.schedulable = False

    def _validate_input(self, name, wcet, period, comp_id):
        if pd.isna(name) or not name.strip():
            raise ValueError("任务名称不能为空")
        if not isinstance(wcet, (int, float)) or wcet <= 0 or pd.isna(wcet):
            raise ValueError(f"任务 {name} 的WCET必须为正数")
        if not isinstance(period, (int, float)) or period <= 0 or pd.isna(period):
            raise ValueError(f"任务 {name} 的周期必须为正数")
        if pd.isna(comp_id):
            raise ValueError("组件ID不能为空")

    def _parse_priority(self, priority):
        if pd.isna(priority) or priority is None:
            return None
        try:
            return int(float(priority))
        except:
            raise ValueError(f"无效优先级格式: {priority}")


class Component:
    def __init__(self, component_id, scheduler, core_id, budget, period, priority=None):
        self._validate_input(component_id, scheduler, core_id, budget, period)

        self.component_id = str(component_id)
        self.scheduler = str(scheduler).upper()
        self.core_id = str(core_id)
        self.budget = float(budget)
        self.period = float(period)
        # Call the modified _parse_priority
        self.priority = self._parse_priority(priority) # Store the parsed priority

        # Runtime properties
        self.tasks = []
        self.alpha = None
        self.delta = None
        self.schedulable = False

    def _validate_input(self, cid, sched, core_id, budget, period):
        if pd.isna(cid) or not cid.strip():
            raise ValueError("组件ID不能为空")
        if pd.isna(core_id):
            raise ValueError("核心ID不能为空")
        # Allow RM or EDF
        valid_schedulers = {'RM', 'EDF'}
        if sched is None or str(sched).upper() not in valid_schedulers:
             raise ValueError(f"无效调度策略: '{sched}'. Must be one of {valid_schedulers}")
        if pd.isna(budget) or not isinstance(budget, (int, float)) or budget <= 0:
            raise ValueError(f"组件 {cid} 预算无效: {budget}")
        if pd.isna(period) or not isinstance(period, (int, float)) or period <= 0:
            raise ValueError(f"组件 {cid} 周期无效: {period}")

    def _parse_priority(self, priority):
        """Parses priority, allowing it even for EDF components."""
        if pd.isna(priority) or priority is None or str(priority).strip() == "":
            # Consider empty string as None as well
            return None
        try:
            # Convert to float first to handle potential decimals before int conversion
            prio = int(float(priority))
            # --- REMOVED THE CHECK THAT PREVENTED EDF COMPONENTS FROM HAVING PRIORITY ---
            # # Original check:
            # if self.scheduler == 'EDF' and prio is not None:
            #     # This rule is too strict if priority is for core-level scheduling
            #     raise ValueError(f"EDF组件不应设置优先级: {self.component_id}")
            return prio
        except (ValueError, TypeError) as e:
             # Catch conversion errors and provide a clear message
            raise ValueError(f"无效优先级格式 '{priority}' for component {self.component_id}: {e}")


class Core:
    def __init__(self, core_id, speed_factor, scheduler):
        self._validate_input(core_id, speed_factor, scheduler)

        self.core_id = str(core_id)
        self.speed_factor = float(speed_factor)
        self.scheduler = str(scheduler).upper()

        # 运行时属性
        self.components = []

    def _validate_input(self, cid, speed, sched):
        if pd.isna(cid):
            raise ValueError("核心ID不能为空")
        if pd.isna(speed) or speed <= 0:
            raise ValueError(f"核心 {cid} 速度因子无效")
        if sched.upper() not in {'RM', 'EDF'}:
            raise ValueError(f"无效调度策略: {sched}")