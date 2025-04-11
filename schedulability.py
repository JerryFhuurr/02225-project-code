# schedulability.py
from models import Task, Component, Core
from bdr_calculator import BDRCalculator
from optimizer import BDRInterfaceOptimizer
import math


class ResponseAnalyzer:
    @classmethod
    def calculate_wcrt(cls, tasks, scheduler, component_budget):
        if scheduler == "RM":
            return cls._rm_response_time_analysis(tasks, component_budget)
        elif scheduler == "EDF":
            return cls._edf_response_time_analysis(tasks, component_budget)
        else:
            raise ValueError(f"未知的调度策略: {scheduler}")

    @staticmethod
    def _rm_response_time_analysis(tasks, component_budget):
        sorted_tasks = sorted(tasks, key=lambda x: x.period)  # Assuming Period = Priority for RM here
        schedulable = True

        for i, task in enumerate(sorted_tasks):
            task.schedulable = False  # 初始化状态
            # Use adjusted_wcet which includes core speed factor
            wcrt = task.adjusted_wcet
            iteration = 0
            MAX_ITERATIONS = 100  # Define a constant

            while True:
                prev_wcrt = wcrt
                # Calculate interference from higher priority tasks (lower period in this sort)
                interference = sum(math.ceil(prev_wcrt / t.period) * t.adjusted_wcet
                                   for t in sorted_tasks[:i])
                wcrt = task.adjusted_wcet + interference

                # *** FIX: Task schedulability depends on meeting its own period (deadline) ***
                # The component budget Q affects *how much* time tasks get overall within P,
                # implicitly limiting wcrt, but the direct check is against the task's period.
                task.schedulable = (wcrt <= task.period)

                # 收敛检查
                if abs(wcrt - prev_wcrt) < 1e-6:
                    break

                # 超时或发散检查
                if wcrt > task.period + 1e-6:  # Early exit if deadline missed
                    task.schedulable = False
                    break

                # 防止无限循环
                iteration += 1
                if iteration > MAX_ITERATIONS:
                    print(f"警告：任务 {task.task_name} 响应时间计算在 {MAX_ITERATIONS} 次迭代后未收敛 (R={wcrt:.2f})")
                    task.schedulable = False  # Mark as unschedulable if RTA doesn't converge
                    break

            task.wcrt = wcrt  # 记录最终响应时间 (Worst-Case Response Time)
            if not task.schedulable:
                schedulable = False
                print(f"[RM分析] {task.task_name} 不可调度: R={wcrt:.2f} > T={task.period}")
            # else:
            #     print(f"[RM分析] {task.task_name} 可调度: R={wcrt:.2f} <= T={task.period}")

        return schedulable

    @staticmethod
    def _edf_response_time_analysis(tasks, component_budget):
        # Calculate task utilization based on adjusted WCET
        total_util = sum(t.adjusted_wcet / t.period for t in tasks)

        # EDF utilization bound within the component's virtual processor is 1.0
        # (Assuming the component provides a virtual processor)
        # Note: This check doesn't use the component's budget/period directly here,
        # relying on the higher-level check in _component_analysis.
        if total_util > 1.0 + 1e-6:
            print(f"[EDF分析] 组件内任务总利用率超标: {total_util:.2f} > 1.0")
            for t in tasks:
                t.schedulable = False
            return False

        # Simplified EDF Response Time Check (often requires more complex analysis in hierarchical)
        # For basic EDF, WCRT is often approximated by WCET if Util <= 1.
        # A more accurate check involves processor demand analysis: sum(floor(t/Ti)*Ci) <= t
        schedulable = True
        for t in tasks:
            # Using adjusted_wcet as a proxy for WCRT under EDF (simplification!)
            t.wcrt = t.adjusted_wcet
            # *** FIX: Check against task period, not component budget ***
            t.schedulable = (t.wcrt <= t.period)
            if not t.schedulable:
                 print(f"[EDF分析] {t.task_name} 不可调度: R(近似)={t.wcrt:.2f} > T={t.period}")
                 schedulable = False
            # else:
            #    print(f"[EDF分析] {t.task_name} 可调度: R(近似)={t.wcrt:.2f} <= T={t.period}")

        return schedulable


