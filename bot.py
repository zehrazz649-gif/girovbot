import os
import re
import json
import statistics
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8707881255:AAGGHKw-_71M3qgEaKmCnCCvAZEM_5xPJAg")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "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")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_HEADERS = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

# ─── Claude API helper ─────────────────────────────────────────────────
async def ask_claude(prompt: str, use_search: bool = True) -> str:
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    if use_search:
        payload["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(ANTHROPIC_URL, headers=ANTHROPIC_HEADERS, json=payload)
        r.raise_for_status()
        data = r.json()
        texts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        return "\n".join(texts).strip()


# ─── Metal prices via Claude web search ───────────────────────────────
async def get_metal_prices() -> str:
    prompt = """Search for current gold and silver spot prices right now.
Return ONLY a JSON object, no markdown, no explanation:
{
  "gold_usd_oz": <number>,
  "silver_usd_oz": <number>,
  "azn_rate": <CBAR USD/AZN rate, use 1.7 if not found>
}"""
    try:
        response = await ask_claude(prompt, use_search=True)
        # Extract JSON
        match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            gold = float(data.get("gold_usd_oz", 0))
            silver = float(data.get("silver_usd_oz", 0))
            rate = float(data.get("azn_rate", 1.7))
            gold_gram = gold / 31.1035
            silver_gram = silver / 31.1035
            return (
                f"💰 *Metal Qiymətləri (Anlıq)*\n\n"
                f"🥇 *Qızıl*\n"
                f"  • 1 troy oz: ${gold:,.2f} = {gold*rate:,.2f} ₼\n"
                f"  • 1 qram:    ${gold_gram:,.2f} = {gold_gram*rate:,.2f} ₼\n\n"
                f"🥈 *Gümüş*\n"
                f"  • 1 troy oz: ${silver:,.2f} = {silver*rate:,.2f} ₼\n"
                f"  • 1 qram:    ${silver_gram:,.4f} = {silver_gram*rate:,.4f} ₼\n\n"
                f"_CBAR USD/AZN: {rate}_"
            )
    except Exception as e:
        pass
    return "❌ Metal qiymətləri alınmadı. Bir az sonra yenidən cəhd edin."


# ─── Phone price via Claude web search ────────────────────────────────
async def get_phone_price(model: str) -> str:
    prompt = f"""Search tap.az for "{model}" second-hand phone prices in Azerbaijan.
Look at current listings on tap.az and find the price range.
Return ONLY a JSON object, no markdown, no explanation:
{{
  "found": true/false,
  "min_azn": <minimum price in AZN>,
  "max_azn": <maximum price in AZN>,
  "avg_azn": <average price in AZN>,
  "count": <approximate number of listings>,
  "url": "https://tap.az/elanlar?keywords={model.replace(' ', '+')}&category_id=743"
}}
If no listings found, set found to false and other values to 0."""

    try:
        response = await ask_claude(prompt, use_search=True)
        match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            url = f"https://tap.az/elanlar?keywords={model.replace(' ', '+')}&category_id=743"
            if data.get("found") and data.get("avg_azn", 0) > 0:
                avg = float(data["avg_azn"])
                mn = float(data.get("min_azn", avg))
                mx = float(data.get("max_azn", avg))
                count = data.get("count", "?")
                return (
                    f"📱 *{model}*\n\n"
                    f"📊 Ortalama:  *{avg:,.0f} ₼*\n"
                    f"⬇️ Minimum:   {mn:,.0f} ₼\n"
                    f"⬆️ Maksimum:  {mx:,.0f} ₼\n"
                    f"📋 Elan sayı: ~{count}\n\n"
                    f"🔗 [tap.az-da bax]({url})"
                )
            else:
                return (
                    f"📱 *{model}*\n\n"
                    f"tap.az-da aktiv elan tapılmadı.\n"
                    f"🔗 [Özünüz baxın]({url})"
                )
    except Exception as e:
        pass

    url = f"https://tap.az/elanlar?keywords={model.replace(' ', '+')}&category_id=743"
    return f"❌ Axtarış zamanı xəta baş verdi.\n🔗 [tap.az-da baxın]({url})"


# ─── Phone brands & models ─────────────────────────────────────────────
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


# ─── Keyboards ─────────────────────────────────────────────────────────
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
        "👋 *Girov Qiymət Botu*\n\n"
        "Nə etmək istəyirsiniz?",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if ctx.user_data.get("waiting_search"):
        ctx.user_data["waiting_search"] = False
        msg = await update.message.reply_text(
            f"🔍 *{text}* tap.az-da axtarılır...\n⏳ 10-20 saniyə gözləyin",
            parse_mode="Markdown"
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
            f"🔍 *{text}* tap.az-da axtarılır...\n⏳ 10-20 saniyə gözləyin",
            parse_mode="Markdown"
        )
        result = await get_phone_price(text)
        await msg.edit_text(result, parse_mode="Markdown",
                           disable_web_page_preview=True,
                           reply_markup=back_keyboard())
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
                parse_mode="Markdown",
                reply_markup=models_keyboard(brand)
            )

    elif data.startswith("model:"):
        model = data.split("model:", 1)[1]
        await query.edit_message_text(
            f"🔍 *{model}* tap.az-da axtarılır...\n⏳ 10-20 saniyə gözləyin",
            parse_mode="Markdown"
        )
        result = await get_phone_price(model)
        await query.edit_message_text(
            result, parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=back_keyboard()
        )

    elif data == "metals":
        await query.edit_message_text("⏳ Qiymətlər axtarılır...")
        result = await get_metal_prices()
        await query.edit_message_text(
            result,
            parse_mode="Markdown",
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


# ─── Main ──────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🤖 Bot işə düşdü...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
