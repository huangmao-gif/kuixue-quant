# -*- coding: utf-8 -*-
"""
葵学3.0 — 每日观察数据积累器（v2）
每天收盘后运行，记录涨停股的：
- 高开幅度（开盘价 vs 前日收盘价）
- 回踩幅度（盘中最低 vs 开盘价）
- 尾盘表现（收盘价 vs 开盘价）
- 成交量对比（vs 前日）
- 概念板块

零成本零风险：只记录数据，不执行交易
数据来源：baostock（免费，本地运行）

用法：每天15:30后运行一次
  python kuixue_3.0_observer.py

Windows任务计划：已通过 kuixue_pipeline 自动触发
"""
import baostock as bs
import json, os, sys, io, time
from collections import defaultdict
from datetime import datetime, timedelta
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

WORKSPACE = r'C:\Users\11503\.openclaw-autoclaw\workspace'
OBSERVE_FILE = os.path.join(WORKSPACE, 'kuixue_observation_log.json')
DB_FILE = os.path.join(WORKSPACE, 'kuixue_history.db')

# 获取今天日期
today = datetime.now().strftime('%Y-%m-%d')
yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

# 如果是周末或非交易日，往前推
# 简化：用baostock查最近交易日
print(f"当前日期: {today}")

# 登录
lg = bs.login()
print(f"baostock: {lg.error_msg}")

# 获取沪深A股列表
rs = bs.query_stock_basic()
all_codes = []
while rs.next():
    r = rs.get_row_data()
    code = r[0]
    if r[4] == '1' and (code.startswith('sh.6') or code.startswith('sz.0') or code.startswith('sz.3')):
        all_codes.append(code)
print(f"A股: {len(all_codes)} 只")

# 找到今天的涨停股
print(f"\n扫描涨停股...")

limit_up_stocks = []
t0 = time.time()

