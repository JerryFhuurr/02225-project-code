# hierarchical_scheduler.py
import math
from functools import reduce
import sys
import copy
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import argparse
import logging
import statistics
import os
import random
import json
from typing import List, Dict, Tuple, Optional, Union, Set

def lcm(a, b):
    """ Calculate the least common multiple (LCM) of two numbers """
    return abs(a * b) // math.gcd(a, b)

def lcm_of_list(numbers):
    """ Calculate the least common multiple of all numbers in the list """
    return reduce(lcm, numbers)

def generate_execution_time_uniform(bcet: int, wcet: int) -> int:
    """
    Generate a random execution time using a uniform distribution (integer values)
    in the interval [bcet, wcet]. This supports BCET = 0.
    """
    if bcet == wcet:
        return bcet
    return random.randint(bcet, wcet)

class Task:
    """ Task Class for both periodic and sporadic tasks """
    def __init__(self, task_id, bcet, wcet, period, deadline, priority=None, is_periodic=True, 
                 component_id=None, core_id=None, min_interarrival=None):
        # Initialize the task with the given parameters
        self.task_id = task_id
        self.period = period if is_periodic else None  # Only for periodic tasks
        self.min_interarrival = min_interarrival if not is_periodic else period  # For sporadic tasks
        self.deadline = deadline if deadline is not None else period  # Default deadline is period if not specified
        self.priority = priority  # Used for FPS, can be None for EDF
        self.bcet = bcet
        self.wcet = wcet
        self.is_periodic = is_periodic
        self.component_id = component_id
        self.core_id = core_id

        # Initialize the task's execution time, release time, remaining time, completion time, response time, wcrt, and finish time
        self.execution_time = 0
        self.release_time = 0                 
        self.remaining_time = 0  
        self.completion_time = None           
        self.response_time = None             
        self.wcrt = 0
        self.finish_time = 0
        self.response_times = []  # Store all response times for statistics

        # Reset the execution time of the task
        self.reset_execution_time()
        
    def reset_execution_time(self):
        """Compute the new execution_time for this job instance using uniform distribution."""
        self.execution_time = generate_execution_time_uniform(self.bcet, self.wcet)
        self.remaining_time = self.execution_time
        
    def release_new_job(self, current_time):
        """Release a new job of this task at current_time."""
        self.release_time = current_time
        self.reset_execution_time()
        self.completion_time = None
        self.response_time = None
    
    def is_ready(self, current_time):
        """ Check if the task is ready to execute """
        return current_time >= self.release_time and self.remaining_time > 0
    
    def execute(self, time_units=1):
        """
        Execute the task for a given number of time units.
        Returns True if the task finishes (remaining_time becomes 0).
        """
        self.remaining_time = max(0, self.remaining_time - time_units)
        return self.remaining_time == 0  

    def calculate_response_time(self, finish_time):
        """Calculate response time and update worst-case response time (WCRT)."""
        self.completion_time = finish_time
        self.response_time = self.completion_time - self.release_time
        self.response_times.append(self.response_time)
        self.wcrt = max(self.wcrt, self.response_time)
        self.finish_time = finish_time
        
    def get_absolute_deadline(self):
        """Get the absolute deadline of the current job."""
        return self.release_time + self.deadline
        
    def get_statistics(self):
        """Get response time statistics for this task."""
        if not self.response_times:
            return {"avg": 0, "max": 0, "min": 0, "median": 0, "missed_deadlines": 0, "total_jobs": 0}
        
        missed_deadlines = sum(1 for rt in self.response_times if rt > self.deadline)
        
        return {
            "avg": sum(self.response_times) / len(self.response_times),
            "max": max(self.response_times),
            "min": min(self.response_times),
            "median": statistics.median(self.response_times) if self.response_times else 0,
            "missed_deadlines": missed_deadlines,
            "total_jobs": len(self.response_times)
        }

