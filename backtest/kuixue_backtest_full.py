"""
葵学3.0 v1.2 完整反查
60个政策事件 × L1大盘过滤 + P4评分 + E3时机判断
目标：验证完整系统的过滤效果
"""
import baostock as bs
import json
import time

lg = bs.login()

def p4_pass_candidate(event):
    """快速估算P4分数，用于L1弹性窗口判断"""
    p4 = estimate_p4(event)
    return p4["weighted"]

# ============================================================
# 方向→指数映射
# ============================================================
direction_index_map = {
    "新能源/双碳": "sh.000076",        # 科创新能源
    "新能源": "sh.000076",
    "半导体/自主可控": "sh.000063",     # 电子信息
    "AI/数字经济": "sz.399624",        # 中证人工智能
    "AI": "sz.399624",
    "工业4.0": "sh.000073",            # 科创高端装备
    "工业4.0+新能源": "sh.000073",
    "AI+工业4.0": "sz.399624",
    "AI+消费": "sz.399624",
    "半导体+AI": "sh.000063",
    "半导体+新能源": "sh.000063",
    "AI+新能源": "sz.399624",
    "新能源+工业4.0": "sh.000076",
    "消费/新基建": "sh.000905",        # 用ZZ500代理
    "消费/服务": "sh.000905",
    "对外开放": "sh.000905",
    "全面": None,  # 全面方向不匹配任何特定方向，系统不入场
}

# ============================================================
# P4评分估算（按事件级别和政策属性）
# ============================================================
def estimate_p4(event):
    """
    v2 P4评分算法：加入发文规格信号 + 财政隐含判断
    核心改进：
    1. 发文规格=信号强度（中办国办>国务院>部委）
    2. 举国体制类政策隐含财政配套（大基金/双碳/军工不需要文件写"拨XX亿"）
    3. 两会/规划类隐含时间表和考核
    """
    level = event.get("level", "中")
    direction = event.get("direction", "")
    name = event.get("name", "")

    # === 举国体制评分 ===
    jtg_score = 0
    if any(k in name for k in ["双碳", "碳中和", "大基金", "关键信息基础设施"]):
        jtg_score = 5
    elif any(k in name for k in ["十九届", "十四五", "二十大", "三中全会", "四中全会", "两会"]):
        jtg_score = 4
    elif any(k in name for k in ["中央经济工作会议", "政治局会议"]):
        jtg_score = 3.5  # 政治局/中央经济工作会议=高规格
    elif "国务院" in name or "中办国办" in name:
        jtg_score = 3
    elif "深改委" in name or "财经委" in name:
        jtg_score = 3
    else:
        jtg_score = 2

    # === 财政配套 ===
    # 改进：举国体制级政策隐含财政配套（大基金本身就是钱，双碳有专项债）
    fiscal = 0
    if any(k in name for k in ["大基金", "降准", "降息", "再贷款", "6万亿", "5000亿", "577"]):
        fiscal = 5
    elif any(k in name for k in ["补贴", "减税", "专项债", "化债", "设备更新"]):
        fiscal = 4
    elif any(k in name for k in ["双碳", "碳中和"]):
        # 双碳隐含财政：专项债+补贴+电价改革=财政已配套但文件不写
        fiscal = 4
    elif "中办国办" in name:
        # 中办国办联合发文=规格极高，通常有财政配套跟进
        fiscal = 3
    elif "国务院" in name or "央行" in name:
        fiscal = 3
    elif any(k in name for k in ["政治局", "中央经济工作会议"]):
        # 这些定调会议后续通常有财政配套
        fiscal = 2.5
    elif "中央" in name or "两会" in name:
        fiscal = 2
    else:
        fiscal = 1

    # === 地方考核 ===
    # 改进：考核办法/中办国办/两会=强考核信号
    local = 0
    if any(k in name for k in ["考核", "问责", "KPI", "评价"]):
        local = 5
    elif "中办国办" in name:
        # 中办国办发文=有地方考核要求
        local = 4
    elif "两会" in name or "规划" in name:
        local = 4
    elif "中央经济工作会议" in name or "政治局" in name:
        local = 3
    elif "国务院" in name:
        local = 2
    else:
        local = 1

    # === 时间表 ===
    # 改进：两会/规划/中央经济工作会议=隐含时间表
    timeline = 0
    if any(k in name for k in ["十五五", "十四五", "2030", "2025", "2027"]):
        timeline = 4
    elif any(k in name for k in ["规划", "纲要"]):
        timeline = 4
    elif any(k in name for k in ["两会", "中央经济工作会议"]):
        # 两会=年度目标，经济工作会议=下一年任务=有时间表
        timeline = 3.5
    elif "中办国办" in name:
        # 中办国办文件通常带时间节点
        timeline = 3
    elif "国务院" in name or "政治局" in name:
        timeline = 3
    else:
        timeline = 2

    # === 发文规格加分 ===
    # 新增维度：不作为独立维度，而是作为举国体制的修正项
    # 仅对产业政策方向有效（新能源/半导体/AI/工业4.0），消费/服务/社会管理不加
    spec_bonus = 0
    is_industrial_policy = any(k in direction for k in ["新能源", "双碳", "半导体", "自主可控", "AI", "工业4.0", "数字经济"])
    if is_industrial_policy:
        if "中办国办" in name:
            spec_bonus = 0.5  # 最高规格发文，+0.5
        elif "国务院令" in name:
            spec_bonus = 0.4  # 行政法规，+0.4
        elif "国发" in name:
            spec_bonus = 0.3  # 国务院文件，+0.3

    # 四维加权 + 规格修正
    weighted = fiscal * 0.25 + local * 0.25 + timeline * 0.20 + jtg_score * 0.30 + spec_bonus
    weighted = min(weighted, 5.0)  # 上限5.0

    return {
        "fiscal": fiscal,
        "local": local,
        "timeline": timeline,
        "jtg": jtg_score,
        "spec_bonus": spec_bonus,
        "weighted": round(weighted, 2)
    }

    weighted = fiscal * 0.25 + local * 0.25 + timeline * 0.20 + jtg_score * 0.30 + spec_bonus
    weighted = min(weighted, 5.0)  # 上限5.0

    return {
        "fiscal": fiscal,
        "local": local,
        "timeline": timeline,
        "jtg": jtg_score,
        "spec_bonus": spec_bonus,
        "weighted": round(weighted, 2)
    }

