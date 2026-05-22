"""
Girov Qiymət Botu — Tam işlək versiya
• tap.az ikinci əl telefon qiymətləri (ScraperAPI)
• Anlıq qızıl & gümüş qiymətləri (gold-api.com)
• CBAR USD/AZN məzənnəsi
"""
import os, re, statistics, logging, urllib.parse
import httpx
from datetime import date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler,
)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN   = os.getenv("BOT_TOKEN", "8707881255:AAGGHKw-_71M3qgEaKmCnCCvAZEM_5xPJAg")
SCRAPER_KEY = os.getenv("SCRAPER_API_KEY", "54d900d64f2b1eec5d6c8ee9db274035")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"


# ═══════════════════════════════════════════
# CBAR — USD/AZN
# ═══════════════════════════════════════════
async def azn_rate() -> float:
    for delta in range(4):
        d = (date.today() - timedelta(days=delta)).strftime("%d-%m-%Y")
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"https://cbar.az/currencies/{d}.xml", headers={"User-Agent": UA})
                if r.status_code == 200 and b"<Val" in r.content:
                    from xml.etree import ElementTree as ET
                    for val in ET.fromstring(r.content).iter("Val"):
                        if val.get("Code") == "USD":
                            return float(val.find("Value").text.replace(",", "."))
        except Exception as e:
            log.warning(f"CBAR {d}: {e}")
    return 1.7


# ═══════════════════════════════════════════
# METAL QİYMƏTLƏRİ
# ═══════════════════════════════════════════
async def metal_message() -> str:
    rate = await azn_rate()
    gold = silver = None

    async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                  headers={"User-Agent": UA, "Accept": "application/json"}) as c:
        try:
            rg = await c.get("https://api.gold-api.com/price/XAU")
            if rg.status_code == 200:
                m = re.search(r'"price"\s*:\s*([\d.]+)', rg.text)
                if m: gold = float(m.group(1))
        except Exception as e:
            log.warning(f"gold XAU: {e}")
        try:
            rs = await c.get("https://api.gold-api.com/price/XAG")
            if rs.status_code == 200:
                m = re.search(r'"price"\s*:\s*([\d.]+)', rs.text)
                if m: silver = float(m.group(1))
        except Exception as e:
            log.warning(f"gold XAG: {e}")

        if not gold:
            try:
                r = await c.get("https://data-asg.goldprice.org/dbXRates/USD",
                                 headers={"User-Agent": UA, "Referer": "https://goldprice.org/"})
                if r.status_code == 200:
                    items = r.json().get("items", [])
                    if items:
                        gold = float(items[0].get("xauPrice") or 0) or None
                        silver = float(items[0].get("xagPrice") or 0) or None
            except Exception as e:
                log.warning(f"goldprice: {e}")

    if not gold:
        return "❌ Metal qiymətləri alınmadı. Bir az sonra yenidən cəhd edin."

    g, s = gold / 31.1035, (silver or 0) / 31.1035
    lines = ["💰 *Metal Qiymətləri (Anlıq)*\n",
             "🥇 *Qızıl*",
             f"  • 1 troy oz : ${gold:,.2f}  =  *{gold*rate:,.2f} ₼*",
             f"  • 1 qram    : ${g:,.2f}  =  *{g*rate:,.2f} ₼*"]
    if silver:
        lines += ["\n🥈 *Gümüş*",
                  f"  • 1 troy oz : ${silver:,.2f}  =  *{silver*rate:,.2f} ₼*",
                  f"  • 1 qram    : ${s:,.4f}  =  *{s*rate:,.4f} ₼*"]
    lines.append(f"\n_CBAR USD/AZN: {rate}_")
    return "\n".join(lines)


