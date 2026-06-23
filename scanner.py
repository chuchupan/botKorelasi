import yfinance as yf
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import logging
import time

logger = logging.getLogger(__name__)
WIB = pytz.timezone('Asia/Jakarta')

# Daftar saham IDX populer (expand sesuai kebutuhan)
IDX_TICKERS = [
    # LQ45
    "AALI.JK","ADRO.JK","AKRA.JK","AMRT.JK","ANTM.JK","ARTO.JK","ASII.JK","BBCA.JK",
    "BBNI.JK","BBRI.JK","BBTN.JK","BMRI.JK","BRIS.JK","BRPT.JK","BUKA.JK","CPIN.JK",
    "EMTK.JK","ERAA.JK","ESSA.JK","EXCL.JK","GGRM.JK","GOTO.JK","HMSP.JK","HRUM.JK",
    "ICBP.JK","INCO.JK","INDF.JK","INKP.JK","INTP.JK","ITMG.JK","JPFA.JK","JSMR.JK",
    "KLBF.JK","MAPI.JK","MBMA.JK","MDKA.JK","MEDC.JK","MIKA.JK","MNCN.JK","PGAS.JK",
    "PGEO.JK","PTBA.JK","PTPP.JK","PWON.JK","SMGR.JK","SMMA.JK","TBIG.JK","TKIM.JK",
    "TLKM.JK","TOWR.JK","TPIA.JK","UNTR.JK","UNVR.JK","WSKT.JK","SIDO.JK","HEAL.JK",
    # IDX80 tambahan
    "ADHI.JK","ACES.JK","ASSA.JK","AUTO.JK","BFIN.JK","BMTR.JK","BSDE.JK","CTRA.JK",
    "DMAS.JK","DSNG.JK","ELSA.JK","GJTL.JK","HOKI.JK","IMJS.JK","INDS.JK","ISAT.JK",
    "ISSP.JK","JAWA.JK","KIJA.JK","LINK.JK","LSIP.JK","MAPI.JK","MYOR.JK","NCKL.JK",
    "NIKL.JK","PNBN.JK","SCMA.JK","SRTG.JK","SSIA.JK","TINS.JK","ULTJ.JK","WIKA.JK",
    "WTON.JK","BNII.JK","FILM.JK","FOOD.JK","GIVE.JK","HRTA.JK","MTEL.JK","PALM.JK",
]