class ResourceSupplyTask(Task):
    """Resource supply task representing a resource interface (α, Δ) using the Half-Half Algorithm."""
    def __init__(self, task_id, component_id, budget, period, core_id=None, priority=None):
        # For the simulator, we directly use the budget and period from the budgets.csv
        super().__init__(
            task_id=task_id,
            bcet=budget,  # Budget is fixed
            wcet=budget,  # Budget is fixed
            period=period,
            deadline=period,  # Deadline equal to period
            priority=priority,
            is_periodic=True,
            component_id=component_id,
            core_id=core_id
        )
        
        # Calculate alpha and delta from budget and period
        self.alpha = budget / period  # Resource availability factor
        self.delta = period / 2  # Maximum delay (using Half-Half theorem in reverse)
        self.budget = budget  # Resource budget
        self.is_resource_supply = True
        self.replenish_time = 0  # Time when next budget replenishment occurs
        self.current_budget = 0  # Current available budget
        self.period = period  # Period of the supply
        
    def release_new_job(self, current_time):
        """Release a new job of this resource supply task at current_time."""
        super().release_new_job(current_time)
        self.replenish_time = current_time + self.period
        self.current_budget = self.budget
    
    def use_budget(self, time_units=1):
        """Use budget for a given number of time units. Return amount of budget used."""
        if self.current_budget <= 0:
            return 0
        
        used = min(self.current_budget, time_units)
        self.current_budget -= used
        return used
    
    def replenish_budget(self, current_time):
        """Replenish budget if it's time to do so."""
        if current_time >= self.replenish_time:
            self.current_budget = self.budget
            self.replenish_time = current_time + self.period
            return True
        return False

class Component:
    """Component class for hierarchical scheduling."""
    def __init__(self, component_id, scheduler_type="EDF", core_id=None, parent_id=None,
                 budget=None, period=None, priority=None):
        self.component_id = component_id
        self.scheduler_type = scheduler_type  # "EDF" or "RM"
        self.core_id = core_id
        self.parent_id = parent_id
        self.tasks = []  # List of tasks assigned to this component
        self.children = []  # List of child components (only for non-leaf components)
        self.resource_supply = None  # ResourceSupplyTask for this component
        
        # Resource parameters
        self.budget = budget
        self.period = period
        self.priority = priority
        
        # Derived BDR interface parameters
        self.alpha = budget / period if budget is not None and period is not None else None
        self.delta = period / 2 if period is not None else None
        
        # For tracking active jobs in the component
        self.active_jobs = []
        
        # For statistics
        self.utilization = 0
        self.idle_time = 0
        self.busy_time = 0
        
    def add_task(self, task):
        """Add a task to this component."""
        self.tasks.append(task)
        task.component_id = self.component_id
        task.core_id = self.core_id
        # Update utilization for periodic tasks
        if task.is_periodic:
            self.utilization += task.wcet / task.period
            
    def add_child(self, component):
        """Add a child component."""
        self.children.append(component)
        component.parent_id = self.component_id
        component.core_id = self.core_id
    
    def set_resource_supply(self):
        """Set the resource supply task for this component based on budget and period."""
        if self.budget is not None and self.period is not None:
            self.resource_supply = ResourceSupplyTask(
                task_id=f"RS_{self.component_id}",
                component_id=self.component_id,
                budget=self.budget,
                period=self.period,
                core_id=self.core_id,
                priority=self.priority
            )
    
    def get_scheduler(self):
        """Get the appropriate scheduler based on the scheduler type."""
        if self.scheduler_type == "EDF":
            return EDFScheduler(self)
        elif self.scheduler_type == "RM":
            return FPSScheduler(self)
        else:
            raise ValueError(f"Unknown scheduler type: {self.scheduler_type}")
            
    def get_statistics(self):
        """Get statistics for this component."""
        if self.busy_time + self.idle_time > 0:
            utilization = self.busy_time / (self.busy_time + self.idle_time)
        else:
            utilization = 0
            
        task_stats = {task.task_id: task.get_statistics() for task in self.tasks}
        
        return {
            "component_id": self.component_id,
            "scheduler_type": self.scheduler_type,
            "utilization": utilization,
            "alpha": self.alpha,
            "delta": self.delta,
            "budget": self.budget,
            "period": self.period,
            "tasks": task_stats
        }

