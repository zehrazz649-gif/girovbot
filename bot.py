import os
import re
import statistics
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler,
    ConversationHandler
)
import httpx
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN", "8707881255:AAGGHKw-_71M3qgEaKmCnCCvAZEM_5xPJAg")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "az,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ─── Phone brands & popular models ────────────────────────────────────
BRANDS = {
    "Apple iPhone": [
        "iPhone 16 Pro Max", "iPhone 16 Pro", "iPhone 16 Plus", "iPhone 16",
        "iPhone 15 Pro Max", "iPhone 15 Pro", "iPhone 15 Plus", "iPhone 15",
        "iPhone 14 Pro Max", "iPhone 14 Pro", "iPhone 14 Plus", "iPhone 14",
        "iPhone 13 Pro Max", "iPhone 13 Pro", "iPhone 13 mini", "iPhone 13",
        "iPhone 12 Pro Max", "iPhone 12 Pro", "iPhone 12 mini", "iPhone 12",
        "iPhone 11 Pro Max", "iPhone 11 Pro", "iPhone 11",
        "iPhone XS Max", "iPhone XS", "iPhone XR", "iPhone X",
        "iPhone SE (2022)", "iPhone SE (2020)",
    ],
    "Samsung Galaxy": [
        "Galaxy S24 Ultra", "Galaxy S24+", "Galaxy S24",
        "Galaxy S23 Ultra", "Galaxy S23+", "Galaxy S23",
        "Galaxy S22 Ultra", "Galaxy S22+", "Galaxy S22",
        "Galaxy S21 Ultra", "Galaxy S21+", "Galaxy S21",
        "Galaxy A55", "Galaxy A54", "Galaxy A53", "Galaxy A52",
        "Galaxy A35", "Galaxy A34", "Galaxy A33", "Galaxy A32",
        "Galaxy A15", "Galaxy A14", "Galaxy A13",
        "Galaxy Note 20 Ultra", "Galaxy Note 20",
        "Galaxy Z Fold 5", "Galaxy Z Fold 4", "Galaxy Z Flip 5", "Galaxy Z Flip 4",
    ],
    "Xiaomi": [
        "Xiaomi 14 Ultra", "Xiaomi 14 Pro", "Xiaomi 14",
        "Xiaomi 13 Ultra", "Xiaomi 13 Pro", "Xiaomi 13",
        "Xiaomi 12 Pro", "Xiaomi 12",
        "Redmi Note 13 Pro+", "Redmi Note 13 Pro", "Redmi Note 13",
        "Redmi Note 12 Pro+", "Redmi Note 12 Pro", "Redmi Note 12",
        "Redmi Note 11 Pro", "Redmi Note 11",
        "Redmi 13C", "Redmi 12C", "Redmi 10C",
        "POCO X6 Pro", "POCO X6", "POCO X5 Pro", "POCO X5",
        "POCO F5 Pro", "POCO F5", "POCO M6 Pro",
    ],
    "Huawei": [
        "Huawei P60 Pro", "Huawei P60",
        "Huawei P50 Pro", "Huawei P50",
        "Huawei P40 Pro+", "Huawei P40 Pro", "Huawei P40",
        "Huawei P30 Pro", "Huawei P30",
        "Huawei Mate 60 Pro", "Huawei Mate 50 Pro", "Huawei Mate 40 Pro",
        "Huawei Nova 11 Pro", "Huawei Nova 10 Pro", "Huawei Nova 9",
        "Honor 90 Pro", "Honor 90", "Honor 80 Pro",
    ],
    "OPPO": [
        "OPPO Find X7 Ultra", "OPPO Find X6 Pro",
        "OPPO Reno 11 Pro", "OPPO Reno 11",
        "OPPO Reno 10 Pro+", "OPPO Reno 10 Pro", "OPPO Reno 10",
        "OPPO A98", "OPPO A78", "OPPO A58", "OPPO A38",
        "OnePlus 12", "OnePlus 11", "OnePlus Nord 3", "OnePlus Nord CE 3",
    ],
    "Realme": [
        "Realme GT 5 Pro", "Realme GT 5",
        "Realme 11 Pro+", "Realme 11 Pro", "Realme 11",
        "Realme 10 Pro+", "Realme 10 Pro", "Realme 10",
        "Realme C67", "Realme C55", "Realme C53", "Realme C35",
        "Realme Narzo 60 Pro", "Realme Narzo 60",
    ],
    "Nokia": [
        "Nokia G60", "Nokia G42", "Nokia G22", "Nokia G21",
        "Nokia X30", "Nokia X20", "Nokia X10",
        "Nokia C32", "Nokia C22", "Nokia C12",
    ],
    "Digər": [],  # manual search
}

BRAND_KEYS = list(BRANDS.keys())

