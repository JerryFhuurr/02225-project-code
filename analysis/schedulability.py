import math


class ResponseAnalyzer:
    @classmethod
    def calculate_wcrt(cls, tasks, scheduler, component_budget):
        if scheduler == "RM":
            return cls._rm_response_time_analysis(tasks, component_budget)
        elif scheduler == "EDF":
            return cls._edf_response_time_analysis(tasks, component_budget)
        else:
            raise ValueError(f"Unknown scheduling strategy: {scheduler}")

    @staticmethod
    def _rm_response_time_analysis(tasks, component_budget):
        sorted_tasks = sorted(tasks, key=lambda x: x.period)  # Assuming Period = Priority for RM here
        schedulable = True

        for i, task in enumerate(sorted_tasks):
            task.schedulable = False  # initialize
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
                task.schedulable = (wcrt <= task.period)

                # Convergence check
                if abs(wcrt - prev_wcrt) < 1e-6:
                    break

                # Time-out or dispersion check
                if wcrt > task.period + 1e-6:  # Early exit if deadline missed
                    task.schedulable = False
                    break

                # Preventing infinite loops
                iteration += 1
                if iteration > MAX_ITERATIONS:
                    print(f"Warning: Task {task.task_name} Response time calculation no convergence after {MAX_ITERATIONS} iterations (R={wcrt:.2f})")
                    task.schedulable = False  # Mark as unschedulable if RTA doesn't converge
                    break

            task.wcrt = wcrt  # Worst-Case Response Time
            if not task.schedulable:
                schedulable = False
                print(f"[RM Analysis] {task.task_name} unschedulable: R={wcrt:.2f} > T={task.period}")

        return schedulable

    @staticmethod
    def _edf_response_time_analysis(tasks, component_budget):
        # Calculate task utilization based on adjusted WCET
        total_util = sum(t.adjusted_wcet / t.period for t in tasks)

        # EDF utilization bound within the component's virtual processor is 1.0
        if total_util > 1.0 + 1e-6:
            print(f"[EDF Analysis] Total Task Utilization Exceeded Within Component: {total_util:.2f} > 1.0")
            for t in tasks:
                t.schedulable = False
            return False

        # EDF Response Time Check (often requires more complex analysis in hierarchical)
        schedulable = True
        for t in tasks:
            # Using adjusted_wcet as a proxy for WCRT under EDF (simplification!)
            t.wcrt = t.adjusted_wcet
            # *** FIX: Check against task period, not component budget ***
            t.schedulable = (t.wcrt <= t.period)
            if not t.schedulable:
                 print(f"[EDF Analysis] {t.task_name} unschedulable: R={t.wcrt:.2f} > T={t.period}")
                 schedulable = False

        return schedulable


