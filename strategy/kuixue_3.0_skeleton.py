# -*- coding: utf-8 -*-
"""
葵学3.0 — 自上而下数据库（骨架版）
不依赖实时API，8本书→投资方向→概念名称 手动构建
stock代码待网络稳定后填充
"""
import json, time, os, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

WORKSPACE = r'C:\Users\11503\.openclaw-autoclaw\workspace'

# ===== 8本书 → 投资方向 → 概念名称 =====
# 概念名称严格使用东方财富标准名称，方便后续API匹配

BOOKS = {
    "习近平在正定": {
        "summary": "菜篮子、农业产业化、解决供给问题",
        "directions": {
            "菜篮子/农业产业化": {
                "priority": 2,
                "concepts": [
                    "预制菜", "社区团购", "冷链物流", "食品加工",
                    "中央厨房", "生鲜电商", "食品安全", "农业种植",
                    "种业", "转基因", "农药", "化肥",
                    "乡村振兴", "智慧农业", "农机",
                ]
            },
        }
    },
    "习近平在厦门": {
        "summary": "经济特区、对外开放、引进外资",
        "directions": {
            "经济特区/对外开放": {
                "priority": 2,
                "concepts": [
                    "自由贸易港", "一带一路", "跨境电商",
                    "跨境支付", "外贸", "航运", "港口",
                    "智慧物流", "数字贸易", "出海",
                ]
            },
        }
    },
    "习近平在宁德": {
        "summary": "弱鸟先飞、扶贫攻坚、从赤贫到产业重镇",
        "directions": {
            "弱鸟先飞/后发突围": {
                "priority": 2,
                "concepts": [
                    "乡村振兴", "产业转移", "农村电商",
                    "农机", "智慧农业", "县域经济",
                ]
            },
            "举国体制产业攻坚": {
                "priority": 3,
                "concepts": [
                    "新能源", "锂电池", "动力电池", "储能",
                    "钠离子电池", "氢能源", "燃料电池",
                    "充电桩", "换电", "新能源车",
                    "宁德时代概念",
                ]
            },
        }
    },
    "习近平在福州": {
        "summary": "农改超、城市治理、闽江开发",
        "directions": {
            "农改超/新零售": {
                "priority": 2,
                "concepts": [
                    "新零售", "社区团购", "生鲜电商",
                    "商超", "便利店",
                ]
            },
            "城市治理/智慧城市": {
                "priority": 3,
                "concepts": [
                    "智慧城市", "数字政府", "安防",
                    "视频监控", "城市大脑", "政务",
                ]
            },
            "环保治水/流域开发": {
                "priority": 2,
                "concepts": [
                    "污水处理", "水务", "水利",
                    "环保", "海绵城市", "节水",
                ]
            },
        }
    },
    "摆脱贫困": {
        "summary": "弱鸟先飞、滴水穿石、扶贫方法论",
        "directions": {
            "产业扶贫/乡村振兴": {
                "priority": 2,
                "concepts": [
                    "乡村振兴", "产业扶贫", "县域经济",
                    "农村电商", "特色农业", "农机",
                ]
            },
            "举国体制攻坚行业": {
                "priority": 3,
                "concepts": [
                    "半导体", "芯片", "大飞机", "航空发动机",
                    "工业母机", "高端装备", "国产替代",
                ]
            },
            "新型城镇化": {
                "priority": 2,
                "concepts": [
                    "装配式建筑", "绿色建筑", "城市更新",
                    "保障房", "旧改",
                ]
            },
        }
    },
    "论中国信息技术产业发展": {
        "summary": "科技自立、数字经济、信息化",
        "directions": {
            "半导体攻坚/国产替代": {
                "priority": 5,
                "concepts": [
                    "半导体", "芯片", "国产芯片",
                    "EDA", "光刻机", "集成电路",
                    "封测", "晶圆", "硅片",
                    "GPU", "CPU", "FPGA",
                    "存储芯片", "功率半导体",
                    "第三代半导体", "碳化硅", "氮化镓",
                    "国产替代", "自主可控", "信创",
                ]
            },
            "数字经济/AI算力": {
                "priority": 5,
                "concepts": [
                    "人工智能", "算力", "光模块",
                    "CPO", "数据中心", "IDC",
                    "AIGC", "大模型", "机器人",
                    "AI芯片", "机器视觉",
                    "数字经济", "云计算", "大数据",
                    "边缘计算", "物联网",
                    "数字人", "AI医疗", "AI教育",
                    "数字中国",
                ]
            },
            "工业4.0/智能制造": {
                "priority": 3,
                "concepts": [
                    "工业软件", "智能制造", "工业互联网",
                    "数控机床", "工业机器人", "机器人",
                    "机器视觉", "传感器",
                    "工业母机", "高端装备",
                ]
            },
            "网络安全/信创": {
                "priority": 3,
                "concepts": [
                    "网络安全", "信创", "数据安全",
                    "国产操作系统", "国产数据库",
                    "信息安全", "密码学", "零信任",
                ]
            },
        }
    },
    "中国能源问题研究": {
        "summary": "能源安全、能源转型、新能源",
        "directions": {
            "能源安全/油气自主": {
                "priority": 2,
                "concepts": [
                    "油气开采", "页岩气", "天然气",
                    "石油", "油田服务", "LNG",
                ]
            },
            "能源转型/双碳": {
                "priority": 4,
                "concepts": [
                    "光伏", "风电", "太阳能",
                    "储能", "绿电", "碳中和",
                    "新能源", "光伏建筑一体化",
                    "分布式能源", "微电网",
                ]
            },
            "新能源车/储能": {
                "priority": 4,
                "concepts": [
                    "新能源车", "锂电池", "动力电池",
                    "充电桩", "换电", "电池回收",
                    "钠离子电池", "氢能源", "燃料电池",
                    "锂矿", "锂电材料", "钴", "稀土永磁",
                ]
            },
            "智能电网/特高压": {
                "priority": 3,
                "concepts": [
                    "特高压", "智能电网", "电力设备",
                    "变压器", "电力物联网", "虚拟电厂",
                ]
            },
        }
    },
    "论坚持人与自然和谐共生": {
        "summary": "绿色发展、生态保护、碳达峰碳中和",
        "directions": {
            "生态保护/环保": {
                "priority": 3,
                "concepts": [
                    "污水处理", "固废处理", "垃圾焚烧",
                    "危废", "土壤修复", "生态修复",
                    "环境监测", "环卫", "再生资源",
                    "环保",
                ]
            },
            "碳交易/绿色金融": {
                "priority": 2,
                "concepts": [
                    "碳交易", "碳中和", "碳排放",
                    "绿色金融", "ESG", "碳捕捉",
                ]
            },
            "绿色制造/节能": {
                "priority": 2,
                "concepts": [
                    "节能", "工业节能", "建筑节能",
                    "绿色建筑", "装配式建筑",
                    "清洁生产", "循环经济",
                ]
            },
        }
    },
}


