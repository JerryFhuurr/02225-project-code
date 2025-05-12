# This file contains the SchedulabilityAnalyzer class and the ResponseAnalyzer class.

from models import Task, Component, Core
from bdr_calculator import BDRCalculator
import math
import sys  # For sys.float_info.epsilon


class ResponseAnalyzer:
    @classmethod
    def calculate_wcrt(cls, tasks, scheduler, component_obj):  # Changed to pass component_obj
        if not tasks:
            return True  # Vacuously schedulable

        if not all(isinstance(t, Task) for t in tasks):
            raise TypeError("Non-Task object found in tasks list for WCRT calculation.")
        if not all(hasattr(t, 'adjusted_wcet') and hasattr(t, 'period') for t in tasks):
            raise AttributeError("One or more tasks missing adjusted_wcet or period for WCRT calc.")

        if scheduler == "RM":
            if component_obj.supply_alpha is None or component_obj.supply_delta is None:
                # This case should ideally be caught before calling calculate_wcrt,
                # e.g., in _component_analysis if BDR params are invalid.
                for task in tasks: task.schedulable = False; task.wcrt = float('inf')
                return False
            return cls._rm_rta_bdr(tasks, component_obj.supply_alpha, component_obj.supply_delta)
        elif scheduler == "EDF":
            # For EDF components, schedulability is determined by DBF/SBF in _component_analysis.
            # WCRT is not directly calculated by that method.
            # This path is less critical if _component_analysis handles EDF task properties.
            # If called, it implies a fallback or a different analysis path.
            # For now, assume _component_analysis sets EDF task properties.
            return True  # Schedulability is determined elsewhere for EDF by DBF/SBF
        else:
            raise ValueError(f"Unknown component scheduler for WCRT: {scheduler}")

    @staticmethod
    def _rm_rta_bdr(tasks, supply_alpha, supply_delta):
        """Performs RM RTA considering BDR supply (alpha, delta)."""
        if supply_alpha <= 0 + sys.float_info.epsilon:
            # print(f"    ! RM RTA BDR: Supply alpha ({supply_alpha:.3f}) is zero or negative. All tasks unschedulable.")
            for task in tasks: task.wcrt = float('inf'); task.schedulable = False
            return False

        sorted_tasks = sorted(
            tasks,
            key=lambda x: (x.priority if x.priority is not None else float('inf'), x.period)
        )

        component_level_schedulable = True
        for i, tk in enumerate(sorted_tasks):
            C, T, name = tk.adjusted_wcet, tk.period, tk.task_name
            if C < 0:  # Should be caught by validation, but defensive
                tk.wcrt = float('inf');
                tk.schedulable = False;
                component_level_schedulable = False;
                continue
            if C == 0:  # Task with no execution time
                tk.wcrt = 0.0
                tk.schedulable = True
                continue

            if supply_alpha <= 0:  # Double check, though covered above
                tk.wcrt = float('inf');
                tk.schedulable = False;
                component_level_schedulable = False;
                continue

            R = (C / supply_alpha) + supply_delta
            iteration = 0;
            MAX_ITERATIONS_RTA_BDR = 100

            while True:
                iteration += 1
                I = 0.0
                for th in sorted_tasks[:i]:
                    if th.period > 0:
                        I += math.ceil(R / th.period) * th.adjusted_wcet

                D = C + I
                Rn = (D / supply_alpha) + supply_delta

                if abs(Rn - R) < 1e-9:
                    R = Rn
                    break
                if Rn > T + 1e-9:
                    R = Rn
                    break
                if iteration > MAX_ITERATIONS_RTA_BDR:
                    R = float('inf')
                    break
                R = Rn

            tk.wcrt = R
            tk.schedulable = (R <= T + 1e-9)

            if not tk.schedulable:
                component_level_schedulable = False

        return component_level_schedulable


