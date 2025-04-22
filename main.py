# main.py
import sys
import os
import pandas as pd
from models import Task, Component, Core
from schedulability import SchedulabilityAnalyzer


def load_data(tasks_csv, budgets_csv, arch_csv):
    """数据加载函数，添加完整的数据验证"""
    cores = {}

    # 加载核心架构
    try:
        arch_df = pd.read_csv(arch_csv, dtype={
            'core_id': 'string',
            'speed_factor': 'float64',
            'scheduler': 'string'
        })
        cores = {row['core_id']: Core(
            core_id=row['core_id'],
            speed_factor=row['speed_factor'],
            scheduler=row['scheduler']
        ) for _, row in arch_df.iterrows()}
    except Exception as e:
        raise ValueError(f"架构文件加载失败: {str(e)}")

    # 加载组件
    try:
        budgets_df = pd.read_csv(budgets_csv, dtype={
            'component_id': 'string',
            'scheduler': 'string',
            'core_id': 'string',
            'budget': 'float64',
            'period': 'float64',
            'priority': 'Int64'
        })

        for _, row in budgets_df.iterrows():
            comp = Component(
                component_id=row['component_id'],
                scheduler=row['scheduler'],
                core_id=row['core_id'],
                budget=row['budget'],
                period=row['period'],
                priority=row.get('priority')
            )
            cores[row['core_id']].components.append(comp)
    except Exception as e:
        raise ValueError(f"组件文件加载失败: {str(e)}")

    # 加载任务
    try:
        tasks_df = pd.read_csv(tasks_csv, dtype={
            'task_name': 'string',
            'wcet': 'float64',
            'period': 'float64',
            'component_id': 'string',
            'priority': 'Int64'
        })

        for _, row in tasks_df.iterrows():
            task = Task(
                task_name=row['task_name'],
                wcet=row['wcet'],
                period=row['period'],
                component_id=row['component_id'],
                priority=row.get('priority')
            )

            # 关联到组件
            for core in cores.values():
                for comp in core.components:
                    if comp.component_id == task.component_id:
                        comp.tasks.append(task)
                        # 初始化响应时间字段
                        task.adjusted_wcet = 0.0
                        task.wcrt = 0.0
                        task.schedulable = False
                        break

    except Exception as e:
        raise ValueError(f"任务文件加载失败: {str(e)}")

    return list(cores.values())


if __name__ == "__main__":
    try:
        cores = load_data("tasks.csv", "budgets.csv", "architecture.csv")

        # 运行分析
        analyzer = SchedulabilityAnalyzer(cores)
        analysis_results = analyzer.analyze()

        # 打印分析结果
        print("\n===== 分析结果 =====")
        for result in analysis_results:
            print(result)

            # 生成solution.csv
            print("\n生成 solution.csv...")
            with open("solution.csv", "w") as f:
                # Add 'wcrt' to the header and output
                f.write(
                    "task_name,component_id,task_schedulable,wcrt,max_response_time,component_schedulable\n")
                for core in cores:
                    for comp in core.components:

                        comp_schedulable = comp.schedulable  # Use the value set during analysis

                        for task in comp.tasks:
                            task_sched = int(task.schedulable)
                            f.write(f"{task.task_name},{comp.component_id},")
                            f.write(f"{task_sched},")
                            f.write(f"{task.wcrt:.2f},")  # WCRT calculated
                            f.write(f"{task.wcrt:.2f},")  # Max Response Time = WCRT
                            f.write(f"{int(comp_schedulable)}\n")
            print("分析完成！solution.csv 已生成。")

    except Exception as e:
        print(f"错误: {str(e)}")
        sys.exit(1)