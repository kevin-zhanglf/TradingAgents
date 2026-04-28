"""Chemical plastics price data tools (stub implementations).

Real implementation would connect to 卓创资讯 (SCI), 隆众资讯, or Bloomberg APIs.
"""
import json
import random
import hashlib
from datetime import datetime, timedelta
from langchain_core.tools import tool


def _seed_from_params(*args) -> int:
    """Generate deterministic seed from parameters."""
    key = "_".join(str(a) for a in args)
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


def _gen_price_series(base_price: float, n_days: int, seed: int, volatility: float = 0.015) -> list:
    """Generate a realistic mock daily price series using a random walk."""
    rng = random.Random(seed)
    prices = [base_price]
    for _ in range(n_days - 1):
        change = rng.gauss(0, volatility) * prices[-1]
        prices.append(round(max(prices[-1] + change, base_price * 0.5), 2))
    return prices


@tool
def get_chem_price_series(grade: str, region: str, price_type: str, start_date: str, end_date: str) -> str:
    """Retrieve daily chemical product price series for a specific grade and region.

    Real implementation: Queries 卓创资讯 (SCI) or 隆众资讯 API for historical spot prices.
    Returns daily quote or deal prices for the specified grade.

    Args:
        grade: Product grade code, e.g. "ABS-3001MF2"
        region: Market region in Chinese, e.g. "华北"
        price_type: "quote" (报价) or "deal" (成交价)
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD

    Returns:
        JSON string with keys: grade, region, price_type, unit, data (list of {date, price})
    """
    seed = _seed_from_params(grade, region, price_type, start_date)
    base_prices = {
        "ABS-3001MF2": 13500.0,
        "ABS-0215A": 13600.0,
        "ABS": 13400.0,
        "PS": 10500.0,
        "SAN": 12800.0,
        "PP": 8000.0,
    }
    base = base_prices.get(grade.upper().replace(" ", "-"), 13000.0)
    if price_type == "quote":
        base *= 1.008  # quotes slightly above deals

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    n_days = (end - start).days + 1
    prices = _gen_price_series(base, n_days, seed)

    data = []
    for i, price in enumerate(prices):
        date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        data.append({"date": date, "price": price})

    return json.dumps({
        "grade": grade,
        "region": region,
        "price_type": price_type,
        "unit": "元/吨",
        "source": "卓创资讯(stub)",
        "data": data,
    }, ensure_ascii=False)


@tool
def get_upstream_price_series(product: str, region: str, start_date: str, end_date: str) -> str:
    """Retrieve upstream raw material price series (styrene, butadiene, acrylonitrile, etc.).

    Real implementation: Queries 卓创资讯 / 隆众 for monomer/feedstock daily spot prices.

    Args:
        product: Product name e.g. "styrene" (苯乙烯), "butadiene" (丁二烯), "acrylonitrile" (丙烯腈)
        region: Market region e.g. "华北", "华东"
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD

    Returns:
        JSON string with keys: product, region, unit, data (list of {date, price})
    """
    seed = _seed_from_params(product, region, start_date)
    base_prices = {
        "styrene": 9800.0,
        "苯乙烯": 9800.0,
        "butadiene": 11200.0,
        "丁二烯": 11200.0,
        "acrylonitrile": 10500.0,
        "丙烯腈": 10500.0,
        "benzene": 7200.0,
        "苯": 7200.0,
        "naphtha": 6500.0,
        "石脑油": 6500.0,
        "crude_oil": 4800.0,
        "原油": 4800.0,
    }
    base = base_prices.get(product.lower(), 9000.0)

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    n_days = (end - start).days + 1
    prices = _gen_price_series(base, n_days, seed, volatility=0.02)

    data = []
    for i, price in enumerate(prices):
        date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        data.append({"date": date, "price": price})

    return json.dumps({
        "product": product,
        "region": region,
        "unit": "元/吨",
        "source": "卓创资讯(stub)",
        "data": data,
    }, ensure_ascii=False)
