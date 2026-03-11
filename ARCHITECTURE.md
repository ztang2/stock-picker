# Stock Picker — Architecture Guide

> 最后更新: 2026-02-28
> 参考: Anthropic financial-services-plugins 架构思路，自主实现

## 概览

自动化美股筛选系统，覆盖 S&P 500 + S&P 400 MidCap（903只股票）。每日扫描、评分、排名，生成买卖信号。

```
Universe (903 tickers)
    ↓
Data Fetch (yfinance + SEC EDGAR)
    ↓
5-Dimension Scoring (Fund/Value/Tech/Risk/Growth)
    ↓
Composite Score + Strategy Weights
    ↓
DCF + Comps + Earnings (Top N deep analysis)
    ↓
Risk Adjustments (MidCap penalty, crash filter, DCF confidence)
    ↓
Smart Money Signals (Analyst + Insider)
    ↓
Entry/Exit Signals + Alerts
    ↓
Dashboard UI + Robin Daily Reports
```

## 核心模块

### Pipeline (`src/pipeline.py`)
**系统入口**。协调整个扫描流程：
1. `get_universe_tickers()` 获取股票列表
2. `detect_market_regime()` 8信号宏观判断（见下）
3. `fetch_stock_data()` 并行获取yfinance数据（带缓存）
4. 5维评分 → `compute_composite()` 加权合成（权重受regime调整）
5. **Sector-capped Top N selection** — 每行业最多4只（`MAX_PER_SECTOR=4`），防止单一行业集中
6. Top N 做 DCF/Comps 深度分析
7. 风险调整（MidCap、crash filter、DCF penalty）
8. Smart money bonus
9. 排名 + 信号生成

> **为什么要sector cap？** 没有forward PE数据时，trailing PE偏低的金融股会占据Top 20的35%+。
> 3/10回测验证：加cap前Tech 8 + Financial 7 = 75%，加cap后8个行业均匀分布。

### 宏观Regime检测 (`src/market_regime.py`)
**8信号系统**判断 Bull/Bear/Sideways：
1. SPY vs 200MA（趋势）
2. SPY vs 50MA（动量）
3. SPY RSI（超买/超卖）
4. VIX（恐慌指数）— ^VIX
5. 10年美债收益率（利率环境）— ^TNX
6. 美元指数DXY（美元强弱）— DX-Y.NYB
7. 油价（通胀/地缘风险）— CL=F
8. FRED经济数据综合（CPI/失业率/GDP/联邦利率/收益率曲线/失业救济）— 上限±3

每个信号独立评分，composite ≥+3 → Bull，≤-3 → Bear，其间 → Sideways。
Bear regime自动调高估值+风险权重，降低成长+技术面权重。

### FRED经济数据 (`src/fred_data.py`)
6个关键指标从美联储FRED API获取（免费，6小时缓存）：
- CPI（通胀）、失业率、GDP增长率、联邦基金利率、收益率曲线（10Y-2Y）、失业救济申请
- 收益率曲线倒挂是最可靠的衰退预测信号
- 经济composite ≥+3 → expansion，≤-3 → contraction

### 风险管理 (`src/risk_manager.py`)
- 止损监控：持仓跌超15%触发警报
- Trailing stop: -10% from peak触发（追踪高水位）
- 仓位限制：单股不超过总portfolio 20%，**单行业不超过35%**
- 油价监控: -15% from 3月peak触发减仓提醒
- P&L追踪：盈亏比、胜率统计
- **性能**: 模块级`_get_sector_cache()`缓存scan_results.json的sector数据（820 tickers），进程内只加载一次
- API: `/risk/summary`, `/risk/stop-losses`, `/risk/positions`, `/risk/trailing-stops`, `/risk/oil`

### 5维评分体系

| 维度 | 模块 | 关键指标 |
|------|------|----------|
| **Fundamentals** | `fundamentals.py` | ROE, profit margin, current ratio, debt/equity |
| **Valuation** | `valuation.py` | P/E, P/B, P/S, PEG, FCF yield |
| **Technicals** | `technicals.py` | RSI, MACD, MA交叉, 价格位置 |
| **Risk** | `risk.py` | Beta, volatility, max drawdown, Sharpe |
| **Growth** | `growth.py` | Revenue growth, earnings growth, margin趋势 |

