# -*- coding: utf-8 -*-
"""葵学2.0 数据管道 — efinance 稳定版 v4
- 自动重试 + 限频冷却
- push2 fallback: efinance 失败时走腾讯 qt.gtimg.cn
- JSON + SQLite 双输出
- Windows 通知（成功/失败）
"""
import json
import os
import sqlite3
import sys
import time
import traceback
from datetime import datetime, date

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import pandas as pd
import requests
import efinance as ef

# === 配置 ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(BASE_DIR, "kuixue_output.json")
OUT_DB = os.path.join(BASE_DIR, "kuixue_history.db")
MAX_RETRIES = 3
COOLDOWN = 10


def notify(title, message):
    """Windows Toast 通知"""
    try:
        if sys.platform == "win32":
            from ctypes import windll
            # 简单的 Windows 通知（通过 powershell）
            import subprocess
            ps_cmd = (
                f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, '
                f'ContentType = WindowsRuntime] > $null; '
                f'$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(0); '
                f'$text = $template.GetElementsByTagName("text"); '
                f'$text.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null; '
                f'$text.Item(1).AppendChild($template.CreateTextNode("{message}")) > $null; '
                f'$toast = [Windows.UI.Notifications.ToastNotification]::new($template); '
                f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("葵学数据管道").Show($toast);'
            )
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, timeout=10)
    except Exception:
        pass  # 通知失败不影响主流程


