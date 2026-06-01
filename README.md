# 🤖 Girov Analiz Botu v4

## Funksiyalar
- 🥇 Qızıl/gümüş anlıq qiymət (24K/18K/14K/9K, AZN və USD)
- 📱 Tap.az-dan telefon analizi — model adını yaz, bot axtarır

---

## Railway Deploy

### 1. Environment Variables (Railway → Variables)

| Key | Value | Qeyd |
|-----|-------|------|
| `TELEGRAM_BOT_TOKEN` | botun tokeni | BotFather-dan |
| `GOLDAPI_KEY` | goldapi.io key | goldapi.io-dan pulsuz alınır |

### goldapi.io key necə alınır (2 dəqiqə):
1. https://www.goldapi.io saytına get
2. "Get Free API Key" düyməsinə bas
3. Email ilə qeydiyyat
4. Dashboard-da key-i kopyala
5. Railway Variables-a əlavə et: `GOLDAPI_KEY` = kopyaladığın key

### 2. GitHub-a yüklə
```bash
git add .
git commit -m "v4 playwright"
git push
```
Railway avtomatik yenidən deploy edəcək.

---

## İstifadə
- `/start` — Ana menyu
- `/qizil` — Anlıq metal qiymətlər
- Telefon modeli yaz — Tap.az analizi (15-30 san)
