# This script is the main entry point for the schedulability analysis tool. 

import sys
import os
import pandas as pd
from models import Task, Component, Core
from schedulability import SchedulabilityAnalyzer  # Ensure this is the updated one


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
        if arch_df.empty: raise ValueError("Architecture file is empty or format is incorrect")
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
            'priority': 'object'  # Read as object, parse in Component
        })
        if budgets_df.empty: raise ValueError("Component budgets file is empty or format is incorrect")
        for _, row in budgets_df.iterrows():
            core_id_str = str(row['core_id'])
            if core_id_str not in cores: raise ValueError(
                f"Component {row['component_id']} references unknown core ID: {core_id_str}")
            comp = Component(
                component_id=row['component_id'],
                scheduler=row['scheduler'],
                core_id=core_id_str,
                budget=row['budget'],
                period=row['period'],
                priority=row.get('priority')  # Pass raw priority
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
            'priority': 'object'  # Read as object, parse in Task
        })
        if tasks_df.empty: raise ValueError("Tasks file is empty or format is incorrect")
        component_task_map = {comp.component_id: comp for core_obj in cores.values() for comp in core_obj.components}
        for _, row in tasks_df.iterrows():
            component_id_str = str(row['component_id'])
            if component_id_str not in component_task_map:
                raise ValueError(f"Task {row['task_name']} references unknown component ID: {component_id_str}")
            task = Task(
                task_name=row['task_name'],
                wcet=row['wcet'],
                period=row['period'],
                component_id=component_id_str,
                priority=row.get('priority')  # Pass raw priority
            )
            comp = component_task_map[component_id_str]
            comp.tasks.append(task)
            # Initialize runtime properties (will be overwritten by analyzer)
            task.adjusted_wcet = 0.0;
            task.wcrt = float('inf');
            task.schedulable = False
    except FileNotFoundError:
        raise FileNotFoundError(f"Tasks file not found: {tasks_csv}")
    except Exception as e:
        raise ValueError(f"Tasks file loading failed: {str(e)}")
    return list(cores.values())


