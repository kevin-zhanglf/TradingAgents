"""Chemical plastics fundamental data tools (stub implementations).

Real implementation: Connects to 卓创资讯, 百川盈孚, 隆众资讯 for inventory, operating rates, trade data.
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
def get_inventory(product: str, region: str, start_date: str, end_date: str) -> str:
    """Retrieve product inventory level time series for a region.

    Real implementation: Queries 卓创资讯 or 百川盈孚 for warehouse inventory data,
    typically reported weekly.

    Args:
        product: Product name e.g. "ABS", "styrene"
        region: Market region e.g. "华北", "全国"
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD

    Returns:
        JSON with: product, region, unit, freq, data (list of {date, inventory_tons, days_of_stock, yoy_pct})
    """
    seed = _seed_from_params(product, region, start_date)
    rng = random.Random(seed)
    base_inventory = {"ABS": 85000.0, "styrene": 120000.0, "butadiene": 45000.0}.get(product.upper(), 70000.0)

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    data = []
    current = start
    current_inv = base_inventory * rng.uniform(0.8, 1.2)
    while current <= end:
        current_inv = max(current_inv * (1 + rng.gauss(0, 0.03)), base_inventory * 0.3)
        data.append({
            "date": current.strftime("%Y-%m-%d"),
            "inventory_tons": round(current_inv, 0),
            "days_of_stock": round(current_inv / (base_inventory / 30), 1),
            "yoy_pct": round(rng.gauss(5.0, 10.0), 1),
        })
        current += timedelta(days=7)

    return json.dumps({
        "product": product,
        "region": region,
        "unit": "吨",
        "freq": "W",
        "source": "百川盈孚(stub)",
        "data": data,
    }, ensure_ascii=False)


@tool
def get_operating_rate(product: str, region: str, start_date: str, end_date: str) -> str:
    """Retrieve production operating rate for ABS or upstream facilities.

    Real implementation: Queries 卓创资讯 for weekly production survey data from major plants.

    Args:
        product: Product name e.g. "ABS", "styrene"
        region: Market region or "全国"
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD

    Returns:
        JSON with operating rate data, capacity info
    """
    seed = _seed_from_params(product, region, start_date)
    rng = random.Random(seed)
    base_rate = {"ABS": 75.0, "styrene": 80.0, "acrylonitrile": 70.0}.get(product.upper(), 72.0)

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    data = []
    current = start
    rate = base_rate + rng.gauss(0, 5)
    while current <= end:
        rate = max(min(rate + rng.gauss(0, 3), 98.0), 30.0)
        data.append({
            "date": current.strftime("%Y-%m-%d"),
            "operating_rate_pct": round(rate, 1),
            "capacity_utilization_pct": round(rate * 0.95, 1),
        })
        current += timedelta(days=7)

    return json.dumps({
        "product": product,
        "region": region,
        "unit": "%",
        "freq": "W",
        "source": "卓创资讯(stub)",
        "data": data,
    }, ensure_ascii=False)


@tool
def get_import_export(product: str, trade_type: str, region: str, start_date: str, end_date: str) -> str:
    """Retrieve import/export volume data for chemical products.

    Real implementation: Queries 中国海关 customs data (monthly) or 卓创资讯 estimates.

    Args:
        product: Product name e.g. "ABS"
        trade_type: "import" or "export"
        region: Country/region e.g. "中国", "韩国"
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD

    Returns:
        JSON with monthly import/export volume and value data
    """
    seed = _seed_from_params(product, trade_type, region, start_date)
    rng = random.Random(seed)
    base_vol = {"ABS_import": 150000.0, "ABS_export": 12000.0}.get(f"{product.upper()}_{trade_type}", 80000.0)

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    data = []
    current = start.replace(day=1)
    vol = base_vol * rng.uniform(0.8, 1.2)
    while current <= end:
        vol = max(vol * (1 + rng.gauss(0, 0.08)), base_vol * 0.2)
        data.append({
            "date": current.strftime("%Y-%m"),
            "volume_tons": round(vol, 0),
            "value_10k_usd": round(vol * 0.0014 * rng.uniform(0.95, 1.05), 1),
            "yoy_pct": round(rng.gauss(3.0, 15.0), 1),
        })
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return json.dumps({
        "product": product,
        "trade_type": trade_type,
        "region": region,
        "unit": "吨",
        "freq": "M",
        "source": "中国海关(stub)",
        "data": data,
    }, ensure_ascii=False)