每维度输出 0-100 分，由策略权重加权合成 composite score。

### 策略 (`src/strategies.py`)

三种策略，不同权重分配：

| 策略 | Fund | Value | Tech | Risk | Growth | 特点 |
|------|------|-------|------|------|--------|------|
| 🛡️ Conservative | 40% | 25% | 8% | 13% | 0% | 低波动，要求分红 |
| ⚖️ Balanced | 26% | 17% | 22% | 8% | 12% | 默认策略，均衡 |
| 🚀 Aggressive | 14% | 8% | 32% | 4% | 30% | 追涨，忽略估值 |

还有 sentiment(5%) 和 sector_relative(10%) 权重。

### 估值模块（Deep Analysis）

#### DCF (`src/dcf_valuation.py`)
- 基于 SEC EDGAR 真实财报数据计算内在价值
- Growth rate = average(revenue growth, earnings growth)
- Terminal growth: 2.5%
- WACC: 动态计算
- **Confidence分级**: HIGH / MEDIUM / LOW
  - 金融/保险行业 → 强制LOW（DCF不适用）
  - IV/Price ratio >3x 或 <0.2x → 强制LOW（结果不可信）
  - LOW confidence → 不给bonus，额外扣1分

#### Comps (`src/comps_analysis.py`)
- 从 yfinance 获取同行业 peers
- 比较 P/E, EV/EBITDA, P/S 倍数
- 输出 comps_score (0-100) 和 verdict

#### Earnings (`src/earnings_analysis.py`)
- Beat/miss历史，beat rate
- Margin趋势（expanding/contracting/stable）
- Quality score
- Signals: consistent_beater, decelerating_growth, margin_compression 等

### 数据源

#### SEC EDGAR (`src/sec_edgar.py`)
- 直接从SEC获取10-K/10-Q原始财报
- `_best_revenue_entries()`: 自动选最新的XBRL concept变体
- OCF fallback: 如果主concept没数据，尝试备选
- 缓存在 `data/sec_cache/`
- 需要User-Agent header

#### yfinance
- 价格、技术指标、基本面比率、peers列表
- 替代了原来的FMP（免费tier被砍）
- 503只S&P 500 + 400只S&P 400 MidCap

### 风险调整（pipeline后处理）

1. **MidCap penalty**: S&P 400 股票 -2分（波动性更高）
2. **Momentum crash filter**: 价格低于MA50超过20% → 信号改WATCH
3. **DCF LOW confidence penalty**: -1分

### 信号系统

| 信号 | 含义 |
|------|------|
| 🟢 STRONG_BUY | Top 10 + 连续3天以上 |
| 🔵 BUY | Top N，技术面向好 |
| ⚪ HOLD | 在持仓但不在Top N |
| 🔴 WAIT | 新进Top N，等确认 |
| ⚪ WATCH | Momentum crash 或 earnings warning |

### ML模型 (`src/ml_model.py`)

6种方法，自动选最优：
1. XGBoost alone (57.4%)
2. LightGBM alone (57.7%)
3. Simple average 50/50 (59.1%)
4. Weighted average (59.1%)
5. Meta-learner (58.6%)
6. **Specialized ensemble** — XGB=classifier, LGB=regressor
   - STRONG BUY: 63.9% accuracy, +4.23% avg excess return

### Early Momentum Score (`src/early_momentum.py`)
预判雷达 — 识别即将突破的股票，弥补pipeline后视镜缺陷。

**5个领先指标**（每个0-2分，总分0-10）：
1. **Analyst estimate revisions** — 目标价upside + 近期升/降级趋势
2. **Insider buying** — 净买入、买入金额>$1M、多人买入
3. **Revenue acceleration** — QoQ收入增速在加快（不只是增长，是增速在提高）
4. **Institutional validation** — 机构持仓比例 + 做空比例（静态快照，非变化量）
5. **Earnings surprise** — 连续beat次数 + 最近surprise幅度

| 分数 | 信号 | 含义 |
|------|------|------|
| ≥8 | 🔥 STRONG_MOMENTUM | 多信号共振，强烈关注 |
| ≥6 | 📈 MOMENTUM | 有明显正向动量 |
| ≥4 | 📊 NEUTRAL | 一般 |
| <4 | WEAK/NO_MOMENTUM | 无特殊信号 |

