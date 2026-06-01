import os
import logging
import requests
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
}

# ─────────────────────────────────────────────
# QIZIL / GÜMÜŞ QİYMƏTLƏRİ
# metals-api.com (pulsuz 10 req/ay)  →  fallback: goldprice.org scrape
# ─────────────────────────────────────────────
def get_gold_silver_prices():
    try:
        # Metod 1: metals.live (pulsuz, API key lazım deyil)
        gold_usd = None
        silver_usd = None

        r = requests.get("https://api.metals.live/v1/spot", timeout=10)
        if r.status_code == 200:
            data = r.json()
            # data is a list of dicts: [{"gold": 2300.5}, {"silver": 27.3}, ...]
            for item in data:
                if "gold" in item:
                    gold_usd = float(item["gold"])
                if "silver" in item:
                    silver_usd = float(item["silver"])

        # Metod 2 (fallback): goldprice.org JSON feed
        if not gold_usd:
            r2 = requests.get(
                "https://data-asg.goldprice.org/dbXRates/USD",
                headers={"x-requested-with": "XMLHttpRequest"},
                timeout=10
            )
            if r2.status_code == 200:
                d = r2.json()
                gold_usd   = float(d["items"][0]["xauPrice"])  # per troy oz
                silver_usd = float(d["items"][0]["xagPrice"])

        if not gold_usd:
            return "❌ Qiymət alına bilmədi. Bir az sonra yenidən cəhd edin."

        # AZN məzənnəsi (sabit oriyentir, hər gün az dəyişir)
        try:
            fx = requests.get(
                "https://api.exchangerate-api.com/v4/latest/USD",
                timeout=8
            ).json()
            azn_rate = float(fx["rates"]["AZN"])
        except Exception:
            azn_rate = 1.7  # təxmini

        gold_azn   = gold_usd   * azn_rate
        silver_azn = silver_usd * azn_rate

        # 1 troy oz = 31.1035 qram
        g_per_gram_usd = gold_usd   / 31.1035
        g_per_gram_azn = gold_azn   / 31.1035
        s_per_gram_usd = silver_usd / 31.1035
        s_per_gram_azn = silver_azn / 31.1035

        karats = [
            ("999 (24K)", 1.000),
            ("750 (18K)", 0.750),
            ("585 (14K)", 0.585),
            ("375 (9K)",  0.375),
        ]

        gold_table = ""
        for name, ratio in karats:
            g_azn = round(g_per_gram_azn * ratio, 2)
            g_usd = round(g_per_gram_usd * ratio, 2)
            gold_table += f"  • {name}: *{g_azn} ₼*/q  ({g_usd} $)\n"

        silver_table = (
            f"  • 999: *{round(s_per_gram_azn,2)} ₼*/q  ({round(s_per_gram_usd,2)} $)\n"
            f"  • 925: *{round(s_per_gram_azn*0.925,2)} ₼*/q\n"
            f"  • 875: *{round(s_per_gram_azn*0.875,2)} ₼*/q\n"
        )

        msg = (
            "🪙 *ANLIQ METAL QİYMƏTLƏRİ*\n"
            "_(Beynəlxalq bazar — London Fix)_\n\n"
            "🥇 *QIZIL* (1 qram)\n"
            f"{gold_table}\n"
            "🥈 *GÜMÜŞ* (1 qram)\n"
            f"{silver_table}\n"
            f"💱 1 USD ≈ {azn_rate} ₼\n\n"
            "⚠️ _Qiymətlər məlumat üçündür. Alış qiyməti bazara görə fərqlənə bilər._"
        )
        return msg

    except Exception as e:
        logger.error(f"Metal qiymət xətası: {e}")
        return "❌ Qiymət alına bilmədi. Bir az sonra yenidən cəhd edin."


