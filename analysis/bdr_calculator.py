import math

class BDRCalculator:
    @staticmethod
    def dbf_edf(tasks_wcet_period_tuples, t):
        """
        EDF Demand Bound Function, aligned with Analyzer.py's logic.
        tasks_wcet_period_tuples: list of (adjusted_wcet, period) tuples.
        """
        if t < 0: return 0.0
        demand = 0.0
        for C, T in tasks_wcet_period_tuples:
            if T > 0: # Avoid division by zero
                # Analyzer.py logic: sum((t//T)*C for C,T in ws)
                demand += (t // T) * C
            # Original, more standard DBF for D_i = T_i (for reference):
            # if t >= T:
            #      demand += (math.floor((t - T) / T) + 1) * C
        return demand

    @staticmethod
    def sbf_bdr(alpha, delta, t):
        """BDR Supply Bound Function."""
        if alpha < 0: # Alpha must be non-negative
            # print(f"Warning: SBF called with negative alpha({alpha})")
            return 0.0
        # Delta can be negative if Q > P in some BDR definitions (e.g. delta = P-Q or 2(P-Q))
        # Analyzer.py logic: alpha*(t-delta) if t >= delta else 0.0
        if t >= delta:
            return alpha * (t - delta)
        else:
            return 0.0

    @staticmethod
    def dbf_fps(tasks, t, task_index):
        """
        Calculates the Demand Bound Function for task i and higher priority tasks under FPS at time t.
        Assumes 'tasks' list is pre-sorted by priority for simplicity of finding HP tasks,
        or that 'task_index' refers to a globally sorted list by priority.
        For this version, we'll sort by explicit priority if available.
        """
        if t < 0: return 0.0
        if not tasks or task_index < 0 or task_index >= len(tasks):
            # print("Warning: dbf_fps called with invalid tasks list or task_index.")
            return 0.0 # Or raise error

        # Ensure tasks have required attributes
        if not all(hasattr(task, 'period') and hasattr(task, 'adjusted_wcet') and (hasattr(task, 'priority') or task.priority is None) for task in tasks):
             raise AttributeError("One or more tasks missing 'period', 'adjusted_wcet', or 'priority' attribute for DBF FPS calculation.")

        # Sort tasks by priority (lower number is higher priority), then by period as tie-breaker
        # Handle None priorities by treating them as lower priority than numerical ones.
        tasks_sorted_by_priority = sorted(
            tasks,
            key=lambda x: (x.priority if x.priority is not None else float('inf'), x.period)
        )


        # Find the current task in the sorted list
        current_task_obj = tasks[task_index] # The task object from the original unsorted list
        try:
            # Find the index of current_task_obj in the priority-sorted list
            sorted_idx_of_current_task = -1
            for i, task_in_sorted_list in enumerate(tasks_sorted_by_priority):
                if task_in_sorted_list is current_task_obj: # Object identity check
                    sorted_idx_of_current_task = i
                    break
            if sorted_idx_of_current_task == -1:
                # print(f"Warning: Task {current_task_obj.task_name} not found in priority-sorted list for DBF FPS calculation.")
                return float('inf') # Indicate an error condition
        except Exception as e:
            # print(f"Error finding task in sorted list for DBF FPS: {e}")
            return float('inf')


        task_i = tasks_sorted_by_priority[sorted_idx_of_current_task]
        # Demand of task_i itself, if its deadline is considered (for DBF, it is)
        # Standard DBF_i(t) = C_i + sum_{j in hp(i)} ceil(t/T_j)*C_j
        # The request for dbf_fps is usually for interference, but here it implies total demand up to task_i
        demand = 0
        # Interference from higher priority tasks (those before it in tasks_sorted_by_priority)
        # including task_i itself for its own demand.
        for hp_task_or_self in tasks_sorted_by_priority[:sorted_idx_of_current_task + 1]:
            if hp_task_or_self.period > 0:
                demand += math.ceil(t / hp_task_or_self.period) * hp_task_or_self.adjusted_wcet
        return demand