class Core:
    """Core class for multicore platform."""
    def __init__(self, core_id, speed_factor=1.0, scheduler_type="EDF"):
        self.core_id = core_id
        self.speed_factor = speed_factor  # Factor affecting execution times
        self.scheduler_type = scheduler_type  # Scheduler type for the root component
        self.components = []  # List of components assigned to this core
        self.root_component = None  # Root component for this core
        
    def add_component(self, component):
        """Add a component to this core."""
        self.components.append(component)
        component.core_id = self.core_id
        
    def set_root_component(self, component):
        """Set the root component for this core."""
        self.root_component = component
        component.core_id = self.core_id
        self.add_component(component)

class Scheduler:
    """Base scheduler class."""
    def __init__(self, component):
        self.component = component
        
    def select_task(self, current_time, active_jobs):
        """Select the next task to execute based on the scheduling policy."""
        raise NotImplementedError("Subclasses must implement select_task")
        
    def update_active_jobs(self, current_time, job_release_times=None):
        """Update active jobs based on current time."""
        # Remove completed jobs
        self.component.active_jobs = [job for job in self.component.active_jobs 
                                      if job.remaining_time > 0]
        
        # Add newly released jobs if job_release_times is provided
        if job_release_times:
            for task in self.component.tasks:
                if job_release_times.get(task.task_id) == current_time:
                    task.release_new_job(current_time)
                    self.component.active_jobs.append(task)
                    job_release_times[task.task_id] += task.period if task.is_periodic else task.min_interarrival

class EDFScheduler(Scheduler):
    """Earliest Deadline First scheduler."""
    def select_task(self, current_time, active_jobs):
        """Select task with earliest absolute deadline."""
        if not active_jobs:
            return None
        return min(active_jobs, key=lambda task: task.get_absolute_deadline())

class FPSScheduler(Scheduler):
    """Fixed Priority Scheduler (Rate Monotonic)."""
    def select_task(self, current_time, active_jobs):
        """Select task with highest priority (lowest priority value)."""
        if not active_jobs:
            return None
        return min(active_jobs, key=lambda task: task.priority)

