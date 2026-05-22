import os
import re
import json
import statistics
import logging
import urllib.parse
import httpx

from datetime import date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)

log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8707881255:AAGGHKw-_71M3qgEaKmCnCCvAZEM_5xPJAg")
SCRAPER_KEY = os.getenv("SCRAPER_API_KEY", "54d900d64f2b1eec5d6c8ee9db274035")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"


# ═══════════════════════════════════════════
# USD / AZN
# ═══════════════════════════════════════════
async def azn_rate() -> float:
    for delta in range(4):
        d = (date.today() - timedelta(days=delta)).strftime("%d-%m-%Y")

        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"https://cbar.az/currencies/{d}.xml",
                    headers={"User-Agent": UA}
                )

                if r.status_code == 200 and b"<Val" in r.content:
                    from xml.etree import ElementTree as ET

                    for val in ET.fromstring(r.content).iter("Val"):
                        if val.get("Code") == "USD":
                            return float(val.find("Value").text.replace(",", "."))

        except Exception as e:
            log.warning(f"CBAR ERROR: {e}")

    return 1.7


# ═══════════════════════════════════════════
# METAL PRICES
# ═══════════════════════════════════════════
async def metal_message() -> str:
    rate = await azn_rate()

    gold = None
    silver = None

    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        headers={
            "User-Agent": UA,
            "Accept": "application/json"
        }
    ) as c:

        try:
            rg = await c.get("https://api.gold-api.com/price/XAU")

            if rg.status_code == 200:
                m = re.search(r'"price"\s*:\s*([\d.]+)', rg.text)

                if m:
                    gold = float(m.group(1))

        except Exception as e:
            log.warning(f"XAU ERROR: {e}")

        try:
            rs = await c.get("https://api.gold-api.com/price/XAG")

            if rs.status_code == 200:
                m = re.search(r'"price"\s*:\s*([\d.]+)', rs.text)

                if m:
                    silver = float(m.group(1))

        except Exception as e:
            log.warning(f"XAG ERROR: {e}")

    if not gold:
        return "❌ Metal qiymətləri alınmadı"

    g = gold / 31.1035
    s = (silver or 0) / 31.1035

    return (
        f"💰 *Metal Qiymətləri*\n\n"
        f"🥇 *Qızıl*\n"
        f"• 1 oz : ${gold:,.2f}\n"
        f"• 1 qram : {g*rate:,.2f} ₼\n\n"
        f"🥈 *Gümüş*\n"
        f"• 1 oz : ${silver:,.2f}\n"
        f"• 1 qram : {s*rate:,.2f} ₼\n\n"
        f"💵 USD/AZN : {rate}"
    )


# ═══════════════════════════════════════════
# OUTLIER FILTER
# ═══════════════════════════════════════════
def clean_outliers(prices):
    if len(prices) < 4:
        return prices

    prices = sorted(prices)

    q1 = statistics.quantiles(prices, n=4)[0]
    q3 = statistics.quantiles(prices, n=4)[2]

    iqr = q3 - q1

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    filtered = [p for p in prices if lower <= p <= upper]

    return filtered if filtered else prices


# ═══════════════════════════════════════════
# PRICE EXTRACTOR
# ═══════════════════════════════════════════
def extract_prices(html: str) -> list:
    prices = []

    # JSON patterns
    json_patterns = [
        r'"price"\s*:\s*"?(\d{2,6})"?',
        r'"azn_price"\s*:\s*"?(\d{2,6})"?',
        r'"sale_price"\s*:\s*"?(\d{2,6})"?',
    ]

    for pattern in json_patterns:
        matches = re.findall(pattern, html)

        for m in matches:
            try:
                val = int(str(m).replace(" ", ""))

                if 50 <= val <= 30000:
                    prices.append(val)

            except:
                pass

    # HTML patterns
    html_patterns = [
        r'(\d{2,6})\s*₼',
        r'(\d{2,6})\s*AZN',
        r'data-price=["\'](\d{2,6})["\']',
        r'class="price[^"]*">\s*(\d{2,6})',
    ]

    for pattern in html_patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)

        for m in matches:
            try:
                val = int(str(m).replace(" ", ""))

                if 50 <= val <= 30000:
                    prices.append(val)

            except:
                pass

    # duplicates sil
    prices = list(set(prices))

    # realistic filter
    filtered = []

    for p in prices:
        if 80 <= p <= 15000:
            filtered.append(p)

    prices = filtered

    # outlier filter
    prices = clean_outliers(prices)

    return sorted(prices)


