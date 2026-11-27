
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE = "https://api.binance.com"
TIMEOUT = 20

def ema(values, period):
    k = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = value * k + result * (1 - k)
    return result

def analyze(symbol):
    try:
        url = f"{BASE}/api/v3/klines"
        data = requests.get(
            url,
            params={"symbol": symbol, "interval": "1h", "limit": 100},
            timeout=TIMEOUT
        ).json()

        if not isinstance(data, list) or len(data) < 50:
            return None

        closes = [float(row[4]) for row in data]

        fast = ema(closes[-50:], 9)
        slow = ema(closes[-50:], 21)

        changes = [
            closes[i] - closes[i - 1]
            for i in range(len(closes) - 14, len(closes))
        ]
        gains = [max(x, 0) for x in changes]
        losses = [abs(min(x, 0)) for x in changes]

        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14

        if avg_loss == 0:
            rsi = 100
        else:
            rsi = 100 - (100 / (1 + avg_gain / avg_loss))

        macd_values = []
        for i in range(34, len(closes)):
            part = closes[:i + 1]
            macd_values.append(
                ema(part[-26:], 12) - ema(part[-26:], 26)
            )

        macd = macd_values[-1]
        signal = ema(macd_values[-9:], 9)

        price = closes[-1]

        if fast > slow and macd > signal and 50 <= rsi <= 68:
            return f"🟢 BUY | {symbol}\nPrice: {price}\nRSI: {rsi:.1f}"

        if fast < slow and macd < signal and rsi < 48:
            return f"🔴 SELL | {symbol}\nPrice: {price}\nRSI: {rsi:.1f}"

    except Exception:
        return None

    return None

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("ERROR: Telegram settings missing")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={"chat_id": CHAT_ID, "text": message},
        timeout=TIMEOUT
    )

    print("Telegram status:", response.status_code)
    print("Telegram response:", response.text)
    response.raise_for_status()

def main():
    print("Starting Binance USDT scanner...")

    info = requests.get(
        f"{BASE}/api/v3/exchangeInfo",
        timeout=TIMEOUT
    ).json()

    symbols = [
        item["symbol"]
        for item in info["symbols"]
        if item["status"] == "TRADING"
        and item["quoteAsset"] == "USDT"
        and item["isSpotTradingAllowed"]
    ]

    print("USDT pairs found:", len(symbols))

    signals = []

    with ThreadPoolExecutor(max_workers=5) as pool:
        jobs = [pool.submit(analyze, symbol) for symbol in symbols]

        for job in as_completed(jobs):
            result = job.result()
            if result:
                signals.append(result)

    print("Signals found:", len(signals))

    if signals:
        message = "📊 Crypto Scanner Signals\n\n"
        message += "\n\n".join(signals[:25])
        message += "\n\n⚠️ Analytical signals, not guaranteed."
    else:
        message = (
            "📊 Crypto Scanner\n\n"
            "No signals found in this scan."
        )

    send_telegram(message)

if __name__ == "__main__":
    main()
