"""Chemical plastics news and policy tools (stub implementations).

Real implementation: Connects to 卓创资讯 news API, wind资讯, 政策数据库 for chemical industry news.
"""
import json
import random
import hashlib
from datetime import datetime, timedelta
from langchain_core.tools import tool


def _seed_from_params(*args) -> int:
    key = "_".join(str(a) for a in args)
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


_CHEM_NEWS_TEMPLATES = [
    {"title": "华北ABS市场成交好转，部分牌号货源趋紧", "sentiment": "bullish", "category": "supply"},
    {"title": "韩国LG化学ABS装置计划检修，预计影响出口5万吨", "sentiment": "bullish", "category": "supply_disruption"},
    {"title": "家电旺季备货启动，ABS下游需求明显回升", "sentiment": "bullish", "category": "demand"},
    {"title": "ABS社会库存持续累积，市场压力有所加大", "sentiment": "bearish", "category": "inventory"},
    {"title": "丙烯腈价格大幅下跌拖累ABS成本端走弱", "sentiment": "bearish", "category": "upstream"},
    {"title": "国产ABS产能新增压力持续，市场竞争加剧", "sentiment": "bearish", "category": "supply"},
    {"title": "华北ABS报价小幅调整，市场观望情绪浓厚", "sentiment": "neutral", "category": "market"},
    {"title": "进口ABS通关量上升，华北港口库存偏高", "sentiment": "bearish", "category": "import"},
    {"title": "吉化ABS停产检修，华北供应缺口预计约2万吨", "sentiment": "bullish", "category": "supply_disruption"},
    {"title": "苯乙烯价格走强，对ABS成本形成支撑", "sentiment": "bullish", "category": "upstream"},
]

_POLICY_NEWS_TEMPLATES = [
    {"title": "国家发改委发布化工行业绿色发展指导意见", "impact": "neutral", "category": "regulation"},
    {"title": "商务部对韩国ABS启动反倾销调查", "impact": "bullish", "category": "trade_policy"},
    {"title": "碳排放配额收紧，石化企业运营成本上升", "impact": "bearish", "category": "environmental"},
    {"title": "家电下乡政策补贴延续，利好ABS下游需求", "impact": "bullish", "category": "subsidy"},
    {"title": "新能源汽车产业链政策扶持，工程塑料需求预期改善", "impact": "bullish", "category": "industry_policy"},
    {"title": "化工园区安全整治持续推进，部分装置受限", "impact": "bullish", "category": "safety_regulation"},
]


@tool
def search_chem_news(query: str, start_date: str, end_date: str, region: str = "华北") -> str:
    """Search chemical industry news related to ABS plastics market.

    Real implementation: Full-text search on 卓创资讯/隆众资讯 news database,
    filtered by product/region tags.

    Args:
        query: Search keywords e.g. "ABS供需 华北"
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD
        region: Target region e.g. "华北"

    Returns:
        JSON with news items including title, date, summary, sentiment, source
    """
    seed = _seed_from_params(query, start_date, region)
    rng = random.Random(seed)

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    n_days = (end - start).days + 1

    n_articles = min(max(rng.randint(3, 8), 1), 10)
    articles = []
    for i in range(n_articles):
        template = rng.choice(_CHEM_NEWS_TEMPLATES)
        days_offset = rng.randint(0, n_days - 1)
        news_date = (start + timedelta(days=days_offset)).strftime("%Y-%m-%d")
        articles.append({
            "title": template["title"],
            "date": news_date,
            "summary": f"【{region}市场快讯】{template['title']}。市场参与者普遍关注该动态对近期{region}ABS价格走势的影响。",
            "sentiment": template["sentiment"],
            "category": template["category"],
            "source": rng.choice(["卓创资讯", "隆众资讯", "百川盈孚", "生意社"]),
            "relevance_score": round(rng.uniform(0.6, 1.0), 2),
        })

    articles.sort(key=lambda x: x["date"], reverse=True)

    return json.dumps({
        "query": query,
        "region": region,
        "period": f"{start_date} to {end_date}",
        "total": len(articles),
        "articles": articles,
    }, ensure_ascii=False)


@tool
def search_policy_news(query: str, start_date: str, end_date: str) -> str:
    """Search government policy and regulatory news affecting chemical plastics industry.

    Real implementation: Queries 国家政策数据库, wind资讯 government document database.

    Args:
        query: Search keywords e.g. "ABS反倾销 化工政策"
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD

    Returns:
        JSON with policy items including title, date, issuer, impact assessment
    """
    seed = _seed_from_params(query, start_date)
    rng = random.Random(seed)

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    n_days = (end - start).days + 1

    n_articles = rng.randint(1, 4)
    articles = []
    issuers = ["国家发改委", "商务部", "工信部", "生态环境部", "国务院"]
    for _ in range(n_articles):
        template = rng.choice(_POLICY_NEWS_TEMPLATES)
        days_offset = rng.randint(0, n_days - 1)
        news_date = (start + timedelta(days=days_offset)).strftime("%Y-%m-%d")
        articles.append({
            "title": template["title"],
            "date": news_date,
            "issuer": rng.choice(issuers),
            "impact": template["impact"],
            "category": template["category"],
            "summary": f"政策要点：{template['title']}。预计对ABS市场{template['impact']}影响。",
            "source": "wind政策数据库(stub)",
        })

    articles.sort(key=lambda x: x["date"], reverse=True)

    return json.dumps({
        "query": query,
        "period": f"{start_date} to {end_date}",
        "total": len(articles),
        "articles": articles,
    }, ensure_ascii=False)
