"""
葵学3.0 — 自上而下数据库构建器

根节点：8本书 → 映射链 → 投资方向 → 概念板块名称 → 个股代码

步骤：
1. 拉取东方财富所有概念板块（名称+代码）
2. 拉取每只概念板块下的股票列表
3. 按8本书的映射体系，把概念板块挂到对应的投资方向下
4. 输出：kuixue_book_map.json（书→方向→概念→个股）
"""

import json
import time
import sys
import os

# ===== 8本书 → 映射链 → 投资方向 → 概念关键词 =====

BOOK_MAP = {
    "习近平在正定": {
        "keywords": ["正定", "菜篮子"],
        "directions": {
            "菜篮子/农业产业化": {
                "concept_keywords": [
                    "预制菜", "中央厨房", "冷链物流", "冷链",
                    "农产品加工", "生鲜电商", "社区团购", "社区零售",
                    "食品加工", "食品安全", "肉类", "蔬菜",
                    "农业产业化", "现代农业", "智慧农业", "农药",
                    "种业", "转基因", "粮食",
                ],
                "concepts": {}  # 运行时填充
            },
        }
    },
    "习近平在厦门": {
        "keywords": ["厦门", "特区", "开放"],
        "directions": {
            "经济特区/对外开放": {
                "concept_keywords": [
                    "自贸区", "自贸港", "跨境", "外贸", "港口",
                    "一带一路", "RCEP", "出海", "对外开放",
                    "智慧物流", "航运", "海运", "保税",
                    "离岸", "跨境支付", "数字贸易",
                ],
                "concepts": {}
            },
        }
    },
    "习近平在宁德": {
        "keywords": ["宁德", "弱鸟先飞", "扶贫"],
        "directions": {
            "弱鸟先飞/扶贫攻坚": {
                "concept_keywords": [
                    "产业转移", "乡村振兴", "扶贫", "脱贫攻坚",
                    "县域经济", "农村电商", "农机", "智慧农业",
                    "农业现代化", "特色农业",
                ],
                "concepts": {}
            },
            "举国体制产业攻坚/新能源": {
                "concept_keywords": [
                    "新能源", "锂电", "锂电池", "动力电池",
                    "新能源车", "电动车", "宁德时代", "电池",
                    "储能", "钠电池", "氢能", "燃料电池",
                    "充电桩", "换电",
                ],
                "concepts": {}
            },
        }
    },
    "习近平在福州": {
        "keywords": ["福州", "农改超", "城市治理"],
        "directions": {
            "农改超/新零售": {
                "concept_keywords": [
                    "新零售", "生鲜超市", "永辉", "社区生鲜",
                    "商超", "零售", "便利店", "超市",
                ],
                "concepts": {}
            },
            "城市治理/智慧城市": {
                "concept_keywords": [
                    "智慧城市", "数字政务", "城市大脑", "政务",
                    "数字政府", "安防", "视频监控", "雪亮工程",
                    "城市管理", "市政",
                ],
                "concepts": {}
            },
            "环保治水/流域开发": {
                "concept_keywords": [
                    "环保", "污水处理", "水务", "水利",
                    "流域治理", "水治理", "节水", "海绵城市",
                ],
                "concepts": {}
            },
        }
    },
    "摆脱贫困": {
        "keywords": ["摆脱贫困", "弱鸟先飞", "滴水穿石"],
        "directions": {
            "产业扶贫/乡村振兴": {
                "concept_keywords": [
                    "乡村振兴", "产业扶贫", "县域经济",
                    "特色产业集群", "农村电商", "农机",
                    "农业现代化", "智慧农业", "农产品加工",
                ],
                "concepts": {}
            },
            "举国体制攻坚行业": {
                "concept_keywords": [
                    "半导体", "芯片", "国产芯片", "大飞机",
                    "航空发动机", "高端装备", "工业母机",
                    "国产替代", "自主可控",
                ],
                "concepts": {}
            },
            "新型城镇化": {
                "concept_keywords": [
                    "新型城镇化", "县城基建", "保障房",
                    "城市更新", "旧改", "棚改",
                    "装配式建筑", "绿色建筑",
                ],
                "concepts": {}
            },
        }
    },
    "论中国信息技术产业发展": {
        "keywords": ["信息技术", "科技自立", "数字经济"],
        "directions": {
            "半导体攻坚/国产替代": {
                "concept_keywords": [
                    "半导体", "芯片", "国产芯片", "EDA",
                    "光刻机", "刻蚀", "薄膜", "封测",
                    "集成电路", "IC设计", "晶圆", "硅片",
                    "国产替代", "自主可控", "信创",
                    "GPU", "CPU", "FPGA", "MCU",
                    "存储芯片", "功率半导体", "碳化硅", "氮化镓",
                    "第三代半导体",
                ],
                "concepts": {}
            },
            "数字经济/AI算力": {
                "concept_keywords": [
                    "人工智能", "AI", "算力", "智算",
                    "光模块", "CPO", "数据中心", "IDC",
                    "AIGC", "大模型", "ChatGPT", "机器人",
                    "AI芯片", "深度学习", "机器视觉", "自然语言",
                    "数字人", "AI办公", "AI医疗", "AI教育",
                    "数字经济", "数字化转型", "数字中国",
                    "云计算", "大数据", "边缘计算",
                ],
                "concepts": {}
            },
            "工业4.0/智能制造": {
                "concept_keywords": [
                    "工业软件", "智能制造", "工业4.0", "工业互联网",
                    "MES", "ERP", "PLC", "DCS", "SCADA",
                    "数控机床", "机器人", "工业机器人",
                    "机器视觉", "传感器", "物联网",
                    "数字化工厂", "柔性制造",
                ],
                "concepts": {}
            },
            "网络安全/信创": {
                "concept_keywords": [
                    "网络安全", "信创", "数据安全", "信息安全",
                    "密码学", "安全芯片", "国产操作系统",
                    "国产数据库", "国产中间件", "PKI",
                    "等保", "零信任",
                ],
                "concepts": {}
            },
        }
    },
    "中国能源问题研究": {
        "keywords": ["能源", "能源安全", "能源转型"],
        "directions": {
            "能源安全/油气自主": {
                "concept_keywords": [
                    "油气", "石油", "天然气", "页岩气",
                    "页岩油", "油气开采", "油田服务",
                    "管道", "LNG",
                ],
                "concepts": {}
            },
            "能源转型/双碳": {
                "concept_keywords": [
                    "光伏", "风电", "风力发电", "太阳能",
                    "新能源", "储能", "碳化硅", "绿电",
                    "碳中和", "碳达峰", "双碳",
                    "光伏建筑一体化", "BIPV",
                    "分布式能源", "微电网",
                ],
                "concepts": {}
            },
            "新能源车/储能": {
                "concept_keywords": [
                    "新能源车", "锂电池", "动力电池", "电动车",
                    "充电桩", "换电", "电池回收",
                    "钠电池", "氢能", "燃料电池",
                    "储能", "锂电", "锂矿", "锂资源",
                    "钴", "镍", "稀土", "锂电材料",
                ],
                "concepts": {}
            },
            "智能电网/特高压": {
                "concept_keywords": [
                    "特高压", "智能电网", "配电", "输配电",
                    "电网", "变压器", "电力设备", "电力物联网",
                    "虚拟电厂", "微电网", "电力市场化",
                ],
                "concepts": {}
            },
        }
    },
    "论坚持人与自然和谐共生": {
        "keywords": ["人与自然", "绿色发展", "生态"],
        "directions": {
            "生态保护/环保": {
                "concept_keywords": [
                    "环保", "污水处理", "固废处理", "垃圾焚烧",
                    "危废", "土壤修复", "矿山修复",
                    "流域治理", "生态修复", "环境监测",
                    "环卫", "再生资源", "垃圾分类",
                ],
                "concepts": {}
            },
            "碳交易/绿色金融": {
                "concept_keywords": [
                    "碳交易", "CCER", "碳排放", "碳监测",
                    "绿色金融", "ESG", "绿色债券",
                    "碳管理", "碳捕捉", "CCUS",
                ],
                "concepts": {}
            },
            "绿色制造/节能": {
                "concept_keywords": [
                    "节能", "工业节能", "建筑节能", "绿色建筑",
                    "装配式建筑", "保温材料", "节能环保",
                    "清洁生产", "循环经济",
                ],
                "concepts": {}
            },
        }
    },
}


