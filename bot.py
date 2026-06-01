import os
import re
import logging
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "az,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://tap.az/",
}


# ─────────────────────────────────────────────
# QIZIL / GÜMÜŞ QİYMƏTLƏRİ
# ─────────────────────────────────────────────
def get_gold_silver_prices():
    gold_usd = None   # 1 troy oz
    silver_usd = None
    azn_rate = 1.7

    # ── API 1: Yahoo Finance (ən etibarlı) ──
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})

        r = session.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X?interval=1d&range=1d",
            timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            gold_usd = float(d["chart"]["result"][0]["meta"]["regularMarketPrice"])
            logger.info(f"Yahoo XAU: {gold_usd}")

        r2 = session.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/XAGUSD=X?interval=1d&range=1d",
            timeout=10
        )
        if r2.status_code == 200:
            d2 = r2.json()
            silver_usd = float(d2["chart"]["result"][0]["meta"]["regularMarketPrice"])
            logger.info(f"Yahoo XAG: {silver_usd}")
    except Exception as e:
        logger.warning(f"Yahoo Finance xətası: {e}")

    # ── API 2: metals.live (SSL ignore) ──
    if not gold_usd:
        try:
            r = requests.get("https://api.metals.live/v1/spot", timeout=10, verify=False)
            if r.status_code == 200:
                for item in r.json():
                    if "gold" in item and not gold_usd:
                        gold_usd = float(item["gold"])
                    if "silver" in item and not silver_usd:
                        silver_usd = float(item["silver"])
                logger.info(f"metals.live XAU={gold_usd}, XAG={silver_usd}")
        except Exception as e:
            logger.warning(f"metals.live xətası: {e}")

    # ── API 3: goldprice.org ──
    if not gold_usd:
        try:
            r = requests.get(
                "https://data-asg.goldprice.org/dbXRates/USD",
                headers={**HEADERS, "x-requested-with": "XMLHttpRequest"},
                timeout=10
            )
            if r.status_code == 200:
                d = r.json()
                gold_usd   = float(d["items"][0]["xauPrice"])
                silver_usd = float(d["items"][0]["xagPrice"])
                logger.info(f"goldprice.org XAU={gold_usd}")
        except Exception as e:
            logger.warning(f"goldprice.org xətası: {e}")

    # ── API 4: fawazahmed CDN (son fallback) ──
    # Bu API-də XAU = "1 XAU neçə USD-dir" formatında
    if not gold_usd:
        try:
            r = requests.get(
                "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/xau.json",
                timeout=10
            )
            if r.status_code == 200:
                d = r.json()
                xau_in_usd = d["xau"].get("usd")  # 1 XAU = ? USD
                if xau_in_usd and float(xau_in_usd) > 100:
                    gold_usd = float(xau_in_usd)
                    logger.info(f"fawazahmed XAU={gold_usd}")
        except Exception as e:
            logger.warning(f"fawazahmed gold xətası: {e}")

    if not silver_usd:
        try:
            r = requests.get(
                "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/xag.json",
                timeout=10
            )
            if r.status_code == 200:
                d = r.json()
                xag_in_usd = d["xag"].get("usd")
                if xag_in_usd and float(xag_in_usd) > 1:
                    silver_usd = float(xag_in_usd)
        except Exception as e:
            logger.warning(f"fawazahmed silver xətası: {e}")

    # ── AZN məzənnəsi ──
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
        if r.status_code == 200:
            azn_rate = float(r.json()["rates"]["AZN"])
    except Exception:
        try:
            r = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=8)
            if r.status_code == 200:
                azn_rate = float(r.json()["rates"]["AZN"])
        except Exception:
            pass

    logger.info(f"Final: gold_usd={gold_usd}, silver_usd={silver_usd}, azn={azn_rate}")

    if not gold_usd or gold_usd < 100:
        return "❌ Qiymət alına bilmədi. Bir az sonra yenidən cəhd edin."

    gold_azn   = gold_usd * azn_rate
    silver_azn = (silver_usd * azn_rate) if silver_usd else None

    # 1 troy oz = 31.1035 qram
    gpg_usd = gold_usd   / 31.1035
    gpg_azn = gold_azn   / 31.1035
    spg_usd = (silver_usd / 31.1035) if silver_usd else None
    spg_azn = (silver_azn / 31.1035) if silver_azn else None

    karats = [
        ("999 (24K)", 1.000),
        ("750 (18K)", 0.750),
        ("585 (14K)", 0.585),
        ("375 (9K)",  0.375),
    ]

    gold_table = ""
    for name, ratio in karats:
        g_azn = round(gpg_azn * ratio, 2)
        g_usd = round(gpg_usd * ratio, 2)
        gold_table += f"  • {name}: *{g_azn} ₼*/q  ({g_usd} $)\n"

    if spg_azn:
        silver_table = (
            f"  • 999: *{round(spg_azn,2)} ₼*/q  ({round(spg_usd,2)} $)\n"
            f"  • 925: *{round(spg_azn*0.925,2)} ₼*/q\n"
            f"  • 875: *{round(spg_azn*0.875,2)} ₼*/q\n"
        )
    else:
        silver_table = "  _(alına bilmədi)_\n"

    return (
        "🪙 *ANLIQ METAL QİYMƏTLƏRİ*\n"
        "_(Beynəlxalq bazar — 1 qram)_\n\n"
        "🥇 *QIZIL*\n"
        f"{gold_table}\n"
        "🥈 *GÜMÜŞ*\n"
        f"{silver_table}\n"
        f"💱 1 USD ≈ *{azn_rate} ₼*\n\n"
        "⚠️ _Qiymətlər məlumat üçündür._"
    )