class HierarchicalScheduler:
    """Hierarchical scheduler for multicore platform."""
    def __init__(self):
        self.cores = {}  # Dictionary of cores by ID
        self.components = {}  # Dictionary of components by ID
        self.tasks = {}  # Dictionary of tasks by ID
        self.schedule_log = {}  # Log of schedule events
        
    def add_core(self, core_id, speed_factor=1.0, scheduler_type="EDF"):
        """Add a core to the platform."""
        self.cores[core_id] = Core(core_id, speed_factor, scheduler_type)
        self.schedule_log[core_id] = []
        
        # Create a root component for this core
        root_component_id = f"root_{core_id}"
        root_component = Component(
            component_id=root_component_id,
            scheduler_type=scheduler_type,
            core_id=core_id
        )
        self.components[root_component_id] = root_component
        self.cores[core_id].set_root_component(root_component)
        
        return root_component
        
    def add_component(self, component_id, scheduler_type="EDF", core_id=None, parent_id=None,
                     budget=None, period=None, priority=None):
        """Add a component to the system."""
        component = Component(
            component_id=component_id, 
            scheduler_type=scheduler_type, 
            core_id=core_id, 
            parent_id=parent_id,
            budget=budget,
            period=period,
            priority=priority
        )
        self.components[component_id] = component
        
        # Add to parent component if parent_id is specified, otherwise add to root component of the core
        if parent_id and parent_id in self.components:
            self.components[parent_id].add_child(component)
        elif core_id and core_id in self.cores:
            root_component_id = f"root_{core_id}"
            if root_component_id in self.components:
                self.components[root_component_id].add_child(component)
            
        # Add to core if core_id is specified
        if core_id and core_id in self.cores:
            self.cores[core_id].add_component(component)
                
        return component
        
    def add_task(self, task_id, bcet, wcet, period, deadline=None, priority=None, is_periodic=True,
                component_id=None, core_id=None, min_interarrival=None):
        """Add a task to the system."""
        # Find the core for this task through the component
        task_core_id = core_id
        if not task_core_id and component_id and component_id in self.components:
            task_core_id = self.components[component_id].core_id
            
        # Adjust WCET based on core speed factor
        if task_core_id and task_core_id in self.cores:
            adjusted_wcet = wcet / self.cores[task_core_id].speed_factor
            adjusted_bcet = bcet / self.cores[task_core_id].speed_factor if bcet is not None else adjusted_wcet
        else:
            adjusted_wcet = wcet
            adjusted_bcet = bcet if bcet is not None else wcet
            
        # If deadline is not specified, use period
        if deadline is None:
            deadline = period
            
        task = Task(
            task_id=task_id,
            bcet=adjusted_bcet,
            wcet=adjusted_wcet,
            period=period,
            deadline=deadline,
            priority=priority,
            is_periodic=is_periodic,
            component_id=component_id,
            core_id=task_core_id,
            min_interarrival=min_interarrival
        )
        
        self.tasks[task_id] = task
        
        # Add to component if component_id is specified
        if component_id and component_id in self.components:
            self.components[component_id].add_task(task)
            
        return task
        
    def setup_resource_supplies(self):
        """Set up resource supply tasks for all components."""
        # Set up resource supplies for each component
        for component in self.components.values():
            if component.parent_id is not None:  # Skip root components
                component.set_resource_supply()
                
                # Add resource supply task to parent component
                if component.parent_id in self.components and component.resource_supply:
                    parent = self.components[component.parent_id]
                    parent.add_task(component.resource_supply)
    
    def simulate(self, simulation_time):
        """Run the hierarchical scheduling simulation."""
        # Initialize release times for periodic tasks
        job_release_times = {}
        for task in self.tasks.values():
            if task.is_periodic:
                job_release_times[task.task_id] = 0
                
        # Run simulation for each core
        for core_id, core in self.cores.items():
            self._simulate_core(core, simulation_time, job_release_times.copy())
            
        return self.get_statistics()
    
    def _simulate_core(self, core, simulation_time, job_release_times):
        """Simulate scheduling on a single core."""
        current_time = 0
        
        # Get the scheduler for the root component
        root_scheduler = core.root_component.get_scheduler()
        
        # Initialize component schedulers
        component_schedulers = {comp.component_id: comp.get_scheduler() 
                               for comp in core.components}
        
        # Initialize resource tracking for components
        component_resources = {comp.component_id: {
            "has_resource": comp.parent_id is None,  # Root component always has resource
            "current_budget": float('inf') if comp.parent_id is None else 0  # Root has unlimited budget
        } for comp in core.components}
        
        # Track which component is currently executing
        current_executing_component = None
        current_executing_task = None
        
        while current_time < simulation_time:
            # 1) Release new jobs for periodic tasks
            for task_id, release_time in list(job_release_times.items()):
                if release_time == current_time:
                    task = self.tasks[task_id]
                    if task.core_id == core.core_id:
                        task.release_new_job(current_time)
                        if task.component_id:
                            self.components[task.component_id].active_jobs.append(task)
                        job_release_times[task_id] += task.period
            
            # 2) Replenish budgets for resource supply tasks
            for comp_id, comp in self.components.items():
                if comp.core_id == core.core_id and comp.resource_supply:
                    if comp.resource_supply.replenish_budget(current_time):
                        # If resource supply is replenished, the component gets the resource
                        component_resources[comp_id]["has_resource"] = True
                        component_resources[comp_id]["current_budget"] = comp.resource_supply.current_budget
            
            # 3) Schedule tasks within the hierarchical system
            # We start at the root component and work our way down
            selected_component, selected_task = self._schedule_component_recursive(
                core.root_component, 
                current_time, 
                component_schedulers, 
                component_resources
            )
            
            # 4) Execute the selected task (if any)
            if selected_task:
                # Record the task execution in the schedule log
                self.schedule_log[core.core_id].append((current_time, selected_task.task_id))
                
                # Execute the task for 1 time unit
                task_finished = selected_task.execute(1)
                
                # Use budget from the component
                if selected_component and selected_component.parent_id is not None:
                    component_resources[selected_component.component_id]["current_budget"] -= 1
                    if component_resources[selected_component.component_id]["current_budget"] <= 0:
                        component_resources[selected_component.component_id]["has_resource"] = False
                    
                    # Update component statistics
                    selected_component.busy_time += 1
                else:
                    # Root component execution
                    core.root_component.busy_time += 1
                
                # If task finished, calculate response time
                if task_finished:
                    finish_time = current_time + 1
                    selected_task.calculate_response_time(finish_time)
                    
                    # Remove from active jobs
                    if selected_component:
                        if selected_task in selected_component.active_jobs:
                            selected_component.active_jobs.remove(selected_task)
                
                current_executing_component = selected_component
                current_executing_task = selected_task
            else:
                # No task to execute, system is idle
                self.schedule_log[core.core_id].append((current_time, "Idle"))
                
                # Update idle time for root component
                core.root_component.idle_time += 1
                
                current_executing_component = None
                current_executing_task = None
            
            # 5) Advance time by 1 unit
            current_time += 1
    
    
    def _schedule_component_recursive(self, component, current_time, component_schedulers, component_resources):
        """Recursively schedule tasks within a component and its children."""
        # If component has no resource, it cannot execute
        if not component_resources[component.component_id]["has_resource"]:
            return None, None
        
        # Get scheduler for this component
        scheduler = component_schedulers[component.component_id]
        
        # Update active jobs for this component
        scheduler.update_active_jobs(current_time)
        
        # If this is a leaf component (no children), schedule a task
        if not component.children:
            selected_task = scheduler.select_task(current_time, component.active_jobs)
            return component, selected_task
        
        # If this is not a leaf component, first try to schedule its children
        for child in component.children:
            if component_resources[child.component_id]["has_resource"]:
                selected_component, selected_task = self._schedule_component_recursive(
                    child, current_time, component_schedulers, component_resources
                )
                if selected_task:
                    return selected_component, selected_task
        
        # If no child can execute, try to schedule tasks of this component
        selected_task = scheduler.select_task(current_time, component.active_jobs)
        return component, selected_task
    
    def get_statistics(self):
        """Get statistics from the simulation."""
        core_stats = {}
        for core_id, core in self.cores.items():
            component_stats = {}
            for comp in core.components:
                component_stats[comp.component_id] = comp.get_statistics()
            
            core_stats[core_id] = {
                "speed_factor": core.speed_factor,
                "scheduler_type": core.scheduler_type,
                "components": component_stats
            }
        
        task_stats = {}
        for task_id, task in self.tasks.items():
            if not task_id.startswith("RS_"):  # Skip resource supply tasks
                task_stats[task_id] = task.get_statistics()
        
        return {
            "cores": core_stats,
            "tasks": task_stats
        }
        
    def plot_gantt_chart(self, core_id, save_path=None):
        """Draw a Gantt chart for a specific core."""
        if core_id not in self.schedule_log:
            print(f"No schedule log for core {core_id}")
            return
            
        schedule_log = self.schedule_log[core_id]
        
        plt.figure(figsize=(15, 8))
        task_colors = {}
        y_pos = {}
        
        # Filter out resource supply tasks for display
        filtered_schedule = []
        for time, task_id in schedule_log:
            if task_id != "Idle" and not task_id.startswith("RS_"):
                filtered_schedule.append((time, task_id))
            else:
                filtered_schedule.append((time, "Idle"))
        
        unique_tasks = set(entry[1] for entry in filtered_schedule if entry[1] != "Idle")
        for i, task in enumerate(sorted(unique_tasks)):
            task_colors[task] = plt.colormaps["tab10"](i % 10)
            y_pos[task] = i

        # Add Idle slot for visualization
        y_pos["Idle"] = len(y_pos)
        task_colors["Idle"] = "white"

        for start_time, task in filtered_schedule:
            plt.barh(y_pos[task], 1, left=start_time, color=task_colors[task], edgecolor="black" if task != "Idle" else "lightgray")

        plt.yticks(range(len(y_pos)), sorted(y_pos.keys()))
        plt.xlabel("Time")
        plt.ylabel("Tasks")
        plt.title(f"Hierarchical Schedule - Core {core_id} - Gantt Chart")
        plt.grid(axis="x")
        
        if save_path:
            plt.savefig(save_path)
            print(f"Gantt chart saved to {save_path}")
        
        plt.show()

    def calculate_sbf_bdr(self, alpha, delta, t):
        """Calculate Supply Bound Function (SBF) for BDR resource model."""
        # Using equation (6) from the project description
        if t < delta:
            return 0
        return alpha * (t - delta)
    
    def calculate_dbf_edf(self, tasks, t):
        """Calculate Demand Bound Function (DBF) for EDF."""
        # Using equation (3) from the project description
        dbf = 0
        for task in tasks:
            dbf += task.wcet * math.floor((t + task.period - task.deadline) / task.period)
        return dbf
    
    def calculate_dbf_fps(self, tasks, t, i):
        """Calculate Demand Bound Function (DBF) for FPS for task i."""
        # Using equation (4) from the project description
        dbf = 0
        task_i = tasks[i]
        
        # Add execution time of task i
        dbf += task_i.wcet
        
        # Add interference from higher priority tasks
        higher_priority_tasks = [task for task in tasks if task.priority < task_i.priority]
        for hp_task in higher_priority_tasks:
            dbf += hp_task.wcet * math.ceil(t / hp_task.period)
            
        return dbf

