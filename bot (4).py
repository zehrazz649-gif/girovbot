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

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "az,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# ─── DEBUG command ─────────────────────────────────────────────────────
async def debug_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Bağlantı test edilir...")
    results = []

    test_urls = [
        ("https://api.gold-api.com/price/XAU", "gold-api.com"),
        ("https://metals.live/api/spot", "metals.live"),
        ("https://cbar.az/currencies/21-05-2025.xml", "cbar.az"),
        ("https://tap.az/elanlar?keywords=iphone&category_id=743", "tap.az"),
    ]

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for url, name in test_urls:
            try:
                r = await client.get(url, headers=BROWSER_HEADERS)
                body_preview = r.text[:80].replace('\n', ' ')
                results.append(f"{'✅' if r.status_code==200 else '❌'} {name}: {r.status_code} | {body_preview}")
            except Exception as e:
                results.append(f"❌ {name}: XƏTA — {str(e)[:60]}")

    await msg.edit_text("```\n" + "\n\n".join(results) + "\n```", parse_mode="Markdown")


# ─── AZN rate ──────────────────────────────────────────────────────────
async def get_azn_rate() -> float:
    try:
        today = date.today().strftime("%d-%m-%Y")
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://cbar.az/currencies/{today}.xml")
            if r.status_code == 200:
                from xml.etree import ElementTree as ET
                root = ET.fromstring(r.content)
                for val in root.iter("Val"):
                    if val.get("Code") == "USD":
                        return float(val.find("Value").text.replace(",", "."))
    except Exception:
        pass
    return 1.7


# ─── Metal prices ──────────────────────────────────────────────────────
async def get_metal_prices() -> str:
    rate = await get_azn_rate()
    gold, silver = None, None
    source_used = "?"
    errors = []

    async with httpx.AsyncClient(timeout=15, headers=BROWSER_HEADERS, follow_redirects=True) as client:

        # 1. gold-api.com
        try:
            rg = await client.get("https://api.gold-api.com/price/XAU")
            rs = await client.get("https://api.gold-api.com/price/XAG")
            if rg.status_code == 200:
                data = rg.json()
                gold = float(data.get("price", 0) or data.get("bid", 0)) or None
            if rs.status_code == 200:
                data = rs.json()
                silver = float(data.get("price", 0) or data.get("bid", 0)) or None
            if gold:
                source_used = "gold-api.com"
        except Exception as e:
            errors.append(f"gold-api: {e}")

        # 2. metals.live
        if not gold:
            try:
                r = await client.get("https://metals.live/api/spot")
                if r.status_code == 200:
                    for item in r.json():
                        if item.get("gold"): gold = float(item["gold"])
                        if item.get("silver"): silver = float(item["silver"])
                    if gold: source_used = "metals.live"
            except Exception as e:
                errors.append(f"metals.live: {e}")

        # 3. goldprice.org
        if not gold:
            try:
                r = await client.get(
                    "https://data-asg.goldprice.org/dbXRates/USD",
                    headers={**BROWSER_HEADERS, "Referer": "https://goldprice.org/"}
                )
                if r.status_code == 200:
                    items = r.json().get("items", [{}])
                    if items:
                        gold = items[0].get("xauPrice")
                        silver = items[0].get("xagPrice")
                    if gold: source_used = "goldprice.org"
            except Exception as e:
                errors.append(f"goldprice: {e}")

        # 4. Scrape kitco.com (reliable, static prices in HTML)
        if not gold:
            try:
                r = await client.get("https://www.kitco.com/gold-price-today-usa/")
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    # Look for price in meta or structured data
                    for script in soup.find_all("script", type="application/ld+json"):
                        try:
                            data = json.loads(script.string)
                            if isinstance(data, dict) and "price" in str(data):
                                prices = re.findall(r'"price":\s*"?([\d.]+)"?', script.string)
                                if prices:
                                    gold = float(prices[0])
                                    source_used = "kitco.com"
                                    break
                        except:
                            pass
                    if not gold:
                        # Try direct text search
                        text = soup.get_text()
                        m = re.search(r'Gold[^\d]*([\d,]+\.?\d*)\s*USD', text)
                        if m:
                            gold = float(m.group(1).replace(',', ''))
                            source_used = "kitco.com"
            except Exception as e:
                errors.append(f"kitco: {e}")

    if not gold:
        err_str = " | ".join(errors[:2])
        return f"❌ Metal qiymətləri tapılmadı.\nXəta: `{err_str}`"

    g_gram = gold / 31.1035
    s_gram = (silver or 0) / 31.1035

    lines = [f"💰 *Metal Qiymətləri (Anlıq)*\n"]
    lines.append(f"🥇 *Qızıl*")
    lines.append(f"  • 1 troy oz: ${gold:,.2f} = *{gold*rate:,.2f} ₼*")
    lines.append(f"  • 1 qram:    ${g_gram:,.2f} = *{g_gram*rate:,.2f} ₼*")
    if silver:
        lines.append(f"\n🥈 *Gümüş*")
        lines.append(f"  • 1 troy oz: ${silver:,.2f} = *{silver*rate:,.2f} ₼*")
        lines.append(f"  • 1 qram:    ${s_gram:,.4f} = *{s_gram*rate:,.4f} ₼*")
    lines.append(f"\n_CBAR USD/AZN: {rate} | Mənbə: {source_used}_")
    return "\n".join(lines)


