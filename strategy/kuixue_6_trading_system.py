# 葵学3.0 — 第6层：交易执行系统
# 基于已验证的结论，生成可执行的交易规则

import json
import os

WORKSPACE = r'C:\Users\11503\.openclaw-autoclaw\workspace'

TRADING_SYSTEM = {
    "name": "葵学3.0 交易执行系统",
    "version": "1.0",
    "date": "2026-04-26",
    
    "entry_rules": {
        "description": "入场条件：三环全部满足才出手",
        "rules": [
            {
                "id": "E1",
                "name": "方向匹配",
                "condition": "当前政策锚点与投资方向匹配",
                "examples": [
                    "双碳政策 → 新能源/光伏/储能",
                    "十四五自主可控 → 半导体/信创",
                    "AI政策 → 算力/数字经济/光模块",
                    "节能降碳 → 光伏/储能/碳中和",
                ],
                "anti_examples": [
                    "双碳政策 → 半导体（错配，已验证亏28%）",
                    "AI政策 → 新能源（错配，已验证亏11%）",
                ],
                "source": "v8回测：方向×政策匹配矩阵"
            },
            {
                "id": "E2",
                "name": "基本面过关",
                "condition": "三条件全部满足",
                "sub_conditions": [
                    "ROE > 0（盈利）",
                    "营收同比 > 0（增长中）",
                    "资产负债率 < 70%（不太缺钱）",
                ],
                "pass_rate": "约40%的出招表方向股通过筛选",
                "source": "v8筛选回测：通过筛选后2年中位+3.5% vs 不筛选-2.0%"
            },
            {
                "id": "E3",
                "name": "时机正确",
                "condition": "政策日大盘没有暴涨",
                "details": [
                    "✅ 政策发布日HS300涨幅<1% → 可介入（后续超额+0.76%~+6.25%）",
                    "❌ 政策发布日HS300涨幅>1% → 等待（后续超额-0.89%~-3.64%）",
                    "❌ 政策发布日HS300涨幅>2% → 绝不追（已验证=接盘）",
                ],
                "source": "v3回测：16个政策事件验证"
            }
        ]
    },
    
    "exit_rules": {
        "description": "出场条件",
        "rules": [
            {
                "id": "X1",
                "name": "止损",
                "condition": "个股亏损>15%",
                "action": "无条件卖出",
                "reason": "基本面过关的股票亏15%说明逻辑已破"
            },
            {
                "id": "X2",
                "name": "目标持仓",
                "condition": "持有满2年",
                "action": "评估是否继续持有（2年是α显现的最短周期）",
                "reason": "v8回测：2年起α才显著"
            },
            {
                "id": "X3",
                "name": "逻辑破坏",
                "condition": "政策方向逆转或个股基本面恶化（ROE转负/营收下滑>20%）",
                "action": "减仓50%，观察1个月后决定去留"
            }
        ]
    },
    
    "position_rules": {
        "description": "仓位管理",
        "rules": [
            {
                "id": "P1",
                "name": "单方向上限",
                "condition": "单一投资方向仓位≤5%",
                "reason": "分散风险，避免方向判断失误的集中损失"
            },
            {
                "id": "P2",
                "name": "总出招表仓位",
                "condition": "出招表方向总仓位≤30%",
                "reason": "留70%资金给确定性更高的资产或现金"
            },
            {
                "id": "P3",
                "name": "分批建仓",
                "condition": "首次买入目标仓位的50%，1个月后基本面无恶化加至100%",
                "reason": "避免一次性买入后遭遇黑天鹅"
            }
        ]
    },
    
    "forbidden_actions": {
        "description": "绝对禁止",
        "rules": [
            {"id": "F1", "name": "不追涨", "detail": "涨停/技术追涨/政策追涨全部负期望"},
            {"id": "F2", "name": "不在暴涨后买入", "detail": "政策日大盘暴涨=接盘"},
            {"id": "F3", "name": "不碰亏损股", "detail": "PE为负=不在筛选范围内"},
            {"id": "F4", "name": "不短线", "detail": "1年以内无α，短线=赌博"},
            {"id": "F5", "name": "不融资", "detail": "高β股×融资=加倍亏损"},
        ]
    },
    
    "checklist": {
        "description": "买入前逐项确认",
        "items": [
            "□ 当前政策锚点是什么？（双碳/自主可控/AI/节能降碳/工业4.0）",
            "□ 投资方向是否匹配该锚点？（不匹配=停止）",
            "□ 该方向是否在出招表8本书的覆盖范围内？（不在=停止）",
            "□ 个股ROE>0？（否=跳过）",
            "□ 个股营收同比>0？（否=跳过）",
            "□ 个股资产负债率<70%？（否=跳过）",
            "□ 政策日HS300涨幅<1%？（否=等待）",
            "□ 单方向仓位≤5%？（否=减仓）",
            "□ 准备持有≥2年？（否=不做）",
            "□ 止损线设好（-15%）？（否=不做）",
        ]
    },
    
    "direction_policy_map": {
        "description": "方向×政策锚点匹配表（已验证）",
        "map": {
            "新能源/双碳": {
                "匹配政策": ["双碳目标", "节能降碳", "十五五规划"],
                "不匹配政策": ["AI大模型", "自主可控"],
                "2年验证收益": "双碳+26%, 十四五+21%, AI+0%"
            },
            "半导体/自主可控": {
                "匹配政策": ["十四五自主可控", "AI大模型（算力硬件）"],
                "不匹配政策": ["双碳目标"],
                "2年验证收益": "双碳-11%, 十四五+18%, AI+23%"
            },
            "AI/数字经济": {
                "匹配政策": ["十四五自主可控", "AI大模型"],
                "不匹配政策": ["双碳目标"],
                "2年验证收益": "双碳-12%, 十四五+19%, AI+24%"
            },
            "工业4.0/智能制造": {
                "匹配政策": ["十四五自主可控"],
                "不匹配政策": ["双碳目标", "AI大模型"],
                "2年验证收益": "双碳+9%, 十四五+18%, AI+8%"
            }
        }
    }
}

# 保存
output_path = os.path.join(WORKSPACE, "kuixue_trading_system.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(TRADING_SYSTEM, f, ensure_ascii=False, indent=2)

# 输出摘要
print("=" * 70)
print("葵学3.0 交易执行系统 v1.0")
print("=" * 70)

print("\n【入场条件】三环全过才出手")
for r in TRADING_SYSTEM["entry_rules"]["rules"]:
    print(f"  E{r['id'][-1]} {r['name']}: {r['condition']}")

print("\n【出场条件】")
for r in TRADING_SYSTEM["exit_rules"]["rules"]:
    print(f"  X{r['id'][-1]} {r['name']}: {r['condition']} → {r['action']}")

print("\n【仓位管理】")
for r in TRADING_SYSTEM["position_rules"]["rules"]:
    print(f"  P{r['id'][-1]} {r['name']}: {r['condition']}")

print("\n【五条禁令】")
for r in TRADING_SYSTEM["forbidden_actions"]["rules"]:
    print(f"  {r['id']} {r['name']}: {r['detail']}")

print("\n【买入前检查清单】")
for item in TRADING_SYSTEM["checklist"]["items"]:
    print(f"  {item}")

print(f"\n系统配置已保存: {output_path}")