# ═══════════════════════════════════════════
# TAP.AZ — ScraperAPI
# ═══════════════════════════════════════════
def extract_prices(html: str) -> list:
    prices = []

    # 1. ₼ işarəsi (UTF-8 həm də encoded formaları)
    for p in re.findall(r'(\d[\d\s]{1,5})\s*(?:₼|\u20bc|&#8380;|&# 8380;)', html):
        try:
            val = int(p.replace(" ", ""))
            if 30 < val < 60000: prices.append(val)
        except: pass

    # 2. JSON içindəki price fieldləri
    for p in re.findall(r'"(?:price|Price|PRICE)"\s*:\s*"?(\d{3,5})"?', html):
        try:
            val = int(p)
            if 30 < val < 60000: prices.append(val)
        except: pass

    # 3. data-price, data-value atributları
    for p in re.findall(r'data-(?:price|value)=["\'](\d{3,5})["\']', html):
        try:
            val = int(p)
            if 30 < val < 60000: prices.append(val)
        except: pass

    # 4. AZN / manat sözü yanındakı rəqəmlər
    for p in re.findall(r'(\d{3,5})\s*(?:AZN|manat|man\.)', html, re.IGNORECASE):
        try:
            val = int(p)
            if 30 < val < 60000: prices.append(val)
        except: pass

    # 5. tap.az-ın tipik HTML: >850 ₼< və ya >850<
    for p in re.findall(r'>(\d{3,5})\s*[₼<]', html):
        try:
            val = int(p)
            if 30 < val < 60000: prices.append(val)
        except: pass

    return list(set(prices))