def fetch_all_concept_boards():
    """拉取东方财富所有概念板块（名称+代码）"""
    import efinance as ef
    
    print("📡 拉取概念板块列表...")
    try:
        df = ef.stock.get_realtime_quotes()
        # 尝试获取概念板块列表
        # efinance 可能有不同的 API
    except Exception as e:
        print(f"  efinance基础接口: {e}")
    
    # 方法2：用 efinance 的概念板块接口
    try:
        # 获取所有概念板块
        concept_df = ef.stock.get_concept_board_list()
        print(f"  ✅ 概念板块列表: {len(concept_df)} 个")
        print(f"  列名: {list(concept_df.columns)}")
        print(f"  前5行:\n{concept_df.head()}")
        return concept_df
    except Exception as e:
        print(f"  ❌ get_concept_board_list 失败: {e}")
    
    return None


def fetch_concept_stocks(concept_code, max_retries=3):
    """拉取某个概念板块下的所有股票"""
    import efinance as ef
    
    for attempt in range(max_retries):
        try:
            df = ef.stock.get_concept_board_detail(concept_code)
            return df
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                print(f"  ❌ 概念 {concept_code} 获取失败: {e}")
                return None


def match_concepts_to_directions(concept_df):
    """把概念板块匹配到8本书的投资方向下"""
    
    if concept_df is None:
        print("❌ 概念板块数据为空，无法匹配")
        return BOOK_MAP
    
    # 构建 概念名称 → 概念代码 映射
    name_to_code = {}
    # 尝试不同的列名
    code_col = None
    name_col = None
    
    for col in concept_df.columns:
        col_lower = str(col).lower()
        if '代码' in str(col) or 'code' in col_lower:
            code_col = col
        if '名称' in str(col) or 'name' in col_lower:
            name_col = col
    
    if code_col and name_col:
        for _, row in concept_df.iterrows():
            name_to_code[str(row[name_col])] = str(row[code_col])
        print(f"📋 概念名称→代码映射: {len(name_to_code)} 条")
    else:
        print(f"⚠️ 无法识别列名，列: {list(concept_df.columns)}")
        # 尝试用前两列
        cols = list(concept_df.columns)
        if len(cols) >= 2:
            for _, row in concept_df.iterrows():
                name_to_code[str(row.iloc[1])] = str(row.iloc[0])
            print(f"📋 概念名称→代码映射(猜测列): {len(name_to_code)} 条")
    
    # 对每个投资方向，匹配概念板块
    matched_total = 0
    unmatched_keywords = set()
    
    for book_name, book_data in BOOK_MAP.items():
        for direction_name, direction_data in book_data["directions"].items():
            keywords = direction_data["concept_keywords"]
            matched = {}
            
            for kw in keywords:
                # 模糊匹配：概念名称包含关键词
                found = False
                for concept_name, concept_code in name_to_code.items():
                    if kw in concept_name:
                        matched[concept_name] = concept_code
                        found = True
                
                if not found:
                    unmatched_keywords.add(kw)
            
            direction_data["concepts"] = matched
            matched_total += len(matched)
            if matched:
                print(f"  📖 {book_name} → {direction_name}: 匹配到 {len(matched)} 个概念")
                for cn, cc in list(matched.items())[:5]:
                    print(f"      - {cn} ({cc})")
                if len(matched) > 5:
                    print(f"      ... 还有 {len(matched)-5} 个")
    
    print(f"\n📊 总计匹配: {matched_total} 个概念板块")
    if unmatched_keywords:
        print(f"⚠️ 未匹配的关键词 ({len(unmatched_keywords)}): {', '.join(list(unmatched_keywords)[:20])}")
    
    return BOOK_MAP


