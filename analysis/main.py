# main.py
import sys
import os
import pandas as pd
from models import Task, Component, Core
# Correct import if ResponseAnalyzer is used directly (it isn't currently)
# from schedulability import SchedulabilityAnalyzer, ResponseAnalyzer
from schedulability import SchedulabilityAnalyzer


def load_data(tasks_csv, budgets_csv, arch_csv):
    """Data loading function with enhanced data validation"""
    cores = {}

    # Load core architecture
    try:
        arch_df = pd.read_csv(arch_csv, dtype={
            'core_id': 'string',
            'speed_factor': 'float64',
            'scheduler': 'string'
        })
        # Handle potential empty file
        if arch_df.empty:
             raise ValueError("Architecture file is empty or format is incorrect")
        cores = {row['core_id']: Core(
            core_id=row['core_id'],
            speed_factor=row['speed_factor'],
            scheduler=row['scheduler']
        ) for _, row in arch_df.iterrows()}
    except FileNotFoundError:
        raise FileNotFoundError(f"Architecture file not found: {arch_csv}")
    except Exception as e:
        raise ValueError(f"Architecture file loading failed: {str(e)}")

    # Load components
    try:
        budgets_df = pd.read_csv(budgets_csv, dtype={
            'component_id': 'string',
            'scheduler': 'string',
            'core_id': 'string',
            'budget': 'float64',
            'period': 'float64',
            'priority': 'object' # Read as object first to handle empty strings/NaNs
        })
        if budgets_df.empty:
             raise ValueError("Component budgets file is empty or format is incorrect")

        for _, row in budgets_df.iterrows():
            # Check if core_id exists
            core_id_str = str(row['core_id'])
            if core_id_str not in cores:
                 raise ValueError(f"Component {row['component_id']} references unknown core ID: {core_id_str}")

            comp = Component(
                component_id=row['component_id'],
                scheduler=row['scheduler'],
                core_id=core_id_str,
                budget=row['budget'],
                period=row['period'],
                # Pass the priority as read (could be NaN, None, str, number)
                priority=row.get('priority')
            )
            cores[core_id_str].components.append(comp)
    except FileNotFoundError:
        raise FileNotFoundError(f"Component budgets file not found: {budgets_csv}")
    except Exception as e:
        raise ValueError(f"Component file loading failed: {str(e)}")

    # Load tasks
    try:
        tasks_df = pd.read_csv(tasks_csv, dtype={
            'task_name': 'string',
            'wcet': 'float64',
            'period': 'float64',
            'component_id': 'string',
            'priority': 'object' # Read as object first
        })
        if tasks_df.empty:
             raise ValueError("Tasks file is empty or format is incorrect")

        component_task_map = {} # Helper map component_id -> component object
        for core in cores.values():
            for comp in core.components:
                component_task_map[comp.component_id] = comp

        for _, row in tasks_df.iterrows():
             # Check if component_id exists
             component_id_str = str(row['component_id'])
             if component_id_str not in component_task_map:
                  raise ValueError(f"Task {row['task_name']} references unknown component ID: {component_id_str}")

             task = Task(
                 task_name=row['task_name'],
                 wcet=row['wcet'],
                 period=row['period'],
                 component_id=component_id_str,
                 priority=row.get('priority')
             )

             # Associate with the component using the map
             comp = component_task_map[component_id_str]
             comp.tasks.append(task)

             # Initialize analysis-relevant fields ONLY
             task.adjusted_wcet = 0.0 # Will be calculated later
             task.wcrt = 0.0           # Will be calculated later (Worst-Case Response Time)
             task.schedulable = False  # Default state
             # Do NOT initialize avg_response_time or max_response_time here

    except FileNotFoundError:
        raise FileNotFoundError(f"Tasks file not found: {tasks_csv}")
    except Exception as e:
        raise ValueError(f"Tasks file loading failed: {str(e)}")

    return list(cores.values())


if __name__ == "__main__":
    # Define file paths (adjust if they are passed as arguments)
    tasks_file = "tasks.csv"
    budgets_file = "budgets.csv"
    arch_file = "architecture.csv"
    solution_file = "solution.csv"

    try:
        # Check if input files exist
        if not os.path.exists(tasks_file):
            raise FileNotFoundError(f"Input file not found: {tasks_file}")
        if not os.path.exists(budgets_file):
            raise FileNotFoundError(f"Input file not found: {budgets_file}")
        if not os.path.exists(arch_file):
            raise FileNotFoundError(f"Input file not found: {arch_file}")

        cores = load_data(tasks_file, budgets_file, arch_file)

        # Run analysis
        analyzer = SchedulabilityAnalyzer(cores)
        # Assuming analyze returns (system_schedulable_bool, results_list)
        system_schedulable, analysis_results = analyzer.analyze()

        # Print analysis results to the console
        print("\n===== Analysis Results =====")
        if not analysis_results:
             print("Analysis produced no results.")
        else:
             for result in analysis_results:
                 print(result)

        # Generate solution.csv based on analysis tool output
        print(f"\nGenerating {solution_file} (Analysis Tool Output)...")
        try:
            with open(solution_file, "w", newline='') as f: # Use newline='' for csv module if used
                # Header based on analysis tool capabilities
                # Include WCRT, exclude avg/max response time.
                header = "task_name,component_id,task_schedulable,wcrt,component_schedulable\n"
                f.write(header)

                if not cores:
                     print("Warning: No core data available to write to solution.csv.")

                for core in cores:
                    # Check core structure before accessing components
                    if core and hasattr(core, 'components') and core.components:
                        for comp in core.components:
                            # Check component structure before accessing tasks
                            if comp and hasattr(comp, 'tasks') and comp.tasks:
                                # Component schedulability determined during analysis
                                # Default to False if not explicitly set (e.g., analysis error)
                                comp_schedulable = getattr(comp, 'schedulable', False)

                                for task in comp.tasks:
                                    # Ensure task has necessary attributes
                                    if not all(hasattr(task, attr) for attr in ['task_name', 'schedulable', 'wcrt']):
                                         print(f"Warning: Task object {getattr(task, 'task_name', 'Unknown')} missing necessary attributes, skipping write.")
                                         continue

                                    # Task schedulability determined during analysis
                                    task_sched = int(task.schedulable)

                                    # Write analysis tool relevant columns
                                    f.write(f"{task.task_name},{comp.component_id},")
                                    f.write(f"{task_sched},")
                                    # WCRT is calculated by the analysis tool
                                    f.write(f"{task.wcrt:.2f},")
                                    # Component schedulability based on analysis
                                    f.write(f"{int(comp_schedulable)}\n")
                            # else: # Optional: Handle components with no tasks
                                # print(f"Info: Component {comp.component_id} has no tasks, no specific task rows written.")

            print(f"Analysis complete! {solution_file} has been generated.")

        except IOError as e:
             print(f"Error: Could not write to file {solution_file}: {e}")
        except Exception as e:
             print(f"Error: An unexpected error occurred while generating {solution_file}: {e}")


    except FileNotFoundError as e:
         print(f"Error: {str(e)}")
         sys.exit(1)
    except ValueError as e:
         print(f"Data loading/validation error: {str(e)}")
         sys.exit(1)
    except Exception as e:
        # Catch any other unexpected errors during the process
        print(f"An unexpected error occurred: {str(e)}")
        import traceback
        traceback.print_exc() # Print detailed traceback for debugging
        sys.exit(1)