def load_system_from_files(arch_file, budgets_file, tasks_file):
    """Load system configuration from CSV files."""
    # Load architecture (cores)
    arch_df = pd.read_csv(arch_file)
    
    # Load component budgets
    budgets_df = pd.read_csv(budgets_file)
    
    # Load tasks
    tasks_df = pd.read_csv(tasks_file)
    
    # Create hierarchical scheduler
    scheduler = HierarchicalScheduler()
    
    # Add cores
    for _, core in arch_df.iterrows():
        scheduler.add_core(
            core_id=core["core_id"],
            speed_factor=core["speed_factor"],
            scheduler_type=core["scheduler"]
        )
    
    # Add components with their budgets
    for _, comp in budgets_df.iterrows():
        # Map RM to FPS
        scheduler_type = "RM" if comp["scheduler"] == "RM" else comp["scheduler"]
        
        scheduler.add_component(
            component_id=comp["component_id"],
            scheduler_type=scheduler_type,
            core_id=comp["core_id"],
            budget=comp["budget"],
            period=comp["period"],
            priority=comp["priority"] if "priority" in comp and not pd.isna(comp["priority"]) else None
        )
    
    # Add tasks
    for _, task in tasks_df.iterrows():
        # For FPS/RM components, tasks must have priorities
        # For EDF components, tasks don't need priorities
        component_id = task["component_id"]
        component = scheduler.components.get(component_id)
        
        priority = None
        if "priority" in task and not pd.isna(task["priority"]):
            priority = task["priority"]
        elif component and component.scheduler_type == "RM":
            # If no priority specified for RM and it's required, assign based on period (RM)
            priority = task["period"]  # Smaller period = higher priority, but we'll sort in the scheduler
        
        bcet = task["bcet"] if "bcet" in task and not pd.isna(task["bcet"]) else task["wcet"]
        deadline = task["deadline"] if "deadline" in task and not pd.isna(task["deadline"]) else task["period"]
        
        scheduler.add_task(
            task_id=task["task_name"],
            bcet=bcet,
            wcet=task["wcet"],
            period=task["period"],
            deadline=deadline,
            priority=priority,
            component_id=component_id
        )
    
    # Setup resource supplies
    scheduler.setup_resource_supplies()
    
    return scheduler



