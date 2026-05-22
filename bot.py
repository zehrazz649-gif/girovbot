"""
═══════════════════════════════════════════════
Girov Qimət Botu — PLAYWRIGHT VERSION
═══════════════════════════════════════════════
"""

import re
import statistics
import logging
import httpx

from datetime import date, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from playwright.async_api import async_playwright


# ═══════════════════════════════════════════
# BOT TOKEN
# ═══════════════════════════════════════════

BOT_TOKEN = "8707881255:AAEtUM4Q6X9-DfGmQ590UUnxTB3JugyKXV4"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

log = logging.getLogger(__name__)


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

    filtered = [
        p for p in prices
        if lower <= p <= upper
    ]

    return filtered if filtered else prices


# ═══════════════════════════════════════════
# PLAYWRIGHT SCRAPER
# ═══════════════════════════════════════════

async def scrape_tapaz_prices(model: str):

    url = (
        "https://tap.az/elanlar"
        f"?keywords={model.replace(' ', '+')}"
        "&category_id=743"
    )

    prices = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ]
        )

        context = await browser.new_context(
            user_agent=UA,
            viewport={
                "width": 1400,
                "height": 900
            }
        )

        page = await context.new_page()

        try:

            log.info(f"OPENING: {url}")

            await page.goto(
                url,
                timeout=90000,
                wait_until="domcontentloaded"
            )

            await page.wait_for_timeout(5000)

            html = await page.content()

            log.info(f"HTML LENGTH: {len(html)}")

            patterns = [
                r'(\\d{2,6})\\s*₼',
                r'(\\d{2,6})\\s*AZN',
                r'"price":"?(\\d{2,6})"?',
                r'data-price="(\\d{2,6})"',
            ]

            for pattern in patterns:

                matches = re.findall(
                    pattern,
                    html,
                    re.IGNORECASE
                )

                for m in matches:

                    try:

                        val = int(
                            str(m)
                            .replace(" ", "")
                            .replace(",", "")
                        )

                        if 50 <= val <= 30000:
                            prices.append(val)

                    except:
                        pass

            prices = list(set(prices))

            prices = [
                p for p in prices
                if 80 <= p <= 15000
            ]

            prices = clean_outliers(prices)

            log.info(f"PRICES: {prices}")

        except Exception as e:

            log.error(f"PLAYWRIGHT ERROR: {e}")

        finally:

            await browser.close()

    return sorted(prices)


# ═══════════════════════════════════════════
# PHONE MESSAGE
# ═══════════════════════════════════════════

async def phone_message(model: str):

    tap_url = (
        "https://tap.az/elanlar"
        f"?keywords={model.replace(' ', '+')}"
        "&category_id=743"
    )

    try:

        prices = await scrape_tapaz_prices(model)

    except Exception as e:

        log.error(e)

        return (
            f"📱 *{model}*\\n\\n"
            f"❌ Xəta baş verdi"
        )

    if not prices:

        return (
            f"📱 *{model}*\\n\\n"
            f"❌ Qiymət tapılmadı\\n\\n"
            f"🔗 [tap.az-da bax]({tap_url})"
        )

    avg = statistics.mean(prices)
    med = statistics.median(prices)

    return (
        f"📱 *{model}*\\n\\n"
        f"📊 Ortalama : *{avg:,.0f} ₼*\\n"
        f"📍 Median : *{med:,.0f} ₼*\\n"
        f"⬇️ Minimum : {min(prices):,} ₼\\n"
        f"⬆️ Maksimum : {max(prices):,} ₼\\n"
        f"📋 Elan sayı : ~{len(prices)}\\n\\n"
        f"🔗 [tap.az-da bax]({tap_url})"
    )


# ═══════════════════════════════════════════
# USD/AZN
# ═══════════════════════════════════════════

async def azn_rate():

    for delta in range(4):

        d = (
            date.today() - timedelta(days=delta)
        ).strftime("%d-%m-%Y")

        try:

            async with httpx.AsyncClient(
                timeout=10
            ) as c:

                r = await c.get(
                    f"https://cbar.az/currencies/{d}.xml"
                )

                if r.status_code == 200:

                    from xml.etree import ElementTree as ET

                    for val in ET.fromstring(r.content).iter("Val"):

                        if val.get("Code") == "USD":

                            return float(
                                val.find("Value")
                                .text.replace(",", ".")
                            )

        except:
            pass

    return 1.7


# ═══════════════════════════════════════════
# METAL PRICES
# ═══════════════════════════════════════════

async def metal_message():

    rate = await azn_rate()

    gold = None

    try:

        async with httpx.AsyncClient(timeout=15) as c:

            r = await c.get(
                "https://api.gold-api.com/price/XAU"
            )

            if r.status_code == 200:

                m = re.search(
                    r'"price"\\s*:\\s*([\\d.]+)',
                    r.text
                )

                if m:
                    gold = float(m.group(1))

    except:
        pass

    if not gold:

        return "❌ Metal qiyməti alınmadı"

    gram = gold / 31.1035

    return (
        f"🥇 *Qızıl Qiyməti*\\n\\n"
        f"• 1 oz : ${gold:,.2f}\\n"
        f"• 1 qram : {gram*rate:,.2f} ₼\\n\\n"
        f"💵 USD/AZN : {rate}"
    )


# ═══════════════════════════════════════════
# KEYBOARD
# ═══════════════════════════════════════════

def kb_main():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📱 Telefon Qiyməti",
                callback_data="phone"
            )
        ],
        [
            InlineKeyboardButton(
                "🥇 Metal Qiymətləri",
                callback_data="metals"
            )
        ]
    ])


# ═══════════════════════════════════════════
# START
# ═══════════════════════════════════════════

async def cmd_start(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "👋 *Girov Qiymət Botu*\\n\\n"
        "📱 tap.az telefon qiymətləri\\n"
        "🥇 Metal qiymətləri\\n\\n"
        "Model yazın:",
        parse_mode="Markdown",
        reply_markup=kb_main()
    )


# ═══════════════════════════════════════════
# TEXT
# ═══════════════════════════════════════════

async def on_text(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text.strip()

    msg = await update.message.reply_text(
        f"🔍 *{text}* axtarılır...\\n"
        f"⏳ 15-30 saniyə gözləyin",
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

async def on_button(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE
):

    q = update.callback_query

    await q.answer()

    if q.data == "metals":

        await q.edit_message_text(
            "⏳ Yüklənir..."
        )

        result = await metal_message()

        await q.edit_message_text(
            result,
            parse_mode="Markdown"
        )

    elif q.data == "phone":

        await q.edit_message_text(
            "✏️ Telefon modelini yazın\\n\\n"
            "Nümunə:\\n"
            "iPhone 13\\n"
            "Samsung S23 Ultra",
            parse_mode="Markdown"
        )


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():

    app = Application.builder().token(
        BOT_TOKEN
    ).build()

    app.add_handler(
        CommandHandler("start", cmd_start)
    )

    app.add_handler(
        CallbackQueryHandler(on_button)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            on_text
        )
    )

    log.info("🤖 PLAYWRIGHT BOT STARTED")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
