# -*- coding: utf-8 -*-
"""葵学2.0 数据管道 — Tushare Pro 版
替代 AKShare，接口更稳定。
"""
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta

import tushare as ts
import pandas as pd

TOKEN = os.environ.get("TUSHARE_TOKEN", "")
if not TOKEN:
    print("ERROR: TUSHARE_TOKEN not set", file=sys.stderr)
    sys.exit(1)

ts.set_token(TOKEN)
pro = ts.pro_api()


def safe(func, *args, retries=2, delay=5, **kwargs):
    """带重试的 API 调用，积分不足或限频时优雅降级"""
    for i in range(retries):
        try:
            df = func(*args, **kwargs)
            if df is not None and not df.empty:
                return df
            elif df is not None:
                return df
        except Exception as e:
            err = str(e)
            # 积分不足 → 不重试
            if "积分" in err or "points" in err.lower():
                print(f"  SKIP (积分不足): {err}", file=sys.stderr)
                return None
            print(f"  retry {i+1}/{retries}: {err}", file=sys.stderr)
            if i < retries - 1 and delay:
                time.sleep(delay)
    return None


def df_sample(df, n=10):
    if df is None or df.empty:
        return []
    return df.head(n).fillna("").to_dict("records")


def main():
    today = datetime.now().strftime("%Y%m%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    # 周末回退到周五
    if datetime.now().weekday() == 6:  # Sunday
        yesterday = (datetime.now() - timedelta(days=2)).strftime("%Y%m%d")
    elif datetime.now().weekday() == 5:  # Saturday
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    out = {"timestamp": datetime.now().isoformat(), "date": today, "signals": {}}

    # === 1. 同花顺行业指数行情（替代东方财富行业板块）===
    print("[1/6] 行业板块行情...", file=sys.stderr)
    try:
        df_index = safe(pro.ths_index, exchange="A")
        if df_index is not None:
            out["signals"]["ths_index_list"] = {
                "ok": True, "count": len(df_index),
                "sample": df_sample(df_index, 5),
            }
            # 拉取今日行情
            codes = df_index["ts_code"].tolist()[:50]  # 先取前50个
            df_daily = safe(pro.ths_daily, ts_code=",".join(codes),
                          start_date=yesterday, end_date=today)
            if df_daily is not None:
                # 找涨跌幅列
                pct_col = "pct_chg" if "pct_chg" in df_daily.columns else None
                if pct_col:
                    df_daily[pct_col] = pd.to_numeric(df_daily[pct_col], errors="coerce")
                    # merge 名称
                    df_daily = df_daily.merge(df_index[["ts_code", "name"]], on="ts_code", how="left")
                    out["signals"]["board_industry"] = {
                        "ok": True, "count": len(df_daily),
                        "top5_up": df_daily.nlargest(5, pct_col).fillna("").to_dict("records"),
                        "top5_down": df_daily.nsmallest(5, pct_col).fillna("").to_dict("records"),
                    }
                else:
                    out["signals"]["board_industry"] = {
                        "ok": True, "count": len(df_daily),
                        "sample": df_sample(df_daily, 5),
                        "note": "no pct_chg column"
                    }
            else:
                out["signals"]["board_industry"] = {"ok": False, "note": "ths_daily failed"}
        else:
            out["signals"]["board_industry"] = {"ok": False}
    except Exception as e:
        out["signals"]["board_industry"] = {"ok": False, "error": str(e)[:200]}
        print(f"  板块行情异常: {e}", file=sys.stderr)

    # === 2. 沪深港通资金流向（替代行业资金流）===
    print("[2/6] 沪深港通资金流向...", file=sys.stderr)
    try:
        df_hsgt = safe(pro.money_flow_hsgt, start_date=yesterday, end_date=today)
        if df_hsgt is not None:
            out["signals"]["hsgt"] = {
                "ok": True, "count": len(df_hsgt),
                "recent": df_sample(df_hsgt, 5),
            }
        else:
            out["signals"]["hsgt"] = {"ok": False}
    except Exception as e:
        out["signals"]["hsgt"] = {"ok": False, "error": str(e)[:200]}

    # === 3. 个股资金流向（需要高积分，降级用换手率替代）===
    print("[3/6] 个股数据（换手率排名）...", file=sys.stderr)
    try:
        df_basic = safe(pro.daily_basic, trade_date=yesterday,
                       fields="ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,pe,pb")
        if df_basic is not None:
            df_basic["turnover_rate"] = pd.to_numeric(df_basic["turnover_rate"], errors="coerce")
            # 获取股票名称
            df_stocks = safe(pro.stock_basic, list_status="L",
                           fields="ts_code,name,industry")
            if df_stocks is not None:
                df_basic = df_basic.merge(df_stocks, on="ts_code", how="left")

            top20 = df_basic.nlargest(20, "turnover_rate")
            stats = {
                "p50": round(float(df_basic["turnover_rate"].quantile(0.5)), 3),
                "p75": round(float(df_basic["turnover_rate"].quantile(0.75)), 3),
                "p90": round(float(df_basic["turnover_rate"].quantile(0.9)), 3),
            }
            out["signals"]["stock_turnover"] = {
                "ok": True, "count": len(df_basic),
                "top20": top20.fillna("").to_dict("records"),
                "turnover_percentiles": stats,
            }
        else:
            out["signals"]["stock_turnover"] = {"ok": False}
    except Exception as e:
        out["signals"]["stock_turnover"] = {"ok": False, "error": str(e)[:200]}

    # === 4. 融资余额 ===
    print("[4/6] 融资余额...", file=sys.stderr)
    try:
        df_margin = safe(pro.margin, start_date=yesterday, end_date=today)
        if df_margin is not None:
            out["signals"]["margin"] = {
                "ok": True, "count": len(df_margin),
                "recent": df_sample(df_margin, 5),
            }
        else:
            # 试试 detail
            df_detail = safe(pro.margin_detail, trade_date=yesterday)
            if df_detail is not None:
                out["signals"]["margin_detail"] = {
                    "ok": True, "count": len(df_detail),
                    "sample": df_sample(df_detail, 10),
                }
            else:
                out["signals"]["margin"] = {"ok": False}
    except Exception as e:
        out["signals"]["margin"] = {"ok": False, "error": str(e)[:200]}

    # === 5. A股行情总览 ===
    print("[5/6] A股行情总览...", file=sys.stderr)
    try:
        df_daily = safe(pro.daily, trade_date=yesterday)
        if df_daily is not None:
            for col in ["pct_chg", "vol", "amount"]:
                if col in df_daily.columns:
                    df_daily[col] = pd.to_numeric(df_daily[col], errors="coerce")

            summary = {"ok": True, "count": len(df_daily)}

            if "pct_chg" in df_daily.columns:
                summary["limit_up"] = int((df_daily["pct_chg"] >= 9.9).sum())
                summary["limit_down"] = int((df_daily["pct_chg"] <= -9.9).sum())
                summary["avg_pct"] = round(float(df_daily["pct_chg"].mean()), 2)
                summary["median_pct"] = round(float(df_daily["pct_chg"].median()), 2)

            out["signals"]["market_overview"] = summary
        else:
            out["signals"]["market_overview"] = {"ok": False}
    except Exception as e:
        out["signals"]["market_overview"] = {"ok": False, "error": str(e)[:200]}

    # === 6. 业绩预告 ===
    print("[6/6] 业绩预告...", file=sys.stderr)
    try:
        # 最近的业绩预告
        periods = ["20250331", "20241231", "20240930"]
        perf_ok = False
        for period in periods:
            df_forecast = safe(pro.forecast, period=period)
            if df_forecast is not None and not df_forecast.empty:
                out["signals"]["performance"] = {
                    "ok": True, "source": "forecast", "period": period,
                    "count": len(df_forecast),
                    "sample": df_sample(df_forecast, 10),
                }
                perf_ok = True
                break
        if not perf_ok:
            out["signals"]["performance"] = {"ok": False, "note": "所有季度均无数据"}
    except Exception as e:
        out["signals"]["performance"] = {"ok": False, "error": str(e)[:200]}

    # 输出
    print(json.dumps(out, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
