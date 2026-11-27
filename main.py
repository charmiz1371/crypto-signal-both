
import os
import time
import requests
import pandas as pd

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE = "https://api.binance.com"

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("Telegram settings are missing")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": message
    }, timeout=20)

def get_top_coins():
    url = BASE + "/api/v3/ticker/24hr"
    data = requests.get(url, timeout=20).json()

    coins = [
        x for x in data
        if x["symbol"].endswith("USDT")
        and float(x["quoteVolume"]) > 10_000_000
        and not any(tag in x["symbol"] for tag in
                    ["UPUSDT", "DOWNUSDT", "BULL", "BEAR"])
    ]

    coins.sort(
        key=lambda x: float(x["quoteVolume"]),
        reverse=True
    )
    return [x["symbol"] for x in coins[:25]]

def analyze(symbol):
    url = BASE + "/api/v3/klines"
    data = requests.get(url, params={
        "symbol": symbol,
        "interval": "15m",
        "limit": 100
    }, timeout=20).json()

    df = pd.DataFrame(data, columns=[
        "time", "open", "high", "low", "close",
        "volume", "close_time", "qav", "trades",
        "taker_base", "taker_quote", "ignore"
    ])

    close = df["close"].astype(float)

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1/14, adjust=False
    ).mean()
    avg_loss = loss.ewm(
        alpha=1/14, adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))

    macd = (
        close.ewm(span=12, adjust=False).mean()
        - close.ewm(span=26, adjust=False).mean()
    )
    signal = macd.ewm(span=9, adjust=False).mean()

    # Use only completed candles
    i = -2
    p = -3

    price = close.iloc[i]

    buy = (
        ema9.iloc[p] <= ema21.iloc[p]
        and ema9.iloc[i] > ema21.iloc[i]
        and 50 < rsi.iloc[i] < 68
        and macd.iloc[i] > signal.iloc[i]
    )

    sell = (
        ema9.iloc[p] >= ema21.iloc[p]
        and ema9.iloc[i] < ema21.iloc[i]
        and rsi.iloc[i] < 50
        and macd.iloc[i] < signal.iloc[i]
    )

    if buy or sell:
        direction = "BUY 🟢" if buy else "SELL 🔴"
        message = (
            f"Crypto Signal\n\n"
            f"Coin: {symbol}\n"
            f"Signal: {direction}\n"
            f"Price: {price:.8g} USDT\n"
            f"RSI: {rsi.iloc[i]:.1f}\n"
            f"Timeframe: 15 minutes\n\n"
            f"EMA and MACD confirmation\n"
            f"Please check risk before trading."
        )
        send_telegram(message)
        print(message)

def main():
    coins = get_top_coins()
    print("Scanning", len(coins), "coins")

    for coin in coins:
        try:
            analyze(coin)
            time.sleep(0.3)
        except Exception as error:
            print(coin, error)

if __name__ == "__main__":
    main()
