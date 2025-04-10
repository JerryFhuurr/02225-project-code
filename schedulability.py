from models import Task, Component, Core
from bdr_calculator import BDRCalculator
from optimizer import BDRInterfaceOptimizer
import math

class SchedulabilityAnalyzer:
    def __init__(self, cores):
        self.cores = cores
        self._component_map = self._build_component_map()

    def analyze(self):
        """执行完整分析流程"""
        print("===== 开始层次化可调度性分析 =====")
        self._calculate_bdr_parameters()
        return self._hierarchical_verification()

    def _build_component_map(self):
        """构建组件ID到对象的映射"""
        component_map = {
            comp.id: comp
            for core in self.cores
            for comp in core.components
        }
        print(f"[调试] 已加载组件列表: {list(component_map.keys())}")
        return component_map

    def _calculate_bdr_parameters(self):
        """为每个组件计算BDR参数"""
        print("\n===== 计算BDR参数 =====")
        for core in self.cores:
            for comp in core.components:
                print(f"\n[调试] 正在处理组件 {comp.id}（算法: {comp.algorithm}）")
                print(f"[调试] 组件参数: budget={comp.budget}, period={comp.period}, 任务数={len(comp.tasks)}")
                
                # 关键修复1: 计算任务总利用率并验证预算约束
                total_utilization = sum(task.wcet / task.period for task in comp.tasks)
                budget_utilization = comp.budget / comp.period
                if total_utilization > budget_utilization + 1e-9:  # 处理浮点误差
                    raise ValueError(f"组件 {comp.id} 任务总利用率 {total_utilization:.2f} > 预算利用率 {budget_utilization:.2f}")

                # 调试任务参数
                for i, task in enumerate(comp.tasks):
                    print(f"[调试] 任务{i+1}: id={task.id}, wcet={task.wcet}, period={task.period}, deadline={task.deadline}")

                hyperperiod = self._calculate_hyperperiod(comp)
                print(f"[调试] 组件 {comp.id} 的超周期: {hyperperiod}")
                
                # 关键修复2: 传入组件预算和周期参数
                optimizer = BDRInterfaceOptimizer(
                    tasks=comp.tasks,
                    algorithm=comp.algorithm,
                    budget=comp.budget,
                    period=comp.period,
                    max_t=min(hyperperiod, 1000)  # 限制最大计算范围
                )
                alpha, delta = optimizer.find_min_delta()
                
                # 类型安全校验
                if alpha is None or delta is None:
                    raise ValueError(f"组件 {comp.id} 的BDR参数计算失败 (alpha={alpha}, delta={delta})")
                
                comp.alpha = alpha
                comp.delta = delta
                print(f"[调试] 组件 {comp.id} 的BDR参数: α={alpha:.2f}, Δ={delta}")

    def _hierarchical_verification(self):
        """层次化可调度性验证"""
        print("\n===== 开始层次化验证 =====")
        results = []
        for core in self.cores:
            core_result = self._verify_core_level(core)
            results.extend(core_result)
        return results

    def _verify_core_level(self, core):
        """核心级全局调度验证"""
        print(f"\n[调试] 验证核心 {core.id}（调度算法: {core.global_algorithm}）")
        
        # 调试核心级参数
        print(f"[调试] 核心速度因子: {core.speed_factor}")
        print(f"[调试] 核心包含组件数: {len(core.components)}")
        
        # 校验alpha参数
        for comp in core.components:
            if comp.alpha is None:
                raise ValueError(f"组件 {comp.id} 的alpha参数未初始化")

        total_alpha = sum(comp.alpha for comp in core.components)
        print(f"[调试] 核心 {core.id} 总资源需求: {total_alpha:.2f}")
        
        if total_alpha > 1.0:
            return [f"Core {core.id} 不可调度：总资源需求 {total_alpha:.2f} > 1"]
        
        results = []
        for comp in core.components:
            if self._verify_component(comp):
                results.append(f"组件 {comp.id} 可调度 (α={comp.alpha:.2f}, Δ={comp.delta})")
            else:
                results.append(f"组件 {comp.id} 不可调度：父资源不足")
        return results
    
    def _verify_component(self, comp):
        """验证组件级可调度性（新增的缺失方法）"""
        # 获取父核心资源供给
        core = next(c for c in self.cores if comp in c.components)
        allocated_resource = core.speed_factor * comp.alpha
        
        # 计算组件实际需求
        component_demand = sum(task.wcet / task.period for task in comp.tasks)
        
        # 精度处理
        return allocated_resource >= component_demand - 1e-9

    def _critical_time_points(self, comp):
        """生成组件关键时间点"""
        points = set()
        for task in comp.tasks:
            points.update(range(task.deadline, 2*comp.delta, task.period))
        return sorted(points)

    @staticmethod
    def _calculate_component_dbf(comp, t):
        """计算组件的DBF"""
        if comp.algorithm == 'EDF':
            return BDRCalculator.dbf_edf(comp.tasks, t)
        else:
            return max(
                BDRCalculator.dbf_fps(comp.tasks, t, i)
                for i in range(len(comp.tasks))
            )

    @staticmethod
    def _calculate_hyperperiod(comp):
        """计算组件任务的超周期（添加防御性校验）"""
        periods = [task.period for task in comp.tasks]
        
        # 校验周期有效性
        for p in periods:
            if not isinstance(p, int) or p <= 0:
                raise ValueError(f"组件 {comp.id} 包含无效任务周期: {p}")
        
        if not periods:
            print(f"[警告] 组件 {comp.id} 没有任务，使用默认超周期 1000")
            return 1000
        
        try:
            return math.lcm(*periods)
        except Exception as e:
            raise ValueError(f"组件 {comp.id} 超周期计算失败: {str(e)}")