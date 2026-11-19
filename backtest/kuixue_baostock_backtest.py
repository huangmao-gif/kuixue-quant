# -*- coding: utf-8 -*-
"""
葵学2.0 baostock 大规模回测
拉取全市场最近60个交易日K线，找涨停，验证次日表现
"""
import baostock as bs
import pandas as pd
import json, sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

lg = bs.login()
print(f"baostock 登录: {lg.error_code}")

# ===== 1. 股票列表 =====
print("[1/3] 获取股票列表...")
rs = bs.query_stock_basic()
all_rows = []
while rs.next():
    all_rows.append(rs.get_row_data())

# code[0], ipoDate[1], outDate[2], type[3], status[4]
# 筛选：沪深A股（code以sh.6或sz.0或sz.3开头），status=1上市
codes = [r[0] for r in all_rows if r[4] == '1' and (
    r[0].startswith('sh.6') or r[0].startswith('sz.0') or r[0].startswith('sz.3')
)]
print(f"  A股上市: {len(codes)} 只")

# ===== 2. 拉K线 =====
print("\n[2/3] 拉取日K线（最近60个交易日）...")
limit_up_events = []
total_codes = len(codes)
failed = 0

for i, code in enumerate(codes):
    try:
        rs = bs.query_history_k_data_plus(
            code,
            "date,code,open,high,low,close,pctChg,turn,volume,amount",
            start_date='2026-02-01', end_date='2026-04-21',
            frequency="d", adjustflag="3"
        )
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        
        if len(rows) < 5:
            continue
        
        df = pd.DataFrame(rows, columns=['date','code','open','high','low','close','pctChg','turn','volume','amount'])
        for col in ['pctChg','turn','close','open','volume','amount']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 找涨停日 → 验证次日
        for idx in range(len(df) - 1):
            pct = df.iloc[idx]['pctChg']
            turn = df.iloc[idx]['turn']
            close = df.iloc[idx]['close']
            
            if pd.isna(pct):
                continue
            
            # 涨停判断：主板/中小板≥9.9%，科创板≥19.9%
            code_num = code.split('.')[1][:1]
            if code_num == '6' and code.startswith('sh.688'):
                limit_threshold = 19.9  # 科创板
            else:
                limit_threshold = 9.9
            
            if pct >= limit_threshold:
                next_pct = df.iloc[idx + 1]['pctChg']
                if pd.isna(next_pct):
                    continue
                
                actual = "涨" if next_pct > 0 else ("跌" if next_pct < 0 else "平")
                
                # 前一日是否也涨停（连板判断）
                prev_pct = df.iloc[idx - 1]['pctChg'] if idx > 0 else 0
                is_consecutive = pd.notna(prev_pct) and prev_pct >= limit_threshold
                
                limit_up_events.append({
                    "code": code,
                    "date": df.iloc[idx]['date'],
                    "pct_t": round(float(pct), 2),
                    "turnover_t": round(float(turn), 1) if pd.notna(turn) else 0,
                    "close": round(float(close), 2) if pd.notna(close) else 0,
                    "is_consecutive": is_consecutive,
                    "next_pct": round(float(next_pct), 2),
                    "actual": actual
                })
    except Exception as e:
        failed += 1
    
    if (i + 1) % 500 == 0:
        print(f"  进度: {i+1}/{total_codes} ({(i+1)/total_codes*100:.0f}%) | 涨停事件: {len(limit_up_events)} | 失败: {failed}")
    time.sleep(0.05)

print(f"\n  完成! {total_codes}只 → 涨停事件: {len(limit_up_events)} | 失败: {failed}")

# ===== 3. 统计 =====
total = len(limit_up_events)
if total == 0:
    print("没有涨停事件！")
    bs.logout()
    sys.exit(1)

up = sum(1 for r in limit_up_events if r['actual'] == "涨")
down = sum(1 for r in limit_up_events if r['actual'] == "跌")
avg = sum(r['next_pct'] for r in limit_up_events) / total

print("\n" + "=" * 70)
print(f"📊 葵学2.0 大规模回测 ({total} 个涨停事件)")
print("=" * 70)

print(f"\n涨停次日总览: 涨{up}({up/total*100:.1f}%) 跌{down}({down/total*100:.1f}%) 均{avg:+.2f}%")

