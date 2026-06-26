import os
import time
import requests
import numpy as np
from datetime import datetime, timezone, timedelta
from threading import Thread
from flask import Flask, request as flask_request

app = Flask(__name__)

WIB = timezone(timedelta(hours=7))
def now_wib():
    return datetime.now(WIB)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID   = os.environ.get("CHAT_ID", "")

STOCKS = [
    "BBCA","BBRI","BMRI","BBNI","BRIS","TLKM","ASII","UNVR","ICBP","KLBF",
    "INDF","PGAS","JSMR","SMGR","CPIN","PTBA","ADRO","ITMG","HRUM","ANTM",
    "INCO","MDKA","NCKL","AALI","LSIP","DSNG","MAPI","EMTK","GOTO","BUKA",
    "EXCL","ISAT","TBIG","TOWR","MTEL","BSDE","CTRA","PWON","SMRA","WIKA",
    "PTPP","ADHI","WSKT","MEDC","ELSA","ESSA","HEAL","MIKA","SIDO","MYOR",
    "ULTJ","JPFA","KAEF","DVLA","TSPC","UNTR","BRPT","TPIA","INKP","TKIM",
    "HMSP","GGRM","SCMA","MNCN","LINK","TOWR","NIKL","TINS","INTP","SMGR",
]
STOCKS = list(dict.fromkeys(STOCKS))

last_results  = []
prev_signals  = set()

# ── WEATHER CORRELATION MAP ───────────────────────────────
WEATHER_MAP = {
    'hujan': {
        'bullish': ['AALI','LSIP','DSNG'],
        'bearish': ['PTBA','ADRO','ITMG'],
        'note': 'Musim hujan → CPO naik, batubara terganggu'
    },
    'kemarau': {
        'bullish': ['PTBA','ADRO','ITMG','INCO'],
        'bearish': ['AALI','LSIP'],
        'note': 'Kemarau → tambang lancar, CPO terancam'
    }
}

MACRO_MAP = {
    'rupiah_lemah': {
        'bullish': ['ADRO','PTBA','ANTM','AALI','INCO'],
        'bearish': ['UNVR','ICBP','KLBF','TLKM'],
        'note': 'USD/IDR naik → eksportir untung'
    },
    'rupiah_kuat': {
        'bullish': ['UNVR','ICBP','KLBF','TLKM'],
        'bearish': ['ADRO','PTBA','ANTM'],
        'note': 'USD/IDR turun → importir untung'
    },
    'oil_naik': {
        'bullish': ['MEDC','ELSA','PGAS','ESSA'],
        'bearish': ['UNVR','ICBP'],
        'note': 'Harga minyak naik → saham energi naik'
    },
    'coal_naik': {
        'bullish': ['PTBA','ADRO','ITMG','HRUM'],
        'bearish': [],
        'note': 'Harga batubara naik → saham coal naik'
    },
    'nickel_naik': {
        'bullish': ['INCO','NCKL','MDKA','NIKL'],
        'bearish': [],
        'note': 'Harga nikel naik → saham nikel naik'
    }
}

# ── TELEGRAM ─────────────────────────────────────────────
def send(msg, chat_id=None):
    cid = chat_id or CHAT_ID
    if not BOT_TOKEN or not cid: return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")

def set_webhook(base_url):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            json={"url": f"{base_url}/webhook"}, timeout=10
        )
        print(f"Webhook set: {r.json()}")
    except Exception as e:
        print(f"Webhook error: {e}")

