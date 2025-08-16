import os
import time
import json
import re
import sys
from datetime import datetime
import pytz
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --------------------------
# Config
# --------------------------
TEHRAN_TZ = pytz.timezone("Asia/Tehran")
MAX_RETRIES = 5
RETRY_DELAY = 10  # seconds

ID_MAP = {
    "ons": "l-ons",
    "dollar": "l-price_dollar_rl",
    "sekee": "l-sekee",
    "gold_18": "l-geram18",
    "tether": "l-crypto-tether-irr",   # ✅ اصلاح شد
    "oil_brent": "l-oil_brent",        # ✅ نفت برنت
    "bitcoin": "l-crypto-bitcoin",     # ✅ بیت‌کوین
}
FA_TITLES = {
    "ons": "⚖️ انس",
    "dollar": "💵 دلار",
    "gold_18": "🥇 طلا ۱۸ عیار",
    "sekee": "🏅 سکه امامی",
    "tether": "🔗 تتر",
    "oil_brent": "🛢 نفت برنت",
    "bitcoin": "₿ بیت‌کوین",
}

TITLE_EMOJIS = {
    "global": "📈",
    "gold_coin": "💰",
}

# --------------------------
# Utils
# --------------------------
def get_credentials():
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

    print(f"🔍 Debug: TELEGRAM_TOKEN length = {len(TOKEN) if TOKEN else 0}")
    print(f"🔍 Debug: TELEGRAM_CHAT_ID = {CHAT_ID if CHAT_ID else 'None'}")

    if not TOKEN or not CHAT_ID:
        raise ValueError("❌ Telegram credentials not set in environment")

    return TOKEN, CHAT_ID


