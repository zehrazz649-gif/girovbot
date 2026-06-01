import os
import re
import asyncio
import logging
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Conflict, NetworkError, TimedOut
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN")
GOLDAPI_KEY = os.environ.get("GOLDAPI_KEY", "")


# ═══════════════════════════════════════════════
# QIZIL / GÜMÜŞ QİYMƏTLƏRİ
# ═══════════════════════════════════════════════
def get_gold_silver_prices():
    gold_usd   = None
    silver_usd = None
    azn_rate   = 1.7

    # ── 1. goldapi.io ──
    if GOLDAPI_KEY:
        try:
            headers = {
                "x-access-token": GOLDAPI_KEY,
                "Content-Type": "application/json"
            }
            r = requests.get("https://www.goldapi.io/api/XAU/USD", headers=headers, timeout=10)
            if r.status_code == 200:
                gold_usd = float(r.json()["price"])
                logger.info(f"goldapi XAU={gold_usd}")
            r2 = requests.get("https://www.goldapi.io/api/XAG/USD", headers=headers, timeout=10)
            if r2.status_code == 200:
                silver_usd = float(r2.json()["price"])
        except Exception as e:
            logger.warning(f"goldapi.io xətası: {e}")

    # ── 2. fawazahmed (fallback) ──
    if not gold_usd:
        try:
            r = requests.get(
                "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/xau.json",
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                gold_usd = 1.0 / float(data["xau"]["usd"]) if float(data["xau"]["usd"]) < 1 else float(data["xau"]["usd"])
                # Əgər qiymət per-gram gəlirsə troy oz-a çevir
                if gold_usd < 200:
                    gold_usd = gold_usd * 31.1035
                logger.info(f"fawazahmed XAU={gold_usd}")
        except Exception as e:
            logger.warning(f"fawazahmed xətası: {e}")

    # ── 3. Yahoo Finance (fallback 2) ──
    if not gold_usd:
        try:
            s = requests.Session()
            s.headers.update({"User-Agent": "Mozilla/5.0"})
            r = s.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X?interval=1d&range=1d",
                timeout=10
            )
            if r.status_code == 200:
                gold_usd = float(r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"])
                logger.info(f"Yahoo XAU={gold_usd}")
            r2 = s.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/XAGUSD=X?interval=1d&range=1d",
                timeout=10
            )
            if r2.status_code == 200:
                silver_usd = float(r2.json()["chart"]["result"][0]["meta"]["regularMarketPrice"])
        except Exception as e:
            logger.warning(f"Yahoo Finance xətası: {e}")

    # ── AZN məzənnəsi ──
    for fx_url in [
        "https://open.er-api.com/v6/latest/USD",
        "https://api.exchangerate-api.com/v4/latest/USD",
    ]:
        try:
            r = requests.get(fx_url, timeout=8)
            if r.status_code == 200:
                azn_rate = float(r.json()["rates"]["AZN"])
                break
        except Exception:
            continue

    logger.info(f"Final: gold_usd={gold_usd}, silver_usd={silver_usd}, azn={azn_rate}")

    if not gold_usd or gold_usd < 500:
        return "❌ Qiymət alına bilmədi. Bir az sonra yenidən cəhd edin."

    gold_azn   = gold_usd * azn_rate
    silver_azn = (silver_usd * azn_rate) if silver_usd else None

    gpg_usd = gold_usd / 31.1035
    gpg_azn = gold_azn / 31.1035
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
            f"  • 999: *{round(spg_azn, 2)} ₼*/q  ({round(spg_usd, 2)} $)\n"
            f"  • 925: *{round(spg_azn * 0.925, 2)} ₼*/q\n"
            f"  • 875: *{round(spg_azn * 0.875, 2)} ₼*/q\n"
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
        f"💱 1 USD ≈ *{azn_rate:.4f} ₼*\n\n"
        "⚠️ _Qiymətlər məlumat üçündür._"
    )


# ═══════════════════════════════════════════════
# TAP.AZ — REQUESTS + BEAUTIFULSOUP İLƏ AXTARIŞ
# ═══════════════════════════════════════════════
HEADERS_LIST = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "az-AZ,az;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://tap.az/",
    },
    {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept-Language": "az,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Accept-Language": "az-AZ,az;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
]

def scrape_tap_az(query: str):
    """Tap.az-dan requests ilə qiymətləri çəkir."""
    query_encoded = query.strip().replace(" ", "+")
    url = f"https://tap.az/elanlar?q={query_encoded}&category_id=3"

    session = requests.Session()
    session.headers.update({"Connection": "keep-alive"})

    # Əvvəl ana səhifəyə get (cookie almaq üçün)
    for headers in HEADERS_LIST:
        try:
            session.headers.update(headers)
            # Ana səhifə — cookie
            session.get("https://tap.az/", timeout=10, verify=False)
            # Axtarış
            resp = session.get(url, timeout=15, verify=False)
            if resp.status_code == 200 and "products-i" in resp.text:
                logger.info(f"tap.az requests: OK, status={resp.status_code}")
                return resp.text, url
            else:
                logger.warning(f"tap.az: status={resp.status_code}, products-i tapılmadı")
        except Exception as e:
            logger.warning(f"tap.az headers cəhdi xətası: {e}")
            continue

    return None, url


