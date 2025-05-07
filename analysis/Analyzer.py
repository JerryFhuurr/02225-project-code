import os, math, pandas as pd
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# —————— 配置 ——————
INPUT_DIR  = "D:\\Desktop\\Study\\02225 Distributed real-time systems\\Project\\analysis tool\\test_cases\\5-huge-test-case"
OUTPUT_DIR = "D:\\Desktop\\Study\\02225 Distributed real-time systems\\Project\\analysis tool\\Results\\out_case5"
LCM_FACTOR = 5
os.makedirs(OUTPUT_DIR, exist_ok=True)

logs = []
def log(msg=""):
    print(msg)
    logs.append(str(msg))

def lcm(a, b):
    return abs(a*b) // math.gcd(a,b) if a and b else 0

# EDF Demand Bound Function
def dbf_edf(ws, t):
    return sum((t//T)*C for C,T in ws)

# BDR Supply Bound Function
def sbf_bdr(alpha, delta, t):
    return alpha*(t-delta) if t >= delta else 0.0

# RM RTA but using BDR service constraint
def rm_rta_bdr(ts, alpha, delta):
    ts_sorted = sorted(ts, key=lambda x: x['prio'])
    res = {}
    for i, tk in enumerate(ts_sorted):
        C, T, name = tk['C'], tk['T'], tk['name']
        R = C/alpha + delta
        while True:
            I = 0.0
            for th in ts_sorted[:i]:
                I += math.ceil(R / th['T'])*th['C']
            D = C + I
            Rn = D/alpha + delta
            if abs(Rn-R) < 1e-9 or Rn > T + 1e-9:
                R = Rn
                break
            R = Rn
        res[name] = (R <= T + 1e-9, R)
    return res

# ============ 分析器主逻辑（直接运行） ============

# 1. 读表
tasks_df   = pd.read_csv(os.path.join(INPUT_DIR, 'tasks.csv'))
budgets_df = pd.read_csv(os.path.join(INPUT_DIR, 'budgets.csv'))
arch_df    = pd.read_csv(os.path.join(INPUT_DIR, 'architecture.csv'))
core_speed = dict(zip(arch_df.core_id, arch_df.speed_factor))
core_algo  = dict(zip(arch_df.core_id, arch_df.scheduler))

# 2. 组件表
comps = {}
for _, r in budgets_df.iterrows():
    comps[r.component_id] = {
        'sched': r.scheduler.upper(),
        'core':  r.core_id,
        'Q':     float(r.budget),
        'P':     float(r.period),
        'prio':  int(r.priority) if 'priority' in r and not pd.isna(r.priority) else None
    }

# 3. 合并任务→实际 WCET
merged = tasks_df.merge(
    budgets_df[['component_id','core_id']], on='component_id'
).merge(
    arch_df[['core_id','speed_factor']], on='core_id'
)
tasks = []
for _, r in merged.iterrows():
    comp = r.component_id
    if comp not in comps: continue
    tasks.append({
        'name': r.task_name,
        'comp': comp,
        'C':    float(r.wcet)/r.speed_factor,
        'T':    float(r.period),
        'prio': int(r.priority) if 'priority' in r and not pd.isna(r.priority) else None
    })

comp_ok = {}
# 4. 组件级分析
for comp, info in comps.items():
    log("="*60)
    core = info['core']
    speed = core_speed.get(core,1.0)
    log(f"[Component {comp}] sched={info['sched']} core={core} speed={speed:.2f}")
    ws = [(t['C'],t['T']) for t in tasks if t['comp']==comp]
    ts = [t for t in tasks if t['comp']==comp]
    if not ws:
        log("  (no tasks) → ✔ sched")
        comp_ok[comp]=True
        continue

    Q, P = info['Q'], info['P']
    alpha = Q/P
    delta = 2*(P-Q)
    log(f"  BDR interface → α={alpha:.6f}, Δ={delta:.6f}  (PRM Q={Q}, P={P})")

    ok = True
    if info['sched']=="EDF":
        Tmax = max(T for _,T in ws)
        limit = int(LCM_FACTOR*Tmax)
        for t in range(limit+1):
            d = dbf_edf(ws,t)
            s = sbf_bdr(alpha,delta,t)
            if d > s +1e-9:
                log(f"    ! t={t}: DBF={d:.3f} > SBF={s:.3f}")
                ok=False
                break
        log(f"  → EDF {'✔ sched' if ok else '✘ NOT sched'}")
    else:
        rr = rm_rta_bdr(ts, alpha, delta)
        for name,(sched,R) in rr.items():
            if not sched:
                log(f"    ! {name}: R={R:.3f} > T={next(t['T'] for t in ts if t['name']==name):.3f}")
                ok=False
            else:
                log(f"    ✔ {name}: R={R:.3f} ≤ T")
        log(f"  → RM {'✔ sched' if ok else '✘ NOT sched'}")

    comp_ok[comp]=ok

# 5. 核级合成
by_core={}
for comp,info in comps.items():
    a=info['Q']/info['P']
    d=2*(info['P']-info['Q'])
    by_core.setdefault(info['core'],[]).append((a,d))
core_ok={}
for c,lst in by_core.items():
    asum=sum(a for a,_ in lst)
    dmin=min(d for _,d in lst)
    ok=(asum<=1+1e-9 and dmin>=-1e-9)
    log("="*60)
    log(f"[Core {c}] ∑α={asum:.6f}≤1? minΔ={dmin:.6f}≥0? → {'✔' if ok else '✘'}")
    core_ok[c]=ok

# 6. 输出 solution.csv
sol=[]
for t in tasks:
    sched = comp_ok[t['comp']]
    sol.append({
        'task_name':t['name'],
        'component_id':t['comp'],
        'task_schedulable':sched,
        'component_schedulable':sched
    })
pd.DataFrame(sol).to_csv(f"{OUTPUT_DIR}/solution.csv", index=False)
log(f"Wrote solution.csv → {OUTPUT_DIR}/solution.csv")

# 7. 输出 analysis.txt
overall = all(comp_ok.values()) and all(core_ok.values())
with open(f"{OUTPUT_DIR}/analysis.txt", 'w', encoding='utf-8') as f:
    f.write("\n".join(logs))
    f.write(f"\n\n=== Overall case schedulable: {overall} ===\n")
log(f"Wrote analysis.txt → {OUTPUT_DIR}/analysis.txt")
log(f"\n=== Overall case schedulable: {overall} ===")
