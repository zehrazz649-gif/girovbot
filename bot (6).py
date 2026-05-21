import os
import re
import json
import statistics
import httpx
from bs4 import BeautifulSoup
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8707881255:AAGGHKw-_71M3qgEaKmCnCCvAZEM_5xPJAg")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "az,en;q=0.9",
}

# ─── AZN rate from CBAR ────────────────────────────────────────────────
async def get_azn_rate() -> float:
    try:
        today = date.today().strftime("%d-%m-%Y")
        url = f"https://cbar.az/currencies/{today}.xml"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=HEADERS)
            # CBAR sometimes returns HTML redirect - check content type
            if r.status_code == 200 and "xml" in r.headers.get("content-type", "").lower():
                from xml.etree import ElementTree as ET
                root = ET.fromstring(r.content)
                for val in root.iter("Val"):
                    if val.get("Code") == "USD":
                        return float(val.find("Value").text.replace(",", "."))
            # Fallback: try previous day
            from datetime import timedelta
            yesterday = (date.today() - timedelta(days=1)).strftime("%d-%m-%Y")
            r2 = await client.get(f"https://cbar.az/currencies/{yesterday}.xml")
            if r2.status_code == 200:
                from xml.etree import ElementTree as ET
                try:
                    root = ET.fromstring(r2.content)
                    for val in root.iter("Val"):
                        if val.get("Code") == "USD":
                            return float(val.find("Value").text.replace(",", "."))
                except Exception:
                    pass
    except Exception:
        pass
    return 1.7


# ─── Metal prices ──────────────────────────────────────────────────────
async def get_metal_prices() -> str:
    rate = await get_azn_rate()
    gold, silver = None, None

    async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:

        # gold-api.com — confirmed 200 on Railway
        # Response: {"currency":"USD","currencySymbol":"$","exchangeRate":1.0,"name":"Gold","price":3342.15,...}
        try:
            rg = await client.get("https://api.gold-api.com/price/XAU")
            if rg.status_code == 200:
                body = rg.text  # get raw text first
                # Parse price from raw text in case json() has issues
                m = re.search(r'"price"\s*:\s*([\d.]+)', body)
                if m:
                    gold = float(m.group(1))
                else:
                    d = rg.json()
                    gold = float(d.get("price") or d.get("bid") or d.get("close") or 0) or None
        except Exception as e:
            print(f"gold-api gold error: {e}")

        try:
            rs = await client.get("https://api.gold-api.com/price/XAG")
            if rs.status_code == 200:
                body = rs.text
                m = re.search(r'"price"\s*:\s*([\d.]+)', body)
                if m:
                    silver = float(m.group(1))
                else:
                    d = rs.json()
                    silver = float(d.get("price") or d.get("bid") or d.get("close") or 0) or None
        except Exception as e:
            print(f"gold-api silver error: {e}")

        # Fallback: goldprice.org
        if not gold:
            try:
                r = await client.get(
                    "https://data-asg.goldprice.org/dbXRates/USD",
                    headers={**HEADERS, "Referer": "https://goldprice.org/"}
                )
                if r.status_code == 200:
                    items = r.json().get("items", [])
                    if items:
                        gold = items[0].get("xauPrice")
                        silver = items[0].get("xagPrice")
            except Exception:
                pass

    if not gold:
        return "❌ Metal qiymətləri hazırda əlçatan deyil. Bir az sonra yenidən cəhd edin."

    g = gold / 31.1035
    s = (silver or 0) / 31.1035

    lines = ["💰 *Metal Qiymətləri (Anlıq)*\n",
             "🥇 *Qızıl*",
             f"  • 1 troy oz: ${gold:,.2f} = *{gold*rate:,.2f} ₼*",
             f"  • 1 qram:    ${g:,.2f} = *{g*rate:,.2f} ₼*"]
    if silver:
        lines += ["\n🥈 *Gümüş*",
                  f"  • 1 troy oz: ${silver:,.2f} = *{silver*rate:,.2f} ₼*",
                  f"  • 1 qram:    ${s:,.4f} = *{s*rate:,.4f} ₼*"]
    lines.append(f"\n_CBAR USD/AZN: {rate}_")
    return "\n".join(lines)