def safe_get(func, name, *args, **kwargs):
    for attempt in range(MAX_RETRIES):
        try:
            result = func(*args, **kwargs)
            if result is not None and hasattr(result, "empty") and not result.empty:
                print(f"  [{name}] OK: {result.shape[0]} rows", file=sys.stderr)
                return result
            elif result is not None:
                return result
        except Exception as e:
            err = str(e)
            print(f"  [{name}] attempt {attempt+1} failed: {err[:100]}", file=sys.stderr)
            if attempt < MAX_RETRIES - 1:
                wait = COOLDOWN * (attempt + 1)
                print(f"  [{name}] waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
    return None


def find_col(df, keywords):
    for c in df.columns:
        for kw in keywords:
            if kw in str(c):
                return c
    return None


def get_spot_via_sina():
    """Fallback: 用新浪财经接口获取全量A股行情（push2 挂了时使用）。
    新浪接口 HTTP 稳定，分页拿全量，每页80条，约70页=5500+只，10秒搞定。
    """
    all_stocks = []
    page = 1
    while True:
        try:
            url = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
            params = {
                "page": page,
                "num": 80,
                "sort": "symbol",
                "asc": 1,
                "node": "hs_a",
                "symbol": "",
                "_s_r_a": "page",
            }
            r = requests.get(url, params=params, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            data = r.json()
            if not data:
                break
            all_stocks.extend(data)
            if page % 20 == 0:
                print(f"  [新浪fallback] page {page}, got {len(all_stocks)} so far", file=sys.stderr)
            page += 1
            time.sleep(0.15)  # 限频（新浪限频较严）
        except Exception as e:
            print(f"  [新浪fallback] page {page} failed: {e}", file=sys.stderr)
            break

    if not all_stocks:
        return None

    # 新浪字段映射 → 葵学标准字段
    records = []
    for s in all_stocks:
        try:
            price = float(s.get("trade", 0))
            if price == 0:
                continue  # 停牌跳过
            records.append({
                "股票代码": s.get("code", ""),
                "股票名称": s.get("name", ""),
                "最新价": price,
                "涨跌幅": float(s.get("changepercent", 0)),
                "换手率": float(s.get("turnoverratio", 0)),
                "成交量": float(s.get("volume", 0)),
                "成交额": float(s.get("amount", 0)),
                "最高": float(s.get("high", 0)),
                "最低": float(s.get("low", 0)),
                "总市值": float(s.get("mktcap", 0)),  # 万元
                "市盈率": float(s.get("per", 0)) if s.get("per") else 0,
                "市净率": float(s.get("pb", 0)) if s.get("pb") else 0,
                "流通市值": float(s.get("nmc", 0)) if s.get("nmc") else 0,
            })
        except (ValueError, TypeError):
            continue

    df = pd.DataFrame(records)
    print(f"  [新浪fallback] OK: {len(df)} rows (via sina, {page-1} pages)", file=sys.stderr)
    return df


def get_board_via_sina(code):
    """获取单只股票的板块归属 — 用东方财富股票详情HTTP接口"""
    try:
        # 判断市场代码
        if code.startswith("68") or code.startswith("6"):
            secid = f"1.{code}"
        else:
            secid = f"0.{code}"
        url = f"http://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f12,f14,f100"
        r = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
        d = r.json()
        if d.get("data") and d["data"].get("f100"):
            return [{"板块": d["data"]["f100"], "代码": code}]
    except:
        pass
    # push2 也挂了就标记未知
    return [{"板块": "未知", "代码": code}]


def get_performance_via_http():
    """用东方财富 datacenter-web HTTP 获取业绩数据（替代 HTTPS efinance）"""
    try:
        url = "http://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPT_DMSK_FN_STAP",
            "columns": "SECURITY_CODE,SECURITY_NAME_ABBR,REPORT_DATE,BASIC_EPS,WEIGHTAVG_ROE,MGJYXJJE",
            "pageSize": "5000",
            "pageNumber": 1,
            "sortColumns": "REPORT_DATE",
            "sortTypes": -1,
            "source": "WEB",
            "client": "WEB",
        }
        r = requests.get(url, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            data = d["result"]["data"]
            records = []
            for item in data:
                try:
                    records.append({
                        "股票代码": item.get("SECURITY_CODE", ""),
                        "股票名称": item.get("SECURITY_NAME_ABBR", ""),
                        "报告期": item.get("REPORT_DATE", ""),
                        "每股收益": item.get("BASIC_EPS", 0),
                        "ROE": item.get("WEIGHTAVG_ROE", 0),
                        "经营现金流": item.get("MGJYXJJE", 0),
                    })
                except (ValueError, TypeError):
                    continue
            if records:
                df = pd.DataFrame(records)
                print(f"  [业绩HTTP fallback] OK: {len(df)} rows", file=sys.stderr)
                return df
    except Exception as e:
        print(f"  [业绩HTTP fallback] failed: {e}", file=sys.stderr)
    return None


def init_db():
    """初始化 SQLite 数据库"""
    conn = sqlite3.connect(OUT_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS daily_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            data_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(date)
        );
        CREATE TABLE IF NOT EXISTS stock_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            price REAL,
            pct_chg REAL,
            turnover_rate REAL,
            volume REAL,
            amount REAL,
            market_cap REAL,
            circ_cap REAL,
            extra_json TEXT DEFAULT '{}',
            UNIQUE(date, code)
        );
        CREATE TABLE IF NOT EXISTS billboard (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            reason TEXT,
            pct_chg REAL,
            buy_amount REAL,
            sell_amount REAL,
            net_amount REAL,
            UNIQUE(date, code)
        );
        CREATE TABLE IF NOT EXISTS run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            finished_at TEXT,
            status TEXT,
            ok_sections INTEGER,
            total_sections INTEGER,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_stock_daily_date ON stock_daily(date);
        CREATE INDEX IF NOT EXISTS idx_stock_daily_pct ON stock_daily(pct_chg);
        CREATE INDEX IF NOT EXISTS idx_stock_daily_turnover ON stock_daily(turnover_rate);
        CREATE INDEX IF NOT EXISTS idx_billboard_date ON billboard(date);
    """)
    conn.commit()
    return conn


def save_to_db(conn, out, df_spot):
    """保存数据到 SQLite"""
    today = date.today().isoformat()
    
    # 1. 每日快照（完整JSON）
    conn.execute(
        "INSERT OR REPLACE INTO daily_snapshot (date, data_json) VALUES (?, ?)",
        (today, json.dumps(out, ensure_ascii=False, default=str))
    )
    
    # 2. 个股日线数据
    if df_spot is not None:
        code_col = find_col(df_spot, ["股票代码"])
        name_col = find_col(df_spot, ["股票名称"])
        pct_col = find_col(df_spot, ["涨跌幅"])
        price_col = find_col(df_spot, ["最新价"])
        turnover_col = find_col(df_spot, ["换手"])
        vol_col = find_col(df_spot, ["成交量"])
        amt_col = find_col(df_spot, ["成交额"])
        cap_col = find_col(df_spot, ["总市值"])
        circ_col = find_col(df_spot, ["流通市值"])
        
        for _, row in df_spot.iterrows():
            code = str(row.get(code_col, "")) if code_col else ""
            if not code:
                continue
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO stock_daily 
                       (date, code, name, price, pct_chg, turnover_rate, volume, amount, market_cap, circ_cap)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        today, code,
                        str(row.get(name_col, "")) if name_col else "",
                        float(row.get(price_col, 0)) if price_col else 0,
                        float(row.get(pct_col, 0)) if pct_col else 0,
                        float(row.get(turnover_col, 0)) if turnover_col else 0,
                        float(row.get(vol_col, 0)) if vol_col else 0,
                        float(row.get(amt_col, 0)) if amt_col else 0,
                        float(row.get(cap_col, 0)) if cap_col else 0,
                        float(row.get(circ_col, 0)) if circ_col else 0,
                    )
                )
            except (ValueError, TypeError):
                pass
    
    # 3. 龙虎榜
    if "billboard" in out["signals"] and out["signals"]["billboard"].get("ok"):
        sample = out["signals"]["billboard"].get("sample", [])
        for item in sample:
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO billboard 
                       (date, code, name, reason, pct_chg, buy_amount, sell_amount, net_amount)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        today,
                        str(item.get("股票代码", "")),
                        str(item.get("股票名称", "")),
                        str(item.get("上榜原因", "")),
                        float(item.get("涨跌幅", 0) or 0),
                        float(item.get("买入金额", 0) or 0),
                        float(item.get("卖出金额", 0) or 0),
                        float(item.get("净买入额", 0) or 0),
                    )
                )
            except (ValueError, TypeError):
                pass
    
    conn.commit()


def main():
    started_at = datetime.now().isoformat()
    print(f"=== 葵学数据管道 {started_at} ===", file=sys.stderr)
    
    conn = init_db()
    out = {"timestamp": started_at, "source": "efinance", "signals": {}}
    df_spot = None

    # === 1. A股实时行情 ===
    print("[1/5] A股实时行情...", file=sys.stderr)
    # push2 HTTPS 当前不通，直接跳过尝试新浪，节省30秒等待
    df = None
    try:
        df = ef.stock.get_realtime_quotes()
        if df is not None and df.empty:
            df = None
    except:
        pass
    if df is None:
        print("  [行情] efinance不可用，尝试新浪 fallback...", file=sys.stderr)
        df = get_spot_via_sina()
    if df is not None:
        df_spot = df
        out["signals"]["spot"] = {"ok": True, "count": len(df), "columns": df.columns.tolist(),
                                   "source": "sina" if "涨跌幅" in df.columns else "efinance"}

        pct_col = find_col(df, ["涨跌幅"])
        if pct_col:
            df[pct_col] = pd.to_numeric(df[pct_col], errors="coerce")
            out["signals"]["spot"]["stats"] = {
                "limit_up": int((df[pct_col] >= 9.9).sum()),
                "limit_down": int((df[pct_col] <= -9.9).sum()),
                "avg": round(float(df[pct_col].mean()), 2),
                "median": round(float(df[pct_col].median()), 2),
                "p90": round(float(df[pct_col].quantile(0.9)), 2),
                "p10": round(float(df[pct_col].quantile(0.1)), 2),
            }
            out["signals"]["spot"]["top10_up"] = df.nlargest(10, pct_col).fillna("").to_dict("records")
            out["signals"]["spot"]["top10_down"] = df.nsmallest(10, pct_col).fillna("").to_dict("records")

        turnover_col = find_col(df, ["换手"])
        if turnover_col:
            df[turnover_col] = pd.to_numeric(df[turnover_col], errors="coerce")
            out["signals"]["turnover"] = {
                "ok": True, "col": turnover_col,
                "top20": df.nlargest(20, turnover_col).fillna("").to_dict("records"),
                "percentiles": {
                    "p50": round(float(df[turnover_col].quantile(0.5)), 3),
                    "p75": round(float(df[turnover_col].quantile(0.75)), 3),
                    "p90": round(float(df[turnover_col].quantile(0.9)), 3),
                },
            }
    else:
        out["signals"]["spot"] = {"ok": False}

    # === 2. 板块归属 ===
    print("[2/5] 板块归属...", file=sys.stderr)
    if df_spot is not None:
        code_col = find_col(df_spot, ["股票代码"])
        pct_col = find_col(df_spot, ["涨跌幅"])
        if code_col and pct_col:
            top_stocks = df_spot.nlargest(10, pct_col)[code_col].tolist()
            bottom_stocks = df_spot.nsmallest(10, pct_col)[code_col].tolist()
            interesting = list(dict.fromkeys(top_stocks + bottom_stocks))[:20]
            board_data = {}
            # 用新浪行业接口代替 efinance (push2已挂)
            for code in interesting:
                try:
                    boards = get_board_via_sina(code)
                    if boards:
                        board_data[code] = boards
                    time.sleep(0.15)
                except:
                    pass
            out["signals"]["boards"] = {"ok": True, "stocks_checked": len(interesting), "data": board_data}
    else:
        out["signals"]["boards"] = {"ok": False}

    # === 3. 龙虎榜 ===
    print("[3/5] 龙虎榜...", file=sys.stderr)
    df_bill = safe_get(ef.stock.get_daily_billboard, "龙虎榜")
    if df_bill is not None:
        out["signals"]["billboard"] = {
            "ok": True, "count": len(df_bill),
            "sample": df_bill.head(15).fillna("").to_dict("records"),
        }
    else:
        out["signals"]["billboard"] = {"ok": False}

    # === 4. 业绩（从新浪行情数据中提取市盈率/市净率统计）===
    print("[4/5] 业绩数据...", file=sys.stderr)
    if df_spot is not None:
        per_col = find_col(df_spot, ["市盈率"])
        pb_col = find_col(df_spot, ["市净率"])
        perf_stats = {"ok": True, "source": "sina"}
        if per_col:
            per_valid = pd.to_numeric(df_spot[per_col], errors="coerce")
            per_valid = per_valid[per_valid > 0]  # 排除亏损股和0
            perf_stats["per_median"] = round(float(per_valid.median()), 2) if len(per_valid) > 0 else 0
            perf_stats["per_p25"] = round(float(per_valid.quantile(0.25)), 2) if len(per_valid) > 0 else 0
            perf_stats["per_p75"] = round(float(per_valid.quantile(0.75)), 2) if len(per_valid) > 0 else 0
            # 低PE Top10
            perf_stats["low_pe_top10"] = df_spot.nsmallest(10, per_col)[["股票代码", "股票名称", per_col]].fillna("").to_dict("records")
        if pb_col:
            pb_valid = pd.to_numeric(df_spot[pb_col], errors="coerce")
            pb_valid = pb_valid[pb_valid > 0]
            perf_stats["pb_median"] = round(float(pb_valid.median()), 2) if len(pb_valid) > 0 else 0
            perf_stats["low_pb_top10"] = df_spot.nsmallest(10, pb_col)[["股票代码", "股票名称", pb_col]].fillna("").to_dict("records")
        out["signals"]["performance"] = perf_stats
    else:
        out["signals"]["performance"] = {"ok": False}

    # === 5. IPO ===
    print("[5/5] 最新IPO...", file=sys.stderr)
    df_ipo = safe_get(ef.stock.get_latest_ipo_info, "IPO")
    if df_ipo is not None:
        out["signals"]["ipo"] = {
            "ok": True, "count": len(df_ipo),
            "sample": df_ipo.head(10).fillna("").to_dict("records"),
        }
    else:
        out["signals"]["ipo"] = {"ok": False}

    # 汇总
    ok_count = sum(1 for v in out["signals"].values() if isinstance(v, dict) and v.get("ok"))
    out["summary"] = {"total": len(out["signals"]), "ok": ok_count, "status": "full" if ok_count == len(out["signals"]) else "partial"}

    # 保存 JSON
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, default=str, indent=2)

    # 保存 SQLite
    try:
        save_to_db(conn, out, df_spot)
        conn.close()
        db_ok = True
    except Exception as e:
        db_ok = False
        print(f"[DB ERROR] {e}", file=sys.stderr)

    # 运行日志
    finished_at = datetime.now().isoformat()
    status = "success" if ok_count == len(out["signals"]) else "partial" if ok_count > 0 else "failed"
    try:
        conn2 = sqlite3.connect(OUT_DB)
        conn2.execute(
            "INSERT INTO run_log (started_at, finished_at, status, ok_sections, total_sections, error) VALUES (?,?,?,?,?,?)",
            (started_at, finished_at, status, ok_count, len(out["signals"]), "" if status == "success" else "partial data")
        )
        conn2.commit()
        conn2.close()
    except:
        pass

    # 通知
    print(f"\nDone: {ok_count}/{len(out['signals'])} sections", file=sys.stderr)
    if status == "success":
        notify("葵学管道 ✅", f"数据拉取完成 {ok_count}/{len(out['signals'])}")
    else:
        notify("葵学管道 ⚠️", f"部分失败 {ok_count}/{len(out['signals'])}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        notify("葵学管道 ❌", f"运行异常: {str(e)[:50]}")
        sys.exit(1)
