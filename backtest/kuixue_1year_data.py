# -*- coding: utf-8 -*-
"""
1年期数据拉取 v3 — 优化版
策略：baostock的query_history_k_data_plus拉1年K线太慢
优化：用rs_dates参数只拉涨停日附近的数据，不拉全年K线
方案：先用baostock的日期范围查询快速找到涨停日，再拉次日数据
"""
import baostock as bs
import json, os, sys, io, time
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

WORKSPACE = r'C:\Users\11503\.openclaw-autoclaw\workspace'
OUTPUT_FILE = os.path.join(WORKSPACE, 'kuixue_1year_result.json')
PROGRESS_FILE = os.path.join(WORKSPACE, 'kuixue_1year_progress.json')

START_DATE = '2025-04-22'
END_DATE = '2026-04-22'

print(f"葵学2.0 1年期 — {START_DATE} ~ {END_DATE}")

lg = bs.login()
print(f"baostock: {lg.error_msg}")

# 加载进度
limit_up_events = []
done_idx = 0
if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
        prog = json.load(f)
        limit_up_events = prog.get('events', [])
        done_idx = prog.get('done_idx', 0)
    print(f"断点续传: {len(limit_up_events)} 事件, 从第 {done_idx} 只继续")

# 获取股票列表
rs = bs.query_stock_basic()
all_codes = []
while rs.next():
    r = rs.get_row_data()
    code = r[0]
    if r[4] == '1' and (code.startswith('sh.6') or code.startswith('sz.0') or code.startswith('sz.3')):
        all_codes.append(code)

print(f"A股: {len(all_codes)} 只, 从第 {done_idx+1} 只开始")

# 核心优化：对每只股票，一次query拉1年K线，在内存中筛选涨停
# 但0.005s间隔应该够，问题可能是之前0.01s不够
# 试试更短的间隔 + 每200只保存
print(f"\n开始扫描...")

t0 = time.time()

for i in range(done_idx, len(all_codes)):
    code = all_codes[i]
    try:
        rs = bs.query_history_k_data_plus(
            code, "date,pctChg,turn,isST",
            START_DATE, END_DATE,
            frequency="d", adjustflag="3"
        )
        
        streak = 0
        prev_date = None
        
        while rs.next():
            r = rs.get_row_data()
            d = r[0]
            try:
                pct = float(r[2])
                turn = float(r[3]) if r[3] else 0
                is_st = r[4] if len(r) > 4 else ''
            except:
                streak = 0; continue
            
            if is_st == '1':
                streak = 0; continue
            
            if pct >= 9.9:
                if prev_date:
                    diff = int(d.replace('-','')) - int(prev_date.replace('-',''))
                    streak = streak + 1 if diff <= 3 else 1
                else:
                    streak = 1
                
                limit_up_events.append({
                    'date': d, 'code': code,
                    'pct': pct, 'turnover': turn, 'streak': streak,
                })
                prev_date = d
            else:
                streak = 0; prev_date = d
    except:
        pass
    
    # 每200只保存+输出
    if (i+1) % 200 == 0:
        elapsed = time.time() - t0
        speed = 200 / elapsed if elapsed > 0 else 0
        remaining = (len(all_codes) - i - 1) / speed if speed > 0 else 0
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'events': limit_up_events, 'done_idx': i+1}, f, ensure_ascii=False)
        print(f"  {i+1}/{len(all_codes)} | 涨停{len(limit_up_events)} | {speed:.0f}只/秒 | 剩余{remaining/60:.0f}分钟")
        t0 = time.time()

# 最终保存
with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
    json.dump({'events': limit_up_events, 'done_idx': len(all_codes)}, f, ensure_ascii=False)

print(f"\n✅ 涨停扫描完成: {len(limit_up_events)} 事件")

# 拉次日数据
print(f"\n拉取次日涨跌幅...")
code_events = defaultdict(list)
for e in limit_up_events:
    code_events[e['code']].append(e)

codes_list = list(code_events.keys())
print(f"  需拉取 {len(codes_list)} 只股票的次日数据")

done_next = 0
for i, code in enumerate(codes_list):
    try:
        rs = bs.query_history_k_data_plus(
            code, "date,pctChg",
            START_DATE, END_DATE,
            frequency="d", adjustflag="3"
        )
        rows = []
        while rs.next(): rows.append(rs.get_row_data())
        
        for e in code_events[code]:
            d = e['date']
            for r in rows:
                if r[0] > d:
                    try:
                        e['next_pct'] = float(r[1])
                        e['actual'] = '涨' if float(r[1]) > 0 else '跌'
                    except:
                        e['next_pct'] = None
                    break
    except:
        pass
    
    if (i+1) % 200 == 0:
        print(f"  {i+1}/{len(codes_list)}")
    time.sleep(0.003)

bs.logout()

# 统计
valid = [e for e in limit_up_events if e.get('next_pct') is not None]
up = sum(1 for e in valid if e['actual']=='涨')
wr = up/len(valid)*100 if valid else 0
avg = sum(e['next_pct'] for e in valid)/len(valid) if valid else 0

print(f"\n1年期统计:")
print(f"  涨停事件: {len(limit_up_events)}")
print(f"  有次日数据: {len(valid)}")
print(f"  胜率: {wr:.1f}% | 均涨: {avg:+.2f}%")

# 按月统计
by_month = defaultdict(list)
for e in valid:
    m = e['date'][:7]
    by_month[m].append(e)

print(f"\n按月分布:")
for m in sorted(by_month.keys()):
    sub = by_month[m]
    m_up = sum(1 for e in sub if e['actual']=='涨')
    m_wr = m_up/len(sub)*100
    m_avg = sum(e['next_pct'] for e in sub)/len(sub)
    print(f"  {m}: {len(sub)}只 | 胜率{m_wr:.1f}% | 均{m_avg:+.2f}%")

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump({
        'start': START_DATE, 'end': END_DATE,
        'total_events': len(limit_up_events),
        'valid_events': len(valid),
        'events': limit_up_events,
    }, f, ensure_ascii=False)

if os.path.exists(PROGRESS_FILE):
    os.remove(PROGRESS_FILE)

print(f"\n✅ 已保存到 {OUTPUT_FILE}")