async def phone_message(model: str) -> str:
    tap_url = f"https://tap.az/elanlar?keywords={model.replace(' ', '+')}&category_id=743"
    scraper_url = (f"https://api.scraperapi.com/"
                   f"?api_key={SCRAPER_KEY}"
                   f"&url={urllib.parse.quote(tap_url, safe='')}"
                   f"&render=true")

    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True,
                                      headers={"User-Agent": UA}) as c:
            r = await c.get(scraper_url)
            log.info(f"ScraperAPI [{model}]: status={r.status_code}, len={len(r.text)}")
            log.info(f"HTML[1000:2000]: {r.text[1000:2000]}")

            if r.status_code != 200 or len(r.text) < 100:
                log.warning(f"Bad response: {r.text[:200]}")
                return (f"📱 *{model}*\n\n❌ tap.az cavab vermədi.\n"
                        f"🔗 [tap.az-da baxın]({tap_url})")

            prices = extract_prices(r.text)
            log.info(f"Prices extracted: {sorted(prices)[:15]}")

    except Exception as e:
        log.error(f"ScraperAPI error: {e}")
        return (f"📱 *{model}*\n\n❌ Axtarış xətası: {str(e)[:50]}\n"
                f"🔗 [tap.az-da baxın]({tap_url})")

    if not prices:
        return (f"📱 *{model}*\n\n"
                f"tap.az-da bu model üçün elan tapılmadı.\n"
                f"🔗 [tap.az-da özünüz baxın]({tap_url})")

    ps = sorted(prices)
    tr = ps[max(1, len(ps)//10) : -max(1, len(ps)//10)] if len(ps) > 5 else ps
    return (f"📱 *{model}*\n\n"
            f"📊 Ortalama :  *{statistics.mean(tr):,.0f} ₼*\n"
            f"📍 Median   :  *{statistics.median(tr):,.0f} ₼*\n"
            f"⬇️ Minimum  :  {min(tr):,} ₼\n"
            f"⬆️ Maksimum :  {max(tr):,} ₼\n"
            f"📋 Elan sayı:  ~{len(prices)}\n\n"
            f"🔗 [tap.az-da bax]({tap_url})")


# ═══════════════════════════════════════════
# MODEL SİYAHISI
# ═══════════════════════════════════════════
BRANDS = {
    "🍎 Apple iPhone": [
        "iPhone 16 Pro Max","iPhone 16 Pro","iPhone 16 Plus","iPhone 16",
        "iPhone 15 Pro Max","iPhone 15 Pro","iPhone 15 Plus","iPhone 15",
        "iPhone 14 Pro Max","iPhone 14 Pro","iPhone 14 Plus","iPhone 14",
        "iPhone 13 Pro Max","iPhone 13 Pro","iPhone 13 mini","iPhone 13",
        "iPhone 12 Pro Max","iPhone 12 Pro","iPhone 12 mini","iPhone 12",
        "iPhone 11 Pro Max","iPhone 11 Pro","iPhone 11",
        "iPhone XS Max","iPhone XS","iPhone XR","iPhone X",
        "iPhone SE 2022","iPhone SE 2020",
    ],
    "📱 Samsung": [
        "Samsung Galaxy S24 Ultra","Samsung Galaxy S24+","Samsung Galaxy S24",
        "Samsung Galaxy S23 Ultra","Samsung Galaxy S23+","Samsung Galaxy S23",
        "Samsung Galaxy S22 Ultra","Samsung Galaxy S22",
        "Samsung Galaxy A55","Samsung Galaxy A54","Samsung Galaxy A53",
        "Samsung Galaxy A35","Samsung Galaxy A34","Samsung Galaxy A15",
        "Samsung Galaxy Z Fold 5","Samsung Galaxy Z Flip 5",
        "Samsung Galaxy Note 20 Ultra","Samsung Galaxy Note 20",
    ],
    "📱 Xiaomi/Redmi": [
        "Xiaomi 14 Ultra","Xiaomi 14 Pro","Xiaomi 14",
        "Xiaomi 13 Pro","Xiaomi 13",
        "Redmi Note 13 Pro+","Redmi Note 13 Pro","Redmi Note 13",
        "Redmi Note 12 Pro","Redmi Note 12",
        "Redmi Note 11 Pro","Redmi Note 11",
        "POCO X6 Pro","POCO X5 Pro","POCO F5 Pro",
        "Redmi 13C","Redmi 12C",
    ],
    "📱 Huawei/Honor": [
        "Huawei P60 Pro","Huawei P50 Pro","Huawei P40 Pro",
        "Huawei P30 Pro","Huawei P30",
        "Huawei Mate 60 Pro","Huawei Mate 50 Pro",
        "Huawei Nova 11 Pro","Huawei Nova 10 Pro",
        "Honor 90 Pro","Honor 90","Honor Magic 5 Pro",
    ],
    "📱 OPPO/OnePlus": [
        "OPPO Find X7 Ultra","OPPO Find X6 Pro",
        "OPPO Reno 11 Pro","OPPO Reno 10 Pro","OPPO Reno 10",
        "OPPO A98","OPPO A78","OPPO A58",
        "OnePlus 12","OnePlus 11","OnePlus Nord 3",
    ],
    "📱 Realme": [
        "Realme GT 5 Pro","Realme GT 5",
        "Realme 11 Pro+","Realme 11 Pro","Realme 11",
        "Realme 10 Pro+","Realme 10 Pro",
        "Realme C67","Realme C55","Realme C53",
    ],
    "📱 Nokia": [
        "Nokia G60","Nokia G42","Nokia G22",
        "Nokia X30","Nokia X20","Nokia C32",
    ],
}
BKEYS = list(BRANDS.keys())


# ═══════════════════════════════════════════
# KLAVIATURALAR
# ═══════════════════════════════════════════
def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Telefon Qiyməti (tap.az)", callback_data="brands")],
        [InlineKeyboardButton("🥇 Qızıl & 🥈 Gümüş Qiyməti", callback_data="metals")],
        [InlineKeyboardButton("✏️ Modeli özüm yazım", callback_data="manual")],
    ])

def kb_brands():
    rows = []
    for i in range(0, len(BKEYS), 2):
        row = [InlineKeyboardButton(BKEYS[i], callback_data=f"B|{BKEYS[i]}")]
        if i+1 < len(BKEYS):
            row.append(InlineKeyboardButton(BKEYS[i+1], callback_data=f"B|{BKEYS[i+1]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("✏️ Özüm yazım", callback_data="manual"),
                 InlineKeyboardButton("🏠 Ana menyu", callback_data="home")])
    return InlineKeyboardMarkup(rows)