# ─────────────────────────────────────────────
# TAP.AZ LİNK ANALİZİ
# ─────────────────────────────────────────────
def parse_tap_link(url: str):
    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        # Əvvəlcə ana səhifəyə gir (cookie almaq üçün)
        session.get("https://tap.az", timeout=10)

        r = session.get(url, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        listings = []

        # Tap.az elan card-larını tap
        items = soup.select("div.products-i, article.products-i")

        for item in items[:15]:
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
                link_el = item.select_one("a[href]")

                title = title_el.get_text(strip=True) if title_el else "?"
                price_raw = price_el.get_text(strip=True) if price_el else "?"
                href = link_el["href"] if link_el else ""
                link = ("https://tap.az" + href) if href.startswith("/") else href

                listings.append({
                    "title": title,
                    "price": price_raw,
                    "link": link
                })
            except Exception:
                continue

        if not listings:
            return (
                "❌ *Tap.az analiz edilə bilmədi.*\n\n"
                "Sayt blok qoymuş ola bilər. Aşağıdakı üsulu sına:\n"
                "1. Tap.az-da istədiyini axtar\n"
                "2. Axtarış URL-ni tam kopyala\n"
                "3. Bura göndər\n\n"
                "Məsələn: `https://tap.az/elanlar?q=iphone+13&price_from=&price_to=`"
            )

        # Qiymət statistikası
        prices_num = []
        for item in listings:
            try:
                cleaned = (
                    item["price"]
                    .replace("\xa0", "")
                    .replace(" ", "")
                    .replace("₼", "")
                    .replace("AZN", "")
                    .replace("man.", "")
                    .strip()
                )
                if cleaned and cleaned != "?":
                    prices_num.append(float(cleaned))
            except Exception:
                pass

        result = f"📱 *TAP.AZ ANALİZİ*\n"
        result += f"🔗 {len(listings)} elan tapıldı\n\n"

        if prices_num:
            avg = sum(prices_num) / len(prices_num)
            # Median
            sorted_p = sorted(prices_num)
            mid = len(sorted_p) // 2
            median = sorted_p[mid] if len(sorted_p) % 2 != 0 else (sorted_p[mid-1] + sorted_p[mid]) / 2

            result += (
                "💰 *Qiymət Analizi:*\n"
                f"  • 📉 Minimum: *{min(prices_num):.0f} ₼*\n"
                f"  • 📈 Maksimum: *{max(prices_num):.0f} ₼*\n"
                f"  • 📊 Orta: *{avg:.0f} ₼*\n"
                f"  • 🎯 Median: *{median:.0f} ₼*\n\n"
                f"💡 _Girov üçün tövsiyə olunan: {median*0.5:.0f}–{median*0.6:.0f} ₼_\n\n"
            )

        result += "*Elanlar:*\n"
        for i, item in enumerate(listings[:6], 1):
            result += f"{i}. {item['title'][:40]} — *{item['price']}*\n"

        return result

    except Exception as e:
        logger.error(f"Tap.az parse xətası: {e}")
        return "❌ Link analiz edilə bilmədi. Linki yoxlayın."


# ─────────────────────────────────────────────
# HANDLERS
# ─────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🥇 Qızıl / Gümüş Qiymətlər", callback_data="metals")],
        [InlineKeyboardButton("📱 Tap.az Analiz — Necə İstifadə?", callback_data="tap_help")],
    ]
    await update.message.reply_text(
        "👋 Salam! *Girov Analiz Botu*\n\n"
        "🔹 Anlıq qızıl & gümüş qiymətlər (əyara görə)\n"
        "🔹 Tap.az-dan ikinci el telefon bazar analizi\n\n"
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

    elif query.data == "tap_help":
        await query.message.reply_text(
            "📋 *Tap.az Analiz Necə İşləyir?*\n\n"
            "1️⃣ [tap.az](https://tap.az) saytına keç\n"
            "2️⃣ Telefon adını axtar (məs: `iPhone 13 128GB`)\n"
            "3️⃣ Axtarış nəticəsinin *URL-ni* kopyala\n"
            "4️⃣ Həmin linki bura göndər ✅\n\n"
            "*Nümunə link:*\n"
            "`https://tap.az/elanlar?q=iphone+13`\n\n"
            "Bot sənə min/max/orta qiymət və girov tövsiyəsi verəcək 📊",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if "tap.az" in text.lower():
        msg = await update.message.reply_text("⏳ Tap.az analiz edilir...")
        result = parse_tap_link(text)
        await msg.edit_text(result, parse_mode="Markdown", disable_web_page_preview=True)

    elif any(w in text.lower() for w in ["qizil", "qızıl", "gumus", "gümüş", "metal", "qiymət", "qiymet", "gold", "silver"]):
        msg = await update.message.reply_text("⏳ Anlıq qiymətlər alınır...")
        result = get_gold_silver_prices()
        await msg.edit_text(result, parse_mode="Markdown")

    else:
        keyboard = [
            [InlineKeyboardButton("🥇 Qızıl / Gümüş", callback_data="metals")],
            [InlineKeyboardButton("📱 Tap.az Necə?", callback_data="tap_help")],
        ]
        await update.message.reply_text(
            "❓ Aşağıdan seçin və ya tap.az linkini göndərin:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def metals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Anlıq qiymətlər alınır...")
    result = get_gold_silver_prices()
    await msg.edit_text(result, parse_mode="Markdown")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN tapılmadı! Railway Variables-da əlavə et.")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("metals",  metals_command))
    app.add_handler(CommandHandler("qizil",   metals_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("✅ Bot işə düşdü!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