class MarketScanner:
    def __init__(self):
        self.last_signals = []

    def fetch_price_data(self, ticker, period='3mo', interval='1d'):
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
            if df.empty or len(df) < 20:
                return None
            return df
        except Exception as e:
            logger.warning(f"Gagal fetch {ticker}: {e}")
            return None

    def calculate_zscore(self, series, window=20):
        mean = series.rolling(window).mean()
        std = series.rolling(window).std()
        zscore = (series - mean) / std
        return zscore

    def analyze_ticker(self, ticker):
        df = self.fetch_price_data(ticker)
        if df is None:
            return None

        try:
            close = df['Close'].squeeze()
            if len(close) < 50:
                return None

            ma20 = close.rolling(20).mean().iloc[-1]
            ma50 = close.rolling(50).mean().iloc[-1]
            current_price = close.iloc[-1]

            zscore_series = self.calculate_zscore(close, 20)
            zscore = zscore_series.iloc[-1]

            # Standar deviasi
            std20 = close.rolling(20).std().iloc[-1]

            # Volume analisis
            volume = df['Volume'].squeeze()
            vol_ma = volume.rolling(20).mean().iloc[-1]
            vol_current = volume.iloc[-1]
            vol_ratio = vol_current / vol_ma if vol_ma > 0 else 1

            # Momentum
            returns = close.pct_change()
            momentum_5d = returns.iloc[-5:].sum()
            momentum_20d = returns.iloc[-20:].sum()

            signal_type = None
            reason = ""
            probability = 50.0

            # RenTech Logic: Mean Reversion + Momentum
            if zscore < -2.0:
                signal_type = "BUY"
                probability = min(95, 60 + abs(zscore) * 10)
                reason = f"Z-Score sangat rendah ({zscore:.2f}), harga jauh di bawah rata-rata, potensi rebound"
            elif zscore > 2.0:
                signal_type = "SELL"
                probability = min(95, 60 + abs(zscore) * 10)
                reason = f"Z-Score sangat tinggi ({zscore:.2f}), harga jauh di atas rata-rata, potensi koreksi"
            elif zscore < -1.5 and vol_ratio > 1.5:
                signal_type = "BUY"
                probability = 65.0
                reason = f"Z-Score rendah + volume spike ({vol_ratio:.1f}x), akumulasi terdeteksi"
            elif zscore > 1.5 and vol_ratio > 1.5:
                signal_type = "SELL"
                probability = 65.0
                reason = f"Z-Score tinggi + volume spike ({vol_ratio:.1f}x), distribusi terdeteksi"
            elif ma20 > ma50 and current_price > ma20 and momentum_5d > 0.02:
                signal_type = "BUY"
                probability = 62.0
                reason = f"Golden cross MA20>MA50, momentum 5 hari positif ({momentum_5d*100:.1f}%)"
            elif ma20 < ma50 and current_price < ma20 and momentum_5d < -0.02:
                signal_type = "SELL"
                probability = 62.0
                reason = f"Death cross MA20<MA50, momentum 5 hari negatif ({momentum_5d*100:.1f}%)"

            if signal_type is None:
                return None

            return {
                'ticker': ticker.replace('.JK', ''),
                'type': signal_type,
                'price': float(current_price),
                'zscore': float(zscore),
                'ma20': float(ma20),
                'ma50': float(ma50),
                'std': float(std20),
                'volume_ratio': float(vol_ratio),
                'momentum_5d': float(momentum_5d),
                'probability': float(probability),
                'reason': reason,
                'time': datetime.now(WIB).strftime('%d/%m/%Y %H:%M WIB')
            }
        except Exception as e:
            logger.warning(f"Error analisis {ticker}: {e}")
            return None

    def find_correlations(self, data_dict):
        """Cari korelasi antar saham ala RenTech"""
        arbitrage_signals = []
        tickers = list(data_dict.keys())

        if len(tickers) < 2:
            return arbitrage_signals

        # Buat matriks return
        returns_df = pd.DataFrame()
        for ticker, df in data_dict.items():
            try:
                close = df['Close'].squeeze()
                returns_df[ticker] = close.pct_change().dropna()
            except:
                continue

        if returns_df.shape[1] < 2:
            return arbitrage_signals

        # Korelasi
        corr_matrix = returns_df.corr()

        # Cari pasangan sangat terkorelasi tapi harga diverge
        for i in range(len(tickers)):
            for j in range(i+1, len(tickers)):
                t1, t2 = tickers[i], tickers[j]
                if t1 not in corr_matrix.index or t2 not in corr_matrix.columns:
                    continue
                corr = corr_matrix.loc[t1, t2]

                if corr > 0.85:  # Sangat terkorelasi
                    try:
                        r1 = returns_df[t1].iloc[-20:].sum()
                        r2 = returns_df[t2].iloc[-20:].sum()
                        spread = r1 - r2

                        if abs(spread) > 0.08:  # Divergensi > 8%
                            arbitrage_signals.append({
                                'ticker': f"{t1.replace('.JK','')} vs {t2.replace('.JK','')}",
                                'type': 'ARBITRAGE',
                                'price': 0,
                                'zscore': spread / 0.04,
                                'ma20': 0,
                                'ma50': 0,
                                'std': 0,
                                'volume_ratio': corr,
                                'momentum_5d': spread,
                                'probability': min(90, 60 + abs(spread) * 100),
                                'reason': f"Korelasi tinggi ({corr:.2f}) tapi divergensi return 20 hari: {spread*100:.1f}%, potensi konvergensi",
                                'time': datetime.now(WIB).strftime('%d/%m/%Y %H:%M WIB')
                            })
                    except:
                        continue

        return arbitrage_signals

    def get_weather_data(self):
        """Data cuaca BMKG sebagai data alternatif"""
        try:
            url = "https://data.bmkg.go.id/DataMKG/MEWS/DigitalForecast/DigitalForecast-Indonesia.xml"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return "✅ Data cuaca BMKG berhasil diambil"
            return "⚠️ Data cuaca BMKG tidak tersedia"
        except:
            return "⚠️ Tidak dapat terhubung ke BMKG"

    def get_macro_data(self):
        """Data makro ekonomi Indonesia"""
        try:
            macro_info = []
            macro_info.append("🌐 *Data Makro Ekonomi Indonesia*\n")

            # Yahoo Finance untuk USDIDR
            try:
                usdidr = yf.download("USDIDR=X", period="5d", progress=False, auto_adjust=True)
                if not usdidr.empty:
                    rate = usdidr['Close'].iloc[-1]
                    rate_prev = usdidr['Close'].iloc[-2]
                    change = ((rate - rate_prev) / rate_prev) * 100
                    icon = "🔴" if change > 0 else "🟢"
                    macro_info.append(f"{icon} USD/IDR: Rp {float(rate):,.0f} ({change:+.2f}%)")
            except:
                macro_info.append("⚠️ USD/IDR: Data tidak tersedia")

            # IHSG
            try:
                ihsg = yf.download("^JKSE", period="5d", progress=False, auto_adjust=True)
                if not ihsg.empty:
                    val = ihsg['Close'].iloc[-1]
                    val_prev = ihsg['Close'].iloc[-2]
                    change = ((val - val_prev) / val_prev) * 100
                    icon = "🟢" if change > 0 else "🔴"
                    macro_info.append(f"{icon} IHSG: {float(val):,.2f} ({change:+.2f}%)")
            except:
                macro_info.append("⚠️ IHSG: Data tidak tersedia")

            # Harga komoditas relevan
            commodities = {
                "Crude Oil (WTI)": "CL=F",
                "Batu Bara": "BTU",
                "Nikel": "NI=F",
                "Emas": "GC=F",
                "CPO (Palm Oil)": "KPO=F"
            }

            macro_info.append("\n🛢 *Komoditas Terkait IDX:*")
            for name, symbol in commodities.items():
                try:
                    data = yf.download(symbol, period="5d", progress=False, auto_adjust=True)
                    if not data.empty and len(data) >= 2:
                        price = data['Close'].iloc[-1]
                        prev = data['Close'].iloc[-2]
                        change = ((price - prev) / prev) * 100
                        icon = "🟢" if change > 0 else "🔴"
                        macro_info.append(f"{icon} {name}: {float(price):,.2f} ({change:+.2f}%)")
                except:
                    pass

            macro_info.append(f"\n🕐 Update: {datetime.now(WIB).strftime('%d/%m/%Y %H:%M')} WIB")
            return "\n".join(macro_info)

        except Exception as e:
            return f"❌ Error mengambil data makro: {str(e)}"

    def get_sentiment(self):
        """Scraping sentimen berita keuangan Indonesia"""
        try:
            headlines = []
            sources = [
                ("https://www.cnbcindonesia.com/market", "CNBC Indonesia"),
                ("https://bisnis.com/finansial", "Bisnis.com"),
            ]

            for url, source in sources:
                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    resp = requests.get(url, headers=headers, timeout=8)
                    soup = BeautifulSoup(resp.text, 'html.parser')

                    # Ambil headline
                    for tag in soup.find_all(['h1', 'h2', 'h3'], limit=5):
                        text = tag.get_text().strip()
                        if len(text) > 20 and len(text) < 200:
                            headlines.append((source, text))
                except:
                    continue

            # Analisis sentimen sederhana
            positive_words = ['naik', 'positif', 'bullish', 'rebound', 'rally', 'untung', 'profit', 'tumbuh', 'meningkat', 'menguat']
            negative_words = ['turun', 'negatif', 'bearish', 'koreksi', 'jatuh', 'rugi', 'loss', 'melemah', 'anjlok', 'krisis']

            pos_count = 0
            neg_count = 0

            msg_lines = ["📰 *Sentimen Berita Pasar Indonesia*\n"]

            for source, headline in headlines[:8]:
                headline_lower = headline.lower()
                p = sum(1 for w in positive_words if w in headline_lower)
                n = sum(1 for w in negative_words if w in headline_lower)
                pos_count += p
                neg_count += n

                icon = "🟢" if p > n else ("🔴" if n > p else "⚪")
                msg_lines.append(f"{icon} [{source}] {headline[:100]}")

            total = pos_count + neg_count
            if total > 0:
                sentiment_score = (pos_count - neg_count) / total * 100
                overall = "🟢 BULLISH" if sentiment_score > 20 else ("🔴 BEARISH" if sentiment_score < -20 else "⚪ NETRAL")
                msg_lines.append(f"\n📊 *Skor Sentimen: {sentiment_score:+.0f}%*")
                msg_lines.append(f"🎯 *Overall: {overall}*")
            else:
                msg_lines.append("\n⚠️ Tidak cukup data untuk skor sentimen")

            msg_lines.append(f"\n🕐 {datetime.now(WIB).strftime('%d/%m/%Y %H:%M')} WIB")
            return "\n".join(msg_lines)

        except Exception as e:
            return f"❌ Error sentimen: {str(e)}"

    def run_full_scan(self):
        """Scan lengkap semua ticker IDX"""
        logger.info(f"Memulai scan {len(IDX_TICKERS)} ticker...")
        signals = []
        data_cache = {}

        for i, ticker in enumerate(IDX_TICKERS):
            try:
                df = self.fetch_price_data(ticker)
                if df is not None:
                    data_cache[ticker] = df
                    result = self.analyze_ticker(ticker)
                    if result:
                        signals.append(result)
                if i % 10 == 0:
                    time.sleep(1)  # Rate limiting
            except Exception as e:
                logger.warning(f"Skip {ticker}: {e}")
                continue

        # Cari arbitrage opportunities
        arb_signals = self.find_correlations(data_cache)
        signals.extend(arb_signals)

        # Sort by probability
        signals.sort(key=lambda x: x['probability'], reverse=True)

        logger.info(f"Scan selesai. {len(signals)} sinyal ditemukan.")
        return signals