def kb_models(brand):
    models = BRANDS.get(brand, [])
    rows = []
    for i in range(0, len(models), 2):
        row = [InlineKeyboardButton(models[i], callback_data=f"M|{models[i]}")]
        if i+1 < len(models):
            row.append(InlineKeyboardButton(models[i+1], callback_data=f"M|{models[i+1]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Brendlər", callback_data="brands"),
                 InlineKeyboardButton("🏠 Ana menyu", callback_data="home")])
    return InlineKeyboardMarkup(rows)

def kb_back():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Brendlər", callback_data="brands"),
        InlineKeyboardButton("🏠 Ana menyu", callback_data="home"),
    ]])

def kb_metals():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Yenilə", callback_data="metals"),
        InlineKeyboardButton("🏠 Ana menyu", callback_data="home"),
    ]])


# ═══════════════════════════════════════════
# HANDLERLƏRİ
# ═══════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "👋 *Girov Qiymət Botu*\n\n"
        "• 📱 tap.az-da ikinci əl telefon qiymətləri\n"
        "• 🥇 Anlıq qızıl və gümüş qiymətləri\n\n"
        "Aşağıdan seçin:",
        parse_mode="Markdown", reply_markup=kb_main())

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if ctx.user_data.pop("awaiting_model", False):
        msg = await update.message.reply_text(
            f"🔍 *{text}* tap.az-da axtarılır...\n⏳ 20-30 saniyə gözləyin",
            parse_mode="Markdown")
        result = await phone_message(text)
        await msg.edit_text(result, parse_mode="Markdown",
                             disable_web_page_preview=True, reply_markup=kb_back())
        return
    kws = ["iphone","samsung","xiaomi","huawei","redmi","oppo","realme",
           "nokia","poco","oneplus","pixel","galaxy","honor","vivo"]
    if any(k in text.lower() for k in kws):
        msg = await update.message.reply_text(
            f"🔍 *{text}* tap.az-da axtarılır...\n⏳ 20-30 saniyə gözləyin",
            parse_mode="Markdown")
        result = await phone_message(text)
        await msg.edit_text(result, parse_mode="Markdown",
                             disable_web_page_preview=True, reply_markup=kb_back())
    else:
        await update.message.reply_text("Nə etmək istəyirsiniz?", reply_markup=kb_main())

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data

    if d == "home":
        ctx.user_data.clear()
        await q.edit_message_text("👋 *Girov Qiymət Botu*\n\nNə etmək istəyirsiniz?",
                                   parse_mode="Markdown", reply_markup=kb_main())
    elif d == "brands":
        await q.edit_message_text("📱 *Brend seçin:*",
                                   parse_mode="Markdown", reply_markup=kb_brands())
    elif d.startswith("B|"):
        brand = d[2:]
        await q.edit_message_text(f"📱 *{brand}* — model seçin:",
                                   parse_mode="Markdown", reply_markup=kb_models(brand))
    elif d.startswith("M|"):
        model = d[2:]
        await q.edit_message_text(
            f"🔍 *{model}* tap.az-da axtarılır...\n⏳ 20-30 saniyə gözləyin",
            parse_mode="Markdown")
        result = await phone_message(model)
        await q.edit_message_text(result, parse_mode="Markdown",
                                   disable_web_page_preview=True, reply_markup=kb_back())
    elif d == "metals":
        await q.edit_message_text("⏳ Anlıq qiymətlər yüklənir...")
        result = await metal_message()
        await q.edit_message_text(result, parse_mode="Markdown", reply_markup=kb_metals())
    elif d == "manual":
        ctx.user_data["awaiting_model"] = True
        await q.edit_message_text(
            "✏️ *Telefon modelini yazın:*\n\n"
            "Nümunə:\n`iPhone 13 128gb`\n`Samsung Galaxy A54`\n`Redmi Note 12`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Geri", callback_data="brands")
            ]]))


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════
def main():
    if not BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN təyin edilməyib!")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("🤖 Girov Qiymət Botu işə düşdü")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
