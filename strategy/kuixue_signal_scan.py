# -*- coding: utf-8 -*-
"""
葵学3.0 实战信号扫描 2026-04-28
"""
import baostock as bs
import json
import time
import sys
sys.stdout.reconfigure(line_buffering=True)

# 加载静态层
with open("kuixue_static_layer.json", "r", encoding="utf-8") as f:
    static = json.load(f)

lg = bs.login()

# ============================================================
# 1. L1 大盘过滤
# ============================================================
rs = bs.query_history_k_data_plus("sh.000300", "date,close",
    start_date="2025-06-01", end_date="2026-04-28", frequency="d")
hs300_rows = []
while rs.error_code == '0' and rs.next():
    hs300_rows.append(rs.get_row_data())

hs300_today = float(hs300_rows[-1][1])
# MA250
ma250_vals = [float(r[1]) for r in hs300_rows[-250:]]
ma250 = sum(ma250_vals) / len(ma250_vals)
l1_pct = round((hs300_today / ma250 - 1) * 100, 2)
l1_pass = hs300_today > ma250
print(f"L1: HS300={hs300_today}, MA250={round(ma250,2)}, {l1_pct}% -> {'PASS' if l1_pass else 'BLOCKED'}")

# ============================================================
# 2. 最近政策事件
# ============================================================
recent_events = [
    {"date": "2026-04-22", "name": "碳达峰碳中和综合评价考核办法", "direction": "新能源/双碳", "p4": 4.15},
    {"date": "2026-04-23", "name": "中办国办节能降碳意见", "direction": "新能源/双碳", "p4": 3.75},
    {"date": "2026-04-07", "name": "国务院令834号（关键信息基础设施）", "direction": "半导体/自主可控", "p4": 3.75},
]

# ============================================================
# 3. E3 时机判断 - 当日HS300涨跌幅
# ============================================================
for evt in recent_events:
    date_str = evt["date"]
    # 找事件日HS300涨跌幅
    for i, r in enumerate(hs300_rows):
        if r[0] == date_str and i > 0:
            prev_close = float(hs300_rows[i-1][1])
            today_close = float(r[1])
            chg = round((today_close / prev_close - 1) * 100, 2)
            evt["e3_chg"] = chg
            evt["e3_pass"] = abs(chg) < 1.0
            break

# ============================================================
# 4. 方向→个股 E2筛选
# ============================================================
def get_direction_stocks(direction_str):
    dirs = [d.strip() for d in direction_str.replace("+", ",").split(",")]
    all_stocks = set()
    dir_map = static["directions"]
    for d in dirs:
        for key in dir_map:
            if d in key or key in d:
                for concept, info in dir_map[key]["concepts"].items():
                    for code in info["stock_codes"]:
                        all_stocks.add(code)
                break
    return list(all_stocks)

def get_fundamentals(code, date_str):
    if code.startswith("6"):
        bs_code = f"sh.{code}"
    else:
        bs_code = f"sz.{code}"
    
    from datetime import datetime
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    year, month = dt.year, dt.month
    if month <= 4: ry, rq = year-1, 3
    elif month <= 7: ry, rq = year, 1
    elif month <= 10: ry, rq = year, 2
    else: ry, rq = year, 3
    
    result = {"roe": None, "profit_growth": None, "debt_ratio": None, "report": f"{ry}Q{rq}"}
    
    rs1 = bs.query_profit_data(code=bs_code, year=ry, quarter=rq)
    rows1 = []
    while rs1.error_code == '0' and rs1.next(): rows1.append(rs1.get_row_data())
    if rows1:
        try: result["roe"] = round(float(rows1[0][3]) * 100, 2)
        except: pass
    
    rs2 = bs.query_growth_data(code=bs_code, year=ry, quarter=rq)
    rows2 = []
    while rs2.error_code == '0' and rs2.next(): rows2.append(rs2.get_row_data())
    if rows2:
        try: result["profit_growth"] = round(float(rows2[0][5]) * 100, 2)
        except: pass
    
    rs3 = bs.query_balance_data(code=bs_code, year=ry, quarter=rq)
    rows3 = []
    while rs3.error_code == '0' and rs3.next(): rows3.append(rs3.get_row_data())
    if rows3:
        try: result["debt_ratio"] = round(float(rows3[0][7]) * 100, 2)
        except: pass
    
    return result