# ============================================================
# 加载事件
# ============================================================
with open("kuixue_policy_events.json", "r", encoding="utf-8") as f:
    events = json.load(f)

# ============================================================
# 获取HS300 MA250数据（一次性拉取）
# ============================================================
print("Loading HS300 data...", flush=True)
hs300_all = {}
rs = bs.query_history_k_data_plus("sh.000300", "date,close", start_date="2020-01-01", end_date="2027-12-31", frequency="d")
while rs.error_code == '0' and rs.next():
    row = rs.get_row_data()
    hs300_all[row[0]] = float(row[1])

hs300_dates = sorted(hs300_all.keys())

def get_hs300_ma250(date_str):
    """获取某日的HS300和MA250"""
    if date_str not in hs300_all:
        # 找最近的交易日
        for d in hs300_dates:
            if d >= date_str:
                date_str = d
                break
        else:
            return None, None

    idx = hs300_dates.index(date_str)
    if idx < 250:
        return hs300_all[date_str], None

    ma250 = sum([hs300_all[d] for d in hs300_dates[idx-250:idx]]) / 250
    return hs300_all[date_str], round(ma250, 2)

def get_hs300_daily_chg(date_str):
    """获取HS300当日涨跌幅"""
    if date_str not in hs300_all:
        return None
    idx = hs300_dates.index(date_str)
    if idx == 0:
        return None
    prev_close = hs300_all[hs300_dates[idx-1]]
    today_close = hs300_all[date_str]
    return round((today_close / prev_close - 1) * 100, 2)

# ============================================================
# 方向指数数据缓存
# ============================================================
index_cache = {}

