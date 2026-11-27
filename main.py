
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://apiv2.nobitex.ir"
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TIMEOUT = 25

S = requests.Session()
S.headers.update({"User-Agent": "NobitexSignalScanner/2.0"})

def api(path, params=None):
    r = S.get(BASE + path, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def ema(values, period):
    k = 2 / (period + 1)
    result = values[0]
    for x in values[1:]:
        result = x * k + result * (1 - k)
    return result

def rsi(values, period=14):
    changes = [values[i] - values[i-1]
               for i in range(1, len(values))]
    gains = [max(x, 0) for x in changes[-period:]]
    losses = [max(-x, 0) for x in changes[-period:]]
    ag = sum(gains) / period
    al = sum(losses) / period
    if al == 0:
        return 100
    return 100 - 100 / (1 + ag / al)

def macd(values):
    line = []
    for i in range(26, len(values)):
        part = values[:i+1]
        line.append(ema(part[-12:], 12) - ema(part[-26:], 26))
    if len(line) < 10:
        return 0, 0
    return line[-1], ema(line[-9:], 9)

def atr(highs, lows, closes, period=14):
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        ))
    return sum(trs[-period:]) / period

def candles(symbol, resolution):
    end = int(time.time())
    start = end - 180 * int(resolution) * 60
    data = api("/market/udf/history", {
        "symbol": symbol,
        "resolution": resolution,
        "from": start,
        "to": end
    })

    if data.get("s") != "ok":
        return None

    keys = ["o", "h", "l", "c", "v"]
    if any(k not in data for k in keys):
        return None

    result = {}
    for key in keys:
        result[key] = [float(x) for x in data[key][:-1]]

    if len(result["c"]) < 60:
        return None
    return result

def evaluate(symbol, quote_volume):
    try:
        h1 = candles(symbol, "60")
        h4 = candles(symbol, "240")
        if not h1 or not h4:
            return None

        c = h1["c"]
        h = h1["h"]
        l = h1["l"]
        v = h1["v"]

        c4 = h4["c"]

        e9 = ema(c[-50:], 9)
        e21 = ema(c[-50:], 21)
        e50 = ema(c[-60:], 50)

        e9_4 = ema(c4[-50:], 9)
        e21_4 = ema(c4[-50:], 21)

        current_rsi = rsi(c)
        m, ms = macd(c)

        avg_volume = sum(v[-21:-1]) / 20
        current_volume = v[-1]

        score = 0
        reasons = []

        if c[-1] > e21 and e9 > e21:
            score += 2
            reasons.append("روند صعودی یک‌ساعته")

        if e21 > e50:
            score += 1
            reasons.append("قیمت بالای EMA50")

        if e9_4 > e21_4 and c4[-1] > e21_4:
            score += 2
            reasons.append("تأیید روند چهارساعته")

        if m > ms:
            score += 1
            reasons.append("MACD صعودی")

        if 52 <= current_rsi <= 67:
            score += 1
            reasons.append("RSI مناسب")

        if avg_volume > 0 and current_volume >= avg_volume * 1.2:
            score += 1
            reasons.append("افزایش حجم معاملات")

        if score < 7:
            return None

        price = c[-1]
        volatility = atr(h, l, c)

        if volatility <= 0:
            return None

        stop = price - 1.5 * volatility
        risk = price - stop
        target1 = price + risk
        target2 = price + 2 * risk

        if stop <= 0:
            return None

        return {
            "symbol": symbol,
            "price": price,
            "stop": stop,
            "target1": target1,
            "target2": target2,
            "rsi": current_rsi,
            "score": score,
            "volume": quote_volume,
            "reasons": reasons
        }

    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Telegram secrets missing")

    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=TIMEOUT
    )
    print("Telegram status:", r.status_code)
    print("Telegram response:", r.text)
    r.raise_for_status()

    if not r.json().get("ok"):
        raise RuntimeError("Telegram rejected message")

def main():
    print("Starting Nobitex quality scanner")

    data = api("/market/stats")
    if data.get("status") != "ok":
        raise RuntimeError(f"Stats error: {data}")

    markets = []
    for key, value in data.get("stats", {}).items():
        if value.get("isClosed", True):
            continue

        parts = key.lower().split("-")
        if len(parts) != 2:
            continue

        base, quote = parts

        if quote == "rls":
            suffix = "IRT"
        elif quote == "usdt":
            suffix = "USDT"
        else:
            continue

        try:
            volume = float(value.get("volumeDst", 0))
        except (TypeError, ValueError):
            continue

        if volume <= 0:
            continue

        symbol = base.upper() + suffix
        markets.append((symbol, volume))

    # اولویت با 60 بازار پرحجم‌تر
    markets.sort(key=lambda x: x[1], reverse=True)
    markets = markets[:60]

    print("Markets selected:", len(markets))

    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [
            pool.submit(evaluate, symbol, volume)
            for symbol, volume in markets
        ]
        for job in as_completed(jobs):
            result = job.result()
            if result:
                results.append(result)

    results.sort(
        key=lambda x: (x["score"], x["volume"]),
        reverse=True
    )

    print("Qualified BUY signals:", len(results))

    if results:
        messages = []
        for item in results[:5]:
            messages.append(
                f"🟢 BUY CANDIDATE | {item['symbol']}\n"
                f"قیمت بررسی: {item['price']:g}\n"
                f"حد ضرر: {item['stop']:g}\n"
                f"هدف اول: {item['target1']:g}\n"
                f"هدف دوم: {item['target2']:g}\n"
                f"RSI: {item['rsi']:.1f}\n"
                f"امتیاز: {item['score']}/8\n"
                f"دلایل: {', '.join(item['reasons'])}"
            )

        message = "📊 فرصت‌های خرید نوبیتکس\n\n"
        message += "\n\n".join(messages)
    else:
        message = (
            "📊 اسکن نوبیتکس انجام شد.\n\n"
            "در این بررسی هیچ فرصت خریدی "
            "با شرایط تعیین‌شده پیدا نشد.\n"
            "فعلاً صبر می‌کنیم."
        )

    message += (
        "\n\n⚠️ سیگنال تحلیلی است، نه تضمین سود. "
        "قبل از سفارش، قیمت و حد ضرر را بررسی کن."
    )

    send_telegram(message)
    print("Scanner finished successfully")

if __name__ == "__main__":
    main()
