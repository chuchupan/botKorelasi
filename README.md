# 🤖 RenTech IDX Telegram Bot

Bot Telegram analisis saham Indonesia dengan metode Renaissance Technologies:
- Analisis statistik (Z-Score, Moving Average, Standar Deviasi)
- Deteksi korelasi & arbitrage antar saham
- Sentimen berita keuangan Indonesia
- Data makro ekonomi (IHSG, USD/IDR, Komoditas)
- Data alternatif (BMKG, dll)

---

## 📦 File Struktur
```
rentech_bot/
├── bot.py          # Main bot Telegram
├── scanner.py      # Engine analisis pasar
├── requirements.txt
├── Procfile        # Untuk Railway
├── runtime.txt
└── README.md
```

---

## 🚀 Cara Deploy ke Railway

### Step 1: Siapkan Bot Telegram
1. Buka Telegram, cari **@BotFather**
2. Kirim `/newbot`, ikuti instruksi
3. Copy **TOKEN** yang diberikan BotFather
4. Cari **@userinfobot** di Telegram, kirim pesan apapun
5. Copy **Chat ID** Anda

### Step 2: Upload ke GitHub
1. Buat repository baru di github.com (nama bebas, contoh: `rentech-bot`)
2. Upload semua file ini ke repository tersebut
3. Pastikan semua 6 file terupload

### Step 3: Deploy ke Railway
1. Buka **railway.app**, login dengan GitHub
2. Klik **"New Project"** → **"Deploy from GitHub repo"**
3. Pilih repository `rentech-bot` Anda
4. Tunggu Railway mendeteksi project

### Step 4: Set Environment Variables
Di Railway dashboard, buka tab **"Variables"**, tambahkan:
```
TELEGRAM_TOKEN = token_dari_botfather_anda
CHAT_ID = chat_id_anda_dari_userinfobot
```

### Step 5: Deploy
1. Klik **"Deploy"**
2. Tunggu 2-3 menit hingga status **"Active"**
3. Buka Telegram, kirim `/start` ke bot Anda

---

## 🎮 Perintah Bot

| Perintah | Fungsi |
|----------|--------|
| `/start` | Mulai bot & lihat info |
| `/scan` | Scan manual semua saham IDX |
| `/top` | Top 10 sinyal terkuat |
| `/status` | Status sistem & pasar |
| `/macro` | Data makro ekonomi |
| `/sentiment` | Sentimen berita |
| `/help` | Bantuan |

---

## 📊 Cara Baca Sinyal

- 🟢 **BUY** — Z-Score sangat rendah, harga jauh di bawah rata-rata historis, probabilitas naik tinggi
- 🔴 **SELL** — Z-Score sangat tinggi, harga jauh di atas rata-rata historis, probabilitas koreksi tinggi  
- ⚡ **ARBITRAGE** — Dua saham terkorelasi tapi harga diverge, potensi konvergensi

**Z-Score:** Angka > 2 atau < -2 berarti harga menyimpang signifikan dari rata-rata

---

## ⚠️ Disclaimer
Bot ini adalah alat analisis statistik, bukan saran investasi. Selalu lakukan riset mandiri sebelum berinvestasi.