class SchedulabilityAnalyzer:
    def __init__(self, cores):
        self.cores = {core.core_id: core for core in cores}
        self._validate_structure()

    def _validate_structure(self):
        """增强数据完整性检查"""
        if not self.cores:
             print("警告: No cores loaded.")
             return # Nothing to validate

        for core_id, core in self.cores.items():
            if not hasattr(core, 'components') or core.components is None:
                print(f"警告：核心 {core.core_id} 没有关联的组件。")
                core.components = []
            elif not isinstance(core.components, list):
                 raise TypeError(f"核心 {core.core_id} 的 components 属性必须是列表")

            for comp in core.components:
                if not hasattr(comp, 'tasks') or comp.tasks is None:
                     print(f"警告：组件 {comp.component_id} 没有关联的任务。")
                     comp.tasks = []
                elif not isinstance(comp.tasks, list):
                     raise TypeError(f"组件 {comp.component_id} 的 tasks 属性必须是列表")

                # Perform basic type and value checks here, complementing models.py
                # These might catch issues if models.py parsing had unexpected results
                if not isinstance(comp.budget, (int, float)) or comp.budget <= 0:
                     raise ValueError(f"结构验证失败: 组件 {comp.component_id} 预算({comp.budget})无效 (必须是 > 0 的数字)")
                if not isinstance(comp.period, (int, float)) or comp.period <= 0:
                     raise ValueError(f"结构验证失败: 组件 {comp.component_id} 周期({comp.period})无效 (必须是 > 0 的数字)")

                # --- FIX: Ensure this check is REMOVED or COMMENTED OUT ---
                # This check was too restrictive. Budget == Period (alpha=1) is valid.
                # Budget > Period results in a warning during BDR calculation.
                #
                # if comp.budget >= comp.period:
                #    raise ValueError(f"组件 {comp.component_id} 预算{comp.budget} ≥ 周期{comp.period}")
                # --- End of Fix ---

                # Validate component scheduler type
                if comp.scheduler not in {'RM', 'EDF'}:
                    raise ValueError(f"结构验证失败: 组件 {comp.component_id} 调度器 '{comp.scheduler}' 无效")


    # ... rest of SchedulabilityAnalyzer methods (_adjust_wcet, _calculate_bdr, etc.) ...

    def analyze(self):
        """增强分析流程"""
        print("===== 开始层次化可调度性分析 =====")
        # Validation is now done in __init__
        # self._validate_structure() # No need to call again if called in init

        self._adjust_wcet()
        self._calculate_bdr()
        # Pass self.cores directly if needed, or rely on instance attribute
        system_schedulable, results = self._hierarchical_verification()

        # 最终状态同步
        for core in self.cores.values():
            for comp in core.components:
                # Ensure schedulable status reflects reality if analysis failed partially
                if hasattr(comp, 'tasks') and comp.tasks:
                     comp.schedulable = all(t.schedulable for t in comp.tasks if hasattr(t, 'schedulable'))
                else:
                     comp.schedulable = True # Empty component is trivially schedulable

        return system_schedulable, results

    def _adjust_wcet(self):
        """增强WCET调整日志"""
        print("\n===== 调整任务WCET =====")
        for core in self.cores.values():
            print(f"[核心 {core.core_id}] 速度因子: {core.speed_factor}x")
            for comp in core.components:
                for task in comp.tasks:
                    original = task.nominal_wcet
                    task.adjusted_wcet = original / core.speed_factor
                    print(f"  {task.task_name}: {original:.1f} → {task.adjusted_wcet:.1f} "
                          f"(组件 {comp.component_id})")

    def _calculate_bdr(self):
        """增强BDR计算异常处理 (使用标准公式)"""
        print("\n===== 计算BDR参数 =====")
        for core in self.cores.values():
            print(f"[核心 {core.core_id}]")
            for comp in core.components:
                try:
                    # 参数检查
                    if comp.budget <= 0 or comp.period <= 0:
                        raise ValueError("预算和周期必须为正数")
                    if comp.budget > comp.period:
                         print(f"警告：组件 {comp.component_id} 预算 {comp.budget} > 周期 {comp.period}. "
                               f"Alpha将>1，Delta将<0.") # Allow but warn

                    # 标准 BDR 参数计算 (for periodic server)
                    # Alpha: Bandwidth (Q/P)
                    # Delta: Latency/Delay (P - Q, assuming worst-case finish time)
                    comp.alpha = comp.budget / comp.period
                    comp.delta = comp.period - comp.budget # Can be negative if Q > P

                    print(f"  {comp.component_id}: α={comp.alpha:.2f} δ={comp.delta:.1f} "
                          f"(Q={comp.budget}, P={comp.period})")
                except ZeroDivisionError:
                     print(f"错误：组件 {comp.component_id} 周期为零，无法计算BDR。")
                     comp.alpha = float('inf')
                     comp.delta = float('inf') # Indicate error
                except Exception as e:
                    print(f"错误：组件 {comp.component_id} BDR计算失败 - {str(e)}")
                    comp.alpha = float('inf')
                    comp.delta = float('inf') # Indicate error

    def _hierarchical_verification(self):
        """增强验证流程"""
        print("\n===== 层次化验证 =====")
        results = []
        system_schedulable = True

        for core in self.cores.values():
            # 核心级验证
            core_schedulable = self._core_analysis(core)
            results.append(f"核心 {core.core_id} ({core.scheduler}) {'可调度' if core_schedulable else '不可调度'}")
            system_schedulable &= core_schedulable

            # 组件级验证
            for comp in core.components:
                comp_schedulable = self._component_analysis(comp)
                results.append(f"  ├─组件 {comp.component_id}: {'可调度' if comp_schedulable else '不可调度'}")

                # 任务级验证
                for task in comp.tasks:
                    status = '可调度' if task.schedulable else f"不可调度 (R={task.wcrt:.1f}, T={task.period})"
                    results.append(f"  │   └─任务 {task.task_name}: {status}")

        return system_schedulable, results

    def _core_analysis(self, core):
        """增强核心级验证"""
        if core.scheduler == 'EDF':
            return self._edf_core_check(core)
        return self._rm_core_check(core)

    def _edf_core_check(self, core):
        """增强EDF核心检查"""
        total_util = sum(comp.budget / comp.period for comp in core.components)
        print(f"[EDF核心 {core.core_id}] 总利用率: {total_util:.2f}/1.0")

        if total_util > 1.0 + 1e-6:
            print(f"  ! 利用率超标: {total_util:.2f} > 1.0")
            return False
        return True

    def _rm_core_check(self, core):
        """增强RM核心检查"""
        print(f"[RM核心 {core.core_id}] 响应时间分析:")
        sorted_comps = sorted(core.components, key=lambda c: c.period)

        for i, comp in enumerate(sorted_comps):
            print(f"  分析组件 {comp.component_id} (P={comp.period}, Q={comp.budget})")
            rt = comp.budget
            iteration = 0

            while True:
                new_rt = comp.budget + sum(
                    math.ceil(rt / c.period) * c.budget
                    for c in sorted_comps[:i]
                )

                print(f"    迭代 {iteration}: R={rt:.1f} → {new_rt:.1f}")

                if new_rt > comp.period + 1e-6:
                    print(f"    ! 响应时间超标: {new_rt:.1f} > {comp.period}")
                    return False

                if abs(new_rt - rt) < 1e-6:
                    break

                rt = new_rt
                iteration += 1
                if iteration > 10:
                    print("    ! 迭代未收敛")
                    return False

        return True

    def _component_analysis(self, comp):
        """增强组件级验证"""
        # 利用率检查
        total_util = sum(t.adjusted_wcet / t.period for t in comp.tasks)
        server_util = comp.budget / comp.period

        print(f"[组件 {comp.component_id}] 利用率检查:"
              f"\n  任务总利用率: {total_util:.2f}"
              f"\n  服务器利用率: {server_util:.2f} (Q/P={comp.budget}/{comp.period})")

        if total_util > server_util + 1e-6:
            print(f"  ! 任务需求超过服务器供给: {total_util:.2f} > {server_util:.2f}")
            return False

        # 响应时间验证
        schedulable = ResponseAnalyzer.calculate_wcrt(comp.tasks, comp.scheduler, comp.budget)
        print(f"  响应时间验证结果: {'可调度' if schedulable else '不可调度'}")

        # 同步组件状态
        comp.schedulable = schedulable
        return schedulable