def main():
    parser = argparse.ArgumentParser(description="Hierarchical Scheduling Simulator")
    parser.add_argument("--arch", required=True, help="CSV file describing architecture (cores)")
    parser.add_argument("--budgets", required=True, help="CSV file describing component budgets")
    parser.add_argument("--tasks", required=True, help="CSV file describing tasks")
    parser.add_argument("--simtime", type=int, default=None, 
                        help="Simulation time (if not provided, use LCM of task periods)")
    parser.add_argument("--verbose", action="store_true", help="Output detailed log")
    parser.add_argument("--output_dir", default="output", help="Directory for output files")
    
    args = parser.parse_args()
    
    # Create output directories
    images_dir = os.path.join(args.output_dir, "images")
    logs_dir = os.path.join(args.output_dir, "logs")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)
    
    # Load system configuration
    scheduler = load_system_from_files(args.arch, args.budgets, args.tasks)
    
    # Determine simulation time
    if args.simtime is None:
        # Calculate LCM of task periods
        periods = [task.period for task in scheduler.tasks.values() if hasattr(task, 'period') and task.period]
        simulation_time = lcm_of_list(periods)
        # Make sure simulation time is reasonable (not too long)
        simulation_time = min(simulation_time, 1000)
    else:
        simulation_time = args.simtime
    
    print(f"Running simulation for {simulation_time} time units")
    
    # Run simulation
    results = scheduler.simulate(simulation_time)
    
    # Print statistics directly
    print("\n=== Simulation Results ===")
    
    # Print overall task statistics
    print("\n--- Task Statistics ---")
    task_stats = results["tasks"]
    
    # Create a table format for tasks
    print(f"{'Task ID':<15} {'Avg RT':<10} {'Max RT':<10} {'Min RT':<10} {'Missed Deadlines':<15} {'Total Jobs':<10}")
    print("-" * 70)
    
    for task_id, stats in task_stats.items():
        print(f"{task_id:<15} {stats['avg']:<10.2f} {stats['max']:<10.2f} {stats['min']:<10.2f} "
              f"{stats['missed_deadlines']:<15} {stats['total_jobs']:<10}")
    
    # Print component statistics
    print("\n--- Component Statistics ---")
    for core_id, core_stats in results["cores"].items():
        print(f"\nCore {core_id} (Speed Factor: {core_stats['speed_factor']}, Scheduler: {core_stats['scheduler_type']})")
        
        for comp_id, comp_stats in core_stats["components"].items():
            # Skip resource supply components
            if comp_id.startswith("RS_"):
                continue
                
            print(f"  Component {comp_id} (Scheduler: {comp_stats['scheduler_type']})")
            if comp_stats['alpha'] is not None:
                print(f"    Resource Model: α={comp_stats['alpha']:.3f}, Δ={comp_stats['delta']}")
                print(f"    Budget: {comp_stats['budget']}, Period: {comp_stats['period']}")
            
            print(f"    Utilization: {comp_stats['utilization']:.3f}")
            
            # Print task stats for this component
            if 'tasks' in comp_stats and comp_stats['tasks']:
                print("    Tasks:")
                for task_id, task_stats in comp_stats['tasks'].items():
                    if not task_id.startswith("RS_"):  # Skip resource supply tasks
                        print(f"      {task_id}: WCRT={task_stats['max']}, Missed Deadlines={task_stats['missed_deadlines']}/{task_stats['total_jobs']}")
    
    plt.switch_backend('Agg')
    # Generate Gantt charts for each core
    for core_id in scheduler.cores:
        output_file = os.path.join(images_dir, f"gantt_core_{core_id}.png")
        scheduler.plot_gantt_chart(core_id, save_path=output_file)
    
    # Save results to JSON
    results_file = os.path.join(logs_dir, "simulation_results.json")
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
        
    
    print(f"Results saved to {results_file}")
    print(f"Gantt charts saved to {images_dir}")

if __name__ == "__main__":
    main()