def parse_tap_listings(html: str):
    """HTML-dən elan başlıqları və qiymətlərini çıxarır."""
    soup = BeautifulSoup(html, "lxml")
    listings = []

    items = soup.select("div.products-i")
    logger.info(f"BeautifulSoup: {len(items)} div.products-i tapıldı")

    for item in items:
        title_el = (
            item.select_one(".products-name span") or
            item.select_one(".products-name") or
            item.select_one("h3")
        )
        price_el = (
            item.select_one(".price-val") or
            item.select_one(".products-price span") or
            item.select_one(".products-price")
        )
        if title_el and price_el:
            listings.append({
                "title": title_el.get_text(strip=True),
                "price": price_el.get_text(strip=True),
            })

    return listings


async def search_tap_az(model: str) -> str:
    query = model.strip()
    query_encoded = query.replace(" ", "+")
    tap_url = f"https://tap.az/elanlar?q={query_encoded}&category_id=3"

    try:
        html, _ = scrape_tap_az(query)

        if not html:
            return (
                f"❌ Tap.az-a qoşulmaq alınmadı.\n\n"
                f"🔗 [Tap.az-da özün bax]({tap_url})"
            )

        listings = parse_tap_listings(html)
        logger.info(f"tap.az: {len(listings)} elan parse edildi")

        if not listings:
            return (
                f"⚠️ *\"{query}\"* üçün tap.az-da elan tapılmadı.\n\n"
                f"Fərqli yazılış sına:\n"
                f"• `iphone 13` → `iPhone 13 128gb`\n"
                f"• `samsung s23` → `Samsung Galaxy S23`\n\n"
                f"🔗 [Tap.az-da özün bax]({tap_url})"
            )

        # Qiymət analizi
        prices = []
        for item in listings:
            try:
                cleaned = re.sub(r"[^\d.]", "", item["price"].replace(",", ".").replace("\xa0", ""))
                val = float(cleaned)
                if val > 10:  # 10 AZN-dən az olanları filtr et (keçərsiz qiymətlər)
                    prices.append(val)
            except Exception:
                continue

        if not prices:
            return f"❌ Elanlar tapıldı amma qiymətlər oxuna bilmədi."

        prices_sorted = sorted(prices)
        avg    = sum(prices) / len(prices)
        mid    = len(prices_sorted) // 2
        median = (
            prices_sorted[mid]
            if len(prices_sorted) % 2 != 0
            else (prices_sorted[mid - 1] + prices_sorted[mid]) / 2
        )

        girov_min = round(median * 0.50)
        girov_max = round(median * 0.60)

        result = (
            f"📱 *{query.upper()} — TAP.AZ*\n"
            f"🔍 {len(prices)} elan analiz edildi\n\n"
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
            result += f"{i}. {item['title'][:38]} — *{item['price']}*\n"

        result += f"\n🔗 [Tap.az-da bax]({tap_url})"
        return result

    except Exception as e:
        logger.error(f"search_tap_az xətası: {e}")
        return (
            f"❌ Tap.az-a qoşulmaq alınmadı.\n\n"
            f"🔗 [Tap.az-da özün bax]({tap_url})"
        )


# ═══════════════════════════════════════════════
# TELEGRAM HANDLERS
# ═══════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🥇 Qızıl / Gümüş Qiymətlər", callback_data="metals")],
        [InlineKeyboardButton("📱 Telefon Qiymət Analizi",   callback_data="phone_help")],
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
            "Model adını birbaşa yaz, bot tap.az-da axtarıb sənə:\n"
            "✅ Min / Max / Orta / Median qiymət\n"
            "✅ Girov üçün tövsiyə olunan qiymət\n\n"
            "*Nümunələr:*\n"
            "`iPhone 13`\n"
            "`Samsung Galaxy S23`\n"
            "`Xiaomi Redmi Note 12`\n"
            "`Huawei P30`",
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
            f"🔍 *\"{text}\"* tap.az-da axtarılır...\n_(5–10 saniyə çəkə bilər)_",
            parse_mode="Markdown"
        )
        result = await search_tap_az(text)
        await msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)


async def metals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Anlıq qiymətlər alınır...")
    result = get_gold_silver_prices()
    await msg.edit_text(result, parse_mode="Markdown")


# ═══════════════════════════════════════════════
# ERROR HANDLER
# ═══════════════════════════════════════════════
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, Conflict):
        # Köhnə instance hələ işləyir — bir az gözlə, özü həll olur
        logger.warning("Conflict xətası: köhnə instance ilə toqquşma, gözlənilir...")
        await asyncio.sleep(3)
    elif isinstance(err, (NetworkError, TimedOut)):
        logger.warning(f"Şəbəkə xətası (keçici): {err}")
    else:
        logger.error(f"Xəta: {err}", exc_info=context.error)


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════
def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN tapılmadı!")
    if not GOLDAPI_KEY:
        logger.warning("GOLDAPI_KEY yoxdur — fallback API-lər istifadə olunacaq")

    app = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("metals", metals_command))
    app.add_handler(CommandHandler("qizil",  metals_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)

    logger.info("✅ Bot işə düşdü!")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,   # ← deploy zamanı yığılmış köhnə mesajları at
        close_loop=False,
    )


if __name__ == "__main__":
    main()