def get_index_returns(index_code, entry_date, months_list=[1,3,6,12,24]):
    """获取指数入场后各时段收益率"""
    cache_key = f"{index_code}_{entry_date}"
    if cache_key in index_cache:
        return index_cache[cache_key]

    rs = bs.query_history_k_data_plus(index_code, "date,close",
        start_date=entry_date, end_date="2027-12-31", frequency="d")
    rows = []
    while rs.error_code == '0' and rs.next():
        rows.append(rs.get_row_data())

    if not rows:
        index_cache[cache_key] = None
        return None

    entry_price = float(rows[0][1])

    # 带止损
    max_hold = 24 * 22
    peak = entry_price
    stop_loss_result = None
    for i in range(1, min(len(rows), max_hold + 1)):
        price = float(rows[i][1])
        peak = max(peak, price)
        pnl = (price / entry_price - 1) * 100
        if pnl <= -15:
            stop_loss_result = {"pnl": round(pnl, 2), "days": i, "reason": "stop_loss"}
            break

    if stop_loss_result is None and len(rows) > max_hold:
        final_price = float(rows[max_hold][1])
        pnl = (final_price / entry_price - 1) * 100
        stop_loss_result = {"pnl": round(pnl, 2), "days": max_hold, "reason": "hold_2y"}

    # 各时段收益
    period_returns = {}
    for m in months_list:
        idx = m * 22
        if idx < len(rows):
            period_returns[f"{m}m"] = round((float(rows[idx][1]) / entry_price - 1) * 100, 2)
        else:
            period_returns[f"{m}m"] = None

    result = {
        "stop_loss": stop_loss_result,
        "periods": period_returns
    }
    index_cache[cache_key] = result
    return result

# ============================================================
# 运行反查
# ============================================================
results = []
passed_count = 0
blocked_count = 0

for evt in events:
    date = evt["date"]
    direction = evt["direction"]

    # Step 0: 全面方向跳过（系统不入场无方向政策）
    if direction == "全面":
        p4 = estimate_p4(evt)
        results.append({
            "date": date,
            "name": evt["name"],
            "direction": direction,
            "p4": p4["weighted"],
            "filter": "SKIP",
            "reason": "全面方向=无方向，系统不入场",
            "l1": None,
            "e3": None
        })
        blocked_count += 1
        continue

    # Step 2: P4 评分
    p4 = estimate_p4(evt)
    p4_pass = p4["weighted"] >= 3.0

    # Step 1: L1 大盘过滤（注意：P4先算，L1弹性窗口需要P4）
    hs300, ma250 = get_hs300_ma250(date)
    if hs300 is None or ma250 is None:
        l1_pass = None
        l1_detail = "数据不足"
    else:
        l1_pct = round((hs300 / ma250 - 1) * 100, 2)
        l1_pass = hs300 > ma250

        # L1弹性窗口：HS300虽在MA250下方，但从近期底部反弹>=15%时，允许条件性入场
        # 条件：P4必须>=3.0 + 反弹>=15%（双重门槛，防止在熊市半山腰入场）
        if not l1_pass:
            idx = hs300_dates.index(date) if date in hs300_all else -1
            if idx > 0:
                lookback = min(idx, 130)  # 约6个月
                recent_low = min([hs300_all[d] for d in hs300_dates[idx-lookback:idx+1]])
                bounce_pct = (hs300 / recent_low - 1) * 100
                if bounce_pct >= 15 and p4["weighted"] >= 3.0:
                    l1_pass = True  # 弹性放行
                    l1_detail = f"弹性窗口(HS300={hs300}, MA250={ma250}, {l1_pct}%, 从低点反弹{round(bounce_pct,1)}%, P4={p4['weighted']})"

        if l1_detail == "数据不足" or not (hs300 is not None and ma250 is not None and l1_detail.startswith("弹性")):
            if hs300 is not None and ma250 is not None:
                l1_detail = f"HS300={hs300}, MA250={ma250}, {l1_pct}%"

    # Step 3: E3 时机判断
    hs300_chg = get_hs300_daily_chg(date)
    if hs300_chg is not None:
        e3_pass = hs300_chg < 1.0
    else:
        e3_pass = None

    # 综合判断
    if l1_pass == False:
        final_filter = "BLOCKED_L1"
        reason = f"L1熊市({l1_detail})"
        blocked_count += 1
    elif not p4_pass:
        final_filter = "BLOCKED_P4"
        reason = f"P4={p4['weighted']}<3.0"
        blocked_count += 1
    elif e3_pass == False:
        final_filter = "BLOCKED_E3"
        reason = f"HS300当日+{hs300_chg}%>=1%"
        blocked_count += 1
    elif l1_pass is None or e3_pass is None:
        final_filter = "UNKNOWN"
        reason = "数据缺失"
        blocked_count += 1
    else:
        final_filter = "PASS"
        reason = f"L1✓ P4={p4['weighted']}✓ E3={hs300_chg}%✓"
        passed_count += 1

    # 获取方向指数收益（PASS的事件才需要）
    index_code = direction_index_map.get(direction)
    index_result = None
    bench_result = None

    if index_code and final_filter == "PASS":
        index_result = get_index_returns(index_code, date)
        bench_result = get_index_returns("sh.000905", date)

    # 也为BLOCKED事件获取收益（用于对比）
    if index_code and final_filter != "PASS" and final_filter != "SKIP":
        index_result = get_index_returns(index_code, date)
        bench_result = get_index_returns("sh.000905", date)

    results.append({
        "date": date,
        "name": evt["name"],
        "direction": direction,
        "level": evt["level"],
        "p4": p4["weighted"],
        "p4_detail": p4,
        "l1_pass": l1_pass,
        "l1_detail": l1_detail,
        "e3_chg": hs300_chg,
        "e3_pass": e3_pass,
        "filter": final_filter,
        "reason": reason,
        "index_returns": index_result,
        "bench_returns": bench_result
    })

    print(f"  {date} {evt['name'][:20]}... {final_filter}", flush=True)

