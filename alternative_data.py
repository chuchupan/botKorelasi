import requests
import numpy as np
from datetime import datetime, timedelta
import pytz
import logging
import json

logger = logging.getLogger(__name__)
WIB = pytz.timezone('Asia/Jakarta')

# ── Mapping korelasi data alternatif ke saham ────────────────────────────────
WEATHER_STOCKS = {
    'hujan_tinggi': {
        'bullish': ['AALI', 'LSIP', 'DSNG', 'PALM'],  # CPO butuh hujan
        'bearish': ['PTBA', 'ADRO', 'ITMG', 'HRUM'],  # Batubara susah tambang
        'reason': 'Curah hujan tinggi → produksi CPO naik, operasi tambang terganggu'
    },
    'hujan_rendah': {
        'bullish': ['PTBA', 'ADRO', 'ITMG', 'HRUM'],  # Tambang lancar
        'bearish': ['AALI', 'LSIP', 'DSNG'],           # CPO turun
        'reason': 'Curah hujan rendah → operasi tambang lancar, produksi CPO terancam'
    },
    'suhu_tinggi': {
        'bullish': ['UNVR', 'ICBP', 'MYOR', 'SIDO'],  # Consumer naik
        'bearish': [],
        'reason': 'Suhu panas → konsumsi minuman & consumer goods meningkat'
    },
    'el_nino': {
        'bullish': ['PTBA', 'ADRO', 'INCO'],
        'bearish': ['AALI', 'LSIP', 'DSNG', 'JPFA'],
        'reason': 'El Nino → kekeringan → tambang lancar, CPO & pakan ternak turun'
    }
}

MACRO_STOCKS = {
    'inflasi_naik': {
        'bullish': ['ANTM', 'INCO', 'MDKA', 'BBRI'],  # Komoditas & bank
        'bearish': ['UNVR', 'ICBP', 'KLBF'],           # Consumer tertekan
        'reason': 'Inflasi naik → harga komoditas naik, margin consumer terpangkas'
    },
    'inflasi_turun': {
        'bullish': ['UNVR', 'ICBP', 'KLBF', 'MYOR'],
        'bearish': ['ANTM', 'INCO'],
        'reason': 'Inflasi turun → daya beli konsumen membaik'
    },
    'bi_rate_naik': {
        'bullish': ['BBCA', 'BBRI', 'BMRI', 'BBNI'],  # NIM bank naik
        'bearish': ['BSDE', 'CTRA', 'PWON', 'WIKA'],  # Properti tertekan
        'reason': 'BI rate naik → NIM perbankan meningkat, properti & konstruksi tertekan'
    },
    'bi_rate_turun': {
        'bullish': ['BSDE', 'CTRA', 'PWON', 'JSMR'],
        'bearish': ['BBCA', 'BBRI', 'BMRI'],
        'reason': 'BI rate turun → properti & infrastruktur menarik, margin bank tertekan'
    },
    'rupiah_lemah': {
        'bullish': ['ADRO', 'PTBA', 'ANTM', 'AALI', 'INCO'],  # Eksportir untung
        'bearish': ['UNVR', 'ICBP', 'KLBF', 'TLKM'],           # Importir bahan baku rugi
        'reason': 'Rupiah melemah → eksportir komoditas untung, importir bahan baku rugi'
    },
    'rupiah_kuat': {
        'bullish': ['UNVR', 'ICBP', 'KLBF', 'TLKM'],
        'bearish': ['ADRO', 'PTBA', 'ANTM'],
        'reason': 'Rupiah menguat → importir bahan baku untung, eksportir komoditas rugi'
    }
}

TREND_STOCKS = {
    'bbca saham':     ['BBCA'],
    'bbri saham':     ['BBRI'],
    'ihsg':           ['BBCA','BBRI','BMRI','TLKM','ASII'],
    'harga emas':     ['ANTM','MDKA'],
    'harga minyak':   ['MEDC','ELSA','PGAS'],
    'harga batubara': ['ADRO','PTBA','ITMG','HRUM'],
    'properti':       ['BSDE','CTRA','PWON'],
    'saham naik':     ['BBCA','BBRI','TLKM'],
    'investasi':      ['BBCA','BBRI','BMRI'],
    'dolar rupiah':   ['ADRO','PTBA','ANTM','AALI'],
}