signals = []
for evt in recent_events:
    print(f"\n=== {evt['name']} ===")
    print(f"  P4={evt['p4']}, E3_chg={evt.get('e3_chg')}%")
    
    # 完整过滤
    filters = []
    if not l1_pass: filters.append(f"L1 BLOCKED({l1_pct}%)")
    if evt["p4"] < 3.0: filters.append(f"P4 BLOCKED({evt['p4']})")
    if not evt.get("e3_pass", True): filters.append(f"E3 BLOCKED(chg={evt.get('e3_chg')}%)")
    
    if filters:
        print(f"  FILTER: {', '.join(filters)} -> NO ENTRY")
        # 但还是看个股
    else:
        print(f"  FILTER: ALL PASS -> ENTRY SIGNAL")
    
    # 个股E2筛选
    stocks = get_direction_stocks(evt["direction"])
    print(f"  Direction stocks: {len(stocks)}")
    
    e2_pass = []
    e2_fail = []
    for i, code in enumerate(stocks):
        if i > 0 and i % 3 == 0:
            time.sleep(0.5)
        fund = get_fundamentals(code, evt["date"])
        roe_ok = fund["roe"] is not None and fund["roe"] > 0
        growth_ok = fund["profit_growth"] is not None and fund["profit_growth"] > -30
        debt_ok = fund["debt_ratio"] is not None and fund["debt_ratio"] < 70
        e2_ok = roe_ok and growth_ok and debt_ok
        
        entry = {"code": code, "fund": fund, "e2": e2_ok}
        if e2_ok:
            e2_pass.append(entry)
        else:
            e2_fail.append(entry)
    
    print(f"  E2 pass: {len(e2_pass)}/{len(stocks)}")
    
    # 获取E2通过个股的最近价格
    print(f"  TOP E2 stocks (with latest price):")
    for s in e2_pass[:10]:
        code = s["code"]
        bs_code = f"sh.{code}" if code.startswith("6") else f"sz.{code}"
        rs = bs.query_history_k_data_plus(bs_code, "date,close",
            start_date="2026-04-20", end_date="2026-04-28", frequency="d")
        price_rows = []
        while rs.error_code == '0' and rs.next(): price_rows.append(rs.get_row_data())
        latest = float(price_rows[-1][1]) if price_rows else None
        print(f"    {code}: ROE={s['fund']['roe']}% growth={s['fund']['profit_growth']}% debt={s['fund']['debt_ratio']}% price={latest}")
        time.sleep(0.3)
    
    # E2失败原因
    fail_reasons = {}
    for s in e2_fail:
        f = s["fund"]
        if not (f["roe"] is not None and f["roe"] > 0): fail_reasons["ROE<=0"] = fail_reasons.get("ROE<=0", 0) + 1
        if not (f["profit_growth"] is not None and f["profit_growth"] > -30): fail_reasons["growth<=-30%"] = fail_reasons.get("growth<=-30%", 0) + 1
        if not (f["debt_ratio"] is not None and f["debt_ratio"] < 70): fail_reasons["debt>=70%"] = fail_reasons.get("debt>=70%", 0) + 1
    print(f"  E2 fail reasons: {fail_reasons}")
    
    signals.append({
        "event": evt["name"],
        "date": evt["date"],
        "direction": evt["direction"],
        "p4": evt["p4"],
        "l1": l1_pass,
        "e3": evt.get("e3_pass"),
        "entry": len(filters) == 0,
        "e2_pass_count": len(e2_pass),
        "e2_pass_codes": [s["code"] for s in e2_pass],
        "e2_fail_reasons": fail_reasons
    })

# ============================================================
# 5. 量能检查 - 新能源指数
# ============================================================
rs = bs.query_history_k_data_plus("sh.000076", "date,close,volume",
    start_date="2026-04-14", end_date="2026-04-28", frequency="d")
ne_rows = []
while rs.error_code == '0' and rs.next(): ne_rows.append(rs.get_row_data())
if len(ne_rows) >= 2:
    vol_today = float(ne_rows[-1][2]) if ne_rows[-1][2] else 0
    vol_5d = [float(r[2]) for r in ne_rows[-5:] if r[2]]
    vol_20d = [float(r[2]) for r in ne_rows[-20:] if r[2]]
    avg_5d = sum(vol_5d)/len(vol_5d) if vol_5d else 0
    avg_20d = sum(vol_20d)/len(vol_20d) if vol_20d else 0
    vol_ratio = round(avg_5d / avg_20d, 2) if avg_20d > 0 else 0
    
    chg_5d = round((float(ne_rows[-1][1]) / float(ne_rows[-5][1]) - 1) * 100, 2) if len(ne_rows) >= 5 else None
    chg_20d = round((float(ne_rows[-1][1]) / float(ne_rows[0][1]) - 1) * 100, 2) if ne_rows else None
    
    print(f"\n=== 新能源指数 量能检查 ===")
    print(f"  5日量比: {vol_ratio} ({'放量' if vol_ratio > 1.2 else '缩量' if vol_ratio < 0.8 else '正常'})")
    print(f"  5日涨幅: {chg_5d}%")
    print(f"  20日涨幅: {chg_20d}%")

with open("kuixue_signal_20260428.json", "w", encoding="utf-8") as f:
    json.dump({"date": "2026-04-28", "hs300": hs300_today, "ma250": round(ma250,2), 
               "l1_pass": l1_pass, "signals": signals}, f, ensure_ascii=False, indent=2)

print(f"\nSignal saved to kuixue_signal_20260428.json")
bs.logout()