if __name__ == "__main__":
    # Default file names, can be overridden by command-line arguments or other config
    tasks_file = "tasks.csv"
    budgets_file = "budgets.csv"
    arch_file = "architecture.csv"
    solution_file = "solution.csv"
    analysis_log_file = "analysis_details.txt"  # For detailed logging

    # Basic command line argument parsing
    if len(sys.argv) > 1 and sys.argv[1] == '--testcase':
        if len(sys.argv) > 2:
            test_case_dir = sys.argv[2]
            tasks_file = os.path.join(test_case_dir, "tasks.csv")
            budgets_file = os.path.join(test_case_dir, "budgets.csv")
            arch_file = os.path.join(test_case_dir, "architecture.csv")
            # Output files could also be directed to a subfolder based on test_case_dir
            # For simplicity, keeping solution_file and analysis_log_file in current dir
            print(f"Running with test case from: {test_case_dir}")
        else:
            print("Error: --testcase flag requires a directory path.")
            sys.exit(1)

    detailed_log_messages = []
    original_stdout = sys.stdout


    # Context manager for capturing print statements if needed for analysis_details.txt
    class Tee(object):
        def __init__(self, *files):
            self.files = files

        def write(self, obj):
            for f in self.files:
                f.write(obj)
                f.flush()  # If you want to see logs in real time

        def flush(self):
            for f in self.files:
                f.flush()


    try:
        with open(analysis_log_file, "w", encoding='utf-8') as log_f:
            # Standard file existence checks
            if not os.path.exists(tasks_file): raise FileNotFoundError(f"Input file not found: {tasks_file}")
            if not os.path.exists(budgets_file): raise FileNotFoundError(f"Input file not found: {budgets_file}")
            if not os.path.exists(arch_file): raise FileNotFoundError(f"Input file not found: {arch_file}")

            print(f"Loading data from: {tasks_file}, {budgets_file}, {arch_file}", file=log_f)
            cores_list = load_data(tasks_file, budgets_file, arch_file)

            print("\nInitializing Schedulability Analyzer...", file=log_f)
            analyzer = SchedulabilityAnalyzer(cores_list)

            print("Starting analysis...\n", file=log_f)
            system_schedulable, analysis_results_log = analyzer.analyze()  # analysis_results_log might be less used now

            # Restore stdout if it was redirected for logging every print

            print("\n===== Analysis Results Summary =====", file=log_f)
            print("===== Analysis Results Summary =====")  # To console
            if not cores_list:
                msg = "Analysis produced no summary results as no cores were loaded."
                print(msg, file=log_f);
                print(msg)
            else:
                for core in cores_list:
                    core_sched_str = f"Core {core.core_id} (Scheduler: {core.scheduler}, Speed: {core.speed_factor}x) Schedulable: {core.schedulable}"
                    print(core_sched_str, file=log_f);
                    print(core_sched_str)
                    for comp in core.components:
                        comp_sched_str = f"  Comp {comp.component_id} (Scheduler: {comp.scheduler}, Q={comp.budget}, P={comp.period}) Schedulable: {comp.schedulable}"
                        print(comp_sched_str, file=log_f);
                        print(comp_sched_str)
                        if not comp.tasks:
                            comp_task_str = f"    (No tasks)"
                            print(comp_task_str, file=log_f);
                            print(comp_task_str)
                        for task in comp.tasks:
                            task_result_str = f"    Task {task.task_name} (Nominal WCET: {task.nominal_wcet:.2f}, Adj WCET: {task.adjusted_wcet:.2f}, Period: {task.period:.2f}, Prio: {task.priority}) -> Schedulable: {task.schedulable}, WCRT: {task.wcrt:.2f}"
                            print(task_result_str, file=log_f);
                            print(task_result_str)

            overall_msg = f"\nOverall System Schedulable: {system_schedulable}"
            print(overall_msg, file=log_f);
            print(overall_msg)

            print(f"\nGenerating {solution_file} (Analysis Tool Output)...", file=log_f)
            print(f"\nGenerating {solution_file} (Analysis Tool Output)...")
            try:
                with open(solution_file, "w", newline='') as f_sol:
                    header = "task_name,component_id,task_schedulable,wcrt,component_schedulable\n";
                    f_sol.write(header)
                    if not cores_list:
                        warn_msg = "Warning: No core data to write to solution.csv."
                        print(warn_msg, file=log_f);
                        print(warn_msg)
                    for core in cores_list:
                        if core and hasattr(core, 'components') and core.components:
                            for comp in core.components:
                                if comp and hasattr(comp, 'tasks') and comp.tasks:
                                    # Component schedulability derived from its internal analysis
                                    comp_sched_val = int(getattr(comp, 'schedulable', False))
                                    for task in comp.tasks:
                                        if not all(
                                                hasattr(task, attr) for attr in ['task_name', 'schedulable', 'wcrt']):
                                            warn_task_msg = f"Warning: Task {getattr(task, 'task_name', 'Unknown')} missing critical attributes, skipping for solution.csv."
                                            print(warn_task_msg, file=log_f);
                                            print(warn_task_msg)
                                            continue
                                        task_sched_val = int(task.schedulable)
                                        # Format WCRT to 2 decimal places, use 'inf' if it is infinity
                                        wcrt_val_str = f"{task.wcrt:.2f}" if task.wcrt != float('inf') else "inf"
                                        f_sol.write(
                                            f"{task.task_name},{comp.component_id},{task_sched_val},{wcrt_val_str},{comp_sched_val}\n")
                                elif comp and hasattr(comp,
                                                      'tasks') and not comp.tasks:  # Component exists but has no tasks
                                    # Represent component schedulability even if no tasks.
                                    # It doesn't make sense to output "task rows" for a component with no tasks.
                                    # solution.csv is task-centric.
                                    pass

                msg_complete = f"Analysis complete! {solution_file} and {analysis_log_file} have been generated."
                print(msg_complete, file=log_f);
                print(msg_complete)
            except IOError as e:
                err_io_msg = f"Error: Could not write {solution_file}: {e}"
                print(err_io_msg, file=log_f);
                print(err_io_msg, file=sys.stderr)
            except Exception as e:
                err_gen_msg = f"Error generating {solution_file}: {e}"
                print(err_gen_msg, file=log_f);
                print(err_gen_msg, file=sys.stderr)
                import traceback

                traceback.print_exc(file=log_f)
                traceback.print_exc()


    except FileNotFoundError as e:
        err_fnf_msg = f"Error: {str(e)}"
        # If log_f was opened, try to write. Otherwise, just print to stderr.
        if 'log_f' in locals() and not log_f.closed: print(err_fnf_msg, file=log_f)
        print(err_fnf_msg, file=sys.stderr);
        sys.exit(1)
    except ValueError as e:
        err_val_msg = f"Data loading/validation error: {str(e)}"
        if 'log_f' in locals() and not log_f.closed: print(err_val_msg, file=log_f)
        print(err_val_msg, file=sys.stderr);
        sys.exit(1)
    except Exception as e:
        err_unexpected_msg = f"An unexpected error occurred: {str(e)}"
        # If log_f was opened, try to write. Otherwise, just print to stderr.
        if 'log_f' in locals() and not log_f.closed:
            print(err_unexpected_msg, file=log_f)
            import traceback

            traceback.print_exc(file=log_f)
        print(err_unexpected_msg, file=sys.stderr)
        import traceback;

        traceback.print_exc();
        sys.exit(1)