# ─── tap.az scraper ────────────────────────────────────────────────────
async def get_phone_price(model: str) -> str:
    query = model.strip().replace(" ", "+")
    url = f"https://tap.az/elanlar?keywords={query}&category_id=743"
    prices = []
    debug_info = []

    tap_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "az-AZ,az;q=0.9,ru;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    }

    async with httpx.AsyncClient(timeout=25, headers=tap_headers, follow_redirects=True) as client:
        try:
            r = await client.get(url)
            debug_info.append(f"status={r.status_code}, len={len(r.text)}")

            if r.status_code == 200:
                text = r.text
                soup = BeautifulSoup(text, "html.parser")

                # Method 1: JSON-LD structured data
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string or "")
                        # Look for offers/price
                        data_str = json.dumps(data)
                        found = re.findall(r'"price":\s*"?([\d.]+)"?', data_str)
                        for f in found:
                            val = float(f)
                            if 20 < val < 60000:
                                prices.append(int(val))
                    except:
                        pass

                # Method 2: Standard CSS selectors
                for sel in [".price-val", ".product-price", ".lot-price",
                            "[class*='price']", "[data-price]"]:
                    for el in soup.select(sel):
                        txt = el.get_text(strip=True)
                        nums = re.findall(r"(\d[\d\s]{1,5})\s*[₼m]", txt)
                        for n in nums:
                            val = int(n.replace(" ", ""))
                            if 20 < val < 60000:
                                prices.append(val)

                # Method 3: Scan all ₼ occurrences in HTML
                if not prices:
                    all_prices = re.findall(r"(\d[\d\s]{1,5})\s*₼", text)
                    for n in all_prices:
                        val = int(n.replace(" ", ""))
                        if 20 < val < 60000:
                            prices.append(val)

                # Method 4: data attributes
                if not prices:
                    for el in soup.find_all(attrs={"data-price": True}):
                        try:
                            val = int(float(el["data-price"]))
                            if 20 < val < 60000:
                                prices.append(val)
                        except:
                            pass

                debug_info.append(f"prices_found={len(prices)}")

                # Check if page is JS-rendered (empty body)
                body_text = soup.get_text(strip=True)
                if len(body_text) < 500:
                    debug_info.append("JS_rendered=likely")

        except Exception as e:
            return (
                f"📱 *{model}*\n\n"
                f"❌ tap.az xəta: `{str(e)[:80]}`\n"
                f"🔗 [tap.az-da baxın]({url})"
            )

    prices = list(set(prices))
    if not prices:
        debug_str = " | ".join(debug_info)
        return (
            f"📱 *{model}*\n\n"
            f"tap.az-da qiymət tapılmadı.\n"
            f"_Debug: {debug_str}_\n\n"
            f"🔗 [tap.az-da özünüz baxın]({url})"
        )

    prices_sorted = sorted(prices)
    trim = max(1, len(prices_sorted) // 10)
    trimmed = prices_sorted[trim:-trim] if len(prices_sorted) > 5 else prices_sorted
    avg = statistics.mean(trimmed)
    median = statistics.median(trimmed)

    return (
        f"📱 *{model}*\n\n"
        f"📊 Ortalama:  *{avg:,.0f} ₼*\n"
        f"📍 Median:    *{median:,.0f} ₼*\n"
        f"⬇️ Minimum:   {min(trimmed):,} ₼\n"
        f"⬆️ Maksimum:  {max(trimmed):,} ₼\n"
        f"📋 Elan sayı: {len(prices)}\n\n"
        f"🔗 [tap.az-da bax]({url})"
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


# ─── Handlers ──────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Girov Qiymət Botu*\n\nNə etmək istəyirsiniz?",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if ctx.user_data.get("waiting_search"):
        ctx.user_data["waiting_search"] = False
        msg = await update.message.reply_text(
            f"🔍 *{text}* axtarılır...", parse_mode="Markdown"
        )
        result = await get_phone_price(text)
        await msg.edit_text(result, parse_mode="Markdown",
                            disable_web_page_preview=True,
                            reply_markup=back_keyboard())
        return

    phone_kws = ["iphone", "samsung", "xiaomi", "huawei", "redmi", "oppo",
                 "realme", "nokia", "poco", "oneplus", "pixel", "galaxy", "honor"]
    if any(k in text.lower() for k in phone_kws):
        msg = await update.message.reply_text(
            f"🔍 *{text}* axtarılır...", parse_mode="Markdown"
        )
        result = await get_phone_price(text)
        await msg.edit_text(result, parse_mode="Markdown",
                            disable_web_page_preview=True,
                            reply_markup=back_keyboard())
    else:
        await update.message.reply_text(
            "Nə etmək istəyirsiniz?", reply_markup=main_menu_keyboard()
        )

async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "home":
        await query.edit_message_text(
            "👋 *Girov Qiymət Botu*\n\nNə etmək istəyirsiniz?",
            parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )
    elif data == "brands_menu":
        await query.edit_message_text(
            "📱 *Brend seçin:*", parse_mode="Markdown",
            reply_markup=brands_keyboard()
        )
    elif data.startswith("brand:"):
        brand = data.split("brand:", 1)[1]
        if brand == "✏️ Özüm yazım":
            ctx.user_data["waiting_search"] = True
            await query.edit_message_text(
                "✏️ *Telefon modelini yazın:*\n\nNümunə: `iPhone 13 128gb`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Geri", callback_data="brands_menu")
                ]])
            )
        else:
            await query.edit_message_text(
                f"📱 *{brand}* — model seçin:",
                parse_mode="Markdown", reply_markup=models_keyboard(brand)
            )
    elif data.startswith("model:"):
        model = data.split("model:", 1)[1]
        await query.edit_message_text(
            f"🔍 *{model}* axtarılır...", parse_mode="Markdown"
        )
        result = await get_phone_price(model)
        await query.edit_message_text(
            result, parse_mode="Markdown",
            disable_web_page_preview=True, reply_markup=back_keyboard()
        )
    elif data == "metals":
        await query.edit_message_text("⏳ Qiymətlər yüklənir...")
        result = await get_metal_prices()
        await query.edit_message_text(
            result, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Yenilə", callback_data="metals"),
                InlineKeyboardButton("🏠 Ana menyu", callback_data="home"),
            ]])
        )
    elif data == "manual_search":
        ctx.user_data["waiting_search"] = True
        await query.edit_message_text(
            "✏️ *Telefon modelini yazın:*\n\n"
            "Nümunə: `iPhone 14 Pro 256gb`\n"
            "və ya: `Samsung Galaxy A54`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Geri", callback_data="brands_menu")
            ]])
        )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🤖 Bot işə düşdü...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