def fetch_stocks_for_matched_concepts(book_map, max_concepts=None):
    """拉取每个匹配概念下的股票列表"""
    
    import efinance as ef
    
    total_concepts = 0
    for book_data in book_map.values():
        for dir_data in book_data["directions"].values():
            total_concepts += len(dir_data["concepts"])
    
    print(f"\n📡 开始拉取概念成分股 ({total_concepts} 个概念)...")
    
    processed = 0
    for book_name, book_data in book_map.items():
        for direction_name, direction_data in book_data["directions"].items():
            concepts = direction_data["concepts"]
            stocks_by_concept = {}
            
            for concept_name, concept_code in concepts.items():
                if max_concepts and processed >= max_concepts:
                    break
                
                processed += 1
                print(f"  [{processed}/{total_concepts}] {concept_name} ({concept_code})...", end="", flush=True)
                
                df = fetch_concept_stocks(concept_code)
                if df is not None and len(df) > 0:
                    # 提取股票代码
                    code_col = None
                    for col in df.columns:
                        if '代码' in str(col) or 'code' in str(col).lower():
                            code_col = col
                            break
                    
                    if code_col is None and len(df.columns) >= 1:
                        code_col = df.columns[0]
                    
                    if code_col:
                        stock_codes = [str(c) for c in df[code_col].tolist()]
                        # 统一格式：6位代码
                        stock_codes = [c.zfill(6) for c in stock_codes if len(str(c)) >= 5]
                        stocks_by_concept[concept_name] = {
                            "code": concept_code,
                            "stocks": stock_codes
                        }
                        print(f" {len(stock_codes)} 只")
                    else:
                        print(f" 列名不明: {list(df.columns)}")
                else:
                    print(f" 0 只")
                    stocks_by_concept[concept_name] = {
                        "code": concept_code,
                        "stocks": []
                    }
                
                time.sleep(0.3)  # 限频
            
            direction_data["concept_stocks"] = stocks_by_concept
            
            if max_concepts and processed >= max_concepts:
                break
        if max_concepts and processed >= max_concepts:
            break
    
    return book_map