def build_skeleton():
    """构建骨架JSON"""
    output = {
        "meta": {
            "version": "3.0",
            "architecture": "top-down: book → direction → concept_name → stock_code",
            "created": time.strftime("%Y-%m-%d"),
            "data_status": "skeleton",
            "description": "葵学3.0数据库骨架：概念名称已列出，stock_codes待填充"
        },
        "books": {}
    }

    total_directions = 0
    total_concepts = 0

    for book_name, book_data in BOOKS.items():
        book_entry = {
            "summary": book_data["summary"],
            "directions": {}
        }

        for dir_name, dir_data in book_data["directions"].items():
            total_directions += 1
            concepts = {}
            for concept_name in dir_data["concepts"]:
                total_concepts += 1
                concepts[concept_name] = {
                    "stock_codes": [],  # 待填充
                    "stock_count": 0,   # 待填充
                }

            book_entry["directions"][dir_name] = {
                "priority": dir_data["priority"],
                "concepts": concepts
            }

        output["books"][book_name] = book_entry

    output["meta"]["total_directions"] = total_directions
    output["meta"]["total_concepts"] = total_concepts
    output["meta"]["total_stocks"] = 0

    return output


def print_summary(output):
    """打印骨架摘要"""
    print("\n" + "=" * 50)
    print("葵学3.0 数据库骨架 — 摘要")
    print("=" * 50)

    for book_name, book_data in output["books"].items():
        print(f"\n📖 {book_name}")
        print(f"   {book_data['summary']}")
        for dir_name, dir_data in book_data["directions"].items():
            priority = "★" * dir_data["priority"]
            concept_names = list(dir_data["concepts"].keys())
            print(f"   {priority} {dir_name}")
            print(f"      概念: {', '.join(concept_names)}")

    print(f"\n{'=' * 50}")
    print(f"总方向: {output['meta']['total_directions']}")
    print(f"总概念: {output['meta']['total_concepts']}")


def check_concept_overlap():
    """检查概念跨书重叠情况（蛛网交叉点）"""
    concept_books = {}  # concept_name → [book_names]

    for book_name, book_data in BOOKS.items():
        for dir_name, dir_data in book_data["directions"].items():
            for concept_name in dir_data["concepts"]:
                if concept_name not in concept_books:
                    concept_books[concept_name] = []
                concept_books[concept_name].append(book_name)

    overlaps = {k: v for k, v in concept_books.items() if len(v) > 1}

    print("\n蛛网交叉点（跨书重叠概念）:")
    print("-" * 50)
    for concept, books in sorted(overlaps.items(), key=lambda x: -len(x[1])):
        print(f"  {concept}: {' + '.join(books)}")

    print(f"\n重叠概念数: {len(overlaps)}")
    print(f"独占概念数: {len(concept_books) - len(overlaps)}")

    return overlaps


def main():
    output = build_skeleton()

    # 保存骨架
    output_path = os.path.join(WORKSPACE, "kuixue_book_map.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"骨架已保存: {output_path}")

    # 打印摘要
    print_summary(output)

    # 检查交叉点
    overlaps = check_concept_overlap()

    # 保存交叉点信息
    overlap_path = os.path.join(WORKSPACE, "kuixue_crossroads.json")
    with open(overlap_path, "w", encoding="utf-8") as f:
        json.dump(overlaps, f, ensure_ascii=False, indent=2)
    print(f"\n蛛网交叉点已保存: {overlap_path}")


if __name__ == "__main__":
    main()
