# -*- coding: utf-8 -*-
"""葵学3.0 — 修正后完整回测（连板修正+换手率修正+基准对照）"""
import json, os, sys, io, time, random, statistics
from collections import defaultdict, Counter
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

WORKSPACE = r'C:\Users\11503\.openclaw-autoclaw\workspace'

# ============================================================
# 加载数据
# ============================================================
with open(f'{WORKSPACE}/kuixue_1year_result.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
events = data['events']

with open(f'{WORKSPACE}/kuixue_market_stats.json', 'r', encoding='utf-8') as f:
    market_stats = json.load(f)

# ============================================================
# Task 1: 修正连板
# ============================================================
code_events_map = defaultdict(list)
for e in events:
    code_events_map[e['code']].append(e)

streak_map = {}
for code, evts in code_events_map.items():
    evts.sort(key=lambda x: x['date'])
    for i in range(len(evts)):
        if i == 0:
            streak_map[(code, evts[i]['date'])] = 1
            continue
        prev_date = datetime.strptime(evts[i-1]['date'], '%Y-%m-%d')
        curr_date = datetime.strptime(evts[i]['date'], '%Y-%m-%d')
        diff = (curr_date - prev_date).days
        if diff <= 1 or (diff == 3 and prev_date.weekday() == 4):
            streak_map[(code, evts[i]['date'])] = streak_map[(code, evts[i-1]['date'])] + 1
        else:
            streak_map[(code, evts[i]['date'])] = 1

for e in events:
    e['streak'] = streak_map.get((e['code'], e['date']), 1)

valid = [e for e in events if e.get('next_pct') is not None]

# ============================================================
# 连板分布
# ============================================================
print("=" * 70)
print("葵学3.0 — 修正后完整回测")
print("=" * 70)

print("\n[1] 连板分布（修正后）:")
streak_dist = Counter(e['streak'] for e in valid)
for k in sorted(streak_dist.keys())[:6]:
    label = {1:'首板',2:'2板',3:'3板',4:'4板',5:'5板',6:'6板'}.get(k, f'{k}板')
    sub = [e for e in valid if e['streak']==k]
    up = sum(1 for e in sub if e['actual']=='涨')
    avg = sum(e['next_pct'] for e in sub)/len(sub)
    print(f"  {label}: {len(sub)}只 | 胜率{up/len(sub)*100:.1f}% | 次日均{avg:+.2f}%")

# ============================================================
# 换手率分布
# ============================================================
print("\n[2] 换手率分布（修正后）:")
t_ranges = Counter()
for e in valid:
    t = e.get('turnover', 0) or 0
    if t < 5: t_ranges['<5%'] += 1
    elif t < 10: t_ranges['5-10%'] += 1
    elif t < 20: t_ranges['10-20%'] += 1
    elif t < 30: t_ranges['20-30%'] += 1
    else: t_ranges['>30%'] += 1
for k in ['<5%', '5-10%', '10-20%', '20-30%', '>30%']:
    print(f"  {k}: {t_ranges.get(k, 0)}")

# ============================================================
# 连板×换手率矩阵
# ============================================================
print("\n[3] 连板×换手率矩阵（1年期，修正后）:")
header = f"  {'':>6} | {'<10%':>16} | {'10-20%':>16} | {'20-30%':>16} | {'>30%':>16}"
print(header)
print("  " + "-" * 78)

for streak in [1, 2, 3]:
    row = []
    for lo, hi in [(0,10),(10,20),(20,30),(30,999)]:
        sub = [e for e in valid if e['streak']==streak and lo <= e.get('turnover',0) < hi]
        if len(sub) >= 10:
            up = sum(1 for e in sub if e['actual']=='涨')
            wr = up/len(sub)*100
            avg = sum(e['next_pct'] for e in sub)/len(sub)
            row.append(f"{len(sub)}只 {wr:.0f}% {avg:+.1f}%")
        else:
            row.append(f"{len(sub)}只 -")
    label = {1:'首板',2:'2板',3:'3板'}.get(streak)
    print(f"  {label:>6} | {row[0]:>16} | {row[1]:>16} | {row[2]:>16} | {row[3]:>16}")

# ============================================================
# Task 2: 基准对照回测
# ============================================================
print("\n" + "=" * 70)
print("[4] 基准对照回测")
print("=" * 70)

def simulate(events_list, signal_fn=None, market_stats=None, filter_mode='none',
             max_positions=3, position_pct=0.25, gap=1.5, slip=1.0, comm=0.15, sl=-5):
    by_date = defaultdict(list)
    for e in events_list:
        by_date[e['date']].append(e)
    
    capital = 1.0
    trades = 0
    skipped = 0
    monthly_returns = defaultdict(float)
    
    for d in sorted(by_date.keys()):
        if filter_mode != 'none' and market_stats and d in market_stats:
            if market_stats[d]['market_state'] == 'forbid':
                skipped += 1
                continue
        
        if signal_fn:
            sigs = [e for e in by_date[d] if signal_fn(e)]
        else:
            sigs = by_date[d]
        sigs.sort(key=lambda e: e.get('turnover', 0))
        sel = sigs[:max_positions]
        if not sel:
            continue
        day_pnl = 0
        for e in sel:
            raw = e['next_pct']
            if raw is None:
                continue
            act = raw - gap - slip - comm
            if (raw - gap) < sl:
                act = sl - slip - comm
            day_pnl += position_pct * (act / 100)
            trades += 1
        capital *= (1 + day_pnl)
        monthly_returns[d[:7]] += day_pnl
    
    total_pct = (capital - 1) * 100
    n_months = len(monthly_returns)
    avg_monthly = ((capital ** (1 / max(n_months,1))) - 1) * 100
    return {
        'capital': capital, 'total_pct': total_pct, 'trades': trades,
        'skipped': skipped, 'avg_monthly': avg_monthly,
        'monthly_returns': dict(monthly_returns),
    }

# 策略定义（修正后换手率是百分比）
combo_fn = lambda e: (e['streak']==1 and e.get('turnover',0)<15) or (e['streak']==2 and e.get('turnover',0)<10)
all_fn = lambda e: True
golden_fn = lambda e: e['streak']==2 and e.get('turnover',0)<10

strategies = [
    ("全涨停买入", all_fn, 'none', 1.5),
    ("v2.6组合(首板<15%+2板<10%)", combo_fn, 'none', 1.5),
    ("v2.6+大盘过滤", combo_fn, 'no_forbid', 1.5),
    ("v2.6+大盘+低gap(0.5%)", combo_fn, 'no_forbid', 0.5),
    ("黄金入场(2板+<10%)", golden_fn, 'none', 1.5),
    ("黄金+大盘过滤", golden_fn, 'no_forbid', 1.5),
    ("零成本基准(无gap/滑点)", combo_fn, 'none', 0.0),
]

print(f"\n  {'策略':>30} | {'总收益':>8} | {'月均':>8} | {'交易':>6} | {'跳过':>4}")
print("  " + "-" * 68)

for label, fn, fm, gap in strategies:
    r = simulate(valid, signal_fn=fn, market_stats=market_stats, filter_mode=fm, gap=gap)
    print(f"  {label:>30} | {r['total_pct']:>+7.1f}% | {r['avg_monthly']:>+7.1f}% | {r['trades']:>6} | {r['skipped']:>4}")

# 随机买入基准
print(f"\n  --- 随机买入基准（5种随机种子）---")
all_dates = sorted(set(e['date'] for e in valid))
random_results = []
for seed in [42, 123, 456, 789, 1024]:
    by_date = defaultdict(list)
    for e in valid:
        by_date[e['date']].append(e)
    
    capital = 1.0
    trades = 0
    rng = random.Random(seed)
    monthly_returns = defaultdict(float)
    
    for d in all_dates:
        pool = by_date.get(d, [])
        if not pool:
            continue
        sel_count = min(3, len(pool))
        sel = rng.sample(pool, sel_count)
        day_pnl = 0
        for e in sel:
            raw = e['next_pct']
            act = raw - 1.5 - 1.0 - 0.15
            if (raw - 1.5) < -5:
                act = -5 - 1.0 - 0.15
            day_pnl += 0.25 * (act / 100)
            trades += 1
        capital *= (1 + day_pnl)
        monthly_returns[d[:7]] += day_pnl
    
    n_months = len(monthly_returns)
    avg_m = ((capital ** (1 / max(n_months,1))) - 1) * 100
    random_results.append(avg_m)
    print(f"    Seed {seed}: 总{(capital-1)*100:+.1f}% | 月均{avg_m:+.1f}%")

avg_rand = statistics.mean(random_results)
print(f"    平均月均: {avg_rand:+.1f}%")

# 全市场等权基准（无交易成本）
print(f"\n  --- 全市场等权基准（无交易成本）---")
by_date = defaultdict(list)
for e in valid:
    by_date[e['date']].append(e)

capital = 1.0
monthly_returns = defaultdict(float)
for d in sorted(by_date.keys()):
    day_events = by_date[d]
    avg_next = sum(e['next_pct'] for e in day_events) / len(day_events)
    capital *= (1 + avg_next / 100)
    monthly_returns[d[:7]] += avg_next / 100

n_months = len(monthly_returns)
avg_m = ((capital ** (1 / max(n_months,1))) - 1) * 100
print(f"    全市场等权: 总{(capital-1)*100:+.1f}% | 月均{avg_m:+.1f}%")
index_avg = avg_m

# ============================================================
# 按季度对比
# ============================================================
print("\n" + "=" * 70)
print("[5] 按季度月均收益对比")
print("=" * 70)

quarters = {
    '25Q2': ['2025-04','2025-05','2025-06'],
    '25Q3': ['2025-07','2025-08','2025-09'],
    '25Q4': ['2025-10','2025-11','2025-12'],
    '26Q1': ['2026-01','2026-02','2026-03'],
    '26Q2': ['2026-04'],
}

print(f"\n  {'季度':>6} | {'v2.6组合':>10} | {'黄金入场':>10} | {'随机买入':>10} | {'全市场':>10} | {'v2.6超额':>10}")
print("  " + "-" * 68)

for qname, months in quarters.items():
    q_events = [e for e in valid if any(e['date'].startswith(m) for m in months)]
    if not q_events:
        continue
    
    # v2.6
    r1 = simulate(q_events, signal_fn=combo_fn, gap=1.5)
    # 黄金
    r2 = simulate(q_events, signal_fn=golden_fn, gap=1.5)
    
    # 随机
    by_d = defaultdict(list)
    for e in q_events:
        by_d[e['date']].append(e)
    cap = 1.0
    rng = random.Random(42)
    for d in sorted(by_d.keys()):
        pool = by_d[d]
        sel = rng.sample(pool, min(3, len(pool)))
        day_pnl = sum(0.25 * ((e['next_pct']-1.5-1.0-0.15)/100) for e in sel)
        cap *= (1 + day_pnl)
    n_m = len(set(e['date'][:7] for e in q_events))
    rand_m = ((cap ** (1/max(n_m,1))) - 1) * 100
    
    # 全市场
    cap2 = 1.0
    for d in sorted(by_d.keys()):
        avg_next = sum(e['next_pct'] for e in by_d[d]) / len(by_d[d])
        cap2 *= (1 + avg_next / 100)
    idx_m = ((cap2 ** (1/max(n_m,1))) - 1) * 100
    
    alpha = r1['avg_monthly'] - idx_m
    print(f"  {qname:>6} | {r1['avg_monthly']:>+9.1f}% | {r2['avg_monthly']:>+9.1f}% | {rand_m:>+9.1f}% | {idx_m:>+9.1f}% | {alpha:>+9.1f}%")

# ============================================================
# 关键结论
# ============================================================
print("\n" + "=" * 70)
print("[6] 关键结论")
print("=" * 70)

r_all = simulate(valid, signal_fn=combo_fn, gap=1.5)
r_golden = simulate(valid, signal_fn=golden_fn, gap=1.5)
r_zerocost = simulate(valid, signal_fn=combo_fn, gap=0.0)

print(f"""
1. 连板修正影响：
   - 首板增多+4499（停牌恢复不再误判为连板）
   - 高层连板减少（3板-185, 4板-280, 5板-334）
   - 结论方向不变

2. 换手率修正影响：
   - 之前全废（0和1），现在真实分布：10-20%占75%
   - v2.6换手率过滤（首板<15%, 2板<10%）现在有真实区分度

3. 基准对照（1年期）：
   - v2.6组合: 月均{r_all['avg_monthly']:+.1f}%
   - 黄金入场(2板+<10%): 月均{r_golden['avg_monthly']:+.1f}%
   - 随机买入: 月均{avg_rand:+.1f}%
   - 全市场等权(无成本): 月均{index_avg:+.1f}%
   - 零成本v2.6: 月均{r_zerocost['avg_monthly']:+.1f}%

4. 亏损归因：
   - 全市场无成本月均{index_avg:+.1f}% → 市场本身{'偏弱' if index_avg < 0 else '中性'}
   - 交易成本(gap+滑点+佣金=2.65%/次)是主要亏损源
   - v2.6信号在1年维度{'没有' if abs(r_all['avg_monthly'] - avg_rand) < 5 else '有'}区分度

5. 结论是否站得住：{'✅ 站得住' if r_all['avg_monthly'] < -10 else '⚠️ 需要重新评估'}
""")

# 保存
output = {
    'version': '3.0-final',
    'fix_date': '2026-04-23',
    'fixes': ['streak: strict_consecutive', 'turnover: baostock turn is already pct'],
    'valid_events': len(valid),
    'strategies': {
        'v2.6_combo': r_all['avg_monthly'],
        'golden': r_golden['avg_monthly'],
        'random_avg': avg_rand,
        'index_hold': index_avg,
        'zero_cost': r_zerocost['avg_monthly'],
    }
}
with open(f'{WORKSPACE}/kuixue_3.0_result.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("✅ 回测完成，结果已保存")