# ═══════════════════════════════════════════
# TAP.AZ SEARCH
# ═══════════════════════════════════════════
async def phone_message(model: str) -> str:
    tap_url = (
        f"https://tap.az/elanlar?keywords="
        f"{model.replace(' ', '+')}&category_id=743"
    )

    scraper_url = (
        f"https://api.scraperapi.com/"
        f"?api_key={SCRAPER_KEY}"
        f"&url={urllib.parse.quote(tap_url, safe='')}"
        f"&render=true"
    )

    try:
        async with httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            headers={"User-Agent": UA}
        ) as c:

            r = await c.get(scraper_url)

            log.info(
                f"ScraperAPI [{model}] => "
                f"status={r.status_code}, len={len(r.text)}"
            )

            if r.status_code != 200:
                return (
                    f"📱 *{model}*\n\n"
                    f"❌ tap.az cavab vermədi"
                )

            html = r.text

            prices = extract_prices(html)

            log.info(f"Extracted prices count: {len(prices)}")
            log.info(f"Extracted prices: {prices[:50]}")

    except Exception as e:
        log.error(f"PHONE SEARCH ERROR: {e}")

        return (
            f"📱 *{model}*\n\n"
            f"❌ Axtarış zamanı xəta baş verdi"
        )

    if not prices:
        return (
            f"📱 *{model}*\n\n"
            f"❌ Qiymət tapılmadı\n\n"
            f"🔗 [tap.az-da bax]({tap_url})"
        )

    avg = statistics.mean(prices)
    med = statistics.median(prices)

    return (
        f"📱 *{model}*\n\n"
        f"📊 Ortalama : *{avg:,.0f} ₼*\n"
        f"📍 Median : *{med:,.0f} ₼*\n"
        f"⬇️ Minimum : {min(prices):,} ₼\n"
        f"⬆️ Maksimum : {max(prices):,} ₼\n"
        f"📋 Elan sayı : ~{len(prices)}\n\n"
        f"🔗 [tap.az-da bax]({tap_url})"
    )


# ═══════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════
def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📱 Telefon Qiyməti",
            callback_data="phone"
        )],
        [InlineKeyboardButton(
            "🥇 Metal Qiymətləri",
            callback_data="metals"
        )]
    ])


# ═══════════════════════════════════════════
# START
# ═══════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Girov Qiymət Botu*\n\n"
        "📱 Telefon qiymətləri\n"
        "🥇 Metal qiymətləri",
        parse_mode="Markdown",
        reply_markup=kb_main()
    )


# ═══════════════════════════════════════════
# TEXT
# ═══════════════════════════════════════════
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    msg = await update.message.reply_text(
        f"🔍 *{text}* axtarılır...\n"
        f"⏳ 20-30 saniyə gözləyin",
        parse_mode="Markdown"
    )

    result = await phone_message(text)

    await msg.edit_text(
        result,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


# ═══════════════════════════════════════════
# BUTTONS
# ═══════════════════════════════════════════
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query

    await q.answer()

    if q.data == "metals":
        await q.edit_message_text("⏳ Yüklənir...")

        result = await metal_message()

        await q.edit_message_text(
            result,
            parse_mode="Markdown"
        )

    elif q.data == "phone":
        await q.edit_message_text(
            "✏️ Telefon modelini yazın\n\n"
            "Nümunə:\n"
            "iPhone 13\n"
            "Samsung S23 Ultra",
            parse_mode="Markdown"
        )


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════
def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN yoxdur")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("🤖 Bot started")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
