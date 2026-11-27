
def get_top_coins():
    url = BASE + "/api/v3/ticker/24hr"

    response = requests.get(url, timeout=20)
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, list):
        raise RuntimeError(
            f"Binance API error: {data}"
        )

    coins = [
        x for x in data
        if isinstance(x, dict)
        and x.get("symbol", "").endswith("USDT")
        and float(x.get("quoteVolume", 0)) > 10_000_000
        and not any(
            tag in x.get("symbol", "")
            for tag in ["UPUSDT", "DOWNUSDT", "BULL", "BEAR"]
        )
    ]

    coins.sort(
        key=lambda x: float(x["quoteVolume"]),
        reverse=True
    )

    return [x["symbol"] for x in coins[:25]]
