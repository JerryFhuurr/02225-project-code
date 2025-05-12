# This file contains the data models for the system, including Task, Component, and Core classes.

import pandas as pd

class Task:
    def __init__(self, task_name, wcet, period, component_id, priority=None):
        self._validate_input(task_name, wcet, period, component_id)

        self.task_name = str(task_name)
        self.nominal_wcet = float(wcet)
        self.period = float(period)
        self.component_id = str(component_id)
        self.priority = self._parse_priority(priority)

        # Runtime properties
        self.adjusted_wcet = 0.0 # Calculated based on core speed
        self.wcrt = 0.0          # Calculated by analysis tool
        self.schedulable = False # Calculated by analysis tool

    def _validate_input(self, name, wcet, period, comp_id):
        if pd.isna(name) or not str(name).strip():
            raise ValueError("Task name cannot be empty")
        if pd.isna(wcet) or not isinstance(wcet, (int, float)) or wcet <= 0:
            raise ValueError(f"Task {name}'s WCET must be a positive number, got {wcet}")
        if pd.isna(period) or not isinstance(period, (int, float)) or period <= 0:
            raise ValueError(f"Task {name}'s period must be a positive number, got {period}")
        if pd.isna(comp_id) or not str(comp_id).strip():
            raise ValueError("Component ID cannot be empty for task")

    def _parse_priority(self, priority):
        if pd.isna(priority) or priority is None or str(priority).strip() == "":
            return None
        try:
            return int(float(priority))
        except (ValueError, TypeError):
            raise ValueError(f"Invalid priority format for task '{self.task_name}': {priority}")


class Component:
    def __init__(self, component_id, scheduler, core_id, budget, period, priority=None):
        self._validate_input(component_id, scheduler, core_id, budget, period)

        self.component_id = str(component_id)
        self.scheduler = str(scheduler).upper()
        self.core_id = str(core_id)
        # Supply parameters (from input budget/period)
        self.budget = float(budget) # Q
        self.period = float(period) # P
        # Core-level priority (if applicable, e.g., core uses RM)
        # This priority is for the component itself when scheduled on the core,
        # distinct from internal task priorities.
        self.priority = self._parse_priority_comp(priority)


        # Runtime properties
        self.tasks = []
        # Supply BDR parameters (derived from budget/period)
        self.supply_alpha = None # Q/P
        self.supply_delta = None # P-Q (or 2*(P-Q) depending on model)
        # Demand BDR parameters (derived from internal tasks)
        self.demand_alpha = None # Represents component's utilization demand from its tasks
        self.demand_delta = None # Represents component's burstiness/delay demand from its tasks
        self.schedulable = False # If tasks within component are schedulable

    def _validate_input(self, cid, sched, core_id, budget, period):
        if pd.isna(cid) or not str(cid).strip():
            raise ValueError("Component ID cannot be empty")
        if pd.isna(core_id) or not str(core_id).strip():
            raise ValueError(f"Core ID cannot be empty for component {cid}")
        valid_schedulers = {'RM', 'EDF'}
        if pd.isna(sched) or str(sched).upper() not in valid_schedulers:
             raise ValueError(f"Invalid scheduler for component {cid}: '{sched}'. Must be one of {valid_schedulers}")
        if pd.isna(budget) or not isinstance(budget, (int, float)) or budget <= 0:
            raise ValueError(f"Component {cid} budget invalid: {budget}")
        if pd.isna(period) or not isinstance(period, (int, float)) or period <= 0:
            raise ValueError(f"Component {cid} period invalid: {period}")

    def _parse_priority_comp(self, priority):
        """Parses priority for the component itself."""
        if pd.isna(priority) or priority is None or str(priority).strip() == "":
            return None
        try:
            # Attempt to convert to float first to handle "1.0" then to int
            prio = int(float(priority))
            return prio
        except (ValueError, TypeError) as e:
            # Use self.component_id if available, otherwise a placeholder
            cid_for_error = getattr(self, 'component_id', 'Unnamed Component')
            raise ValueError(f"Invalid priority format '{priority}' for component {cid_for_error}: {e}")


class Core:
    def __init__(self, core_id, speed_factor, scheduler):
        self._validate_input(core_id, speed_factor, scheduler)

        self.core_id = str(core_id)
        self.speed_factor = float(speed_factor)
        self.scheduler = str(scheduler).upper() # Core's own scheduler

        # Runtime properties
        self.components = []
        self.schedulable = False # If components assigned to it are schedulable (initially False)

    def _validate_input(self, cid, speed, sched):
        if pd.isna(cid) or not str(cid).strip():
            raise ValueError("Core ID cannot be empty")
        if pd.isna(speed) or not isinstance(speed, (int, float)) or speed <= 0:
            raise ValueError(f"Core {cid} speed factor invalid: {speed}")
        valid_schedulers = {'RM', 'EDF'}
        if pd.isna(sched) or str(sched).upper() not in valid_schedulers:
            raise ValueError(f"Invalid scheduler for core {cid}: '{sched}'. Must be one of {valid_schedulers}")