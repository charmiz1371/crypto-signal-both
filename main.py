
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://apiv2.nobitex.ir"
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TIMEOUT = 20

S = requests.Session()

def get_json(path, params=None):
    r = S.get(BASE + path, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"Nobitex API error: {data}")
    return data

def ema(values, period):
    k = 2 / (period + 1)
    result = values[0]
    for x in values[1:]:
        result = x * k + result * (1 - k)
    return result

def analyze(symbol):
    try:
        import time
        end = int(time.time())
        start = end - 100 * 3600

        data = get_json(
            "/market/udf/history",
            {
                "symbol": symbol,
                "resolution": "60",
                "from": start,
                "to": end
            }
        )

        if data.get("s") != "ok" or len(data.get("c", [])) < 50:
            return None

        # آخرین کندل ممکن است هنوز بسته نشده باشد
        closes = [float(x) for x in data["c"][:-1]]

        if len(closes) < 35:
            return None

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

        # نمونه سیگنال خرید
        if fast > slow and macd > signal and 50 <= rsi <= 65:
            stop = price * 0.98
            target1 = price * 1.03
            target2 = price * 1.05

            return (
                f"🟢 BUY | {symbol}\n"
                f"Price: {price:g}\n"
                f"RSI: {rsi:.1f}\n"
                f"Stop: {stop:g}\n"
                f"Target 1: {target1:g}\n"
                f"Target 2: {target2:g}"
            )

        # سیگنال نزولی؛ هشدار بررسی فروش دارایی موجود
        if fast < slow and macd < signal and rsi < 45:
            return (
                f"🔴 SELL WARNING | {symbol}\n"
                f"Price: {price:g}\n"
                f"RSI: {rsi:.1f}"
            )

    except Exception as e:
        print(f"Error {symbol}: {e}")

    return None

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Telegram secrets missing")

    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": message},
        timeout=TIMEOUT
    )

    print("Telegram status:", r.status_code)
    print("Telegram response:", r.text)
    r.raise_for_status()

    if not r.json().get("ok"):
        raise RuntimeError("Telegram rejected message")

def main():
    print("Starting Nobitex scanner...")

    stats = get_json("/market/stats")["stats"]

    symbols = []
    for key, value in stats.items():
        symbol = key.upper().replace("-", "")
        if (
            symbol.endswith("IRT") or symbol.endswith("USDT")
        ) and not value.get("isClosed", True):
            symbols.append(symbol)

    symbols = sorted(set(symbols))
    print("Active Nobitex markets:", len(symbols))

    signals = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(analyze, symbol) for symbol in symbols]

        for job in as_completed(jobs):
            result = job.result()
            if result:
                signals.append(result)

    print("Signals found:", len(signals))

    if signals:
        message = "📊 NOBITEX SIGNALS\n\n"
        message += "\n\n".join(signals[:20])
    else:
        message = (
            "📊 NOBITEX SCANNER\n\n"
            "No signals found in this scan."
        )

    message += "\n\n⚠️ Analytical signals only. Not guaranteed."
    send_telegram(message)
    print("Scanner completed.")

if __name__ == "__main__":
    main()