for code in all_codes:
    try:
        # 拉最近5天数据（确保能找到前日和今日）
        rs = bs.query_history_k_data_plus(
            code,
            "date,open,high,low,close,pctChg,turn,volume,isST",
            (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
            today,
            frequency="d", adjustflag="3"
        )
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        
        if len(rows) < 2:
            continue
        
        # 最后一个交易日
        last = rows[-1]
        d = last[0]
        try:
            pct = float(last[4])
            is_st = last[8] if len(last) > 8 else ''
        except:
            continue
        
        if is_st == '1' or pct < 9.9:
            continue
        
        # 前一个交易日
        prev = rows[-2]
        
        limit_up_stocks.append({
            'date': d,
            'code': code,
            'name': '',  # baostock不直接返回名称
            'pct': pct,
            'close': float(last[3]),
            'open': float(last[1]),
            'high': float(last[2]),
            'low': float(last[3]) if float(last[3]) == float(last[2]) else float(last[3]),  # 涨停板可能open=high=low=close
            'turnover': float(last[5]) * 100,  # 转为百分比
            'volume': float(last[6]) if last[6] else 0,
            'prev_close': float(prev[3]),
            'prev_turnover': float(prev[5]) * 100 if prev[5] else 0,
            'prev_volume': float(prev[6]) if prev[6] else 0,
        })
    except:
        pass
    
    if len(limit_up_stocks) % 500 == 0 and len(limit_up_stocks) > 0:
        elapsed = time.time() - t0
        print(f"  已扫描: {len(limit_up_stocks)} 只涨停 | {elapsed:.0f}秒")

bs.logout()

print(f"\n今日涨停: {len(limit_up_stocks)} 只")

if not limit_up_stocks:
    print("没有涨停股（可能非交易日或数据未更新）")
    sys.exit(0)

# 计算观察指标
for s in limit_up_stocks:
    # 高开幅度（相对前日收盘）
    if s['prev_close'] > 0:
        s['gap_up_pct'] = (s['open'] - s['prev_close']) / s['prev_close'] * 100
    else:
        s['gap_up_pct'] = 0
    
    # 回踩幅度（盘中最低相对开盘）
    if s['open'] > 0:
        s['pullback_pct'] = (s['low'] - s['open']) / s['open'] * 100
    else:
        s['pullback_pct'] = 0
    
    # 量比（今日成交/昨日成交）
    if s['prev_volume'] > 0:
        s['volume_ratio'] = s['volume'] / s['prev_volume']
    else:
        s['volume_ratio'] = 0

# 统计摘要
import statistics
gap_ups = [s['gap_up_pct'] for s in limit_up_stocks]
pullbacks = [s['pullback_pct'] for s in limit_up_stocks]
vol_ratios = [s['volume_ratio'] for s in limit_up_stocks if s['volume_ratio'] > 0]

print(f"\n--- 观察指标摘要 ---")
print(f"  高开幅度: 均值{statistics.mean(gap_ups):+.2f}% | 中位{statistics.median(gap_ups):+.2f}%")
if pullbacks:
    print(f"  回踩幅度: 均值{statistics.mean(pullbacks):+.2f}% | 中位{statistics.median(pullbacks):+.2f}%")
    max_pull = max(pullbacks, key=abs)
    min_pull = min(pullbacks)
    print(f"  最大回踩: {max_pull:+.2f}% | 最小回踩: {min_pull:+.2f}%")
if vol_ratios:
    print(f"  量比: 均值{statistics.mean(vol_ratios):.2f} | 中位{statistics.median(vol_ratios):.2f}")

# 高开分布
from collections import Counter
gap_dist = Counter()
for g in gap_ups:
    if g >= 9.9: gap_dist['一字板(≥9.9%)'] += 1
    elif g >= 7: gap_dist['高开7-9.9%'] += 1
    elif g >= 5: gap_dist['高开5-7%'] += 1
    elif g >= 3: gap_dist['高开3-5%'] += 1
    elif g >= 0: gap_dist['微开0-3%'] += 1
    else: gap_dist['低开'] += 1

print(f"\n  高开分布:")
for label in ['一字板(≥9.9%)', '高开7-9.9%', '高开5-7%', '高开3-5%', '微开0-3%', '低开']:
    if label in gap_dist:
        print(f"    {label}: {gap_dist[label]}只")

# 保存到观察日志
log_entry = {
    'date': limit_up_stocks[0]['date'],
    'timestamp': datetime.now().isoformat(),
    'summary': {
        'total': len(limit_up_stocks),
        'avg_gap_up': round(statistics.mean(gap_ups), 2),
        'median_gap_up': round(statistics.median(gap_ups), 2),
        'avg_pullback': round(statistics.mean(pullbacks), 2) if pullbacks else 0,
        'median_pullback': round(statistics.median(pullbacks), 2) if pullbacks else 0,
        'avg_volume_ratio': round(statistics.mean(vol_ratios), 2) if vol_ratios else 0,
        'gap_distribution': dict(gap_dist),
    },
    'stocks': limit_up_stocks,
}

# 追加到日志文件
existing_log = []
if os.path.exists(OBSERVE_FILE):
    with open(OBSERVE_FILE, 'r', encoding='utf-8') as f:
        existing_log = json.load(f)

# 检查是否已有当天数据
dates = [e['date'] for e in existing_log]
if log_entry['date'] in dates:
    print(f"\n  {log_entry['date']} 已有记录，更新")
    existing_log = [e for e in existing_log if e['date'] != log_entry['date']]

existing_log.append(log_entry)

with open(OBSERVE_FILE, 'w', encoding='utf-8') as f:
    json.dump(existing_log, f, ensure_ascii=False, indent=2)

print(f"\n✅ 观察数据已保存到 {OBSERVE_FILE}")
print(f"  累计观察天数: {len(existing_log)}")

# 如果积累超过5天，输出统计趋势
if len(existing_log) >= 5:
    print(f"\n--- 多日趋势（最近{len(existing_log)}天）---")
    for entry in existing_log[-7:]:
        s = entry['summary']
        print(f"  {entry['date']}: {s['total']}只涨停 | 均高开{s['avg_gap_up']:+.1f}% | 均回踩{s['avg_pullback']:+.1f}% | 量比{s['avg_volume_ratio']:.1f}")
    
    # 跨天平均
    all_gaps = []
    all_pulls = []
    for entry in existing_log:
        all_gaps.append(entry['summary']['avg_gap_up'])
        all_pulls.append(entry['summary']['avg_pullback'])
    
    print(f"\n  长期均值: 高开{statistics.mean(all_gaps):+.2f}% | 回踩{statistics.mean(all_pulls):+.2f}%")
    print(f"  高开标准差: {statistics.stdev(all_gaps):.2f}%")
    if len(all_pulls) > 1:
        print(f"  回踩标准差: {statistics.stdev(all_pulls):.2f}%")