# ── AMBIL DATA YAHOO ──────────────────────────────────────
def get_yahoo_data(ticker):
    try:
        symbol = f"{ticker}.JK"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=60d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        if r.status_code != 200: return None
        data   = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result: return None

        meta   = result[0].get("meta", {})
        price  = meta.get("regularMarketPrice", 0)
        prev   = meta.get("chartPreviousClose", 0)
        volume = meta.get("regularMarketVolume", 0)
        change = ((price - prev) / prev * 100) if prev else 0
        if price == 0: return None

        quote  = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = [x for x in (quote.get("close")  or []) if x]
        vols   = [x for x in (quote.get("volume") or []) if x]
        highs  = [x for x in (quote.get("high")   or []) if x]
        lows   = [x for x in (quote.get("low")    or []) if x]

        if len(closes) < 20: return None

        # Z-Score (RenTech style)
        arr    = np.array(closes[-20:])
        ma20   = float(np.mean(arr))
        ma50   = float(np.mean(closes[-50:])) if len(closes) >= 50 else ma20
        std20  = float(np.std(arr))
        zscore = (price - ma20) / std20 if std20 > 0 else 0

        # Volume
        avg_vol = np.mean(vols[-15:-1]) if len(vols) >= 15 else np.mean(vols)
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1

        # Range harian
        ranges = [(h-l)/l*100 for h,l in zip(highs[-10:], lows[-10:]) if l > 0]
        avg_range = float(np.mean(ranges)) if ranges else 0

        # Momentum
        momentum_5d = (closes[-1] - closes[-6]) / closes[-6] if len(closes) >= 6 else 0

        # Price compression (akumulasi diam-diam)
        last5 = closes[-5:]
        price_range_5d = (max(last5) - min(last5)) / min(last5) * 100 if min(last5) > 0 else 0
        price_compression = price_range_5d < 3.0

        # Volume trend naik
        vol_trend_up = len(vols) >= 3 and vols[-1] > vols[-2] > vols[-3]

        return {
            "price": price, "change": round(change, 2),
            "volume": volume, "vol_ratio": round(vol_ratio, 2),
            "ma20": round(ma20, 0), "ma50": round(ma50, 0),
            "zscore": round(zscore, 2), "std": round(std20, 0),
            "avg_range": round(avg_range, 2),
            "momentum_5d": round(momentum_5d * 100, 2),
            "price_compression": price_compression,
            "vol_trend_up": vol_trend_up,
            "closes": closes, "vols": vols,
        }
    except Exception as e:
        print(f"Yahoo error {ticker}: {e}")
        return None

# ── AMBIL DATA ALTERNATIF ─────────────────────────────────
def get_macro_signals():
    signals = {}
    try:
        # USD/IDR
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/USDIDR=X?interval=1d&range=30d",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10
        )
        if r.status_code == 200:
            data = r.json().get("chart", {}).get("result", [])
            if data:
                closes = [x for x in (data[0].get("indicators", {}).get("quote", [{}])[0].get("close") or []) if x]
                if len(closes) >= 20:
                    chg = (closes[-1] - closes[-20]) / closes[-20] * 100
                    if chg > 2: signals['rupiah_lemah'] = round(chg, 1)
                    elif chg < -2: signals['rupiah_kuat'] = round(abs(chg), 1)
    except: pass

    try:
        # Crude Oil
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/CL=F?interval=1d&range=10d",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10
        )
        if r.status_code == 200:
            data = r.json().get("chart", {}).get("result", [])
            if data:
                closes = [x for x in (data[0].get("indicators", {}).get("quote", [{}])[0].get("close") or []) if x]
                if len(closes) >= 5:
                    chg = (closes[-1] - closes[-5]) / closes[-5] * 100
                    if chg > 3: signals['oil_naik'] = round(chg, 1)
    except: pass

    try:
        # Nikel
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/NI=F?interval=1d&range=10d",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10
        )
        if r.status_code == 200:
            data = r.json().get("chart", {}).get("result", [])
            if data:
                closes = [x for x in (data[0].get("indicators", {}).get("quote", [{}])[0].get("close") or []) if x]
                if len(closes) >= 5:
                    chg = (closes[-1] - closes[-5]) / closes[-5] * 100
                    if chg > 3: signals['nickel_naik'] = round(chg, 1)
    except: pass

    return signals

def get_weather_season():
    month = now_wib().month
    if month in [11, 12, 1, 2, 3]: return 'hujan'
    if month in [6, 7, 8, 9]: return 'kemarau'
    return None

def get_news_sentiment():
    pos_words = ['naik','positif','bullish','rebound','rally','untung','tumbuh','menguat','surplus','laba']
    neg_words = ['turun','negatif','bearish','koreksi','jatuh','rugi','melemah','anjlok','defisit','rugi']
    headlines = []
    sources = [
        "https://www.cnbcindonesia.com/market",
        "https://finansial.bisnis.com",
    ]
    try:
        from bs4 import BeautifulSoup
        for url in sources:
            try:
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
                soup = BeautifulSoup(r.text, 'html.parser')
                for tag in soup.find_all(['h1','h2','h3'], limit=8):
                    text = tag.get_text().strip()
                    if 15 < len(text) < 200:
                        headlines.append(text)
            except: continue
    except: pass

    pos = sum(1 for h in headlines for w in pos_words if w in h.lower())
    neg = sum(1 for h in headlines for w in neg_words if w in h.lower())
    total = pos + neg
    score = (pos - neg) / total * 100 if total > 0 else 0
    return round(score, 1), headlines[:5]