# ─────────────────────────────────────────────
# TAP.AZ AXTARIŞ
# ─────────────────────────────────────────────
def search_tap_az(model: str):
    query = model.strip()
    query_encoded = query.replace(" ", "+")

    # Tap.az mobil versiyası daha az blok qoyur
    urls_to_try = [
        f"https://tap.az/elanlar?q={query_encoded}&category_id=3",
        f"https://tap.az/elanlar?q={query_encoded}",
    ]

    user_agents = [
        # Desktop Chrome
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        # iPhone Safari
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        # Android Chrome
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
    ]

    soup = None
    for url in urls_to_try:
        for ua in user_agents:
            try:
                session = requests.Session()
                session.headers.update({
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "az-AZ,az;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                })
                # Əvvəl ana səhifəyə gir
                session.get("https://tap.az", timeout=8)
                r = session.get(url, timeout=15)

                if r.status_code == 200 and len(r.text) > 1000:
                    soup = BeautifulSoup(r.text, "lxml")
                    logger.info(f"tap.az OK: {url} ua={ua[:30]}")
                    break
            except Exception as e:
                logger.warning(f"tap.az cəhd xətası: {e}")
                continue
        if soup:
            break

    if not soup:
        return (
            f"❌ *Tap.az-a qoşulmaq alınmadı.*\n\n"
            f"Tap.az bot girişini bloklamış ola bilər.\n"
            f"🔗 Özün bax: [tap.az-da `{query}` axtar](https://tap.az/elanlar?q={query_encoded}&category_id=3)"
        )

    listings = []
    items = soup.select("div.products-i, article.products-i")
    logger.info(f"tap.az items found: {len(items)}")

    for item in items[:20]:
        try:
            title_el = (
                item.select_one(".products-name span") or
                item.select_one(".products-name") or
                item.select_one("h3")
            )
            price_el = (
                item.select_one(".price-val") or
                item.select_one(".products-price")
            )

            title = title_el.get_text(strip=True) if title_el else ""
            price_raw = price_el.get_text(strip=True) if price_el else ""

            if not price_raw:
                continue

            cleaned = re.sub(r"[^\d.]", "", price_raw.replace(",", ".").replace("\xa0", ""))
            if cleaned and float(cleaned) > 0:
                listings.append({
                    "title": title,
                    "price_str": price_raw.replace("\xa0", " ").strip(),
                    "price_num": float(cleaned)
                })
        except Exception:
            continue

    if not listings:
        return (
            f"⚠️ *\"{query}\"* üçün tap.az-da elan tapılmadı.\n\n"
            f"Fərqli yazılış sına:\n"
            f"• `iPhone 13` → `iphone 13 128`\n"
            f"• `Samsung S23` → `samsung galaxy s23`\n\n"
            f"🔗 [Tap.az-da özün bax](https://tap.az/elanlar?q={query_encoded}&category_id=3)"
        )

    prices = [x["price_num"] for x in listings]
    prices_sorted = sorted(prices)
    avg = sum(prices) / len(prices)
    mid = len(prices_sorted) // 2
    median = (
        prices_sorted[mid]
        if len(prices_sorted) % 2 != 0
        else (prices_sorted[mid-1] + prices_sorted[mid]) / 2
    )

    girov_min = round(median * 0.50)
    girov_max = round(median * 0.60)

    result = (
        f"📱 *{query.upper()} — TAP.AZ*\n"
        f"🔍 {len(listings)} elan analiz edildi\n\n"
        f"💰 *Qiymət Statistikası:*\n"
        f"  • 📉 Ən ucuz: *{min(prices):.0f} ₼*\n"
        f"  • 📈 Ən baha: *{max(prices):.0f} ₼*\n"
        f"  • 📊 Orta: *{avg:.0f} ₼*\n"
        f"  • 🎯 Median: *{median:.0f} ₼*\n\n"
        f"🏦 *Girov Tövsiyəsi:*\n"
        f"  *{girov_min}–{girov_max} ₼*\n"
        f"  _(median-ın 50–60%-i)_\n\n"
        f"*Nümunə elanlar:*\n"
    )

    for i, item in enumerate(listings[:5], 1):
        result += f"{i}. {item['title'][:38]} — *{item['price_str']}*\n"

    result += f"\n🔗 [Tap.az-da bax](https://tap.az/elanlar?q={query_encoded}&category_id=3)"
    return result


# ─────────────────────────────────────────────
# HANDLERS
# ─────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🥇 Qızıl / Gümüş Qiymətlər", callback_data="metals")],
        [InlineKeyboardButton("📱 Telefon Qiymət Analizi", callback_data="phone_help")],
    ]
    await update.message.reply_text(
        "👋 Salam! *Girov Analiz Botu*\n\n"
        "🔹 Anlıq qızıl & gümüş qiymətlər (əyara görə, AZN)\n"
        "🔹 Tap.az-dan telefon bazar qiyməti + girov tövsiyəsi\n\n"
        "📱 *Telefon analizi üçün sadəcə yaz:*\n"
        "`iPhone 13 128gb`\n"
        "`Samsung S23`\n"
        "`Redmi Note 12`\n\n"
        "Seçin 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "metals":
        msg = await query.message.reply_text("⏳ Anlıq qiymətlər alınır...")
        result = get_gold_silver_prices()
        await msg.edit_text(result, parse_mode="Markdown")

    elif query.data == "phone_help":
        await query.message.reply_text(
            "📱 *Telefon Analizi*\n\n"
            "Model adını birbaşa yaz:\n\n"
            "`iPhone 13`\n"
            "`Samsung Galaxy S23`\n"
            "`Xiaomi Redmi Note 12`\n"
            "`Huawei P30`\n\n"
            "Bot tap.az-da axtarıb sənə min/max/orta qiymət və girov tövsiyəsi verəcək 📊",
            parse_mode="Markdown"
        )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if any(w in text.lower() for w in ["qizil", "qızıl", "gumus", "gümüş", "metal", "gold", "silver"]):
        msg = await update.message.reply_text("⏳ Anlıq qiymətlər alınır...")
        result = get_gold_silver_prices()
        await msg.edit_text(result, parse_mode="Markdown")
    else:
        msg = await update.message.reply_text(
            f"🔍 *\"{text}\"* tap.az-da axtarılır...\n_(5–15 saniyə çəkə bilər)_",
            parse_mode="Markdown"
        )
        result = search_tap_az(text)
        await msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)


async def metals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Anlıq qiymətlər alınır...")
    result = get_gold_silver_prices()
    await msg.edit_text(result, parse_mode="Markdown")


def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN tapılmadı!")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("metals", metals_command))
    app.add_handler(CommandHandler("qizil",  metals_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("✅ Bot işə düşdü!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
