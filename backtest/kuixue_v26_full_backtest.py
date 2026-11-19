# -*- coding: utf-8 -*-
"""
葵学 v2.6 — 大盘择时 + 板块联动 + T+2持仓 三合一回测
数据源：baostock
"""
import baostock as bs
import json, time, sys, io
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

START_DATE = '2026-02-01'
END_DATE = '2026-04-22'

# ============================================================
# Step 1: 拉取每日全市场涨跌统计
# ============================================================
print("="*60)
print("Step 1: 拉取每日市场统计数据")
print("="*60)

lg = bs.login()
print(f"baostock 登录: {lg.error_code} {lg.error_msg}")

# 拉取所有A股日线数据（用于统计每日涨跌家数、跌停家数等）
# 先获取股票列表
rs = bs.query_stock_basic()
all_codes = []
while rs.next():
    r = rs.get_row_data()
    code = r[0]
    if r[4] == '1' and (code.startswith('sh.6') or code.startswith('sz.0') or code.startswith('sz.3')):
        all_codes.append(code)

print(f"A股上市股票: {len(all_codes)} 只")

# 分批拉取日线数据，统计每日涨跌
# 太慢了，换个思路：用指数数据 + 抽样
# baostock 有 query_market_data 接口吗？没有
# 那就拉上证+深证指数，指数数据里有涨跌家数

# 方案B：直接用指数的涨跌数据，结合我们已有的涨停数据来推断市场状态
# 拉上证指数和深证成指
print("\n拉取指数数据...")

index_data = {}
for idx_code, idx_name in [('sh.000001', '上证指数'), ('sz.399001', '深证成指')]:
    rs = bs.query_history_k_data_plus(
        idx_code,
        "date,close,pctChg,turn",
        START_DATE, END_DATE,
        frequency="d", adjustflag="3"
    )
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    index_data[idx_name] = rows
    print(f"  {idx_name}: {len(rows)}天")

# 方案C：抽样拉取股票日线，统计每日涨跌家数
# 用随机抽样300只来估算市场状态（比全量快5倍）
import random
random.seed(42)
sample_codes = random.sample(all_codes, min(300, len(all_codes)))
print(f"\n抽样 {len(sample_codes)} 只股票统计每日涨跌...")

daily_stats = defaultdict(lambda: {
    'up': 0, 'down': 0, 'flat': 0, 'limit_up': 0, 'limit_down': 0, 'total': 0
})

batch_size = 50
for batch_start in range(0, len(sample_codes), batch_size):
    batch = sample_codes[batch_start:batch_start+batch_size]
    for code in batch:
        try:
            rs = bs.query_history_k_data_plus(
                code,
                "date,pctChg",
                START_DATE, END_DATE,
                frequency="d", adjustflag="3"
            )
            while rs.next():
                row = rs.get_row_data()
                d = row[0]
                try:
                    pct = float(row[1])
                except:
                    continue
                daily_stats[d]['total'] += 1
                if pct >= 9.9:
                    daily_stats[d]['limit_up'] += 1
                    daily_stats[d]['up'] += 1
                elif pct <= -9.9:
                    daily_stats[d]['limit_down'] += 1
                    daily_stats[d]['down'] += 1
                elif pct > 0.5:
                    daily_stats[d]['up'] += 1
                elif pct < -0.5:
                    daily_stats[d]['down'] += 1
                else:
                    daily_stats[d]['flat'] += 1
        except:
            pass
        time.sleep(0.03)
    
    done = min(batch_start + batch_size, len(sample_codes))
    if done % 100 == 0 or done == len(sample_codes):
        print(f"  已拉取 {done}/{len(sample_codes)} 只")

print(f"有统计数据的交易日: {len(daily_stats)} 天")