# ─── Phone price: Google search snippets ──────────────────────────────
async def get_phone_price(model: str) -> str:
    tap_url = f"https://tap.az/elanlar?keywords={model.replace(' ', '+')}&category_id=743"
    prices = []

    # Since tap.az blocks VPS IPs, scrape Google search results
    # Google shows tap.az listing prices in search snippets
    google_query = f"site:tap.az {model} ₼"
    google_url = f"https://www.google.com/search?q={google_query.replace(' ', '+')}&num=20&hl=az"

    search_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "az-AZ,az;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
    }

    html_content = None

    async with httpx.AsyncClient(timeout=20, headers=search_headers, follow_redirects=True) as client:

        # Try 1: Google search
        try:
            r = await client.get(google_url)
            if r.status_code == 200 and len(r.text) > 500:
                html_content = r.text
                source = "google"
        except Exception:
            pass

        # Try 2: DuckDuckGo HTML search (more scraper-friendly)
        if not html_content:
            try:
                ddg_url = f"https://html.duckduckgo.com/html/?q=site:tap.az+{model.replace(' ', '+')}+manat"
                r = await client.get(ddg_url)
                if r.status_code == 200 and len(r.text) > 500:
                    html_content = r.text
                    source = "duckduckgo"
            except Exception:
                pass

        # Try 3: allorigins proxy for tap.az
        if not html_content:
            try:
                import urllib.parse
                encoded = urllib.parse.quote(tap_url)
                r = await client.get(f"https://api.allorigins.win/raw?url={encoded}")
                if r.status_code == 200 and len(r.text) > 1000 and "tap.az" in r.text:
                    html_content = r.text
                    source = "allorigins"
            except Exception:
                pass

    if not html_content:
        return (
            f"📱 *{model}*\n\n"
            f"⚠️ tap.az əlçatan deyil.\n"
            f"🔗 [tap.az-da özünüz baxın]({tap_url})"
        )

    # Extract ₼ prices from whatever HTML we got
    all_matches = re.findall(r"(\d[\d\s]{1,5})\s*[₼m]", html_content)
    for n in all_matches:
        val = int(n.replace(" ", ""))
        if 20 < val < 60000:
            prices.append(val)

    # Also try BeautifulSoup for cleaner extraction
    if prices:
        prices = list(set(prices))
        ps = sorted(prices)
        trim = max(1, len(ps) // 10)
        tr = ps[trim:-trim] if len(ps) > 5 else ps
        return (
            f"📱 *{model}*\n\n"
            f"📊 Ortalama:  *{statistics.mean(tr):,.0f} ₼*\n"
            f"📍 Median:    *{statistics.median(tr):,.0f} ₼*\n"
            f"⬇️ Minimum:   {min(tr):,} ₼\n"
            f"⬆️ Maksimum:  {max(tr):,} ₼\n"
            f"📋 Elan sayı: ~{len(prices)}\n\n"
            f"🔗 [tap.az-da bax]({tap_url})"
        )
    else:
        return (
            f"📱 *{model}*\n\n"
            f"tap.az-da qiymət tapılmadı.\n"
            f"🔗 [tap.az-da özünüz baxın]({tap_url})"
        )


# ─── Brands & models ───────────────────────────────────────────────────
BRANDS = {
    "Apple iPhone": [
        "iPhone 16 Pro Max", "iPhone 16 Pro", "iPhone 16 Plus", "iPhone 16",
        "iPhone 15 Pro Max", "iPhone 15 Pro", "iPhone 15 Plus", "iPhone 15",
        "iPhone 14 Pro Max", "iPhone 14 Pro", "iPhone 14 Plus", "iPhone 14",
        "iPhone 13 Pro Max", "iPhone 13 Pro", "iPhone 13 mini", "iPhone 13",
        "iPhone 12 Pro Max", "iPhone 12 Pro", "iPhone 12 mini", "iPhone 12",
        "iPhone 11 Pro Max", "iPhone 11 Pro", "iPhone 11",
        "iPhone XS Max", "iPhone XS", "iPhone XR", "iPhone X",
        "iPhone SE 2022", "iPhone SE 2020",
    ],
    "Samsung Galaxy": [
        "Samsung Galaxy S24 Ultra", "Samsung Galaxy S24+", "Samsung Galaxy S24",
        "Samsung Galaxy S23 Ultra", "Samsung Galaxy S23+", "Samsung Galaxy S23",
        "Samsung Galaxy S22 Ultra", "Samsung Galaxy S22",
        "Samsung Galaxy A55", "Samsung Galaxy A54", "Samsung Galaxy A53",
        "Samsung Galaxy A35", "Samsung Galaxy A34", "Samsung Galaxy A15",
        "Samsung Galaxy Z Fold 5", "Samsung Galaxy Z Flip 5",
        "Samsung Galaxy Note 20 Ultra", "Samsung Galaxy Note 20",
    ],
    "Xiaomi / Redmi": [
        "Xiaomi 14 Ultra", "Xiaomi 14 Pro", "Xiaomi 14",
        "Xiaomi 13 Pro", "Xiaomi 13",
        "Redmi Note 13 Pro+", "Redmi Note 13 Pro", "Redmi Note 13",
        "Redmi Note 12 Pro", "Redmi Note 12",
        "Redmi Note 11 Pro", "Redmi Note 11",
        "POCO X6 Pro", "POCO X5 Pro", "POCO F5 Pro",
        "Redmi 13C", "Redmi 12C",
    ],
    "Huawei / Honor": [
        "Huawei P60 Pro", "Huawei P50 Pro", "Huawei P40 Pro",
        "Huawei P30 Pro", "Huawei P30",
        "Huawei Mate 60 Pro", "Huawei Mate 50 Pro",
        "Huawei Nova 11 Pro", "Huawei Nova 10 Pro",
        "Honor 90 Pro", "Honor 90", "Honor Magic 5 Pro",
    ],
    "OPPO / OnePlus": [
        "OPPO Find X7 Ultra", "OPPO Find X6 Pro",
        "OPPO Reno 11 Pro", "OPPO Reno 10 Pro", "OPPO Reno 10",
        "OPPO A98", "OPPO A78", "OPPO A58",
        "OnePlus 12", "OnePlus 11", "OnePlus Nord 3",
    ],
    "Realme": [
        "Realme GT 5 Pro", "Realme GT 5",
        "Realme 11 Pro+", "Realme 11 Pro", "Realme 11",
        "Realme 10 Pro+", "Realme 10 Pro",
        "Realme C67", "Realme C55", "Realme C53",
    ],
    "Nokia": [
        "Nokia G60", "Nokia G42", "Nokia G22",
        "Nokia X30", "Nokia X20", "Nokia C32",
    ],
    "✏️ Özüm yazım": [],
}
BRAND_KEYS = list(BRANDS.keys())


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Telefon Qiyməti", callback_data="brands_menu")],
        [InlineKeyboardButton("🥇 Qızıl & Gümüş", callback_data="metals")],
        [InlineKeyboardButton("✏️ Model özüm yazım", callback_data="manual_search")],
    ])