class SchedulabilityAnalyzer:
    def __init__(self, cores):
        self.cores = {core.core_id: core for core in cores}
        self._validate_structure()

    def _validate_structure(self):
        """data integrity checks"""
        if not self.cores:
             print("Warning: No cores loaded.")
             return # Nothing to validate

        for core_id, core in self.cores.items():
            if not hasattr(core, 'components') or core.components is None:
                print(f"Waning: Core {core.core_id} has no associated components.")
                core.components = []
            elif not isinstance(core.components, list):
                 raise TypeError(f"Core {core.core_id} components must be a list")

            for comp in core.components:
                if not hasattr(comp, 'tasks') or comp.tasks is None:
                     print(f"Warning: Component {comp.component_id} has no associated tasks.")
                     comp.tasks = []
                elif not isinstance(comp.tasks, list):
                     raise TypeError(f"Component {comp.component_id} tasks must be a list")

                # Perform basic type and value checks here, complementing models.py
                # These might catch issues if models.py parsing had unexpected results
                if not isinstance(comp.budget, (int, float)) or comp.budget <= 0:
                     raise ValueError(f"Structure validation failed: Component {comp.component_id} budget({comp.budget})is invalid (must be a number > 0)")
                if not isinstance(comp.period, (int, float)) or comp.period <= 0:
                     raise ValueError(f"Structure validation failed: Component {comp.component_id} period({comp.period})is invalid (must be a number > 0)")

                # Validate component scheduler type
                if comp.scheduler not in {'RM', 'EDF'}:
                    raise ValueError(f"Structure validation failed: Component {comp.component_id} scheduler '{comp.scheduler}' is invalid")

    def analyze(self):
        print("===== Beginning Schedulability Analysis =====")

        self._adjust_wcet()
        self._calculate_bdr()
        # Pass self.cores directly if needed, or rely on instance attribute
        system_schedulable, results = self._hierarchical_verification()

        for core in self.cores.values():
            for comp in core.components:
                # Ensure schedulable status reflects reality if analysis failed partially
                if hasattr(comp, 'tasks') and comp.tasks:
                     comp.schedulable = all(t.schedulable for t in comp.tasks if hasattr(t, 'schedulable'))
                else:
                     comp.schedulable = True # Empty component is trivially schedulable

        return system_schedulable, results

    def _adjust_wcet(self):
        print("\n===== Adjusting Tasks WCET =====")
        for core in self.cores.values():
            print(f"[Core {core.core_id}] speed factor: {core.speed_factor}x")
            for comp in core.components:
                for task in comp.tasks:
                    original = task.nominal_wcet
                    task.adjusted_wcet = original / core.speed_factor
                    print(f"  {task.task_name}: {original:.1f} → {task.adjusted_wcet:.1f} "
                          f"(Component {comp.component_id})")

    def _calculate_bdr(self):
        print("\n===== Calculating BDR parameters =====")
        for core in self.cores.values():
            print(f"[Core {core.core_id}]")
            for comp in core.components:
                try:
                    if comp.budget <= 0 or comp.period <= 0:
                        raise ValueError("Budget and period must be positive")
                    if comp.budget > comp.period:
                         print(f"Warning: Component {comp.component_id} budget {comp.budget} > period {comp.period}. "
                               f"If Alpha>1，Delta<0.") # Allow but warn

                    # BDR Parameter Calculation
                    # Alpha: Bandwidth (Q/P)
                    # Delta: Latency/Delay (P - Q, assuming worst-case finish time)
                    comp.alpha = comp.budget / comp.period
                    comp.delta = comp.period - comp.budget # Can be negative if Q > P

                    print(f"  {comp.component_id}: α={comp.alpha:.2f} δ={comp.delta:.1f} "
                          f"(Q={comp.budget}, P={comp.period})")
                except ZeroDivisionError:
                     print(f"Error: Component {comp.component_id} period is 0 and BDR cannot be calculated.")
                     comp.alpha = float('inf')
                     comp.delta = float('inf') # Indicate error
                except Exception as e:
                    print(f"Error: Component {comp.component_id} BDR calculation failed - {str(e)}")
                    comp.alpha = float('inf')
                    comp.delta = float('inf') # Indicate error

    def _hierarchical_verification(self):
        print("\n===== Hierarchical verification =====")
        results = []
        system_schedulable = True

        for core in self.cores.values():
            # Core verification
            core_schedulable = self._core_analysis(core)
            results.append(f"Core {core.core_id} ({core.scheduler}) {'schedulable' if core_schedulable else 'unschedulable'}")
            system_schedulable &= core_schedulable

            # Component verification
            for comp in core.components:
                comp_schedulable = self._component_analysis(comp)
                results.append(f"  ├─Component {comp.component_id}: {'schedulable' if comp_schedulable else 'unschedulable'}")

                # Task verification
                for task in comp.tasks:
                    status = 'schedulable' if task.schedulable else f"unschedulable (R={task.wcrt:.1f}, T={task.period})"
                    results.append(f"  │   └─Task {task.task_name}: {status}")

        return system_schedulable, results

    def _core_analysis(self, core):
        if core.scheduler == 'EDF':
            return self._edf_core_check(core)
        return self._rm_core_check(core)

    def _edf_core_check(self, core):
        total_util = sum(comp.budget / comp.period for comp in core.components)
        print(f"[EDF core {core.core_id}] Total utilization: {total_util:.2f}/1.0")

        if total_util > 1.0 + 1e-6:
            print(f"  ! Utilization exceeded: {total_util:.2f} > 1.0")
            return False
        return True

    def _rm_core_check(self, core):
        print(f"[RM core {core.core_id}] Response Time Analysis:")
        sorted_comps = sorted(core.components, key=lambda c: c.period)

        for i, comp in enumerate(sorted_comps):
            print(f"  Analysis component {comp.component_id} (P={comp.period}, Q={comp.budget})")
            rt = comp.budget
            iteration = 0

            while True:
                new_rt = comp.budget + sum(
                    math.ceil(rt / c.period) * c.budget
                    for c in sorted_comps[:i]
                )

                print(f"    Iteration {iteration}: R={rt:.1f} → {new_rt:.1f}")

                if new_rt > comp.period + 1e-6:
                    print(f"    ! Utilization exceeded: {new_rt:.1f} > {comp.period}")
                    return False

                if abs(new_rt - rt) < 1e-6:
                    break

                rt = new_rt
                iteration += 1
                if iteration > 10:
                    print("    ! Iteration not converged")
                    return False

        return True

    def _component_analysis(self, comp):
        total_util = sum(t.adjusted_wcet / t.period for t in comp.tasks)
        server_util = comp.budget / comp.period

        print(f"[Component {comp.component_id}] Utilization check:"
              f"\n  Task utilization: {total_util:.2f}"
              f"\n  Server utilization: {server_util:.2f} (Q/P={comp.budget}/{comp.period})")

        if total_util > server_util + 1e-6:
            print(f"  ! Task demand exceeds server supply: {total_util:.2f} > {server_util:.2f}")
            return False

        schedulable = ResponseAnalyzer.calculate_wcrt(comp.tasks, comp.scheduler, comp.budget)
        print(f"  Response time validation: {'schedulable' if schedulable else 'unschedulable'}")

        comp.schedulable = schedulable
        return schedulable