# 保存每日市场统计
market_stats = {}
for d in sorted(daily_stats.keys()):
    s = daily_stats[d]
    total = s['total']
    if total == 0:
        continue
    adv_dec_ratio = s['up'] / s['down'] if s['down'] > 0 else 99.0
    # 推算全市场（抽样比例）
    scale = len(all_codes) / len(sample_codes)
    estimated_limit_down = int(s['limit_down'] * scale)
    
    market_stats[d] = {
        'up': s['up'], 'down': s['down'], 'flat': s['flat'],
        'limit_up': s['limit_up'], 'limit_down': s['limit_down'],
        'total': total,
        'adv_dec_ratio': round(adv_dec_ratio, 2),
        'est_limit_down_all': estimated_limit_down,
        'market_state': 'allow' if (estimated_limit_down <= 20 and adv_dec_ratio >= 0.5) else
                       ('caution' if (estimated_limit_down <= 30 and adv_dec_ratio >= 0.3) else 'forbid')
    }

# 打印每日市场状态
print(f"\n{'日期':>12} | {'上涨':>4} | {'下跌':>4} | {'涨跌比':>6} | {'跌停(估)':>8} | {'状态':>6}")
print("-"*60)
for d in sorted(market_stats.keys()):
    s = market_stats[d]
    state_label = {'allow': '✅允许', 'caution': '⚠️谨慎', 'forbid': '❌禁止'}
    print(f"  {d} | {s['up']:>4} | {s['down']:>4} | {s['adv_dec_ratio']:>6.2f} | {s['est_limit_down_all']:>8} | {state_label[s['market_state']]}")

# 保存
with open(r'C:\Users\11503\.openclaw-autoclaw\workspace\kuixue_market_stats.json', 'w', encoding='utf-8') as f:
    json.dump(market_stats, f, ensure_ascii=False, indent=2)
print(f"\n市场统计已保存")

# ============================================================
# Step 2: 拉取行业分类（板块联动用）
# ============================================================
print("\n" + "="*60)
print("Step 2: 拉取行业分类")
print("="*60)

# baostock行业分类
rs = bs.query_stock_industry()
industry_map = {}
while rs.next():
    r = rs.get_row_data()
    # r[0]=code, r[1]=industry
    code = r[0]
    industry = r[1] if len(r) > 1 else ''
    if code.startswith('sh.6') or code.startswith('sz.0') or code.startswith('sz.3'):
        industry_map[code] = industry

print(f"有行业分类的股票: {len(industry_map)} 只")

# 行业分布
ind_counts = defaultdict(int)
for ind in industry_map.values():
    ind_counts[ind] += 1
top_ind = sorted(ind_counts.items(), key=lambda x: -x[1])[:15]
print("前15大行业:")
for ind, cnt in top_ind:
    print(f"  {ind}: {cnt}只")

bs.logout()
print("\nbaostock 登出")

# ============================================================
# Step 3: 大盘择时回测
# ============================================================
print("\n" + "="*60)
print("Step 3: 大盘择时回测")
print("="*60)