class AlternativeDataScanner:
    def __init__(self):
        self.cache = {}
        self.cache_time = {}
        self.cache_duration = 3600  # 1 jam

    def _is_cache_valid(self, key):
        if key not in self.cache_time:
            return False
        return (datetime.now() - self.cache_time[key]).seconds < self.cache_duration

    def get_bmkg_weather(self):
        """Ambil data cuaca BMKG"""
        key = 'bmkg'
        if self._is_cache_valid(key):
            return self.cache[key]
        try:
            # BMKG cuaca harian Indonesia
            url = "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm1=31"  # Jakarta
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=10)

            weather_signals = []

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    # Parse data BMKG
                    cuaca_list = []
                    if isinstance(data, dict):
                        for key_d in ['data', 'lokasi', 'cuaca']:
                            if key_d in data:
                                cuaca_list = data[key_d]
                                break

                    # Analisis cuaca
                    hujan_count = 0
                    cerah_count = 0
                    for item in cuaca_list[:10] if cuaca_list else []:
                        if isinstance(item, dict):
                            cuaca = str(item.get('cuaca', item.get('weather', ''))).lower()
                            if any(w in cuaca for w in ['hujan', 'rain', 'thunder', 'badai']):
                                hujan_count += 1
                            elif any(w in cuaca for w in ['cerah', 'clear', 'sunny']):
                                cerah_count += 1

                    if hujan_count > cerah_count:
                        condition = 'hujan_tinggi'
                    elif cerah_count > hujan_count:
                        condition = 'hujan_rendah'
                    else:
                        condition = None

                    if condition and condition in WEATHER_STOCKS:
                        info = WEATHER_STOCKS[condition]
                        weather_signals.append({
                            'source': 'BMKG',
                            'condition': condition,
                            'bullish_stocks': info['bullish'],
                            'bearish_stocks': info['bearish'],
                            'reason': info['reason'],
                            'confidence': 60
                        })
                except:
                    pass

            # Fallback: cek musim berdasarkan bulan
            month = datetime.now().month
            if month in [11, 12, 1, 2, 3]:  # Musim hujan
                condition = 'hujan_tinggi'
            elif month in [6, 7, 8, 9]:  # Musim kemarau
                condition = 'hujan_rendah'
                # Cek El Nino (kemarau panjang)
                if month in [7, 8, 9]:
                    condition = 'el_nino'
            else:
                condition = None

            if condition and condition in WEATHER_STOCKS:
                info = WEATHER_STOCKS[condition]
                weather_signals.append({
                    'source': 'BMKG Seasonal',
                    'condition': condition,
                    'bullish_stocks': info['bullish'],
                    'bearish_stocks': info['bearish'],
                    'reason': f"[Pola Musiman] {info['reason']}",
                    'confidence': 55
                })

            self.cache[key] = weather_signals
            self.cache_time[key] = datetime.now()
            return weather_signals

        except Exception as e:
            logger.warning(f"BMKG error: {e}")
            return []

    def get_google_trends(self):
        """Simulasi Google Trends via scraping SerpAPI alternatif"""
        key = 'trends'
        if self._is_cache_valid(key):
            return self.cache[key]

        trend_signals = []
        try:
            # Cek trending di Google Indonesia via scraping
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

            # Ambil trending searches Indonesia
            url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=ID"
            resp = requests.get(url, headers=headers, timeout=10)

            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, 'html.parser')
                items = soup.find_all('title')[1:11]  # Skip first (feed title)

                trending_terms = [item.get_text().lower() for item in items]

                for term, stocks in TREND_STOCKS.items():
                    for trend in trending_terms:
                        if any(word in trend for word in term.split()):
                            trend_signals.append({
                                'source': 'Google Trends ID',
                                'keyword': term,
                                'trending': trend,
                                'affected_stocks': stocks,
                                'reason': f"Keyword '{term}' trending di Indonesia → potensi perhatian investor ke {', '.join(stocks)}",
                                'confidence': 55
                            })
                            break

        except Exception as e:
            logger.warning(f"Google Trends error: {e}")

        self.cache[key] = trend_signals
        self.cache_time[key] = datetime.now()
        return trend_signals

    def get_bps_macro(self):
        """Data makro BPS & BI"""
        key = 'bps'
        if self._is_cache_valid(key):
            return self.cache[key]

        macro_signals = []
        try:
            import yfinance as yf

            # USD/IDR untuk deteksi kurs
            usdidr = yf.Ticker("USDIDR=X")
            hist = usdidr.history(period="30d")
            if not hist.empty and len(hist) >= 20:
                recent = float(hist['Close'].iloc[-1])
                month_ago = float(hist['Close'].iloc[-20])
                change_pct = (recent - month_ago) / month_ago * 100

                if change_pct > 2.0:  # Rupiah melemah > 2%
                    info = MACRO_STOCKS['rupiah_lemah']
                    macro_signals.append({
                        'source': 'Kurs USD/IDR',
                        'indicator': 'rupiah_lemah',
                        'value': f"USD/IDR: Rp {recent:,.0f} ({change_pct:+.1f}% sebulan)",
                        'bullish_stocks': info['bullish'],
                        'bearish_stocks': info['bearish'],
                        'reason': info['reason'],
                        'confidence': 70
                    })
                elif change_pct < -2.0:  # Rupiah menguat > 2%
                    info = MACRO_STOCKS['rupiah_kuat']
                    macro_signals.append({
                        'source': 'Kurs USD/IDR',
                        'indicator': 'rupiah_kuat',
                        'value': f"USD/IDR: Rp {recent:,.0f} ({change_pct:+.1f}% sebulan)",
                        'bullish_stocks': info['bullish'],
                        'bearish_stocks': info['bearish'],
                        'reason': info['reason'],
                        'confidence': 70
                    })

            # Harga komoditas global → sinyal saham terkait
            commodities = {
                'CL=F':  ('minyak', ['MEDC','ELSA','PGAS'], ['UNVR','ICBP']),
                'GC=F':  ('emas',   ['ANTM','MDKA'],        []),
                'BTU':   ('batubara',['ADRO','PTBA','ITMG'], []),
                'NI=F':  ('nikel',  ['INCO','NCKL','MDKA'], []),
                'KPO=F': ('CPO',    ['AALI','LSIP','DSNG'], []),
            }

            for symbol, (name, bull, bear) in commodities.items():
                try:
                    tk = yf.Ticker(symbol)
                    h = tk.history(period="10d")
                    if h.empty or len(h) < 5:
                        continue
                    p_now = float(h['Close'].iloc[-1])
                    p_5d  = float(h['Close'].iloc[-5])
                    chg   = (p_now - p_5d) / p_5d * 100

                    if abs(chg) > 3.0:  # Perubahan signifikan > 3%
                        direction = 'bullish' if chg > 0 else 'bearish'
                        affected_bull = bull if chg > 0 else bear
                        affected_bear = bear if chg > 0 else bull
                        macro_signals.append({
                            'source': f'Komoditas Global ({name.upper()})',
                            'indicator': f'{name}_{direction}',
                            'value': f"Harga {name}: {chg:+.1f}% (5 hari)",
                            'bullish_stocks': affected_bull,
                            'bearish_stocks': affected_bear,
                            'reason': f"Harga {name} {('naik' if chg > 0 else 'turun')} {abs(chg):.1f}% → langsung mempengaruhi saham terkait",
                            'confidence': 72
                        })
                except:
                    continue

        except Exception as e:
            logger.warning(f"Macro BPS error: {e}")

        self.cache[key] = macro_signals
        self.cache_time[key] = datetime.now()
        return macro_signals

    def get_news_nlp(self):
        """Scraping berita + NLP scoring"""
        key = 'news_nlp'
        if self._is_cache_valid(key):
            return self.cache[key]

        nlp_signals = []
        try:
            from bs4 import BeautifulSoup

            # Kata kunci positif & negatif
            pos_words = ['naik','positif','bullish','rebound','rally','untung','profit',
                        'tumbuh','meningkat','menguat','optimis','surplus','record',
                        'ekspansi','dividen','akuisisi','laba','pendapatan naik']
            neg_words = ['turun','negatif','bearish','koreksi','jatuh','rugi','loss',
                        'melemah','anjlok','krisis','defisit','bangkrut','gagal bayar',
                        'penurunan','kontraksi','resesi','inflasi tinggi']

            # Mapping ticker ke nama perusahaan
            ticker_names = {
                'BBCA': ['bca','bank central asia'],
                'BBRI': ['bri','bank rakyat'],
                'BMRI': ['mandiri','bank mandiri'],
                'BBNI': ['bni','bank negara'],
                'TLKM': ['telkom','telkomsel'],
                'ASII': ['astra'],
                'UNVR': ['unilever'],
                'GOTO': ['gojek','tokopedia','goto'],
                'ANTM': ['antam','aneka tambang'],
                'ADRO': ['adaro'],
                'PTBA': ['bukit asam'],
                'AALI': ['astra agro'],
                'KLBF': ['kalbe'],
                'INDF': ['indofood'],
                'ICBP': ['icbp','indofood cbp'],
                'SMGR': ['semen indonesia'],
                'PGAS': ['perusahaan gas','pgn'],
                'JSMR': ['jasa marga'],
                'BSDE': ['bsd','sinar mas land'],
                'MEDC': ['medco'],
            }

            sources = [
                "https://www.cnbcindonesia.com/market",
                "https://finansial.bisnis.com",
                "https://investasi.kontan.co.id",
            ]

            all_headlines = []
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

            for url in sources:
                try:
                    resp = requests.get(url, headers=headers, timeout=8)
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    for tag in soup.find_all(['h1','h2','h3','h4'], limit=10):
                        text = tag.get_text().strip()
                        if 15 < len(text) < 250:
                            all_headlines.append(text)
                except:
                    continue

            # Analisis per headline
            for headline in all_headlines:
                hl_lower = headline.lower()
                pos = sum(1 for w in pos_words if w in hl_lower)
                neg = sum(1 for w in neg_words if w in hl_lower)

                if pos == 0 and neg == 0:
                    continue

                # Cari ticker yang disebut
                mentioned = []
                for ticker, names in ticker_names.items():
                    if any(n in hl_lower for n in names) or ticker.lower() in hl_lower:
                        mentioned.append(ticker)

                sentiment = 'BULLISH' if pos > neg else 'BEARISH'
                score = (pos - neg) / max(pos + neg, 1) * 100

                nlp_signals.append({
                    'headline': headline[:120],
                    'sentiment': sentiment,
                    'score': score,
                    'mentioned_stocks': mentioned,
                    'pos_count': pos,
                    'neg_count': neg,
                    'confidence': min(85, 50 + abs(score) * 0.5)
                })

        except Exception as e:
            logger.warning(f"News NLP error: {e}")

        # Sort by confidence
        nlp_signals.sort(key=lambda x: x['confidence'], reverse=True)
        self.cache[key] = nlp_signals
        self.cache_time[key] = datetime.now()
        return nlp_signals

    def get_all_alternative_signals(self):
        """Gabungkan semua sinyal data alternatif"""
        result = {
            'weather': self.get_bmkg_weather(),
            'trends': self.get_google_trends(),
            'macro': self.get_bps_macro(),
            'news_nlp': self.get_news_nlp()
        }
        return result

    def format_alternative_report(self):
        """Format laporan data alternatif untuk Telegram"""
        data = self.get_all_alternative_signals()
        lines = ["🌍 *LAPORAN DATA ALTERNATIF — RenTech Style*\n"]

        # Cuaca
        lines.append("🌤 *DATA CUACA (BMKG)*")
        if data['weather']:
            for w in data['weather']:
                lines.append(f"📍 {w['source']}: {w['condition'].replace('_',' ').upper()}")
                lines.append(f"   📝 {w['reason']}")
                if w['bullish_stocks']:
                    lines.append(f"   🟢 Bullish: {', '.join(w['bullish_stocks'])}")
                if w['bearish_stocks']:
                    lines.append(f"   🔴 Bearish: {', '.join(w['bearish_stocks'])}")
                lines.append(f"   🎯 Confidence: {w['confidence']}%\n")
        else:
            lines.append("   ⚠️ Data tidak tersedia\n")

        # Makro & Komoditas
        lines.append("🌐 *DATA MAKRO & KOMODITAS*")
        if data['macro']:
            for m in data['macro'][:5]:
                lines.append(f"📍 {m['source']}: {m['value']}")
                lines.append(f"   📝 {m['reason']}")
                if m['bullish_stocks']:
                    lines.append(f"   🟢 Bullish: {', '.join(m['bullish_stocks'])}")
                if m['bearish_stocks']:
                    lines.append(f"   🔴 Bearish: {', '.join(m['bearish_stocks'])}")
                lines.append(f"   🎯 Confidence: {m['confidence']}%\n")
        else:
            lines.append("   ⚠️ Data tidak tersedia\n")

        # Google Trends
        lines.append("📈 *GOOGLE TRENDS INDONESIA*")
        if data['trends']:
            for t in data['trends'][:3]:
                lines.append(f"🔍 Trending: '{t['trending']}'")
                lines.append(f"   📝 {t['reason']}")
                lines.append(f"   🎯 Confidence: {t['confidence']}%\n")
        else:
            lines.append("   ⚠️ Tidak ada trending relevan\n")

        # Berita NLP
        lines.append("📰 *BERITA + NLP SCORING*")
        if data['news_nlp']:
            for n in data['news_nlp'][:5]:
                icon = "🟢" if n['sentiment'] == 'BULLISH' else "🔴"
                lines.append(f"{icon} [{n['sentiment']} {n['score']:+.0f}%] {n['headline']}")
                if n['mentioned_stocks']:
                    lines.append(f"   📌 Saham terkait: {', '.join(n['mentioned_stocks'])}")
        else:
            lines.append("   ⚠️ Data tidak tersedia")

        lines.append(f"\n🕐 {datetime.now(WIB).strftime('%d/%m/%Y %H:%M')} WIB")
        return "\n".join(lines)