def build_final_output(book_map):
    """构建最终输出格式"""
    
    output = {
        "meta": {
            "version": "3.0",
            "architecture": "top-down: book → direction → concept → stock",
            "created": time.strftime("%Y-%m-%d %H:%M"),
            "description": "葵学3.0数据库：以8本书为根节点的自上而下映射"
        },
        "books": {}
    }
    
    total_directions = 0
    total_concepts = 0
    total_stocks = set()
    
    for book_name, book_data in book_map.items():
        book_entry = {
            "directions": {}
        }
        
        for dir_name, dir_data in book_data["directions"].items():
            total_directions += 1
            dir_entry = {
                "concepts": {}
            }
            
            # 优先用 concept_stocks（含成分股），否则用 concepts（仅名称+代码）
            if "concept_stocks" in dir_data:
                concepts_data = dir_data["concept_stocks"]
            else:
                # 只有名称和代码，没有股票列表
                concepts_data = {}
                for cn, cc in dir_data.get("concepts", {}).items():
                    concepts_data[cn] = {"code": cc, "stocks": []}
            
            for concept_name, concept_info in concepts_data.items():
                total_concepts += 1
                stocks = concept_info.get("stocks", [])
                total_stocks.update(stocks)
                dir_entry["concepts"][concept_name] = {
                    "code": concept_info["code"],
                    "stock_count": len(stocks),
                    "stocks": stocks
                }
            
            book_entry["directions"][dir_name] = dir_entry
        
        output["books"][book_name] = book_entry
    
    output["meta"]["total_directions"] = total_directions
    output["meta"]["total_concepts"] = total_concepts
    output["meta"]["total_unique_stocks"] = len(total_stocks)
    
    return output


def main():
    print("=" * 60)
    print("葵学3.0 — 自上而下数据库构建器")
    print("架构: book → direction → concept_name → stock_code")
    print("=" * 60)
    
    # Step 1: 拉取概念板块列表
    print("\n📍 Step 1: 拉取概念板块列表")
    concept_df = fetch_all_concept_boards()
    
    # Step 2: 匹配概念到投资方向
    print("\n📍 Step 2: 匹配概念板块到8本书的投资方向")
    book_map = match_concepts_to_directions(concept_df)
    
    # Step 3: 先保存匹配结果（不含股票列表），方便检查
    match_output_path = os.path.join(os.path.dirname(__file__), "kuixue_book_match.json")
    match_output = build_final_output(book_map)
    with open(match_output_path, "w", encoding="utf-8") as f:
        json.dump(match_output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 匹配结果已保存: {match_output_path}")
    print(f"   方向数: {match_output['meta']['total_directions']}")
    print(f"   概念数: {match_output['meta']['total_concepts']}")
    
    # Step 4: 拉取每个概念的成分股
    print("\n📍 Step 3: 拉取概念成分股")
    book_map = fetch_stocks_for_matched_concepts(book_map)
    
    # Step 5: 构建最终输出
    print("\n📍 Step 4: 构建最终输出")
    final_output = build_final_output(book_map)
    
    output_path = os.path.join(os.path.dirname(__file__), "kuixue_book_map.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 最终输出已保存: {output_path}")
    print(f"   📚 书籍: {len(final_output['books'])}")
    print(f"   🧭 投资方向: {final_output['meta']['total_directions']}")
    print(f"   🏷️ 概念板块: {final_output['meta']['total_concepts']}")
    print(f"   📈 覆盖个股: {final_output['meta']['total_unique_stocks']}")


if __name__ == "__main__":
    main()