def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("window-size=1920x1080")

    chrome_options.binary_location = "/usr/bin/chromium-browser"

    service = Service(executable_path="/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=chrome_options)

# --------------------------
# Scraping Functions
# --------------------------
def get_prices_selenium():
    driver = get_driver()
    try:
        driver.get("https://www.tgju.org/")
        wait = WebDriverWait(driver, 10)

        data = {}
        all_keys = ID_MAP.copy()  # دیگه تتر رو اضافه نمی‌کنیم

        for key, elem_id in all_keys.items():
            try:
                elem = wait.until(EC.presence_of_element_located((By.ID, elem_id)))
                price_text = elem.find_element(By.CLASS_NAME, "info-price").text.strip()
                change_text = elem.find_element(By.CLASS_NAME, "info-change").text.strip()

                price_clean = price_text.replace(",", "").replace("$", "")
                try:
                    price_val = float(price_clean)
                except Exception:
                    price_val = None

                m = re.search(r"\(([-\d\.]+)%\)", change_text)
                percent_val = float(m.group(1)) if m else 0.0

                cls = elem.get_attribute("class")
                is_positive = "high" in cls
                is_negative = "low" in cls

                change_val = percent_val if is_positive else -percent_val if is_negative else 0.0

                data[key] = {"price": price_val, "change": change_val}
            except Exception as e:
                print(f"❌ Error reading {key}: {e}")
                data[key] = {"price": None, "change": 0.0}

        # Get gold funds data
        driver.get("https://www.tgju.org/gold-chart")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.data-table.market-table tbody tr")))

        funds = {}
        rows = driver.find_elements(By.CSS_SELECTOR, "table.data-table.market-table tbody tr")
        for row in rows:
            try:
                name = row.find_element(By.TAG_NAME, "th").text.strip()
                price_text = row.find_elements(By.TAG_NAME, "td")[0].text.strip()
                price_clean = price_text.replace(",", "")
                try:
                    price_val = int(float(price_clean))
                except Exception:
                    price_val = None
                funds[name] = {"price": price_val}
            except Exception as e:
                print(f"❌ Error reading funds: {e}")
                continue

        data["funds"] = funds
        return data
    finally:
        driver.quit()

# --------------------------
# Price formatting with rounding
# --------------------------
def format_price_rounded(price):
    if price is None:
        return "—"
    try:
        rounded = round(price)
        return f"{rounded:,}"
    except Exception:
        return "—"

# --------------------------
# Report Generation
# --------------------------
def build_report_message(data):
    lines = []

    # Global FX
    #lines.append(f"📈 Global FX")
    global_rows = [
        ("ons", True),
        ("dollar", False),
        ("tether", False),
    ]
    for key, is_dollar in global_rows:
        price = data.get(key, {}).get("price")
        change = data.get(key, {}).get("change")
        price_str = format_price_rounded(price)
        if change is None:
            change_str = "0.00%"
            emoji = "⚪️"
        else:
            emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪️"
            if change < 0:
                change_str = f"({abs(change):.2f}%)"
            else:
                change_str = f"{change:.2f}%"
        lines.append(f"{FA_TITLES.get(key)}: {price_str}   {change_str} {emoji}")
    lines.append("")

    # Gold & Coins
    #lines.append(f"🪙 Gold & Coins ")
    for key in ["gold_18", "sekee"]:
        price = data.get(key, {}).get("price")
        change = data.get(key, {}).get("change")
        price_str = format_price_rounded(price)
        if change is None:
            change_str = "0.00%"
            emoji = "⚪️"
        else:
            emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪️"
            if change < 0:
                change_str = f"({abs(change):.2f}%)"
            else:
                change_str = f"{change:.2f}%"
        lines.append(f"{FA_TITLES.get(key)}: {price_str}   {change_str} {emoji}")
    lines.append("")

    # Gold Funds
   # lines.append(f"📦 Gold Funds ")
    funds = data.get("funds", {})
    for fund_name in ["صندوق طلای زر", "صندوق طلای عیار", "صندوق طلای لوتوس"]:
        f = funds.get(fund_name, {"price": None})
        price_str = format_price_rounded(f.get("price"))
        lines.append(f"💳 {fund_name}: {price_str}")
    lines.append("")

    # Intrinsic & Bubbles
    #lines.append(f"💹 Intrinsic & Bubbles")
    factor = 4.24927
    ons_price = data.get("ons", {}).get("price")
    dollar_price = data.get("dollar", {}).get("price")
    sekee_price = data.get("sekee", {}).get("price")
    gold_18_price = data.get("gold_18", {}).get("price")

    if ons_price and dollar_price and sekee_price:
        zati_sekee = int((ons_price * dollar_price) / factor)
        habb = ((sekee_price - zati_sekee) / zati_sekee) * 100 if zati_sekee != 0 else None
        lines.append(f"📏 قیمت ذاتی سکه امامی: {zati_sekee:,}")
        if habb is not None:
            habb_str = f"{habb:.2f}%"
            habb_emoji = "🟩" if habb > 0 else "🟥"
        else:
            habb_str, habb_emoji = "—", "⚪️"
        lines.append(f"🎈 حباب سکه امامی: {habb_str} {habb_emoji}")
        lines.append("")

    if ons_price and dollar_price and gold_18_price:
        zati_18 = int((dollar_price * ons_price * 0.75) / 31.1035)
        habb18 = ((gold_18_price - zati_18) / zati_18) * 100 if zati_18 != 0 else None
        lines.append(f"📏 ارزش ذاتی طلا ۱۸ عیار: {zati_18:,}")
        if habb18 is not None:
            habb18_str = f"{habb18:.2f}%"
            habb18_emoji = "🟩" if habb18 > 0 else "🟥"
        else:
            habb18_str, habb18_emoji = "—", "⚪️"
        if habb18 < 0:
            habb18_str = f"({abs(habb18):.2f}%)"
        lines.append(f"🎈 حباب طلا ۱۸ عیار: {habb18_str} {habb18_emoji}")
        lines.append("")

    # Dollar Equivalent
    #lines.append(f"💵 Dollar Equivalents")
    if ons_price and sekee_price:
        dollar_sekee = int((factor * sekee_price) / ons_price)
        lines.append(f"💲 دلار سکه: {dollar_sekee:,}")
    else:
        lines.append(f"💲 دلار سکه: —")
    lines.append("")

    # Persian Timestamp
    def gregorian_to_jalali(g_y, g_m, g_d):
        gy = g_y - 1600
        gm = g_m - 1
        gd = g_d - 1
        g_day_no = 365 * gy + (gy + 3)//4 - (gy + 99)//100 + (gy + 399)//400
        for i in range(gm):
            g_day_no += [31, 28 + (1 if (g_y%4==0 and g_y%100!=0) or (g_y%400==0) else 0), 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][i]
        g_day_no += gd
        j_day_no = g_day_no - 79
        j_np = j_day_no // 12053
        j_day_no %= 12053
        jy = 979 + 33*j_np + 4*(j_day_no//1461)
        j_day_no %= 1461
        if j_day_no >= 366:
            jy += (j_day_no-1)//365
            j_day_no = (j_day_no-1)%365
        jm_list = [31,31,31,31,31,31,30,30,30,30,30,29]
        jm = 0
        while jm < 12 and j_day_no >= jm_list[jm]:
            j_day_no -= jm_list[jm]
            jm += 1
        jd = j_day_no + 1
        return jy, jm+1, jd

    iran_now = datetime.now(TEHRAN_TZ)
    jy, jm, jd = gregorian_to_jalali(iran_now.year, iran_now.month, iran_now.day)
    weekdays = ["شنبه", "یک‌شنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]
    months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
              "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
    weekday_index = (iran_now.weekday() + 2) % 7
    weekday = weekdays[weekday_index]
    month = months[jm - 1]
    hour = f"{iran_now.hour:02}"
    minute = f"{iran_now.minute:02}"
    persian_date_str = f"{weekday} {jd} {month} {jy} - {hour}:{minute}"

    lines.append(f"🕓 {persian_date_str}")

    return "\n".join(lines)

# --------------------------
# Telegram API
# --------------------------
def send_message_to_telegram(text):
    TOKEN, CHAT_ID = get_credentials()
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json().get("result", {}).get("message_id")
        print(f"⚠️ Telegram API error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Telegram send error: {e}")
    return None

# --------------------------
# Main Execution
# --------------------------
def main():
    print("="*50)
    print(f"🔁 Starting execution - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"⏳ Attempt {attempt}/{MAX_RETRIES}: Fetching prices...")
                data = get_prices_selenium()
                break
            except Exception as e:
                print(f"⚠️ Attempt {attempt} failed: {e}")
                if attempt == MAX_RETRIES:
                    raise
                print(f"⏳ Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)

        report = build_report_message(data)
        print("✅ Data fetched successfully")

        message_id = send_message_to_telegram(report)
        if message_id:
            print("📨 Message sent successfully")
        else:
            raise Exception("Failed to send message")

    except Exception as e:
        print(f"❌ Critical error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