# ── ANALISA SAHAM ─────────────────────────────────────────
def analyze(ticker, macro_signals, weather):
    d = get_yahoo_data(ticker)
    if not d: return None

    price    = d["price"]
    zscore   = d["zscore"]
    vol_ratio= d["vol_ratio"]

    # Sinyal statistik (RenTech Z-Score)
    stat_signal = None
    stat_reason = ""
    probability = 50.0

    if zscore < -2.0:
        stat_signal = "BUY"
        probability = min(95, 60 + abs(zscore) * 10)
        stat_reason = f"Z-Score {zscore:.2f} sangat rendah, potensi rebound"
    elif zscore > 2.0:
        stat_signal = "SELL"
        probability = min(95, 60 + abs(zscore) * 10)
        stat_reason = f"Z-Score {zscore:.2f} sangat tinggi, potensi koreksi"
    elif zscore < -1.5 and vol_ratio > 1.5:
        stat_signal = "BUY"
        probability = 65.0
        stat_reason = f"Z-Score rendah + volume {vol_ratio:.1f}x, akumulasi"
    elif zscore > 1.5 and vol_ratio > 1.5:
        stat_signal = "SELL"
        probability = 65.0
        stat_reason = f"Z-Score tinggi + volume {vol_ratio:.1f}x, distribusi"
    elif d["ma20"] > d["ma50"] and price > d["ma20"] and d["momentum_5d"] > 2:
        stat_signal = "BUY"
        probability = 62.0
        stat_reason = f"Golden cross + momentum +{d['momentum_5d']:.1f}%"
    elif d["ma20"] < d["ma50"] and price < d["ma20"] and d["momentum_5d"] < -2:
        stat_signal = "SELL"
        probability = 62.0
        stat_reason = f"Death cross + momentum {d['momentum_5d']:.1f}%"

    # Akumulasi
    akum_score = 0
    patterns   = []
    if vol_ratio >= 3:    akum_score += 30; patterns.append("Volume 3x+")
    elif vol_ratio >= 2:  akum_score += 20; patterns.append("Volume 2x+")
    elif vol_ratio >= 1.5:akum_score += 10; patterns.append("Volume naik")
    if d["price_compression"]: akum_score += 25; patterns.append("Price compression")
    if d["vol_trend_up"]:      akum_score += 15; patterns.append("Volume trend naik")
    if price > d["ma20"]:      akum_score += 10; patterns.append("Di atas MA20")

    # Boost dari data alternatif
    alt_boost = 0
    alt_notes = []

    # Makro
    for sig, chg in macro_signals.items():
        if sig in MACRO_MAP:
            info = MACRO_MAP[sig]
            if ticker in info['bullish'] and stat_signal == 'BUY':
                alt_boost += 5; alt_notes.append(f"📊 {info['note']}")
            elif ticker in info['bearish'] and stat_signal == 'SELL':
                alt_boost += 5; alt_notes.append(f"📊 {info['note']}")

    # Cuaca musim
    if weather and weather in WEATHER_MAP:
        info = WEATHER_MAP[weather]
        if ticker in info['bullish'] and stat_signal == 'BUY':
            alt_boost += 4; alt_notes.append(f"🌤 {info['note']}")
        elif ticker in info['bearish'] and stat_signal == 'SELL':
            alt_boost += 4; alt_notes.append(f"🌤 {info['note']}")

    probability = min(97, probability + alt_boost)

    return {
        "ticker": ticker,
        "price": price, "change": d["change"],
        "volume": d["volume"], "vol_ratio": vol_ratio,
        "zscore": zscore, "ma20": d["ma20"], "ma50": d["ma50"],
        "momentum_5d": d["momentum_5d"], "avg_range": d["avg_range"],
        "stat_signal": stat_signal, "stat_reason": stat_reason,
        "probability": round(probability, 1),
        "akum_score": min(akum_score, 100), "patterns": patterns,
        "is_akum": akum_score >= 40,
        "alt_boost": alt_boost, "alt_notes": alt_notes[:2],
    }

