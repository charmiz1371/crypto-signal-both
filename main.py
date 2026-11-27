
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE = "https://data-api.binance.vision"
TIMEOUT = 25

session = requests.Session()

def get_json(url, params=None):
    response = session.get(url, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and "code" in data:
        raise RuntimeError(f"Binance API error: {data}")
    return data

def ema(values, period):
    k = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = value * k + result * (1 - k)
    return result

def analyze(symbol):
    try:
        data = get_json(
            f"{BASE}/api/v3/klines",
            {"symbol": symbol, "interval": "1h", "limit": 100}
        )

        if not isinstance(data, list) or len(data) < 50:
            return None

        # فقط کندل‌های بسته‌شده
        closes = [float(row[4]) for row in data[:-1]]

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
        rsi = 100 if avg_loss == 0 else (
            100 - 100 / (1 + avg_gain / avg_loss)
        )

        macd_values = []
        for i in range(34, len(closes)):
            part = closes[:i + 1]
            macd_values.append(
                ema(part[-12:], 12) - ema(part[-26:], 26)
            )

        macd = macd_values[-1]
        signal = ema(macd_values[-9:], 9)
        price = closes[-1]

        if fast > slow and macd > signal and 50 <= rsi <= 68:
            return f"🟢 BUY | {symbol}\nPrice: {price}\nRSI: {rsi:.1f}"

        if fast < slow and macd < signal and rsi < 48:
            return f"🔴 SELL | {symbol}\nPrice: {price}\nRSI: {rsi:.1f}"

    except Exception as error:
        print(f"Scan error {symbol}: {error}")

    return None

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Telegram settings are missing")

    response = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": message},
        timeout=TIMEOUT
    )

    print("Telegram status:", response.status_code)
    print("Telegram response:", response.text)
    response.raise_for_status()

    if not response.json().get("ok"):
        raise RuntimeError("Telegram did not accept the message")

def main():
    print("Starting Binance USDT scanner...")

    info = get_json(f"{BASE}/api/v3/exchangeInfo")

    if not isinstance(info, dict) or "symbols" not in info:
        raise RuntimeError(f"Unexpected exchangeInfo response: {info}")

    symbols = [
        item["symbol"]
        for item in info["symbols"]
        if item.get("status") == "TRADING"
        and item.get("quoteAsset") == "USDT"
        and item.get("isSpotTradingAllowed") is True
    ]

    print("USDT spot pairs found:", len(symbols))

    signals = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        jobs = [pool.submit(analyze, symbol) for symbol in symbols]
        for job in as_completed(jobs):
            result = job.result()
            if result:
                signals.append(result)

    print("Signals found:", len(signals))

    if signals:
        message = "📊 Binance USDT Signals\n\n" + "\n\n".join(signals[:25])
    else:
        message = "📊 Crypto Scanner\n\nNo signals found in this scan."

    message += "\n\n⚠️ Analytical signals only. Not guaranteed."
    send_telegram(message)
    print("Scanner finished successfully.")

if __name__ == "__main__":
    main()
