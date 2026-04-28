# 化塑材料牌号价格预测智能体

> 基于多智能体 LLM 协作框架（TradingAgents）的化工塑料现货价格预测系统，  
> 以 ABS（丙烯腈-丁二烯-苯乙烯）树脂为首要分析品种，面向中国化塑现货市场。

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [智能体角色详解](#3-智能体角色详解)
4. [产业链图谱](#4-产业链图谱)
5. [情景叠加引擎](#5-情景叠加引擎)
6. [快速开始](#6-快速开始)
7. [配置说明](#7-配置说明)
8. [数据接口说明](#8-数据接口说明)
9. [输出格式](#9-输出格式)
10. [Neo4j 产业链图库](#10-neo4j-产业链图库)
11. [扩展与定制](#11-扩展与定制)

---

## 1. 项目概述

化塑价格预测智能体是 TradingAgents 框架在大宗化工品现货市场的垂直延伸。  
系统通过四个专业分析师智能体并行采集、分析市场信号，再经由统计模型和情景叠加引擎，  
生成**未来 30 天 P10/P50/P90 三分位价格区间预测**。

### 核心能力

| 能力 | 说明 |
|------|------|
| 多维分析 | 上游成本传导、库存与开工率、资讯与政策、下游需求热度四个维度同步分析 |
| 区间预测 | 输出悲观/中性/乐观三分位（P10/P50/P90）日度价格序列 |
| 情景注入 | 支持交易员主观情景（偏多/偏空/中性）叠加到基础统计预测 |
| 产业链感知 | 内置 ABS 产业链图谱（原油→石脑油→单体→ABS→下游），支持持久化到 Neo4j |
| 牌号级预测 | 可单独预测指定牌号（如 ABS-3001MF2、ABS-0215A）的成交价或报价 |

---

## 2. 系统架构

### 整体流程

```
  用户输入（牌号 / 地区 / 价格类型 / 基准日期 / 情景文本）
                       │
                 ChemForecastGraph
                       │
    ┌──────────────────┼──────────────────┐
    │                  │                  │
 产业链价格        供需基本面         资讯政策
  分析师              分析师             分析师
    │                  │                  │
    └──────────────────┼──────────────────┘
                       │            需求热度分析师
                       │                  │
                       └──────────────────┘
                                │
                       模型智能体（统计基线 P10/P50/P90）
                                │
                       情景智能体（LLM 提炼结构化情景参数）
                                │
                       预测合成器（情景叠加 + 报告叙述）
                                │
                      最终预测输出（JSON / Markdown）
```

### LangGraph 节点拓扑

```
START
  │
  ▼
Chain Price Analyst ──(tool call?)──► tools_chain_price ──► (循环)
  │ (完成)
  ▼
Msg Clear Chain Price
  │
  ▼
Supply Demand Analyst ──(tool call?)──► tools_supply_demand ──► (循环)
  │ (完成)
  ▼
Msg Clear Supply Demand
  │
  ▼
News Policy Analyst ──(tool call?)──► tools_news_policy ──► (循环)
  │ (完成)
  ▼
Msg Clear News Policy
  │
  ▼
Demand Heat Analyst ──(tool call?)──► tools_demand_heat ──► (循环)
  │ (完成)
  ▼
Msg Clear Demand Heat
  │
  ▼
Model Agent  （纯计算，不调用 LLM 工具）
  │
  ▼
Scenario Agent  （LLM 综合报告 → ScenarioSpec JSON）
  │
  ▼
Forecast Synthesizer  （OverlayEngine + 叙述摘要）
  │
  ▼
END
```

每个分析师节点均配备**工具调用循环**：当 LLM 决定调用外部数据工具时，路由跳转至对应 ToolNode 执行，返回结果后重新进入分析师节点，直到产出完整分析报告再进入下一阶段。

---

## 3. 智能体角色详解

### 3.1 产业链价格分析师（Chain Price Analyst）

**职责**：分析目标牌号现货价格走势及上游单体成本传导。

**使用工具**

| 工具 | 功能 |
|------|------|
| `get_chem_price_series` | 获取指定牌号、地区、价格类型（成交/报价）的历史日度价格序列 |
| `get_upstream_price_series` | 获取苯乙烯、丁二烯、丙烯腈等上游单体历史价格 |

**分析内容**

- ABS 近 30 日价格趋势、波动率、最高/最低/均价/最新价
- 三大单体加权成本（苯乙烯 55%、丁二烯 25%、丙烯腈 20%）
- 成本-价格价差（加工差）趋势，判断当前利润空间
- 初步价格方向判断（偏多/中性/偏空）

---

### 3.2 供需基本面分析师（Supply Demand Analyst）

**职责**：分析 ABS 市场库存、装置开工率和进出口数据，给出供需平衡信号。

**使用工具**

| 工具 | 功能 |
|------|------|
| `get_inventory` | 获取 ABS 社会库存量（吨）及库存天数，周频 |
| `get_operating_rate` | 获取 ABS 装置开工率（%），周频 |
| `get_import_export` | 获取 ABS 进出口量（吨），月频 |

**信号规则**

| 情形 | 信号 |
|------|------|
| 库存低（<45天）+ 开工率低 + 进口减少 | 供需偏紧，价格利多 |
| 库存高（>90天）+ 开工率高 + 进口增加 | 供需偏松，价格利空 |
| 混合信号 | 中性 |

---

### 3.3 资讯政策分析师（News Policy Analyst）

**职责**：扫描 ABS 行业新闻与政策动态，识别供应扰动事件和政策利多/利空。

**使用工具**

| 工具 | 功能 |
|------|------|
| `search_chem_news` | 搜索化工行业新闻（卓创资讯/隆众资讯风格） |
| `search_policy_news` | 搜索贸易与监管政策（发改委/商务部/工信部） |

**识别要点**

- **供应扰动**：装置停产/检修、物流中断、韩国/台湾进口异动
- **需求信号**：家电旺季备货、汽车产销数据、新能源政策
- **贸易政策**：ABS 反倾销调查、进口配额调整
- **环保监管**：化工园区整治、碳排放收紧

---

### 3.4 需求热度分析师（Demand Heat Analyst）

**职责**：通过报价/成交活跃度数据，量化下游买家的实时采购意愿。

**使用工具**

| 工具 | 功能 |
|------|------|
| `get_quote_activity` | 获取日度报价笔数、买卖价差、报价修改频率 |
| `get_deal_activity` | 获取日度成交笔数、成交量、报价转成交率、折扣幅度 |

**热度评级**

| 评级 | 信号组合 |
|------|---------|
| 强（Strong）| 成交量↑ + 转化率↑ + 折扣收窄 + 报价密集 |
| 弱（Weak）  | 成交量↓ + 转化率↓ + 折扣扩大 + 报价稀疏 |
| 中性（Normal）| 混合信号 |

---

### 3.5 模型智能体（Model Agent）

**职责**：纯计算节点，不调用 LLM 工具，基于历史价格统计生成基础预测区间。

**算法**

1. 获取过去 90 天历史成交/报价数据
2. 取最近 30 个交易日的均值（μ）和标准差（σ）
3. 估算近 7 日相对前 7 日的日均漂移（drift），并限制在 ±0.5%/日
4. 构建 30 日 P50 预测序列：`P50(d) = μ + drift × d`
5. P10/P90 区间：`P50 ± 1.28σ`（80% 预测区间）

**输出**：`BaseForecast`（含 30 日 P10/P50/P90 序列 + 置信说明）

---

### 3.6 情景智能体（Scenario Agent）

**职责**：综合四份分析报告及可选的交易员主观情景，用 LLM 提炼结构化情景参数。

**输出结构**

```python
class ScenarioSpec(BaseModel):
    trader_bias: Literal["bullish", "neutral", "bearish"]  # 综合方向偏向
    trader_rationale: str             # 偏向判断依据（中文，≤200字）
    inventory_survey_text: str        # 库存情况摘要
    inventory_signal: Literal["high", "normal", "low"]     # 库存信号
    supply_disruption: bool           # 是否存在供应扰动事件
    demand_heat: Literal["strong", "normal", "weak"]       # 下游需求热度
    max_p50_shift_pct: float          # P50 调整幅度上限（默认 ±5%）
```

---

### 3.7 预测合成器（Forecast Synthesizer）

**职责**：将 `BaseForecast` 与 `ScenarioSpec` 合并，通过 `OverlayEngine` 生成最终预测，并撰写中文叙述摘要。

**输出**：`FinalForecast`（含基础预测、情景假设、调整说明、最终 30 日价格序列）

---

## 4. 产业链图谱

系统内置 ABS 产业链定义文件（`tradingagents/chain_graph/abs_chain.yaml`），覆盖从原料到终端的完整链条：

```
原油 / 石脑油 / 煤炭 / 天然气
       │
       ▼
   苯乙烯（55%）  丁二烯（25%）  丙烯腈（20%）
       │              │              │
       └──────────────┴──────────────┘
                      │
                   ABS 树脂
                      │
          ┌───────────┼───────────┐
          │           │           │
      ABS-3001MF2  ABS-0215A  其他牌号
          │
    ┌─────┼─────┬──────┐
    │     │     │      │
  家电  汽车  电子  包装
          │
     替代关系：PS / SAN / PP
```

### 节点类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `feedstock` | 基础原料 | 原油、石脑油、煤炭 |
| `monomer` | 化工单体 | 苯乙烯、丁二烯、丙烯腈 |
| `polymer` | 聚合物 | ABS 树脂、PS、SAN、PP |
| `grade` | 具体牌号 | ABS-3001MF2（吉化）、ABS-0215A（台化） |
| `downstream` | 下游行业 | 家电、汽车配件、电子电器、包装 |
| `region` | 区域市场 | 华北、华东、华南 |

### 边关系类型

| 关系类型 | 含义 |
|----------|------|
| `UPSTREAM_COST` | 上游成本传导（含弹性系数、价格传导滞后天数） |
| `SUPPLY_LINK` | 聚合物→牌号供应关联 |
| `DEMAND_LINK` | 牌号→下游行业需求关联 |
| `SUBSTITUTE` | 替代品关系（含价格弹性、切换条件） |
| `REGIONAL_ARBITRAGE` | 跨区套利价差关系 |

---

## 5. 情景叠加引擎

`OverlayEngine`（`tradingagents/chem_overlay.py`）以**确定性规则**将情景信号叠加到 P50 基线，并在不确定性高时扩宽 P10/P90 区间。

### 调整规则

| 情景信号 | P50 调整幅度 |
|----------|-------------|
| `trader_bias = bullish` | +1.5% |
| `trader_bias = bearish` | −1.5% |
| `inventory_signal = low`（偏紧） | +1.5% |
| `inventory_signal = high`（偏松） | −1.5% |
| `supply_disruption = True` | +2.0% |
| `demand_heat = strong` | +1.0% |
| `demand_heat = weak` | −1.0% |
| **综合上限** | ±`max_p50_shift_pct`（默认 ±5%） |

### 区间扩宽规则

当以下任一条件满足时，P10/P90 区间扩宽为原来的 **1.3 倍**：

- `supply_disruption = True`
- `|P50 综合调整幅度| > 2%`

### 调整示例

```
基础 P50 均值：13,500 元/吨
情景：bullish (+1.5%) + 供应扰动 (+2.0%) + demand_heat=strong (+1.0%)
→ 原始调整：+4.5%
→ 触发 ±5% 上限后实际调整：+4.5%
→ 最终 P50 均值：~14,108 元/吨
→ P10/P90 区间扩宽至 1.3 倍（供应扰动触发）
```

---

## 6. 快速开始

### 6.1 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

### 6.2 配置 API Key

将 `.env.example` 复制为 `.env`，填写所使用的 LLM 服务密钥：

```bash
cp .env.example .env
```

```env
# .env 示例（按实际使用的 LLM 服务填写其中一个）
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
ANTHROPIC_API_KEY=sk-ant-...
DASHSCOPE_API_KEY=sk-...   # 阿里云百炼（Qwen）
ZHIPU_API_KEY=...           # 智谱 GLM
```

### 6.3 运行预测

```bash
# 默认运行：ABS-3001MF2，华北，成交价，今日日期
python chem_main.py

# 自定义牌号与地区
python chem_main.py \
  --grade ABS-3001MF2 \
  --region 华北 \
  --price-type deal \
  --asof-date 2025-03-01

# 注入交易员情景
python chem_main.py \
  --grade ABS-3001MF2 \
  --region 华北 \
  --asof-date 2025-03-01 \
  --scenario "近期吉化停产检修，库存偏低，家电旺季备货启动，预计价格偏多"

# 仅启用部分分析师（加快速度）
python chem_main.py --analysts chain_price,news_policy

# 保存 JSON 结果
python chem_main.py --output-json forecast_output.json

# 开启调试模式（逐节点打印消息）
python chem_main.py --debug
```

### 6.4 Python API 调用

```python
from tradingagents.graph.chem_graph import ChemForecastGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["quick_think_llm"] = "gpt-4o-mini"
config["deep_think_llm"] = "gpt-4o"

graph = ChemForecastGraph(
    selected_analysts=["chain_price", "supply_demand", "news_policy", "demand_heat"],
    debug=False,
    config=config,
)

final_state, final_forecast = graph.propagate(
    grade="ABS-3001MF2",
    region="华北",
    price_type="deal",
    asof_date="2025-03-01",
    scenario_input="库存偏低，家电旺季备货，预计价格偏多",
)

# 访问结构化预测
for point in final_forecast.forecast[:5]:
    print(f"{point.date}: P10={point.p10:.0f} P50={point.p50:.0f} P90={point.p90:.0f}")

# 渲染 Markdown 报告
from tradingagents.chem_schemas import render_final_forecast_md
print(render_final_forecast_md(final_forecast))
```

---

## 7. 配置说明

主配置在 `tradingagents/default_config.py`，所有参数均可通过环境变量或在代码中覆盖。

### LLM 相关

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `llm_provider` | LLM 服务商 | `"openai"` |
| `quick_think_llm` | 四个分析师 + 模型智能体使用的快速模型 | `"gpt-5.4-mini"` |
| `deep_think_llm` | 情景智能体 + 预测合成器使用的深度推理模型 | `"gpt-5.4"` |
| `backend_url` | 自定义 API 端点（兼容 OpenAI 格式的代理） | `None` |

支持的 `llm_provider` 值：`"openai"`、`"anthropic"`、`"google"`、`"deepseek"`、`"dashscope"`、`"zhipu"`、`"openrouter"`、`"xai"`

### Neo4j 图库

| 参数 / 环境变量 | 说明 | 默认值 |
|----------------|------|--------|
| `NEO4J_URI` | Neo4j 连接地址 | `bolt://localhost:7687` |
| `NEO4J_USER` | 用户名 | `neo4j` |
| `NEO4J_PASSWORD` | 密码 | `""` |
| `NEO4J_DATABASE` | 目标数据库 | `neo4j` |

> 未配置 Neo4j 时，产业链查询工具将自动降级使用内置 stub 数据，不影响预测主流程。

### 其他参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `max_recur_limit` | LangGraph 最大递归深度 | `100` |
| `checkpoint_enabled` | 是否启用 LangGraph 检查点（支持断点续跑） | `False` |

---

## 8. 数据接口说明

系统当前附带 **Stub（模拟）实现**，产生确定性随机数据用于开发测试。  
生产部署时需将对应函数替换为真实数据源对接代码。

### 价格数据（`chem_price_tools.py`）

| 函数 | 真实数据源 | 说明 |
|------|------------|------|
| `get_chem_price_series` | 卓创资讯（SCI）、隆众资讯 | 日度现货成交价/报价 |
| `get_upstream_price_series` | 卓创资讯、隆众资讯 | 苯乙烯/丁二烯/丙烯腈等单体价格 |

### 基本面数据（`chem_fundamental_tools.py`）

| 函数 | 真实数据源 | 说明 |
|------|------------|------|
| `get_inventory` | 百川盈孚、卓创资讯 | ABS 社会库存（周频） |
| `get_operating_rate` | 卓创资讯 | ABS 装置开工率（周频） |
| `get_import_export` | 中国海关总署 | ABS 进出口量（月频） |

### 资讯数据（`chem_news_tools.py`）

| 函数 | 真实数据源 | 说明 |
|------|------------|------|
| `search_chem_news` | 卓创资讯、隆众资讯、百川盈孚、生意社 | 化工行业新闻全文检索 |
| `search_policy_news` | Wind 政策数据库、国家政策文件库 | 监管政策文件检索 |

### 成交活跃度（`chem_trade_tools.py`）

| 函数 | 真实数据源 | 说明 |
|------|------------|------|
| `get_quote_activity` | 化纤网、找塑料网 | 日度报价笔数、买卖价差 |
| `get_deal_activity` | 找塑料网、塑料交易平台 | 日度成交笔数、量、转化率 |

---

## 9. 输出格式

### FinalForecast（结构化 JSON）

```python
class PriceForecastPoint(BaseModel):
    date: str    # 预测日期，格式 YYYY-MM-DD
    p10: float   # 悲观价格（元/吨）
    p50: float   # 中性价格（元/吨）
    p90: float   # 乐观价格（元/吨）

class FinalForecast(BaseModel):
    base_forecast: BaseForecast           # 统计基线预测
    scenario_spec: Optional[ScenarioSpec] # 情景假设参数
    overlay_explain: Optional[OverlayExplain]  # 调整过程说明
    forecast: List[PriceForecastPoint]    # 最终 30 日价格区间序列
```

### Markdown 报告示例

```markdown
# ABS-3001MF2 华北 价格预测报告
**预测基准日:** 2025-03-01  |  **价格类型:** deal  |  **预测期:** 30天

## 情景假设
- 交易员偏向: bullish
- 库存信号: low
- 供应扰动: 有
- 需求热度: strong
- 交易员判断: 吉化检修叠加家电备货旺季，供需双向利多

## 情景叠加说明
- 方向信号触发: 是
- 基础P50均值: 13,450 元/吨
- 最终P50均值: 13,987 元/吨
- P50调整幅度: +4.00%
- 置信区间扩宽: 是

## 价格预测区间

| 日期       | P10 (悲观) | P50 (中性) | P90 (乐观) |
|------------|-----------|-----------|-----------|
| 2025-03-02 | 13,210    | 13,987    | 14,764    |
| 2025-03-03 | 13,198    | 13,975    | 14,752    |
| ...        | ...       | ...       | ...       |

## 关键驱动因素
- 上游单体（苯乙烯/丁二烯/丙烯腈）成本传导
- 库存水平与开工率变化
- 行业资讯与政策动态
- 下游需求热度（成交活跃度）
```

---

## 10. Neo4j 产业链图库

系统通过 `ChainGraphNeo4jWriter` 将 YAML 定义的产业链数据持久化到 Neo4j 图数据库，  
供 LLM 智能体在推理时查询上下游关系和替代品关系。

### 写入图库

```python
from tradingagents.chain_graph import load_graph, ChainGraphNeo4jWriter
import os

# 加载 YAML 产业链定义
graph = load_graph("tradingagents/chain_graph/abs_chain.yaml")

# 写入 Neo4j（MERGE 操作，幂等，多牌号共享上游节点不重复）
with ChainGraphNeo4jWriter(
    uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    user=os.getenv("NEO4J_USER", "neo4j"),
    password=os.getenv("NEO4J_PASSWORD", ""),
) as writer:
    writer.write_graph(graph, clear=False)
```

### 查询图库（LangChain 工具）

```python
from tradingagents.agents.utils.chem_chain_neo4j_tools import (
    query_upstream_chain,
    query_substitutes,
    query_downstream_sectors,
)

# 查询 ABS-3001MF2 的完整上游成本链
upstream = query_upstream_chain.invoke({"grade_id": "abs_3001mf2"})

# 查询替代品关系（PS、SAN、PP）
subs = query_substitutes.invoke({"grade_id": "abs_3001mf2"})

# 查询下游行业
downstream = query_downstream_sectors.invoke({"grade_id": "abs_3001mf2"})
```

> **注意**：未配置 `NEO4J_URI` 和 `NEO4J_PASSWORD` 环境变量时，工具自动返回内置 stub 数据，不影响预测流程正常运行。

### 去重机制

`ChainGraphNeo4jWriter` 使用 `MERGE`（而非 `CREATE`）操作，以 `node.id` 为唯一键。  
多个 ABS 牌号（如 ABS-3001MF2 和 ABS-0215A）共享的上游节点（苯乙烯、丁二烯等）  
在图数据库中**仅存储一份**，通过关系指向各自的牌号节点，构成真实的树形产业链结构。

---

## 11. 扩展与定制

### 增加新分析师

1. 在 `tradingagents/agents/chem_analysts/` 新建分析师文件
2. 在 `ChemForecastGraph._setup_chem_graph()` 中注册节点和条件边
3. 在 `ChemConditionalLogic` 中添加对应路由方法
4. 在 `_create_chem_tool_nodes()` 中添加工具节点

### 替换为真实数据源

每个工具函数（`get_chem_price_series`、`get_inventory` 等）均有完整的参数说明和返回格式注释。  
只需将函数体替换为对卓创资讯、百川盈孚、隆众资讯等 API 的真实调用即可，无需修改智能体逻辑。

### 扩展品种

当前 YAML 和分析师 Prompt 以 ABS 为主。  
扩展到 PP、PE、PVC 等其他化塑品种时，需：

1. 在 `abs_chain.yaml`（或新建 YAML）中添加对应品种的产业链节点
2. 调整各分析师 `system_message` 中的品种名称和原料配比
3. 在 `get_chem_price_series` 的 `base_prices` 字典中补充品种基础价格

### 调整情景叠加参数

在 `tradingagents/chem_overlay.py` 中，可直接修改以下类属性自定义调整幅度：

```python
class OverlayEngine:
    INTERVAL_WIDEN_FACTOR: float = 1.3       # 区间扩宽倍数（默认 1.3 倍）
    INTERVAL_WIDEN_THRESHOLD_PCT: float = 2.0  # 触发扩宽的 |P50 调整| 阈值
```

各信号的百分比调整量在 `apply()` 方法内的 `shift_pct +=` 语句中直接修改。

---

## 许可证

本项目遵循 Apache 2.0 开源许可证，详见根目录 `LICENSE` 文件。
