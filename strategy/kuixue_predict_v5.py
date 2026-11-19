"""
葵学3.0 预测 v5 — 全量版
Step1: 新浪快照5502只初筛 → 500只候选
Step2: 腾讯K线接口精拉3个月历史
Step3: 全因子评分 → Top20看涨 + Bottom20对照组
"""
import requests
import pandas as pd
import numpy as np
import json, sys, io, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ==========================================
# Step1: 新浪快照初筛
# ==========================================
print("=" * 60)
print("Step1: 新浪快照初筛")
print("=" * 60)

# 加载已缓存的新浪数据
try:
    sina_stocks = json.load(open('sina_a_stocks.json', 'r', encoding='utf-8'))
    print(f"缓存: {len(sina_stocks)}只")
except:
    print("无缓存，重新拉取...")
    sina_stocks = []
    page = 1
    while True:
        url = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
        params = {"page": page, "num": 80, "sort": "symbol", "asc": 1, "node": "hs_a"}
        try:
            r = requests.get(url, params=params, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            data = r.json()
            if not data: break
            sina_stocks.extend(data)
            page += 1
            time.sleep(0.15)
        except:
            break
    print(f"拉取: {len(sina_stocks)}只")

# 解析
records = []
for s in sina_stocks:
    try:
        price = float(s.get('trade', 0))
        if price <= 0: continue
        pct = float(s.get('changepercent', 0))
        per = float(s.get('per', 0)) if s.get('per') else 0
        pb = float(s.get('pb', 0)) if s.get('pb') else 0
        mktcap = float(s.get('mktcap', 0)) / 10000 if s.get('mktcap') else 0  # 亿
        turnover = float(s.get('turnoverratio', 0)) if s.get('turnoverratio') else 0
        nmc = float(s.get('nmc', 0)) / 10000 if s.get('nmc') else 0  # 亿
        code = s.get('code', '')
        name = s.get('name', '')
        
        records.append({
            'code': code, 'name': name, 'price': price,
            'pct': pct, 'per': per, 'pb': pb,
            'mktcap': mktcap, 'turnover': turnover, 'nmc': nmc,
        })
    except:
        continue

df = pd.DataFrame(records)
print(f"原始: {len(df)}只")

# 初筛 — 宽松有梯度
df = df[~df['name'].str.contains('ST', na=False)]  # 排除ST
df = df[~df['name'].str.startswith('N')]  # 排除新股
df = df[df['price'] > 3]  # 排除仙股
df = df[df['pct'].abs() < 19]  # 排除涨跌停
df = df[df['mktcap'] > 20]  # 市值>20亿（流动性底线）
print(f"硬过滤后: {len(df)}只")

# 梯度筛选 — 不是一刀切，而是按策略分池
# 池A: 成长动量股（有涨幅、有换手、估值不极端）
pool_a = df[
    (df['turnover'] > 1) &           # 有交易活跃度
    (df['per'] > 5) & (df['per'] < 80) &  # 有盈利但不太贵
    (df['pct'] > -5) &               # 近期没暴跌
    (df['mktcap'] > 30)              # 中大盘
].copy()
pool_a['pool'] = 'A_growth'

# 池B: 价值稳健股（低PE/PB、大市值、温和换手）
pool_b = df[
    (df['per'] > 3) & (df['per'] < 15) &  # 低估值
    (df['pb'] > 0.3) & (df['pb'] < 2) &   # 破净附近
    (df['mktcap'] > 100) &                 # 大盘
    (df['turnover'] > 0.3)                 # 至少有一点活跃
].copy()
pool_b['pool'] = 'B_value'

# 池C: 回调反弹股（近期跌但中期不差）
pool_c = df[
    (df['pct'] < -1) & (df['pct'] > -8) &  # 近期回调
    (df['per'] > 0) & (df['per'] < 60) &    # 有盈利
    (df['turnover'] > 1.5) &                # 放量下跌=可能有承接
    (df['mktcap'] > 30)
].copy()
pool_c['pool'] = 'C_rebound'

# 合并去重
df_pool = pd.concat([pool_a, pool_b, pool_c]).drop_duplicates(subset='code')
print(f"三池合并: {len(df_pool)}只 (A={len(pool_a)}, B={len(pool_b)}, C={len(pool_c)})")

# 如果超过500只，按池优先级截取
if len(df_pool) > 500:
    # 先取A池全部，再补B，再补C
    selected = []
    for pool_name in ['A_growth', 'C_rebound', 'B_value']:
        pool_df = df_pool[df_pool['pool'] == pool_name].head(200)
        selected.append(pool_df)
    df_pool = pd.concat(selected).drop_duplicates(subset='code').head(500)

print(f"最终候选: {len(df_pool)}只")

# ==========================================
# Step2: 腾讯K线接口精拉3个月历史
# ==========================================
print(f"\n{'=' * 60}")
print("Step2: 腾讯K线拉取")
print("=" * 60)

def get_kline_sina(code, days=60):
    """用新浪接口拿单只股票日K线"""
    if code.startswith('6'):
        symbol = f"sh{code}"
    else:
        symbol = f"sz{code}"
    url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {
        "symbol": symbol,
        "scale": 240,  # 日线
        "ma": "no",
        "datalen": days,
    }
    try:
        r = requests.get(url, params=params, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        if not data:
            return None
        rows = []
        for item in data:
            rows.append({
                'date': item['day'],
                'open': float(item['open']),
                'close': float(item['close']),
                'high': float(item['high']),
                'low': float(item['low']),
                'volume': float(item['volume']),
            })
        return rows
    except:
        return None

# 测试一只
test = get_kline_sina('600000', 60)
print(f"测试600000: {len(test) if test else 0}条K线")
if test:
    print(f"  最早: {test[0]['date']} 最新: {test[-1]['date']}")

# 批量拉取
all_kline = {}
fail_count = 0
t0 = time.time()

for i, row in df_pool.iterrows():
    code = row['code']
    kline = get_kline_sina(code, 60)
    if kline and len(kline) >= 20:
        all_kline[code] = kline
    else:
        fail_count += 1
    
    if (len(all_kline) + fail_count) % 50 == 0:
        elapsed = time.time() - t0
        rate = (len(all_kline) + fail_count) / elapsed
        print(f"  {len(all_kline) + fail_count}/{len(df_pool)}: {len(all_kline)} OK, {fail_count} fail, {elapsed:.0f}s")
    
    time.sleep(0.05)  # 限频

elapsed = time.time() - t0
print(f"完成: {len(all_kline)}只成功, {fail_count}只失败, 耗时{elapsed:.0f}s")

if len(all_kline) < 10:
    print("K线数据太少，退出")
    sys.exit(1)

# ==========================================
# Step3: 全因子评分
# ==========================================
print(f"\n{'=' * 60}")
print("Step3: 全因子评分")
print("=" * 60)

# 合并快照+K线数据
results = []

for code, kline in all_kline.items():
    # 快照信息
    snap = df_pool[df_pool['code'] == code]
    if snap.empty:
        continue
    snap = snap.iloc[0]
    
    close_arr = np.array([k['close'] for k in kline])
    volume_arr = np.array([k['volume'] for k in kline])
    high_arr = np.array([k['high'] for k in kline])
    low_arr = np.array([k['low'] for k in kline])
    n = len(close_arr)
    
    if n < 20: continue
    
    # 涨跌幅序列
    pct_arr = np.zeros(n)
    pct_arr[1:] = (close_arr[1:] / close_arr[:-1] - 1) * 100
    
    try:
        f = {
            'code': code,
            'name': snap['name'],
            'pool': snap['pool'],
            'close': close_arr[-1],
            'per': snap['per'],
            'pb': snap['pb'],
            'mktcap': snap['mktcap'],
            'turnover': snap['turnover'],
            # 动量
            'mom_5': (close_arr[-1]/close_arr[-6]-1)*100 if n>5 else 0,
            'mom_10': (close_arr[-1]/close_arr[-11]-1)*100 if n>10 else 0,
            'mom_20': (close_arr[-1]/close_arr[-21]-1)*100 if n>21 else 0,
            'mom_60': (close_arr[-1]/close_arr[0]-1)*100,
            # 均线
            'ma5': np.mean(close_arr[-5:]),
            'ma10': np.mean(close_arr[-10:]),
            'ma20': np.mean(close_arr[-20:]),
            # 量能
            'vol_ratio': np.mean(volume_arr[-5:])/max(np.mean(volume_arr[-20:]),1),
            # 波动
            'volatility': np.std(pct_arr[-20:]),
            # 短期涨跌
            'pct_3d': np.sum(pct_arr[-3:]),
            'pct_1d': pct_arr[-1],
        }
        
        # 均线多头 (0-3)
        f['ma_score'] = sum([
            f['ma5'] > f['ma10'],
            f['ma10'] > f['ma20'],
            close_arr[-1] > f['ma5']
        ])
        
        # 价格位置
        h20 = np.max(close_arr[-20:])
        l20 = np.min(close_arr[-20:])
        f['price_pos'] = (close_arr[-1]-l20)/max(h20-l20, 0.01)
        
        # RSI14
        if n >= 14:
            gains = np.where(pct_arr[-14:] > 0, pct_arr[-14:], 0)
            losses = np.where(pct_arr[-14:] < 0, -pct_arr[-14:], 0)
            avg_g = np.mean(gains)
            avg_l = max(np.mean(losses), 0.01)
            f['rsi14'] = 100 - 100/(1 + avg_g/avg_l)
        else:
            f['rsi14'] = 50
        
        # MACD近似 (12/26 EMA差)
        if n >= 26:
            ema12 = close_arr[0]
            ema26 = close_arr[0]
            for c in close_arr[1:]:
                ema12 = c * 2/13 + ema12 * 11/13
                ema26 = c * 2/27 + ema26 * 25/27
            f['macd_diff'] = ema12 - ema26
            f['macd_signal'] = 1 if ema12 > ema26 else -1
        else:
            f['macd_diff'] = 0
            f['macd_signal'] = 0
        
        # 布林带位置
        ma20 = np.mean(close_arr[-20:])
        std20 = np.std(close_arr[-20:])
        if std20 > 0:
            f['boll_pos'] = (close_arr[-1] - ma20) / (2 * std20)  # -1到+1之间
        else:
            f['boll_pos'] = 0
        
        results.append(f)
    except:
        continue

df_f = pd.DataFrame(results)
print(f"全因子: {len(df_f)}只")

# ==========================================
# 评分模型
# ==========================================
print("评分...")

df_f['score'] = 0.0

# === 趋势类 (权重40%) ===
# 均线多头 (0-3 → 0-12分)
df_f['score'] += df_f['ma_score'] * 4

# MACD金叉
df_f.loc[df_f['macd_signal'] == 1, 'score'] += 6
df_f.loc[df_f['macd_signal'] == -1, 'score'] -= 3

# 动量5日（涨但不过热）
df_f.loc[(df_f['mom_5'] > 0) & (df_f['mom_5'] < 8), 'score'] += df_f.loc[(df_f['mom_5'] > 0) & (df_f['mom_5'] < 8), 'mom_5'] * 1.0
df_f.loc[(df_f['mom_5'] >= 8) & (df_f['mom_5'] < 20), 'score'] += 6
df_f.loc[df_f['mom_5'] >= 20, 'score'] -= 3  # 过热
df_f.loc[(df_f['mom_5'] < 0) & (df_f['mom_5'] > -5), 'score'] += df_f['mom_5'] * 0.2

# 动量20日
df_f.loc[df_f['mom_20'] > 0, 'score'] += np.minimum(df_f.loc[df_f['mom_20'] > 0, 'mom_20'] * 0.3, 8)
df_f.loc[(df_f['mom_20'] < 0) & (df_f['mom_20'] > -10), 'score'] += df_f['mom_20'] * 0.1

# === 量能类 (权重25%) ===
# 量比温和放大
df_f.loc[(df_f['vol_ratio'] > 1.2) & (df_f['vol_ratio'] < 2.0), 'score'] += 8
df_f.loc[(df_f['vol_ratio'] >= 2.0) & (df_f['vol_ratio'] < 3.0), 'score'] += 5
df_f.loc[(df_f['vol_ratio'] >= 3.0) & (df_f['vol_ratio'] < 5.0), 'score'] += 1
df_f.loc[df_f['vol_ratio'] >= 5.0, 'score'] -= 4  # 异常放量

# === 技术形态 (权重20%) ===
# RSI
df_f.loc[(df_f['rsi14'] > 25) & (df_f['rsi14'] < 45), 'score'] += 8   # 超卖回升
df_f.loc[(df_f['rsi14'] >= 45) & (df_f['rsi14'] < 65), 'score'] += 5   # 正常偏强
df_f.loc[(df_f['rsi14'] >= 65) & (df_f['rsi14'] < 75), 'score'] += 2   # 偏强
df_f.loc[df_f['rsi14'] >= 80, 'score'] -= 5  # 超买

# 回调买点：中期涨+短期跌
df_f.loc[(df_f['mom_20'] > 5) & (df_f['pct_3d'] < -2) & (df_f['pct_3d'] > -10), 'score'] += 10

# 布林带低位
df_f.loc[df_f['boll_pos'] < -1, 'score'] += 5   # 低位反弹
df_f.loc[df_f['boll_pos'] > 1.5, 'score'] -= 3  # 高位风险

# 价格位置
df_f.loc[df_f['price_pos'] < 0.25, 'score'] += 4
df_f.loc[df_f['price_pos'] > 0.9, 'score'] -= 3

# === 估值安全垫 (权重15%) ===
# PE
df_f.loc[(df_f['per'] > 5) & (df_f['per'] < 20), 'score'] += 4   # 低估
df_f.loc[(df_f['per'] >= 20) & (df_f['per'] < 40), 'score'] += 2  # 合理
df_f.loc[(df_f['per'] >= 40) & (df_f['per'] < 60), 'score'] += 0  # 偏贵不加分
df_f.loc[df_f['per'] <= 0, 'score'] -= 3  # 亏损
df_f.loc[df_f['per'] >= 80, 'score'] -= 2  # 太贵

# PB
df_f.loc[(df_f['pb'] > 0.5) & (df_f['pb'] < 2), 'score'] += 3
df_f.loc[df_f['pb'] <= 0, 'score'] -= 2

# === 波动率调节 ===
df_f.loc[(df_f['volatility'] > 0.8) & (df_f['volatility'] < 2.5), 'score'] += 2
df_f.loc[df_f['volatility'] > 4, 'score'] -= 2

df_f = df_f.sort_values('score', ascending=False)

# ==========================================
# 输出 Top20 + Bottom20 对照组
# ==========================================
print(f"\n{'=' * 70}")
print("葵学3.0 预测 — 2026-04-27(周一)")
print("=" * 70)
print(f"数据: 新浪快照{len(df_pool)}只初筛 → 腾讯K线{len(df_f)}只全因子评分")
print(f"模型: 趋势40% + 量能25% + 技术形态20% + 估值15%")
print(f"因子: 动量5/10/20日+均线3重+MACD+量比+RSI14+布林+回调买点+PE/PB")

print(f"\n{'─' * 70}")
print("看涨 Top20（预测周一上涨）")
print('─' * 70)
top20 = df_f.head(20)
for rank, (i, r) in enumerate(top20.iterrows(), 1):
    pool_tag = {'A_growth':'成','B_value':'值','C_rebound':'反'}.get(r['pool'],'?')
    print(f"  {rank:>2}. {r['code']} {r['name']:<6}[{pool_tag}] "
          f"收{r['close']:.2f} 5日{r['mom_5']:+.1f}% 20日{r['mom_20']:+.1f}% "
          f"量比{r['vol_ratio']:.2f} RSI{r['rsi14']:.0f} "
          f"MACD{'金' if r['macd_signal']==1 else '死'} "
          f"PE{r['per']:.0f} "
          f"总分{r['score']:.1f}")

print(f"\n{'─' * 70}")
print("看跌 Bottom20（对照组 — 预测周一弱势）")
print('─' * 70)
bot20 = df_f.tail(20).iloc[::-1]  # 从最低分开始
for rank, (i, r) in enumerate(bot20.iterrows(), 1):
    pool_tag = {'A_growth':'成','B_value':'值','C_rebound':'反'}.get(r['pool'],'?')
    print(f"  {rank:>2}. {r['code']} {r['name']:<6}[{pool_tag}] "
          f"收{r['close']:.2f} 5日{r['mom_5']:+.1f}% 20日{r['mom_20']:+.1f}% "
          f"量比{r['vol_ratio']:.2f} RSI{r['rsi14']:.0f} "
          f"MACD{'金' if r['macd_signal']==1 else '死'} "
          f"PE{r['per']:.0f} "
          f"总分{r['score']:.1f}")

# 保存
out_top = top20[['code','name','pool','close','mom_5','mom_20','vol_ratio','rsi14','macd_signal','per','pb','score']].copy()
out_bot = bot20[['code','name','pool','close','mom_5','mom_20','vol_ratio','rsi14','macd_signal','per','pb','score']].copy()
out_top['group'] = 'top20'
out_bot['group'] = 'bottom20'
pd.concat([out_top, out_bot]).to_csv('kuixue_prediction_20260427.csv', index=False, encoding='utf-8-sig')
print(f"\n已保存: kuixue_prediction_20260427.csv")
print(f"\n周一验证: 比较Top20平均涨幅 vs Bottom20平均涨幅 vs 大盘中位数")
print(f"区分度指标: Top均值 - Bottom均值 > 1% 才算有信号")