# 加载合并的涨停数据
with open(r'C:\Users\11503\.openclaw-autoclaw\workspace\kuixue_merged_result.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
events = data['events']

# 重建连板映射
code_events_map = defaultdict(list)
for e in events:
    code_events_map[e['code']].append(e)

streak_map = {}
for code, evts in code_events_map.items():
    evts.sort(key=lambda x: x['date'])
    streak = 1
    for i in range(len(evts)):
        if i == 0:
            streak_map[(code, evts[i]['date'])] = 1
            continue
        d_prev = evts[i-1]['date'].replace('-', '')
        d_curr = evts[i]['date'].replace('-', '')
        diff = int(d_curr) - int(d_prev)
        if diff <= 3:
            streak += 1
        else:
            streak = 1
        streak_map[(code, evts[i]['date'])] = streak

# 策略函数
combo_fn = lambda e: (
    (streak_map.get((e['code'], e['date']), 1) == 1 and e['turnover_t'] < 15) or
    (streak_map.get((e['code'], e['date']), 1) == 2 and e['turnover_t'] < 10)
)

# 模拟函数（现实版）
def simulate_with_filter(events_list, signal_fn, market_stats, 
                         filter_mode='none',  # none/allow_only/caution_ok
                         max_positions=3, position_pct=0.25,
                         gap_open_pct=1.5, slippage_pct=1.0, commission_pct=0.15,
                         stop_loss_pct=-5):
    by_date = defaultdict(list)
    for e in events_list:
        by_date[e['date']].append(e)
    
    capital = 1.0
    daily_returns = []
    trade_count = 0
    skipped_days = 0
    
    for d in sorted(by_date.keys()):
        # 大盘过滤
        if filter_mode != 'none' and d in market_stats:
            state = market_stats[d]['market_state']
            if filter_mode == 'allow_only' and state != 'allow':
                skipped_days += 1
                daily_returns.append(0)
                continue
            elif filter_mode == 'caution_ok' and state == 'forbid':
                skipped_days += 1
                daily_returns.append(0)
                continue
        
        signals = [e for e in by_date[d] if signal_fn(e)]
        signals.sort(key=lambda e: e['turnover_t'])
        selected = signals[:max_positions]
        
        if not selected:
            daily_returns.append(0)
            continue
        
        day_pnl = 0
        for e in selected:
            raw_pct = e['next_pct']
            if raw_pct is None:
                continue
            actual_pct = raw_pct - gap_open_pct - slippage_pct - commission_pct
            intraday_move = raw_pct - gap_open_pct
            if intraday_move < stop_loss_pct:
                actual_pct = stop_loss_pct - slippage_pct - commission_pct
            pnl = position_pct * (actual_pct / 100)
            day_pnl += pnl
            trade_count += 1
        
        capital *= (1 + day_pnl)
        daily_returns.append(day_pnl)
    
    return capital, trade_count, skipped_days, daily_returns

# 运行对比
valid = [e for e in events if e.get('next_pct') is not None]
filter_modes = [
    ('无过滤', 'none'),
    ('仅允许日交易', 'allow_only'),
    ('谨慎日也可(禁止日除外)', 'caution_ok'),
]

print(f"\n{'模式':>20} | {'3月总':>8} | {'月均':>8} | {'交易笔数':>6} | {'跳过天数':>6}")
print("-"*65)

for label, mode in filter_modes:
    final, trades, skipped, daily = simulate_with_filter(
        valid, combo_fn, market_stats, filter_mode=mode,
        max_positions=3, position_pct=0.25,
        gap_open_pct=1.5, slippage_pct=1.0, commission_pct=0.15
    )
    monthly = ((final**(1/3))-1)*100
    total_pct = (final-1)*100
    print(f"  {label:>20} | {total_pct:>+7.1f}% | {monthly:>+7.1f}% | {trades:>6} | {skipped:>6}")

# ============================================================
# Step 4: 板块联动回测
# ============================================================
print("\n" + "="*60)
print("Step 4: 板块联动回测")
print("="*60)

# 给涨停股添加行业分类
for e in events:
    e['industry'] = industry_map.get(e['code'], '未知')

# 按日期统计各行业涨停家数
date_industry_limitup = defaultdict(lambda: defaultdict(int))
for e in events:
    date_industry_limitup[e['date']][e['industry']] += 1

# 分析：板块涨停≥3家的个股 vs 孤立涨停
sector_confirmed = []  # 板块涨停≥3家
isolated = []          # 板块涨停<3家

for e in valid:
    d = e['date']
    ind = e.get('industry', '未知')
    ind_count = date_industry_limitup[d].get(ind, 0)
    e['sector_count'] = ind_count
    if ind_count >= 3:
        sector_confirmed.append(e)
    else:
        isolated.append(e)

print(f"\n板块涨停≥3家: {len(sector_confirmed)}只 | 孤立涨停: {len(isolated)}只")

for name, sub in [("板块≥3家确认", sector_confirmed), ("孤立涨停", isolated)]:
    up = sum(1 for e in sub if e['actual'] == '涨')
    down = sum(1 for e in sub if e['actual'] == '跌')
    pcts = [e['next_pct'] for e in sub if e['next_pct'] is not None]
    avg = sum(pcts)/len(pcts) if pcts else 0
    wr = up/len(sub)*100 if sub else 0
    wins = [p for p in pcts if p > 0]
    losses = [p for p in pcts if p < 0]
    avg_w = sum(wins)/len(wins) if wins else 0
    avg_l = sum(losses)/len(losses) if losses else 0
    pnl = abs(avg_w/avg_l) if avg_l != 0 else 0
    exp = wr/100*avg_w + (1-wr/100)*avg_l if sub else 0
    print(f"  {name}: {len(sub)}只 | 胜率{wr:.1f}% | 次日均{avg:+.2f}% | 盈亏比{pnl:.2f} | 期望{exp:+.2f}%")

# 板块联动 + 组合策略
sector_fn = lambda e: (
    combo_fn(e) and e.get('sector_count', 0) >= 3
)

print(f"\n--- 板块联动+组合策略 vs 纯组合策略 ---")
for label, fn in [("组合策略(无板块过滤)", combo_fn), ("组合+板块≥3家", sector_fn)]:
    final, trades, skipped, daily = simulate_with_filter(
        valid, fn, market_stats, filter_mode='none',
        max_positions=3, position_pct=0.25,
        gap_open_pct=1.5, slippage_pct=1.0, commission_pct=0.15
    )
    monthly = ((final**(1/3))-1)*100
    sub_valid = [e for e in valid if fn(e)]
    wr = sum(1 for e in sub_valid if e['actual']=='涨')/len(sub_valid)*100 if sub_valid else 0
    print(f"  {label}: 月均{monthly:+.1f}% | 交易{trades}笔 | 胜率{wr:.1f}%")

# ============================================================
# Step 5: T+2/T+3 持仓分析
# ============================================================
print("\n" + "="*60)
print("Step 5: T+2/T+3 持仓周期分析")
print("="*60)

# 需要每只股票的连续K线数据来计算T+2/T+3收益
# 用已有的事件数据，计算涨停后第2天、第3天的累计收益
# 但我们只有next_pct（次日），没有第3天数据
# 需要从baostock拉取这些涨停股的后续K线

# 先收集所有涨停股代码和日期
limitup_codes_dates = set()
for e in valid:
    limitup_codes_dates.add((e['code'], e['date']))

print(f"需要拉取T+2/T+3数据的涨停事件: {len(limitup_codes_dates)}个")

# 重新登录baostock
lg = bs.login()

# 拉取涨停股的5日K线（看T+1到T+3的累计收益）
t2_results = []
t3_results = []
processed = 0
errors = 0

for code, limit_date in list(limitup_codes_dates):
    try:
        rs = bs.query_history_k_data_plus(
            code,
            "date,pctChg",
            START_DATE, END_DATE,
            frequency="d", adjustflag="3"
        )
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        
        # 找到涨停日
        limit_idx = None
        for i, row in enumerate(rows):
            if row[0] == limit_date:
                limit_idx = i
                break
        
        if limit_idx is None:
            continue
        
        # T+1 (次日)
        t1_pct = float(rows[limit_idx+1][1]) if limit_idx+1 < len(rows) else None
        # T+2 (第3天)
        t2_pct = float(rows[limit_idx+2][1]) if limit_idx+2 < len(rows) else None
        # T+3 (第4天)
        t3_pct = float(rows[limit_idx+3][1]) if limit_idx+3 < len(rows) else None
        
        # 累计收益
        if t1_pct is not None:
            cum_t1 = t1_pct
            cum_t2 = t1_pct + (t2_pct if t2_pct is not None else 0)
            cum_t3 = t1_pct + (t2_pct if t2_pct is not None else 0) + (t3_pct if t3_pct is not None else 0)
            
            t2_results.append({
                'code': code, 'date': limit_date,
                't1': round(t1_pct, 2), 
                't2': round(t2_pct, 2) if t2_pct is not None else None,
                't3': round(t3_pct, 2) if t3_pct is not None else None,
                'cum_t1': round(cum_t1, 2),
                'cum_t2': round(cum_t2, 2),
                'cum_t3': round(cum_t3, 2),
                'turnover': next((e['turnover_t'] for e in valid if e['code']==code and e['date']==limit_date), 0),
                'streak': streak_map.get((code, limit_date), 1),
            })
    
    except Exception as ex:
        errors += 1
    
    processed += 1
    if processed % 200 == 0:
        print(f"  已处理 {processed}/{len(limitup_codes_dates)} (错误{errors})")
    time.sleep(0.03)

print(f"\nT+2/T+3数据拉取完成: {len(t2_results)}条, 错误{errors}条")

bs.logout()

# T+N收益分析
print(f"\n=== T+N 持仓周期收益分析 ===")
print(f"{'持仓周期':>8} | {'样本数':>6} | {'胜率':>6} | {'均涨':>8} | {'盈亏比':>6} | {'期望':>8}")
print("-"*55)

for period, key in [("T+1", "cum_t1"), ("T+2", "cum_t2"), ("T+3", "cum_t3")]:
    vals = [r for r in t2_results if r[key] is not None]
    if not vals:
        continue
    wins = [r[key] for r in vals if r[key] > 0]
    losses = [r[key] for r in vals if r[key] < 0]
    up_count = len(wins)
    total = len(vals)
    wr = up_count/total*100
    avg = sum(r[key] for r in vals)/total
    avg_w = sum(wins)/len(wins) if wins else 0
    avg_l = sum(losses)/len(losses) if losses else 0
    pnl = abs(avg_w/avg_l) if avg_l != 0 else 0
    exp = wr/100*avg_w + (1-wr/100)*avg_l
    print(f"  {period:>8} | {total:>6} | {wr:>5.1f}% | {avg:>+7.2f}% | {pnl:>5.2f} | {exp:>+7.2f}%")

# 按策略分组的T+N收益
print(f"\n=== 按信号分组的T+N收益 ===")
signal_groups = [
    ("首板+换手<15%", lambda r: r['streak']==1 and r['turnover']<15),
    ("2板+换手<10%", lambda r: r['streak']==2 and r['turnover']<10),
    ("组合信号", lambda r: (r['streak']==1 and r['turnover']<15) or (r['streak']==2 and r['turnover']<10)),
]

for sname, sfn in signal_groups:
    sub = [r for r in t2_results if sfn(r)]
    if len(sub) < 5:
        continue
    print(f"\n  {sname} ({len(sub)}只):")
    for period, key in [("T+1", "cum_t1"), ("T+2", "cum_t2"), ("T+3", "cum_t3")]:
        vals = [r for r in sub if r[key] is not None]
        if not vals:
            continue
        wins = [r[key] for r in vals if r[key] > 0]
        losses_v = [r[key] for r in vals if r[key] < 0]
        wr = len(wins)/len(vals)*100
        avg = sum(r[key] for r in vals)/len(vals)
        avg_w = sum(wins)/len(wins) if wins else 0
        avg_l = sum(losses_v)/len(losses_v) if losses_v else 0
        pnl = abs(avg_w/avg_l) if avg_l != 0 else 0
        exp = wr/100*avg_w + (1-wr/100)*avg_l
        print(f"    {period}: 胜率{wr:.1f}% | 均{avg:+.2f}% | 盈亏比{pnl:.2f} | 期望{exp:+.2f}%")

# 保存结果
with open(r'C:\Users\11503\.openclaw-autoclaw\workspace\kuixue_t2_t3_results.json', 'w', encoding='utf-8') as f:
    json.dump(t2_results, f, ensure_ascii=False)

print(f"\nT+2/T+3结果已保存到 kuixue_t2_t3_results.json")
