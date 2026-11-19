# -*- coding: utf-8 -*-
"""
葵学2.0 数据管道 — 温度计 + 拥挤度检测
从 AKShare 拉取A股数据，输出结构化 JSON 供模型分析。

使用：python kuixue_pipeline.py [--date 2026-04-17] [--output json|md]
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd


def safe_fetch(func, *args, retries=3, delay=2, **kwargs):
    """带重试的数据拉取"""
    for i in range(retries):
        try:
            df = func(*args, **kwargs)
            if df is not None and not df.empty:
                return df
            print(f"  ⚠ {func.__name__} 返回空数据，重试 {i+1}/{retries}")
        except Exception as e:
            print(f"  ⚠ {func.__name__} 异常: {e}，重试 {i+1}/{retries}")
        time.sleep(delay)
    return pd.DataFrame()


def fetch_industry_fund_flow():
    """信号组1：行业资金流向 — TOP5流入/流出"""
    print("📡 拉取行业资金流向...")
    # 东方财富行业资金流向
    df = safe_fetch(ak.stock_individual_fund_flow_rank, indicator="今日")
    if df.empty:
        return {"top5_inflow": [], "top5_outflow": [], "raw_available": False}
    
    # 尝试不同列名
    cols = df.columns.tolist()
    print(f"  列名: {cols}")
    
    result = {
        "raw_available": True,
        "columns": cols,
        "top5_inflow": [],
        "top5_outflow": [],
    }
    return result


def fetch_sector_fund_flow():
    """信号组1：板块资金流向（行业级别）"""
    print("📡 拉取板块资金流向...")
    try:
        df = ak.stock_board_industry_name_em()
        print(f"  板块列表: {len(df)} 个行业, 列名: {df.columns.tolist()}")
        return {"available": True, "count": len(df), "columns": df.columns.tolist()}
    except Exception as e:
        print(f"  ⚠ 板块列表拉取失败: {e}")
        return {"available": False, "error": str(e)}


def fetch_stock_fund_flow(symbol="000001"):
    """信号组1：个股资金流向"""
    print(f"📡 拉取个股资金流向 ({symbol})...")
    try:
        df = ak.stock_individual_fund_flow(stock=symbol, market="sh")
        print(f"  个股资金流: {len(df)} 条, 列名: {df.columns.tolist()}")
        return {"available": True, "rows": len(df), "columns": df.columns.tolist()}
    except Exception as e:
        print(f"  ⚠ 个股资金流失败: {e}")
        return {"available": False, "error": str(e)}


def fetch_margin_data():
    """拥挤度：融资余额数据"""
    print("📡 拉取融资余额...")
    try:
        # 沪市融资余额
        df_sh = ak.stock_margin_detail_sse(date=datetime.now().strftime("%Y%m%d"))
        print(f"  沪市融资: {len(df_sh)} 条, 列名: {df_sh.columns.tolist()}")
        return {"available": True, "exchange": "SSE", "rows": len(df_sh), "columns": df_sh.columns.tolist()}
    except Exception as e:
        print(f"  ⚠ 沪市融资余额失败: {e}")
        # 尝试汇总数据
        try:
            df = ak.stock_margin_underlying_info_szse(date=datetime.now().strftime("%Y%m%d"))
            print(f"  深市融资: {len(df)} 条, 列名: {df.columns.tolist()}")
            return {"available": True, "exchange": "SZSE", "rows": len(df), "columns": df.columns.tolist()}
        except Exception as e2:
            print(f"  ⚠ 深市融资余额也失败: {e2}")
            return {"available": False, "error": f"SSE: {e}; SZSE: {e2}"}


def fetch_spot_data():
    """信号组2+拥挤度：A股实时行情（含换手率）"""
    print("📡 拉取A股实时行情...")
    df = safe_fetch(ak.stock_zh_a_spot_em)
    if df.empty:
        return {"available": False}
    
    print(f"  A股行情: {len(df)} 只股票, 列名: {df.columns.tolist()}")
    # 检查是否含换手率
    has_turnover = any("换手" in c for c in df.columns)
    has_amount = any("成交" in c or "额" in c for c in df.columns)
    
    return {
        "available": True, 
        "count": len(df), 
        "columns": df.columns.tolist(),
        "has_turnover_rate": has_turnover,
        "has_amount": has_amount,
    }


def fetch_board_info():
    """信号组2：板块-个股对应关系"""
    print("📡 拉取板块成分股...")
    try:
        # 获取行业板块列表
        df = ak.stock_board_industry_name_em()
        if df.empty:
            return {"available": False}
        
        # 取第一个板块试试
        first_board = df.iloc[0]
        board_name = first_board.get("板块名称", df.columns[0])
        print(f"  尝试板块: {board_name}")
        
        members = ak.stock_board_industry_cons_em(symbol=board_name)
        print(f"  板块成分: {len(members)} 只, 列名: {members.columns.tolist()}")
        
        return {
            "available": True, 
            "board_count": len(df),
            "sample_board": board_name,
            "sample_members": len(members),
            "member_columns": members.columns.tolist(),
        }
    except Exception as e:
        print(f"  ⚠ 板块成分拉取失败: {e}")
        return {"available": False, "error": str(e)}


def fetch_performance_forecast():
    """信号组4：业绩预告数据"""
    print("📡 拉取业绩预告...")
    try:
        df = ak.stock_profit_sheet_by_report_em(symbol="000001")
        print(f"  利润表样例: {len(df)} 条, 列名: {df.columns.tolist()}")
        return {"available": True, "rows": len(df), "columns": df.columns.tolist()}
    except Exception as e:
        print(f"  ⚠ 利润表失败: {e}")
    
    # 备选：业绩预告
    try:
        df = ak.stock_em_yjyg(date=datetime.now().strftime("%Y1231"))
        print(f"  业绩预告: {len(df)} 条, 列名: {df.columns.tolist()}")
        return {"available": True, "source": "yjyg", "rows": len(df), "columns": df.columns.tolist()}
    except Exception as e:
        print(f"  ⚠ 业绩预告也失败: {e}")
        return {"available": False, "error": str(e)}


def run_probe():
    """
    探测模式：逐个测试 AKShare 接口可用性
    不追求数据完整，只确认哪些接口能用、返回什么列
    """
    print("=" * 60)
    print("葵学2.0 数据管道 — 探测模式")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    results = {}
    
    # 1. 行业资金流向
    results["industry_fund_flow"] = fetch_industry_fund_flow()
    print()
    
    # 2. 板块资金流向
    results["sector_fund_flow"] = fetch_sector_fund_flow()
    print()
    
    # 3. 个股资金流向
    results["stock_fund_flow"] = fetch_stock_fund_flow("000001")
    print()
    
    # 4. 融资余额
    results["margin_data"] = fetch_margin_data()
    print()
    
    # 5. A股实时行情
    results["spot_data"] = fetch_spot_data()
    print()
    
    # 6. 板块成分
    results["board_info"] = fetch_board_info()
    print()
    
    # 7. 业绩预告
    results["performance_forecast"] = fetch_performance_forecast()
    print()
    
    return results


def run_full():
    """
    完整模式：拉取温度计所需全部数据
    """
    print("=" * 60)
    print("葵学2.0 数据管道 — 完整模式")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    data = {}
    
    # === 信号组1：资金流向温度 ===
    print("\n📊 信号组1：资金流向温度")
    
    # 行业资金流向排名
    print("  拉取行业资金流向排名...")
    try:
        df = ak.stock_fund_flow_industry(symbol="今日")
        if df is not None and not df.empty:
            print(f"  ✅ 行业资金流: {len(df)} 条, 列: {df.columns.tolist()}")
            # TOP5 流入
            if "主力净流入-净额" in df.columns:
                top5_in = df.nlargest(5, "主力净流入-净额")[["行业", "主力净流入-净额"]].to_dict("records")
                top5_out = df.nsmallest(5, "主力净流入-净额")[["行业", "主力净流入-净额"]].to_dict("records")
                data["industry_top5_inflow"] = top5_in
                data["industry_top5_outflow"] = top5_out
            else:
                data["industry_fund_flow_columns"] = df.columns.tolist()
                data["industry_fund_flow_sample"] = df.head(5).to_dict("records")
    except Exception as e:
        print(f"  ❌ 行业资金流向失败: {e}")
        data["industry_fund_flow_error"] = str(e)
    
    # 个股资金流向排名
    print("  拉取个股资金流向排名...")
    try:
        df = ak.stock_individual_fund_flow_rank(indicator="今日")
        if df is not None and not df.empty:
            print(f"  ✅ 个股资金流排名: {len(df)} 条, 列: {df.columns.tolist()}")
            data["stock_fund_flow_rank_columns"] = df.columns.tolist()
            data["stock_fund_flow_rank_sample"] = df.head(10).to_dict("records")
    except Exception as e:
        print(f"  ❌ 个股资金流排名失败: {e}")
        data["stock_fund_flow_rank_error"] = str(e)
    
    # === 信号组2：标杆背离温度 ===
    print("\n📊 信号组2：标杆背离温度")
    
    # 板块行情
    print("  拉取板块行情...")
    try:
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            print(f"  ✅ 板块行情: {len(df)} 条, 列: {df.columns.tolist()}")
            data["board_industry_columns"] = df.columns.tolist()
            data["board_industry_sample"] = df.head(5).to_dict("records")
    except Exception as e:
        print(f"  ❌ 板块行情失败: {e}")
        data["board_industry_error"] = str(e)
    
    # === 信号组3：政策信号温度（手动判断，数据管道不负责） ===
    print("\n📊 信号组3：政策信号温度 — 需人工判断，跳过")
    
    # === 信号组4：业绩验证温度 ===
    print("\n📊 信号组4：业绩验证温度")
    print("  拉取业绩预告...")
    try:
        # 尝试最近报告期
        for period in ["20250331", "20241231", "20240930"]:
            try:
                df = ak.stock_em_yjyg(date=period)
                if df is not None and not df.empty:
                    print(f"  ✅ 业绩预告({period}): {len(df)} 条, 列: {df.columns.tolist()}")
                    data["performance_forecast_period"] = period
                    data["performance_forecast_columns"] = df.columns.tolist()
                    data["performance_forecast_count"] = len(df)
                    data["performance_forecast_sample"] = df.head(5).to_dict("records")
                    break
            except:
                continue
    except Exception as e:
        print(f"  ❌ 业绩预告失败: {e}")
        data["performance_forecast_error"] = str(e)
    
    # === 信号组5：蛛网位移温度 ===
    print("\n📊 信号组5：蛛网位移温度 — 需多日对比计算，暂跳过")
    
    # === 拥挤度检测 ===
    print("\n📊 拥挤度检测")
    
    # 融资余额
    print("  拉取融资余额...")
    try:
        df = ak.stock_margin_sse()
        if df is not None and not df.empty:
            print(f"  ✅ 沪市融资汇总: {len(df)} 条, 列: {df.columns.tolist()}")
            data["margin_sse_columns"] = df.columns.tolist()
            data["margin_sse_recent"] = df.tail(10).to_dict("records")
    except Exception as e:
        print(f"  ❌ 沪市融资汇总失败: {e}")
        data["margin_sse_error"] = str(e)
    
    # 深市融资
    try:
        df = ak.stock_margin_szse()
        if df is not None and not df.empty:
            print(f"  ✅ 深市融资汇总: {len(df)} 条, 列: {df.columns.tolist()}")
            data["margin_szse_columns"] = df.columns.tolist()
            data["margin_szse_recent"] = df.tail(10).to_dict("records")
    except Exception as e:
        print(f"  ❌ 深市融资汇总失败: {e}")
        data["margin_szse_error"] = str(e)
    
    # 换手率（从A股行情里拿）
    print("  拉取换手率数据...")
    try:
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            print(f"  ✅ A股行情: {len(df)} 条, 列: {df.columns.tolist()}")
            data["spot_columns"] = df.columns.tolist()
            # 取含换手率字段的样例
            turnover_col = next((c for c in df.columns if "换手" in c), None)
            if turnover_col:
                data["has_turnover_rate"] = True
                data["turnover_column"] = turnover_col
                # 换手率TOP10
                top_turnover = df.nlargest(10, turnover_col)
                code_col = next((c for c in df.columns if "代码" in c), df.columns[0])
                name_col = next((c for c in df.columns if "名称" in c), df.columns[1])
                data["top10_turnover"] = top_turnover[[code_col, name_col, turnover_col]].to_dict("records")
            else:
                data["has_turnover_rate"] = False
    except Exception as e:
        print(f"  ❌ A股行情失败: {e}")
        data["spot_error"] = str(e)
    
    return data


def main():
    parser = argparse.ArgumentParser(description="葵学2.0 数据管道")
    parser.add_argument("--mode", choices=["probe", "full"], default="probe",
                        help="probe=探测接口可用性, full=完整拉取")
    parser.add_argument("--output", choices=["json", "md"], default="json",
                        help="输出格式")
    parser.add_argument("--save", type=str, default=None,
                        help="保存到文件路径")
    args = parser.parse_args()
    
    if args.mode == "probe":
        results = run_probe()
    else:
        results = run_full()
    
    # 输出
    if args.output == "json":
        output = json.dumps(results, ensure_ascii=False, indent=2, default=str)
    else:
        # 简单 markdown 格式
        output = "# 葵学2.0 数据管道输出\n\n"
        output += f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        output += f"```json\n{json.dumps(results, ensure_ascii=False, indent=2, default=str)}\n```"
    
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\n✅ 已保存到: {args.save}")
    else:
        print("\n" + output)


if __name__ == "__main__":
    main()