def brands_keyboard():
    rows = []
    for i in range(0, len(BRAND_KEYS), 2):
        row = [InlineKeyboardButton(BRAND_KEYS[i], callback_data=f"brand:{BRAND_KEYS[i]}")]
        if i + 1 < len(BRAND_KEYS):
            row.append(InlineKeyboardButton(BRAND_KEYS[i+1], callback_data=f"brand:{BRAND_KEYS[i+1]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🏠 Ana menyu", callback_data="home")])
    return InlineKeyboardMarkup(rows)

def models_keyboard(brand: str):
    models = BRANDS.get(brand, [])
    rows = []
    for i in range(0, len(models), 2):
        row = [InlineKeyboardButton(models[i], callback_data=f"model:{models[i]}")]
        if i + 1 < len(models):
            row.append(InlineKeyboardButton(models[i+1], callback_data=f"model:{models[i+1]}"))
        rows.append(row)
    rows.append([
        InlineKeyboardButton("🔙 Geri", callback_data="brands_menu"),
        InlineKeyboardButton("✏️ Özüm yazım", callback_data="manual_search"),
    ])
    return InlineKeyboardMarkup(rows)

def back_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Brendlər", callback_data="brands_menu"),
        InlineKeyboardButton("🏠 Ana menyu", callback_data="home"),
    ]])


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Girov Qiymət Botu*\n\nNə etmək istəyirsiniz?",
        parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if ctx.user_data.get("waiting_search"):
        ctx.user_data["waiting_search"] = False
        msg = await update.message.reply_text(f"🔍 *{text}* axtarılır...", parse_mode="Markdown")
        result = await get_phone_price(text)
        await msg.edit_text(result, parse_mode="Markdown",
                            disable_web_page_preview=True, reply_markup=back_keyboard())
        return
    phone_kws = ["iphone", "samsung", "xiaomi", "huawei", "redmi", "oppo",
                 "realme", "nokia", "poco", "oneplus", "pixel", "galaxy", "honor"]
    if any(k in text.lower() for k in phone_kws):
        msg = await update.message.reply_text(f"🔍 *{text}* axtarılır...", parse_mode="Markdown")
        result = await get_phone_price(text)
        await msg.edit_text(result, parse_mode="Markdown",
                            disable_web_page_preview=True, reply_markup=back_keyboard())
    else:
        await update.message.reply_text("Nə etmək istəyirsiniz?", reply_markup=main_menu_keyboard())