# ── FORMAT PESAN ──────────────────────────────────────────
def build_scan_msg(results, macro_signals, weather, sentiment_score):
    buy  = [r for r in results if r["stat_signal"] == "BUY"]
    sell = [r for r in results if r["stat_signal"] == "SELL"]
    akum = [r for r in results if r["is_akum"]]
    buy  = sorted(buy,  key=lambda x: x["probability"], reverse=True)[:5]
    sell = sorted(sell, key=lambda x: x["probability"], reverse=True)[:3]

    lines = [
        f"🤖 <b>RENTECH IDX SCAN</b>",
        f"📅 {now_wib().strftime('%d/%m/%Y %H:%M')} WIB",
        f"🔍 {len(results)} saham IDX dipindai\n",
    ]

    # Sentimen
    icon_s = "🟢" if sentiment_score > 20 else ("🔴" if sentiment_score < -20 else "⚪")
    lines.append(f"{icon_s} Sentimen Berita: {sentiment_score:+.0f}%")

    # Cuaca
    if weather:
        info = WEATHER_MAP.get(weather, {})
        lines.append(f"🌤 Musim: {weather.upper()} → {info.get('note','')}")

    # Makro
    for sig, chg in macro_signals.items():
        if sig in MACRO_MAP:
            lines.append(f"🌐 {MACRO_MAP[sig]['note']} ({chg:+.1f}%)")

    lines.append("")

    if buy:
        lines.append("🟢 <b>SINYAL BUY TERKUAT:</b>")
        for r in buy:
            alt = f" | +{r['alt_boost']}% alt data" if r['alt_boost'] > 0 else ""
            lines.append(
                f"  ⭐ <b>{r['ticker']}</b> Rp{r['price']:,.0f} ({r['change']:+.1f}%)\n"
                f"     Z:{r['zscore']:.2f} | Prob:{r['probability']}%{alt}\n"
                f"     {r['stat_reason']}"
            )

    if sell:
        lines.append("\n🔴 <b>SINYAL SELL/HINDARI:</b>")
        for r in sell:
            lines.append(
                f"  ⚠ <b>{r['ticker']}</b> Rp{r['price']:,.0f} ({r['change']:+.1f}%)\n"
                f"     Z:{r['zscore']:.2f} | {r['stat_reason']}"
            )

    if akum:
        lines.append(f"\n📈 <b>TERDETEKSI AKUMULASI ({len(akum)} saham):</b>")
        for r in sorted(akum, key=lambda x: x['akum_score'], reverse=True)[:3]:
            lines.append(f"  • <b>{r['ticker']}</b> Score:{r['akum_score']}/100 | {', '.join(r['patterns'][:2])}")

    lines.append("\n⚠ Bukan rekomendasi. DYOR!")
    return "\n".join(lines)

def build_status_msg():
    now = now_wib()
    is_open = now.weekday() < 5 and 9 <= now.hour < 16
    return (
        f"📊 <b>Status RenTech IDX Bot</b>\n"
        f"🕐 {now.strftime('%d/%m/%Y %H:%M')} WIB\n"
        f"{'🟢 Bursa BUKA' if is_open else '🔴 Bursa TUTUP'}\n"
        f"📈 Universe: {len(STOCKS)} saham IDX\n"
        f"🔄 Auto-scan: setiap 30 menit jam bursa\n\n"
        f"<b>Metode RenTech:</b>\n"
        f"• Z-Score & Moving Average\n"
        f"• Deteksi akumulasi (volume + price)\n"
        f"• Data makro: kurs, minyak, nikel\n"
        f"• Data musim BMKG\n"
        f"• Sentimen berita NLP\n\n"
        f"Ketik /scan untuk scan manual"
    )

def build_help_msg():
    return (
        "🤖 <b>RenTech IDX Bot — Perintah:</b>\n\n"
        "🔄 /scan    — Scan semua saham IDX sekarang\n"
        "📈 /top     — Top sinyal BUY terkuat\n"
        "📉 /akum    — Saham terdeteksi akumulasi\n"
        "🌐 /macro   — Data makro & komoditas\n"
        "📰 /news    — Sentimen berita terkini\n"
        "📋 /status  — Status bot\n"
        "❓ /help    — Perintah ini\n\n"
        "💡 Gunakan /scan untuk analisis lengkap!"
    )

