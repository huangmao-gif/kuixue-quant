# -*- coding: utf-8 -*-
"""
1年期v2.6全策略回测 + 连板修正
"""
import json, sys, io
from collections import defaultdict
from datetime import datetime, timedelta
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

WORKSPACE = r'C:\Users\11503\.openclaw-autoclaw\workspace'

with open(f'{WORKSPACE}/kuixue_1year_result.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
events = data['events']

with open(f'{WORKSPACE}/kuixue_market_stats.json', 'r', encoding='utf-8') as f:
    market_stats = json.load(f)

# 重新计算连板（修正版：只看最近5天）
code_events_map = defaultdict(list)
for e in events:
    code_events_map[e['code']].append(e)

streak_map = {}
for code, evts in code_events_map.items():
    evts.sort(key=lambda x: x['date'])
    for i in range(len(evts)):
        streak = 1
        for j in range(i-1, -1, -1):
            diff = (datetime.strptime(evts[i]['date'], '%Y-%m-%d') - datetime.strptime(evts[j]['date'], '%Y-%m-%d')).days
            if diff <= 3:
                streak += 1
            else:
                break
            if j == 0 and diff <= 3:
                pass  # 继续往前
        streak_map[(code, evts[i]['date'])] = streak

# 应用修正连板
for e in events:
    e['streak'] = streak_map.get((e['code'], e['date']), 1)

valid = [e for e in events if e.get('next_pct') is not None]

# 连板分布（修正后）
print("修正后连板分布:")
streak_dist = defaultdict(int)
for e in valid:
    streak_dist[e['streak']] += 1
for k in sorted(streak_dist.keys())[:6]:
    label = {1:'首板',2:'2板',3:'3板',4:'4板',5:'5板'}.get(k, f'{k}板')
    sub = [e for e in valid if e['streak']==k]
    s_up = sum(1 for e in sub if e['actual']=='涨')
    print(f"  {label}: {len(sub)}只 | 胜率{s_up/len(sub)*100:.1f}% | 均{sum(e['next_pct'] for e in sub)/len(sub):+.2f}%")

# 换手率
for e in events:
    e['turnover_t'] = e.get('turnover', 0)

# ============================================================
# 1年期 vs 3月期 回测对比
# ============================================================
print(f"\n{'='*60}")
print(f"1年期 vs 3月期回测对比")
print(f"{'='*60}")

combo_fn = lambda e: (e['streak']==1 and e.get('turnover_t',0)<15) or (e['streak']==2 and e.get('turnover_t',0)<10)

# 模拟
def simulate(events_list, signal_fn, market_stats=None, filter_mode='none',
             max_positions=3, position_pct=0.25, gap=1.5, slip=1.0, comm=0.15, sl=-5):
    by_date = defaultdict(list)
    for e in events_list:
        by_date[e['date']].append(e)
    
    capital = 1.0; trades = 0; skipped = 0
    monthly_returns = defaultdict(float)
    
    for d in sorted(by_date.keys()):
        if filter_mode != 'none' and market_stats and d in market_stats:
            if market_stats[d]['market_state'] == 'forbid':
                skipped += 1; continue
        sigs = [e for e in by_date[d] if signal_fn(e)]
        sigs.sort(key=lambda e: e.get('turnover_t',0))
        sel = sigs[:max_positions]
        if not sel: continue
        day_pnl = 0
        for e in sel:
            raw = e['next_pct']
            if raw is None: continue
            act = raw - gap - slip - comm
            if (raw - gap) < sl: act = sl - slip - comm
            day_pnl += position_pct * (act/100)
            trades += 1
        capital *= (1 + day_pnl)
        month = d[:7]
        monthly_returns[month] += day_pnl
    
    total_pct = (capital-1)*100
    n_months = len(monthly_returns)
    avg_monthly = ((capital**(1/n_months))-1)*100 if n_months > 0 else 0
    return capital, trades, skipped, avg_monthly, monthly_returns

print(f"\n{'策略':>30} | {'1年期总':>8} | {'月均':>8} | {'交易':>5}")
print("-"*60)

for label, fn, fm, gap in [
    ("v2.5原版", combo_fn, 'none', 1.5),
    ("+大盘过滤", combo_fn, 'no_forbid', 1.5),
    ("+大盘+回调(0.5%)", combo_fn, 'no_forbid', 0.5),
]:
    final, trades, skipped, monthly, mr = simulate(valid, fn, market_stats, filter_mode=fm, gap=gap)
    print(f"  {label:>30} | {(final-1)*100:>+7.1f}% | {monthly:>+7.1f}% | {trades:>5}")

# 按季度看稳定性
print(f"\n按季度月均收益:")
final_all, _, _, _, mr = simulate(valid, combo_fn, market_stats, filter_mode='none', gap=1.5)

quarters = {
    '25Q2': ['2025-04','2025-05','2025-06'],
    '25Q3': ['2025-07','2025-08','2025-09'],
    '25Q4': ['2025-10','2025-11','2025-12'],
    '26Q1': ['2026-01','2026-02','2026-03'],
    '26Q4': ['2026-04'],
}

for qname, months in quarters.items():
    sub_events = [e for e in valid if any(e['date'].startswith(m) for m in months)]
    if not sub_events: continue
    f, t, s, m, _ = simulate(sub_events, combo_fn, filter_mode='none', gap=1.5)
    print(f"  {qname}: {(f-1)*100:+.1f}% ({len(sub_events)}只) | 月均{m:+.1f}%")

# 2板+换手<10% 在1年期数据中的表现
print(f"\n--- 连板×换手率二维矩阵（1年期）---")
for streak in [1, 2, 3]:
    for turn_range, turn_label in [((0,10),"<10%"), ((10,20),"10-20%"), ((20,100),">20%")]:
        sub = [e for e in valid if e['streak']==streak and turn_range[0]<=e.get('turnover_t',0)<turn_range[1]]
        if len(sub) < 10: continue
        up = sum(1 for e in sub if e['actual']=='涨')
        wr = up/len(sub)*100
        avg = sum(e['next_pct'] for e in sub)/len(sub)
        print(f"  {streak}板+换手{turn_label}: {len(sub)}只 | 胜率{wr:.1f}% | 均{avg:+.2f}%")

# 金牌策略：2板+换手<10% 月度一致性
golden = [e for e in valid if e['streak']==2 and e.get('turnover_t',0)<10]
if golden:
    print(f"\n--- 黄金入场点(2板+换手<10%) 按月 ---")
    by_m = defaultdict(list)
    for e in golden:
        by_m[e['date'][:7]].append(e)
    for m in sorted(by_m.keys()):
        sub = by_m[m]
        up = sum(1 for e in sub if e['actual']=='涨')
        wr = up/len(sub)*100
        avg = sum(e['next_pct'] for e in sub)/len(sub)
        print(f"  {m}: {len(sub)}只 | 胜率{wr:.1f}% | 均{avg:+.2f}%")

print(f"\n✅ 1年期回测完成")
