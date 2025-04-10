import sys
import os
import pandas as pd
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import Task, Component, Core
from schedulability import SchedulabilityAnalyzer

def load_data(tasks_csv, budgets_csv, arch_csv):
    # ================ 核心架构加载 ================
    cores = {}
    arch_df = pd.read_csv(arch_csv)
    for _, row in arch_df.iterrows():
        cores[row['core_id']] = Core(
            core_id=row['core_id'],
            speed_factor=float(row['speed_factor']),
            global_algorithm=row['scheduler']
        )

    # ================ 组件数据加载 ================
    components = {}
    budgets_df = pd.read_csv(budgets_csv)
    budgets_df['priority'] = budgets_df['priority'].fillna(0).astype(int)
    for _, row in budgets_df.iterrows():
        comp = Component(
            comp_id=row['component_id'],
            algorithm=row['scheduler'],
            core_id=row['core_id'],
            budget=int(row['budget']),
            period=int(row['period']),
            priority=int(row.get('priority'))
        )
        components[comp.id] = comp
        # print("已加载组件ID列表:", list(components.keys()))
        cores[row['core_id']].components.append(comp)

    # ================ 任务数据加载 ================
    tasks_df = pd.read_csv(tasks_csv)

    tasks_df['priority'] = tasks_df['priority'].fillna(0).astype(int)  # 最终强制为整数
    # 数据有效性验证
    required_columns = ['task_name', 'wcet', 'period', 'component_id', 'priority']
    if not set(required_columns).issubset(tasks_df.columns):
        missing = set(required_columns) - set(tasks_df.columns)
        raise ValueError(f"CSV文件缺少必要列: {missing}")

    for _, row in tasks_df.iterrows():
        # 组件存在性验证
        component_id = row['component_id']
        if component_id not in components:
            raise ValueError(f"任务 {row['task_name']} 分配到不存在的组件 {component_id}")

        # 数值类型验证
        try:
            task = Task(
                task_id=row['task_name'],
                wcet=int(row['wcet']),
                period=int(row['period']),
                component=component_id,
                priority=int(row['priority'])
            )
            components[component_id].tasks.append(task)
        except ValueError as e:
            raise ValueError(f"任务 {row['task_name']} 数据格式错误") from e

    return list(cores.values())

if __name__ == "__main__":
    try:
        cores = load_data(
            tasks_csv="tasks.csv",
            budgets_csv="budgets.csv",
            arch_csv="architecture.csv"
        )
        analyzer = SchedulabilityAnalyzer(cores)
        results = analyzer.analyze()
        
        print("===== 层次化可调度性分析报告 =====")
        for line in results:
            print(f"• {line}")
            
    except Exception as e:
        print(f"错误: {str(e)}")  # 错误信息