# ── RUN SCAN ─────────────────────────────────────────────
def run_scan(notify=True, chat_id=None):
    global last_results, prev_signals
    print(f"[{now_wib().strftime('%H:%M')}] Scanning {len(STOCKS)} saham...")

    macro_signals = get_macro_signals()
    weather       = get_weather_season()
    sentiment_score, _ = get_news_sentiment()

    results = []
    for i, ticker in enumerate(STOCKS):
        try:
            r = analyze(ticker, macro_signals, weather)
            if r: results.append(r)
            if (i+1) % 15 == 0: time.sleep(1)
        except Exception as e:
            print(f"Error {ticker}: {e}")

    results.sort(key=lambda x: x["probability"], reverse=True)
    last_results = results

    buy_signals = [r for r in results if r["stat_signal"] == "BUY"]
    new_signals = [r for r in buy_signals if r["ticker"] not in prev_signals]
    prev_signals = {r["ticker"] for r in buy_signals}

    print(f"Selesai. {len(results)} ok | BUY: {len(buy_signals)} | Baru: {len(new_signals)}")

    if notify and new_signals:
        msg = build_scan_msg(results, macro_signals, weather, sentiment_score)
        send(msg, chat_id)
    elif notify and not last_results:
        send("✅ Scan selesai. Tidak ada sinyal baru.", chat_id)

    return results, macro_signals, weather, sentiment_score

# ── WEBHOOK ───────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = flask_request.get_json()
        msg  = data.get("message", {})
        text = msg.get("text", "").strip().lower().split("@")[0]
        cid  = str(msg.get("chat", {}).get("id", ""))
        if not text or not cid: return "ok"

        if text in ["/scan", "/start"]:
            send("🔍 Scanning... harap tunggu.", cid)
            def do_scan():
                results, macro, weather, score = run_scan(notify=False)
                msg_out = build_scan_msg(results, macro, weather, score)
                send(msg_out, cid)
            Thread(target=do_scan).start()

        elif text == "/top":
            if not last_results:
                send("⏳ Ketik /scan dulu.", cid)
            else:
                buy = sorted([r for r in last_results if r["stat_signal"] == "BUY"],
                             key=lambda x: x["probability"], reverse=True)[:5]
                lines = ["🟢 <b>TOP SINYAL BUY</b>\n"]
                for r in buy:
                    alt = f"\n     🌍 {' | '.join(r['alt_notes'])}" if r['alt_notes'] else ""
                    lines.append(
                        f"⭐ <b>{r['ticker']}</b> Rp{r['price']:,.0f} ({r['change']:+.1f}%)\n"
                        f"   Z-Score: {r['zscore']:.2f} | Prob: {r['probability']}%\n"
                        f"   MA20: {r['ma20']:,.0f} | MA50: {r['ma50']:,.0f}\n"
                        f"   {r['stat_reason']}{alt}\n"
                    )
                send("\n".join(lines) or "Tidak ada sinyal BUY saat ini.", cid)

        elif text == "/akum":
            if not last_results:
                send("⏳ Ketik /scan dulu.", cid)
            else:
                akum = sorted([r for r in last_results if r["is_akum"]],
                              key=lambda x: x["akum_score"], reverse=True)[:5]
                lines = ["📈 <b>SAHAM TERDETEKSI AKUMULASI</b>\n"]
                for r in akum:
                    lines.append(
                        f"• <b>{r['ticker']}</b> Score: {r['akum_score']}/100\n"
                        f"  Rp{r['price']:,.0f} ({r['change']:+.1f}%) | Vol: {r['vol_ratio']:.1f}x\n"
                        f"  {', '.join(r['patterns'][:3])}\n"
                    )
                send("\n".join(lines) or "Tidak ada sinyal akumulasi.", cid)

        elif text == "/macro":
            macro, weather = get_macro_signals(), get_weather_season()
            lines = ["🌐 <b>DATA MAKRO & ALTERNATIF</b>\n"]
            for sig, chg in macro.items():
                if sig in MACRO_MAP:
                   
