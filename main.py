def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("ERROR: Telegram settings are missing")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        response = requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": message
        }, timeout=20)

        print("Telegram status:", response.status_code)
        print("Telegram response:", response.text)

    except Exception as error:
        print("Telegram error:", error)