# 换手率分层
print(f"\n--- 换手率分层 ---")
for lo, hi, label in [(0,5,"0-5%"), (5,10,"5-10%"), (10,15,"10-15%"), (15,20,"15-20%"), (20,30,"20-30%"), (30,40,"30-40%"), (40,200,">40%")]:
    cases = [r for r in limit_up_events if lo <= r['turnover_t'] < hi]
    if cases:
        c_up = sum(1 for r in cases if r['actual'] == "涨")
        c_down = sum(1 for r in cases if r['actual'] == "跌")
        c_avg = sum(r['next_pct'] for r in cases) / len(cases)
        print(f"  {label}: {len(cases)}个 → 涨{c_up}({c_up/len(cases)*100:.0f}%) 跌{c_down}({c_down/len(cases)*100:.0f}%) 均{c_avg:+.2f}%")

# 首板 vs 连板
first_board = [r for r in limit_up_events if not r['is_consecutive']]
second_board = [r for r in limit_up_events if r['is_consecutive']]
print(f"\n--- 首板 vs 连板 ---")
if first_board:
    fb_down = sum(1 for r in first_board if r['actual'] == "跌")
    fb_avg = sum(r['next_pct'] for r in first_board) / len(first_board)
    print(f"  首板: {len(first_board)}个 → 跌{fb_down}({fb_down/len(first_board)*100:.0f}%) 均{fb_avg:+.2f}%")
if second_board:
    sb_down = sum(1 for r in second_board if r['actual'] == "跌")
    sb_avg = sum(r['next_pct'] for r in second_board) / len(second_board)
    print(f"  连板: {len(second_board)}个 → 跌{sb_down}({sb_down/len(second_board)*100:.0f}%) 均{sb_avg:+.2f}%")

# v2.4规则回测
print(f"\n--- v2.4 规则回测 ---")
kuixue_correct = 0
kuixue_missed = 0
for r in limit_up_events:
    t = r['turnover_t']
    if t > 40:
        kuixue_correct += 1  # 不参与
    elif t > 20:
        kuixue_correct += 1 if r['actual'] == "跌" else 0
        if r['actual'] == "涨":
            pass  # 翻车
    elif t > 10:
        kuixue_correct += 1  # 观望/观察不亏
        if r['actual'] == "涨":
            kuixue_missed += 1
    else:
        kuixue_correct += 1  # 观望不亏
        if r['actual'] == "涨":
            kuixue_missed += 1

print(f"  防守成功率: {kuixue_correct}/{total} = {kuixue_correct/total*100:.1f}%")
print(f"  错过上涨: {kuixue_missed}只 ({kuixue_missed/total*100:.1f}%)")

# 高换手回避命中率
avoid_cases = [r for r in limit_up_events if r['turnover_t'] > 20]
if avoid_cases:
    avoid_hits = sum(1 for r in avoid_cases if r['actual'] == "跌")
    avoid_avg = sum(r['next_pct'] for r in avoid_cases) / len(avoid_cases)
    print(f"  高换手(>20%)回避命中率: {avoid_hits}/{len(avoid_cases)} = {avoid_hits/len(avoid_cases)*100:.1f}% (均{avoid_avg:+.2f}%)")

# 按月统计（看是否稳定）
print(f"\n--- 按月统计 ---")
months = sorted(set(r['date'][:7] for r in limit_up_events))
for m in months:
    mc = [r for r in limit_up_events if r['date'][:7] == m]
    m_up = sum(1 for r in mc if r['actual'] == "涨")
    m_avg = sum(r['next_pct'] for r in mc) / len(mc)
    print(f"  {m}: {len(mc)}个涨停 → 涨{m_up}({m_up/len(mc)*100:.0f}%) 均{m_avg:+.2f}%")

bs.logout()

# 保存
outpath = r"C:\Users\11503\.openclaw-autoclaw\workspace\kuixue_baostock_backtest.json"
with open(outpath, "w", encoding="utf-8") as f:
    json.dump({
        "source": "baostock",
        "total_events": total,
        "next_day_up_rate": round(up/total*100, 1),
        "next_day_avg": round(avg, 2),
        "kuixue_defense_rate": round(kuixue_correct/total*100, 1),
        "avoid_hit_rate": round(avoid_hits/len(avoid_cases)*100, 1) if avoid_cases else 0,
        "events": limit_up_events[:500]  # 限制大小
    }, f, ensure_ascii=False, indent=2)
print(f"\n结果已保存: {outpath}")