- `scan_top_momentum(n)`: 扫描pipeline Top 100，并行5线程（ThreadPoolExecutor）
- 缓存: `data/early_momentum_cache.json`（12小时TTL，scan后批量写入避免竞争）
- **注意**: `institutional_validation`是静态数据，真正的机构动向需要13F季度数据

### Smart Money (`src/insider.py`)
- Analyst revisions: upgrades/downgrades, price target, consensus
- Insider trading: buy/sell ratio, net shares
- Composite score bonus: ±2 to ±5（根据策略）

### 卖出信号 (`src/sell_signals.py` + `src/rebalance.py`)
- Tolerance Band: 连续5天跌出Top 20 → 触发卖出评估
- 30天最短持有期
- STRONG BUY替换: 新信号需连续5天确认
- 最多每月1次swap

## API (`src/api.py`)

FastAPI server, 默认 `http://localhost:8000`

| Endpoint | 用途 |
|----------|------|
| `GET /scan` | 运行完整扫描 |
| `GET /results` | 获取缓存的扫描结果 |
| `GET /stock/{ticker}` | 单股详情 |
| `GET /dcf/{ticker}/summary` | DCF估值 |
| `GET /comps/{ticker}` | 可比分析 |
| `GET /earnings/{ticker}/analysis` | 盈利分析 |
| `GET /backtest` | 回测 |
| `GET /accuracy` | 历史准确率 |
| `GET /portfolio` | 投资组合 |
| `GET /alerts` | 警报 |
| `GET /momentum/scan/{n}` | Momentum雷达扫描（必须在/{ticker}前注册） |
| `GET /momentum/{ticker}` | 单股momentum评分 |

## Dashboard (`static/index.html`)

单页应用，7个tab：
- **Scanner**: 903股排名表，信号过滤，sector筛选
- **Portfolio**: 持仓管理
- **Backtest**: 策略回测
- **Alerts**: 信号变化通知
- **Accuracy**: 历史预测准确率
- **Deep Dive**: 单股深度分析（Summary + DCF + Comps + Earnings）
- **🚀 Momentum**: Early Momentum Radar — 扫描Top 100并显示领先指标，点击行跳转Deep Dive
- **FMP Data**: 旧数据源状态（已弃用）

## Cron Schedule (PT, weekdays)

| 时间 | 任务 | Agent |
|------|------|-------|
| 6:30am | Morning briefing + consensus signals | Robin (Sonnet) |
| 9:00am | Midday check (>3% drop才报) | Robin |
| 1:30pm | Post-market portfolio update | Robin |
| Sat 10am | Weekly report + ML retrain | Main (Opus) |
| Monthly 17th 8am | Full optimization | Main (Opus) |

## 数据流

```
yfinance API → stock_data cache (JSON)
SEC EDGAR → data/sec_cache/ (per-ticker JSON)
Pipeline scan → data/scan_results.json
Previous scan → data/prev_scan_results.json (rotated before each new scan)
Daily snapshots → data/daily_snapshots/YYYY-MM-DD.json
ML model → data/ml_model.pkl
Backtest → data/backtest_results.json
```

## 关键配置 (`config.yaml`)

```yaml
default_strategy: balanced
risk_free_rate: 0.045
include_midcap: true
cache_hours: 24
top_n: 20
thresholds:
  min_market_cap: 2.0e9
  min_volume: 500000
```

## 当前性能

- **Win rate**: 67.6% (92/136 picks)
- **Alpha vs SPY**: +1.0%
- **Backtest alpha**: +1.5%/6mo (balanced strategy)
- **Sharpe ratio**: 0.78
- **Universe**: 903 tickers

## Evolution Roadmap

### 近期
1. **Sensitivity分析** — DCF的WACC/growth rate敏感度矩阵
2. **动态peer选择** — 用业务描述匹配comparable

### 中期
3. **3-statement建模** — 完整收入/资产/现金流三表
4. **历史回测验证** — 校准DCF/Comps预测准确度

### 长期 ($25K+)
5. 期权对冲策略
6. 多策略动态组合
7. 专业数据源接入

---

*参考: [Anthropic financial-services-plugins](https://github.com/anthropics/financial-services-plugins) — 借鉴了全市场扫描 + DCF/Comps/Earnings三角验证的架构思路，数据源和实现完全独立。*