# ============================================================
# 统计汇总
# ============================================================
summary = {
    "total_events": len(events),
    "passed": passed_count,
    "blocked": blocked_count,
    "pass_rate": round(passed_count / len(events) * 100, 1),

    "pass_returns": [],
    "blocked_returns": [],

    "l1_blocked_count": 0,
    "p4_blocked_count": 0,
    "e3_blocked_count": 0,
}

for r in results:
    if r["filter"] == "BLOCKED_L1":
        summary["l1_blocked_count"] += 1
    elif r["filter"] == "BLOCKED_P4":
        summary["p4_blocked_count"] += 1
    elif r["filter"] == "BLOCKED_E3":
        summary["e3_blocked_count"] += 1

    if r.get("index_returns") and r["index_returns"].get("stop_loss"):
        pnl = r["index_returns"]["stop_loss"]["pnl"]
        reason = r["index_returns"]["stop_loss"]["reason"]
        bench_pnl = None
        br = r.get("bench_returns")
        if br and isinstance(br, dict) and br.get("stop_loss"):
            bench_pnl = br["stop_loss"].get("pnl")
        excess = round(pnl - bench_pnl, 2) if bench_pnl is not None else None

        entry = {
            "date": r["date"],
            "name": r["name"],
            "direction": r["direction"],
            "pnl": pnl,
            "bench_pnl": bench_pnl,
            "excess": excess,
            "exit": reason,
            "filter": r["filter"]
        }

        if r["filter"] == "PASS":
            summary["pass_returns"].append(entry)
        elif r["filter"] not in ["SKIP", "UNKNOWN"]:
            summary["blocked_returns"].append(entry)

# PASS事件统计
if summary["pass_returns"]:
    pass_pnls = [e["pnl"] for e in summary["pass_returns"]]
    pass_excess = [e["excess"] for e in summary["pass_returns"] if e["excess"] is not None]
    summary["pass_avg_pnl"] = round(sum(pass_pnls) / len(pass_pnls), 2)
    summary["pass_median_pnl"] = sorted(pass_pnls)[len(pass_pnls)//2]
    summary["pass_win_rate"] = round(sum(1 for p in pass_pnls if p > 0) / len(pass_pnls) * 100, 1)
    if pass_excess:
        summary["pass_avg_excess"] = round(sum(pass_excess) / len(pass_excess), 2)

# BLOCKED事件统计
if summary["blocked_returns"]:
    block_pnls = [e["pnl"] for e in summary["blocked_returns"]]
    block_excess = [e["excess"] for e in summary["blocked_returns"] if e["excess"] is not None]
    summary["blocked_avg_pnl"] = round(sum(block_pnls) / len(block_pnls), 2)
    summary["blocked_median_pnl"] = sorted(block_pnls)[len(block_pnls)//2]
    summary["blocked_win_rate"] = round(sum(1 for p in block_pnls if p > 0) / len(block_pnls) * 100, 1)
    if block_excess:
        summary["blocked_avg_excess"] = round(sum(block_excess) / len(block_excess), 2)

with open("kuixue_backtest_full_results.json", "w", encoding="utf-8") as f:
    json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)

print(f"\nDONE! Pass={passed_count}, Blocked={blocked_count}")
print(f"L1 blocked={summary['l1_blocked_count']}, P4 blocked={summary['p4_blocked_count']}, E3 blocked={summary['e3_blocked_count']}")
bs.logout()