# ─── Gold & Silver ─────────────────────────────────────────────────────
async def get_metal_prices() -> dict:
    result = {"gold_usd": None, "silver_usd": None, "azn_rate": 1.7}
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        # CBAR AZN rate
        try:
            from datetime import date
            today = date.today().strftime("%d-%m-%Y")
            r = await client.get(f"https://cbar.az/currencies/{today}.xml")
            if r.status_code == 200:
                from xml.etree import ElementTree as ET
                root = ET.fromstring(r.content)
                for val in root.iter("Val"):
                    if val.get("Code") == "USD":
                        result["azn_rate"] = float(val.find("Value").text.replace(",", "."))
        except Exception:
            pass

        # Gold/Silver price
        try:
            r = await client.get(
                "https://data-asg.goldprice.org/dbXRates/USD",
                headers={**HEADERS, "Referer": "https://goldprice.org/"}
            )
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [{}])
                if items:
                    result["gold_usd"] = items[0].get("xauPrice")
                    result["silver_usd"] = items[0].get("xagPrice")
        except Exception:
            pass

        # Fallback
        if not result["gold_usd"]:
            try:
                r = await client.get("https://metals.live/api/spot")
                if r.status_code == 200:
                    for item in r.json():
                        if item.get("gold"):
                            result["gold_usd"] = item["gold"]
                        if item.get("silver"):
                            result["silver_usd"] = item["silver"]
            except Exception:
                pass
    return result


def format_metal_prices(prices: dict) -> str:
    rate = prices.get("azn_rate") or 1.7
    gold = prices.get("gold_usd")
    silver = prices.get("silver_usd")
    lines = ["💰 *Metal Qiymətləri (Anlıq)*\n"]
    if gold:
        gold_gram_usd = gold / 31.1035
        lines.append(f"🥇 *Qızıl*")
        lines.append(f"  • 1 troy oz: ${gold:,.2f} = {gold*rate:,.2f} ₼")
        lines.append(f"  • 1 qram:    ${gold_gram_usd:,.2f} = {gold_gram_usd*rate:,.2f} ₼")
    else:
        lines.append("🥇 Qızıl: məlumat tapılmadı")
    lines.append("")
    if silver:
        silver_gram_usd = silver / 31.1035
        lines.append(f"🥈 *Gümüş*")
        lines.append(f"  • 1 troy oz: ${silver:,.2f} = {silver*rate:,.2f} ₼")
        lines.append(f"  • 1 qram:    ${silver_gram_usd:,.4f} = {silver_gram_usd*rate:,.4f} ₼")
    else:
        lines.append("🥈 Gümüş: məlumat tapılmadı")
    lines.append(f"\n_CBAR USD/AZN: {rate}_")
    return "\n".join(lines)


# ─── tap.az scraper ────────────────────────────────────────────────────
async def search_tap_az(model: str) -> dict:
    query = model.strip().replace(" ", "+")
    url = f"https://tap.az/elanlar?keywords={query}&category_id=743"
    prices = []
    async with httpx.AsyncClient(timeout=25, headers=HEADERS, follow_redirects=True) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            # Try multiple price selectors
            for selector in [".price-val", ".product-price", "[class*='price']"]:
                els = soup.select(selector)
                for el in els:
                    txt = el.get_text(strip=True)
                    nums = re.findall(r"(\d[\d\s]{1,5})\s*₼", txt)
                    for n in nums:
                        val = int(n.replace(" ", ""))
                        if 20 < val < 50000:
                            prices.append(val)
                if prices:
                    break

            # Fallback: scan all text for ₼ amounts
            if not prices:
                all_text = soup.get_text()
                found = re.findall(r"(\d[\d\s]{1,5})\s*₼", all_text)
                for f in found:
                    val = int(f.replace(" ", ""))
                    if 20 < val < 50000:
                        prices.append(val)

        except Exception as e:
            return {"error": str(e), "url": url, "prices": [], "query": model}

    return {"prices": list(set(prices)), "url": url, "query": model}


def format_phone_result(data: dict) -> str:
    if data.get("error"):
        return f"❌ Xəta: {data['error']}"
    prices = data["prices"]
    model = data["query"]
    url = data["url"]
    if not prices:
        return (
            f"📱 *{model}*\n\n"
            f"tap.az-da qiymət tapılmadı.\n"
            f"🔗 [Özünüz baxın]({url})"
        )
    prices_sorted = sorted(prices)
    trim = max(1, len(prices_sorted) // 10)
    trimmed = prices_sorted[trim:-trim] if len(prices_sorted) > 5 else prices_sorted
    avg = statistics.mean(trimmed)
    median = statistics.median(trimmed)
    mn = min(trimmed)
    mx = max(trimmed)
    return (
        f"📱 *{model}*\n\n"
        f"📊 Ortalama:  *{avg:,.0f} ₼*\n"
        f"📍 Median:    *{median:,.0f} ₼*\n"
        f"⬇️ Minimum:   {mn:,} ₼\n"
        f"⬆️ Maksimum:  {mx:,} ₼\n"
        f"📋 Elan sayı: {len(prices)}\n\n"
        f"🔗 [tap.az-da bax]({url})"
    )


# ─── Keyboards ─────────────────────────────────────────────────────────
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Telefon Qiyməti", callback_data="brands_menu")],
        [InlineKeyboardButton("🥇 Qızıl & Gümüş", callback_data="metals")],
        [InlineKeyboardButton("✏️ Özüm yazım", callback_data="manual_search")],
    ])