class SchedulabilityAnalyzer:
    def __init__(self, cores):
        if not cores or not isinstance(cores, list) or not all(isinstance(c, Core) for c in cores):
            raise TypeError("SchedulabilityAnalyzer expects a list of Core objects.")
        self.cores = {core.core_id: core for core in cores}
        self._validate_structure()

    def _validate_structure(self):
        if not self.cores: return  # Allow empty core list
        for core_id, core in self.cores.items():
            if not hasattr(core, 'components') or not isinstance(core.components, list):
                raise TypeError(f"Core {core_id} 'components' missing/not list.")
            for comp in core.components:
                if not isinstance(comp, Component): raise TypeError(f"Core {core_id} has non-Component.")
                if not hasattr(comp, 'tasks') or not isinstance(comp.tasks, list):
                    raise TypeError(f"Comp {comp.component_id} 'tasks' missing/not list.")
                for task in comp.tasks:
                    if not isinstance(task, Task): raise TypeError(f"Comp {comp.component_id} has non-Task.")
                    if task.nominal_wcet < 0:  # wcet can be 0
                        raise ValueError(f"Task {task.task_name} invalid WCET {task.nominal_wcet}.")
                    if task.period <= 0:
                        raise ValueError(f"Task {task.task_name} invalid Period {task.period}.")
                if comp.budget <= 0 or comp.period <= 0: raise ValueError(
                    f"Comp {comp.component_id} invalid Budget/Period.")
                if comp.scheduler not in {'RM', 'EDF'}: raise ValueError(f"Comp {comp.component_id} invalid scheduler.")
            if core.speed_factor <= 0: raise ValueError(f"Core {core_id} invalid speed factor.")
            if core.scheduler not in {'RM', 'EDF'}: raise ValueError(f"Core {core_id} invalid scheduler.")

    def analyze(self):
        self._adjust_wcet()
        self._calculate_supply_bdr()
        self._calculate_demand_bdr()  # Calculates demand properties, does not decide schedulability here

        system_schedulable, results = self._hierarchical_verification()

        for core in self.cores.values():
            if core.components:
                core.schedulable = all(c.schedulable for c in core.components if hasattr(c, 'schedulable'))
            else:
                core.schedulable = True
        return system_schedulable, results

    def _adjust_wcet(self):
        for core in self.cores.values():
            if core.speed_factor == 0:
                raise ValueError(f"Core {core.core_id} speed factor is 0, cannot adjust WCETs.")
            for comp in core.components:
                for task in comp.tasks:
                    if task.nominal_wcet == 0:
                        task.adjusted_wcet = 0.0
                    else:
                        task.adjusted_wcet = task.nominal_wcet / core.speed_factor
                    if task.adjusted_wcet < 0:
                        task.schedulable = False;
                        task.wcrt = float('inf');
                        comp.schedulable = False;
                        core.schedulable = False

    def _calculate_supply_bdr(self):
        for core in self.cores.values():
            for comp in core.components:
                try:
                    if comp.period <= 0: raise ValueError("Component period must be positive.")
                    if comp.budget < 0: raise ValueError("Component budget must be non-negative.")  # Allow Q=0

                    comp.supply_alpha = comp.budget / comp.period if comp.period > 0 else float(
                        'inf')  # Avoid div by zero
                    if comp.budget == 0: comp.supply_alpha = 0.0

                    comp.supply_delta = 2 * (comp.period - comp.budget)
                except Exception:  # Catch any error during calculation
                    comp.supply_alpha = None
                    comp.supply_delta = None
                    comp.schedulable = False

    def _calculate_demand_bdr(self):
        """Calculates component internal demand alpha and delta. Does not set schedulability."""
        for core in self.cores.values():
            for comp in core.components:
                # comp.schedulable is not touched here based on demand properties.
                # It's determined later in _component_analysis.
                try:
                    if not comp.tasks:
                        comp.demand_alpha = 0.0
                        comp.demand_delta = 0.0
                        continue

                    comp.demand_alpha = sum(
                        t.adjusted_wcet / t.period for t in comp.tasks if t.period > 0 and t.adjusted_wcet >= 0)

                    comp.demand_delta = max(t.adjusted_wcet for t in comp.tasks if t.adjusted_wcet >= 0) if \
                        any(t.adjusted_wcet >= 0 for t in comp.tasks) else 0.0

                    # This check is implicitly handled by _component_analysis.
                    # If demand_alpha > supply_alpha, RM RTA or EDF DBF/SBF will fail.
                    # No need to set comp.schedulable = False here.
                    # if comp.supply_alpha is not None and comp.demand_alpha > comp.supply_alpha + 1e-9:
                    #     pass # This will be caught by _component_analysis

                except Exception:  # Catch any error during calculation
                    comp.demand_alpha = float('inf');
                    comp.demand_delta = float('inf');

    def _hierarchical_verification(self):
        results = [];
        overall_system_schedulable = True

        # --- Component Level Analysis (Internal Task Schedulability) ---
        for core in self.cores.values():
            for comp in core.components:
                # _component_analysis is now solely responsible for comp.schedulable
                # and related task properties based on internal analysis.
                self._component_analysis(comp)

                if not comp.schedulable:
                    overall_system_schedulable = False

        # --- Core Level Analysis (Component Composition on Core) ---
        for core_id, core in self.cores.items():
            if not core.components:
                core.schedulable = True
                continue

            all_comps_internally_sched = all(c.schedulable for c in core.components)
            if not all_comps_internally_sched:
                core.schedulable = False
                overall_system_schedulable = False
                continue

            core_composition_status = self._core_composition_analysis(core)
            core.schedulable = core_composition_status
            if not core_composition_status:
                overall_system_schedulable = False

        return overall_system_schedulable, results

    def _core_composition_analysis(self, core):
        """Analyzes schedulability of components on a core, matching Analyzer.py."""
        if not core.components:  # Should be caught by caller
            return True

        component_supply_alphas = []
        component_supply_deltas = []

        for comp in core.components:
            if comp.supply_alpha is None or comp.supply_delta is None:
                # This indicates an issue in _calculate_supply_bdr or component data
                return False
            component_supply_alphas.append(comp.supply_alpha)
            component_supply_deltas.append(comp.supply_delta)

        if not component_supply_alphas:  # Should not happen if core.components is not empty
            return False

        sum_alpha_supply = sum(component_supply_alphas)
        min_delta_supply = min(component_supply_deltas) if component_supply_deltas else 0

        utilization_ok = (sum_alpha_supply <= 1.0 + 1e-9)
        delta_ok = (min_delta_supply >= 0.0 - 1e-9)

        core_sched = utilization_ok and delta_ok
        return core_sched

    def _component_analysis(self, comp):
        """
        Analyzes internal schedulability of tasks within a component using its BDR supply.
        Sets comp.schedulable and task.schedulable, task.wcrt.
        This is the primary decider for component internal schedulability.
        """
        # Initialize component schedulability to False. It will be set True if analysis passes.
        comp.schedulable = False  # Start with False, prove True.

        if not comp.tasks:
            comp.schedulable = True  # Vacuously schedulable
            return  # comp.schedulable is True

        alpha_supply, delta_supply = comp.supply_alpha, comp.supply_delta
        if alpha_supply is None or delta_supply is None or alpha_supply < 0:  # alpha can be 0 if budget is 0
            # Invalid BDR parameters mean component cannot be schedulable.
            # Tasks within it are also unschedulable.
            for task in comp.tasks: task.schedulable = False; task.wcrt = float('inf')
            comp.schedulable = False  # Already False, but explicit.
            return  # comp.schedulable remains False

        internal_analysis_passed = False
        if comp.scheduler == "EDF":
            tasks_wcet_period = []
            max_period = 0
            has_positive_wcet_task = False
            for t in comp.tasks:
                if t.period > 0 and t.adjusted_wcet >= 0:
                    tasks_wcet_period.append((t.adjusted_wcet, t.period))
                    if t.adjusted_wcet > 0: has_positive_wcet_task = True
                    if t.period > max_period:
                        max_period = t.period

            if not tasks_wcet_period and not has_positive_wcet_task:  # No tasks or only zero-WCET tasks
                internal_analysis_passed = True
            elif alpha_supply <= 0 + 1e-9 and has_positive_wcet_task:  # No supply but demand exists
                internal_analysis_passed = False
            else:
                check_limit = int(5 * max_period)
                if check_limit == 0 and tasks_wcet_period: check_limit = 1000

                dbf_sbf_ok = True
                if has_positive_wcet_task:  # Only run check if there's actual demand
                    for t_check in range(1, check_limit + 1):
                        demand = BDRCalculator.dbf_edf(tasks_wcet_period, t_check)
                        supply = BDRCalculator.sbf_bdr(alpha_supply, delta_supply, t_check)

                        if demand > supply + 1e-9:
                            dbf_sbf_ok = False;
                            break
                internal_analysis_passed = dbf_sbf_ok

            if internal_analysis_passed:
                comp.schedulable = True
                for task in comp.tasks:
                    task.schedulable = True
                    task.wcrt = task.period  # Approximation for EDF WCRT
            else:
                comp.schedulable = False  # Redundant if already false, but explicit
                for task in comp.tasks:
                    task.schedulable = False;
                    task.wcrt = float('inf')

        elif comp.scheduler == "RM":
            # ResponseAnalyzer.calculate_wcrt handles RM and updates task.wcrt, task.schedulable
            # It returns True if all tasks in component are schedulable, False otherwise.
            component_rm_schedulable = ResponseAnalyzer.calculate_wcrt(comp.tasks, "RM", comp)
            comp.schedulable = component_rm_schedulable
            # Task properties (schedulable, wcrt) are set within _rm_rta_bdr

        else:
            # Unsupported scheduler, mark component and tasks as unschedulable
            comp.schedulable = False
            for task in comp.tasks: task.schedulable = False; task.wcrt = float('inf')
            raise ValueError(f"Unsupported component scheduler: {comp.scheduler} for component {comp.component_id}")

        return  # comp.schedulable is now set