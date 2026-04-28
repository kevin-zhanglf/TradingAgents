"""Chemical plastics trade activity tools (stub implementations).

Real implementation: Connects to trading platform APIs (化纤平台, 找塑料网 etc.)
for quote/deal activity data distinguishing 报价 vs 成交.
"""
import json
import random
import hashlib
from datetime import datetime, timedelta
from langchain_core.tools import tool


def _seed_from_params(*args) -> int:
    key = "_".join(str(a) for a in args)
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


@tool
def get_quote_activity(grade: str, region: str, start_date: str, end_date: str) -> str:
    """Retrieve quote activity statistics (报价活跃度) for a specific ABS grade.

    Real implementation: Queries trading platform APIs for daily quote count,
    bid-ask spread, and quote revision frequency.

    Args:
        grade: Product grade e.g. "ABS-3001MF2"
        region: Market region e.g. "华北"
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD

    Returns:
        JSON with daily quote activity: count, avg_bid, avg_ask, spread, revision_count
    """
    seed = _seed_from_params(grade, region, start_date, "quote")
    rng = random.Random(seed)

    base_ask = {"ABS-3001MF2": 13550.0, "ABS-0215A": 13650.0}.get(grade, 13500.0)
    base_bid = base_ask - 100.0

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    data = []
    ask = base_ask
    bid = base_bid
    for i in range((end - start).days + 1):
        date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        ask = max(ask + rng.gauss(0, 50), 10000.0)
        spread = rng.uniform(80, 200)
        bid = ask - spread
        data.append({
            "date": date,
            "quote_count": rng.randint(5, 25),
            "avg_ask_price": round(ask, 2),
            "avg_bid_price": round(bid, 2),
            "avg_spread": round(spread, 2),
            "quote_revision_count": rng.randint(1, 8),
            "active_sellers": rng.randint(3, 12),
        })

    return json.dumps({
        "grade": grade,
        "region": region,
        "price_type": "quote",
        "unit": "元/吨",
        "source": "化纤网(stub)",
        "data": data,
    }, ensure_ascii=False)


@tool
def get_deal_activity(grade: str, region: str, start_date: str, end_date: str) -> str:
    """Retrieve deal activity statistics (成交活跃度) for a specific ABS grade.

    Real implementation: Queries 找塑料网 or platform transaction records for
    actual completed deals, volume, and prices.

    Args:
        grade: Product grade e.g. "ABS-3001MF2"
        region: Market region e.g. "华北"
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD

    Returns:
        JSON with daily deal activity: count, volume_tons, avg_deal_price, quote_to_deal_ratio
    """
    seed = _seed_from_params(grade, region, start_date, "deal")
    rng = random.Random(seed)

    base_deal = {"ABS-3001MF2": 13400.0, "ABS-0215A": 13500.0}.get(grade, 13350.0)

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    data = []
    deal_price = base_deal
    for i in range((end - start).days + 1):
        date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        deal_price = max(deal_price + rng.gauss(0, 40), 10000.0)
        deal_count = rng.randint(2, 15)
        quote_count = deal_count + rng.randint(3, 15)
        data.append({
            "date": date,
            "deal_count": deal_count,
            "deal_volume_tons": round(rng.uniform(50, 500), 0),
            "avg_deal_price": round(deal_price, 2),
            "quote_to_deal_ratio": round(quote_count / max(deal_count, 1), 2),
            "price_vs_quote_discount": round(rng.uniform(-150, -50), 2),
        })

    return json.dumps({
        "grade": grade,
        "region": region,
        "price_type": "deal",
        "unit": "元/吨",
        "source": "找塑料网(stub)",
        "data": data,
    }, ensure_ascii=False)