def brands_keyboard():
    rows = []
    for i in range(0, len(BRAND_KEYS) - 1, 2):
        row = [InlineKeyboardButton(BRAND_KEYS[i], callback_data=f"brand:{BRAND_KEYS[i]}")]
        if i + 1 < len(BRAND_KEYS):
            row.append(InlineKeyboardButton(BRAND_KEYS[i+1], callback_data=f"brand:{BRAND_KEYS[i+1]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("✏️ Özüm yazım", callback_data="manual_search")])
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
    rows.append([InlineKeyboardButton("🔙 Geri", callback_data="brands_menu")])
    return InlineKeyboardMarkup(rows)


# ─── Handlers ──────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Girov Qiymət Botu*\n\n"
        "Nə etmək istəyirsiniz?",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )


async def metals_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Yüklənir...")
    prices = await get_metal_prices()
    await msg.edit_text(
        format_metal_prices(prices),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Yenilə", callback_data="metals"),
            InlineKeyboardButton("🏠 Ana menyu", callback_data="home")
        ]])
    )


WAITING_SEARCH = 1

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if ctx.user_data.get("waiting_search"):
        ctx.user_data["waiting_search"] = False
        msg = await update.message.reply_text(f"🔍 *{text}* axtarılır...", parse_mode="Markdown")
        data = await search_tap_az(text)
        result = format_phone_result(data)
        await msg.edit_text(
            result, parse_mode="Markdown", disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Brendlər", callback_data="brands_menu"),
                InlineKeyboardButton("🏠 Ana menyu", callback_data="home")
            ]])
        )
        return

    phone_kws = ["iphone", "samsung", "xiaomi", "huawei", "redmi", "oppo",
                 "realme", "nokia", "poco", "oneplus", "pixel", "galaxy", "honor"]
    if any(k in text.lower() for k in phone_kws):
        msg = await update.message.reply_text(f"🔍 *{text}* axtarılır...", parse_mode="Markdown")
        data = await search_tap_az(text)
        result = format_phone_result(data)
        await msg.edit_text(
            result, parse_mode="Markdown", disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Brendlər", callback_data="brands_menu"),
                InlineKeyboardButton("🏠 Ana menyu", callback_data="home")
            ]])
        )
    else:
        await update.message.reply_text(
            "Nə etmək istəyirsiniz?",
            reply_markup=main_menu_keyboard()
        )


async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "home":
        await query.edit_message_text(
            "👋 *Girov Qiymət Botu*\n\nNə etmək istəyirsiniz?",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )

    elif data == "brands_menu":
        await query.edit_message_text(
            "📱 *Brend seçin:*",
            parse_mode="Markdown",
            reply_markup=brands_keyboard()
        )

    elif data.startswith("brand:"):
        brand = data.split("brand:", 1)[1]
        if brand == "Digər":
            ctx.user_data["waiting_search"] = True
            await query.edit_message_text(
                "✏️ *Telefon modelini yazın:*\n\n"
                "Nümunə: `iPhone 13 128gb` və ya `Samsung A52`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Geri", callback_data="brands_menu")
                ]])
            )
        else:
            models = BRANDS.get(brand, [])
            if models:
                await query.edit_message_text(
                    f"📱 *{brand}* — model seçin:",
                    parse_mode="Markdown",
                    reply_markup=models_keyboard(brand)
                )
            else:
                ctx.user_data["waiting_search"] = True
                await query.edit_message_text(
                    f"✏️ *{brand}* modelini yazın:",
                    parse_mode="Markdown"
                )

    elif data.startswith("model:"):
        model = data.split("model:", 1)[1]
        await query.edit_message_text(
            f"🔍 *{model}* tap.az-da axtarılır...",
            parse_mode="Markdown"
        )
        result_data = await search_tap_az(model)
        result_text = format_phone_result(result_data)
        await query.edit_message_text(
            result_text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Brendlər", callback_data="brands_menu"),
                InlineKeyboardButton("🏠 Ana menyu", callback_data="home")
            ]])
        )

    elif data == "metals":
        await query.edit_message_text("⏳ Yüklənir...")
        prices = await get_metal_prices()
        await query.edit_message_text(
            format_metal_prices(prices),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Yenilə", callback_data="metals"),
                InlineKeyboardButton("🏠 Ana menyu", callback_data="home")
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


# ─── Main ──────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("metaller", metals_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🤖 Bot işə düşdü...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
