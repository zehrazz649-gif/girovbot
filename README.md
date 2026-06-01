# 🤖 Girov Analiz Botu

Qızıl/gümüş anlıq qiymət və Tap.az ikinci el telefon analizi üçün Telegram botu.

## Funksiyalar
- 🥇 Qızıl qiyməti (24K, 18K, 14K, 9K) — AZN və USD
- 🥈 Gümüş qiyməti (999, 925, 875) — AZN və USD
- 📱 Tap.az axtarış linkini analiz edib min/max/orta qiymət göstərir

---

## Railway-də Deploy (Pulsuz)

### 1. GitHub-a yüklə
```bash
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/SƏNIN_USERNAME/pawn-bot.git
git push -u origin main
```

### 2. Railway qeydiyyat
1. [railway.app](https://railway.app) → **Login with GitHub**
2. **New Project** → **Deploy from GitHub repo**
3. Repo-nu seç

### 3. Environment Variable əlavə et
Railway dashboard-da:
- **Variables** tabına keç
- `+ New Variable` düyməsinə bas
- **Name:** `TELEGRAM_BOT_TOKEN`
- **Value:** BotFather-dan aldığın yeni token
- **Add** düyməsinə bas

### 4. Deploy
Railway avtomatik deploy edəcək. **Logs** tabında `Bot işə düşdü...` yazısını görəcəksən.

---

## Yerli Test (İstəyə görə)

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="TOKENINI_BUR_YAZ"
python bot.py
```

---

## Tap.az Necə İstifadə Edilir

1. [tap.az](https://tap.az) saytına get
2. Axtarış yerinə telefon adı yaz (məs: `iPhone 13`)
3. Axtarış nəticəsinin URL-ni kopyala
4. Bota göndər

Məsələn: `https://tap.az/elanlar?q=iphone+13`

---

## Komandalar
- `/start` — Ana menyu
- `/metals` — Anlıq qızıl/gümüş qiymətlər  
- `/qizil` — Eyni funksiya