async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "home":
        await query.edit_message_text("👋 *Girov Qiymət Botu*\n\nNə etmək istəyirsiniz?",
                                       parse_mode="Markdown", reply_markup=main_menu_keyboard())
    elif data == "brands_menu":
        await query.edit_message_text("📱 *Brend seçin:*", parse_mode="Markdown",
                                       reply_markup=brands_keyboard())
    elif data.startswith("brand:"):
        brand = data.split("brand:", 1)[1]
        if brand == "✏️ Özüm yazım":
            ctx.user_data["waiting_search"] = True
            await query.edit_message_text(
                "✏️ *Telefon modelini yazın:*\n\nNümunə: `iPhone 13 128gb`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="brands_menu")]]))
        else:
            await query.edit_message_text(f"📱 *{brand}* — model seçin:",
                                           parse_mode="Markdown", reply_markup=models_keyboard(brand))
    elif data.startswith("model:"):
        model = data.split("model:", 1)[1]
        await query.edit_message_text(f"🔍 *{model}* axtarılır...", parse_mode="Markdown")
        result = await get_phone_price(model)
        await query.edit_message_text(result, parse_mode="Markdown",
                                       disable_web_page_preview=True, reply_markup=back_keyboard())
    elif data == "metals":
        await query.edit_message_text("⏳ Qiymətlər yüklənir...")
        result = await get_metal_prices()
        await query.edit_message_text(result, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Yenilə", callback_data="metals"),
                InlineKeyboardButton("🏠 Ana menyu", callback_data="home"),
            ]]))
    elif data == "manual_search":
        ctx.user_data["waiting_search"] = True
        await query.edit_message_text(
            "✏️ *Telefon modelini yazın:*\n\nNümunə: `iPhone 14 Pro 256gb`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="brands_menu")]]))


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🤖 Bot işə düşdü...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
