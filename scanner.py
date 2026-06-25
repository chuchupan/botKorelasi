import yfinance as yf
import numpy as np
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import logging
import time

logger = logging.getLogger(__name__)
WIB = pytz.timezone('Asia/Jakarta')

IDX_TICKERS = [
    "AALI.JK","ADRO.JK","AKRA.JK","AMRT.JK","ANTM.JK","ASII.JK","BBCA.JK",
    "BBNI.JK","BBRI.JK","BBTN.JK","BMRI.JK","BRIS.JK","BRPT.JK","CPIN.JK",
    "EXCL.JK","GGRM.JK","GOTO.JK","HMSP.JK","HRUM.JK","ICBP.JK","INCO.JK",
    "INDF.JK","INKP.JK","INTP.JK","ITMG.JK","JPFA.JK","JSMR.JK","KLBF.JK",
    "MAPI.JK","MDKA.JK","MEDC.JK","MIKA.JK","PGAS.JK","PTBA.JK","PWON.JK",
    "SMGR.JK","TBIG.JK","TLKM.JK","TOWR.JK","TPIA.JK","UNTR.JK","UNVR.JK",
    "SIDO.JK","HEAL.JK","ADHI.JK","ACES.JK","AUTO.JK","BSDE.JK","CTRA.JK",
    "ELSA.JK","ISAT.JK","LINK.JK","LSIP.JK","MYOR.JK","PNBN.JK","SCMA.JK",
    "TINS.JK","ULTJ.JK","WIKA.JK","WTON.JK","MTEL.JK","FILM.JK","NCKL.JK",
    "EMTK.JK","ESSA.JK","PGEO.JK","PTPP.JK","BMTR.JK","DSNG.JK","NIKL.JK",
]

class MarketScanner:
    def __init__(self):
        self.last_signals = []

    def fetch_price_data(self, ticker, period='3mo'):
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period=period)
            if hist.empty or len(hist) < 20:
                return None
            return hist
        except Exception as e:
            logger.warning(f"Gagal fetch {ticker}: {e}")
            return None

    def analyze_ticker(self, ticker):
        df = self.fetch_price_data(ticker)
        if df is None:
            return None
        try:
            close = np.array(df['Close'].tolist(), dtype=float)
            volume = np.array(df['Volume'].tolist(), dtype=float)

            if len(close) < 50:
                return None

            # Moving averages
            ma20 = float(np.mean(close[-20:]))
            ma50 = float(np.mean(close[-50:]))
            current_price = float(close[-1])

            # Z-Score
            std20 = float(np.std(close[-20:]))
            zscore = (current_price - ma20) / std20 if std20 > 0 else 0

            # Volume ratio
            vol_ma = float(np.mean(volume[-20:]))
            vol_current = float(volume[-1])
            vol_ratio = vol_current / vol_ma if vol_ma > 0 else 1

            # Momentum
            if len(close) >= 6:
                momentum_5d = float((close[-1] - close[-6]) / close[-6])
            else:
                momentum_5d = 0.0

            signal_type = None
            reason = ""
            probability = 50.0

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
                reason = f"Golden cross MA20>MA50, momentum 5 hari +{momentum_5d*100:.1f}%"
            elif ma20 < ma50 and current_price < ma20 and momentum_5d < -0.02:
                signal_type = "SELL"
                probability = 62.0
                reason = f"Death cross MA20<MA50, momentum 5 hari {momentum_5d*100:.1f}%"

            if signal_type is None:
                return None

            return {
                'ticker': ticker.replace('.JK', ''),
                'type': signal_type,
                'price': current_price,
                'zscore': zscore,
                'ma20': ma20,
                'ma50': ma50,
                'volume_ratio': vol_ratio,
                'momentum_5d': momentum_5d,
                'probability': probability,
                'reason': reason,
                'time': datetime.now(WIB).strftime('%d/%m/%Y %H:%M WIB')
            }
        except Exception as e:
            logger.warning(f"Error analisis {ticker}: {e}")
            return None

    def find_correlations(self, data_cache):
        arbitrage_signals = []
        tickers = list(data_cache.keys())
        if len(tickers) < 2:
            return arbitrage_signals

        returns_map = {}
        for ticker, df in data_cache.items():
            try:
                close = np.array(df['Close'].tolist(), dtype=float)
                if len(close) < 21:
                    continue
                rets = np.diff(close) / close[:-1]
                returns_map[ticker] = rets
            except:
                continue

        ticker_list = list(returns_map.keys())
        for i in range(len(ticker_list)):
            for j in range(i+1, len(ticker_list)):
                t1, t2 = ticker_list[i], ticker_list[j]
                r1, r2 = returns_map[t1], returns_map[t2]
                min_len = min(len(r1), len(r2))
                if min_len < 20:
                    continue
                try:
                    corr = float(np.corrcoef(r1[-min_len:], r2[-min_len:])[0,1])
                    if corr > 0.85:
                        ret1_20 = float(np.sum(r1[-20:]))
                        ret2_20 = float(np.sum(r2[-20:]))
                        spread = ret1_20 - ret2_20
                        if abs(spread) > 0.08:
                            arbitrage_signals.append({
                                'ticker': f"{t1.replace('.JK','')} vs {t2.replace('.JK','')}",
                                'type': 'ARBITRAGE',
                                'price': 0,
                                'zscore': spread / 0.04,
                                'ma20': 0,
                                'ma50': 0,
                                'volume_ratio': corr,
                                'momentum_5d': spread,
                                'probability': min(90, 60 + abs(spread) * 100),
                                'reason': f"Korelasi tinggi ({corr:.2f}) tapi divergensi 20 hari: {spread*100:.1f}%, potensi konvergensi",
                                'time': datetime.now(WIB).strftime('%d/%m/%Y %H:%M WIB')
                            })
                except:
                    continue

        return arbitrage_signals

    def get_macro_data(self):
        try:
            lines = ["🌐 *Data Makro Ekonomi Indonesia*\n"]

            pairs = {
                "USD/IDR": "USDIDR=X",
                "IHSG": "^JKSE",
                "Crude Oil": "CL=F",
                "Emas": "GC=F",
                "Nikel": "NI=F",
            }

            for name, symbol in pairs.items():
                try:
                    tk = yf.Ticker(symbol)
                    hist = tk.history(period="5d")
                    if not hist.empty and len(hist) >= 2:
                        price = float(hist['Close'].iloc[-1])
                        prev = float(hist['Close'].iloc[-2])
                        change = (price - prev) / prev * 100
                        icon = "🟢" if change > 0 else "🔴"
                        lines.append(f"{icon} {name}: {price:,.2f} ({change:+.2f}%)")
                except:
                    lines.append(f"⚠️ {name}: tidak tersedia")

            lines.append(f"\n🕐 {datetime.now(WIB).strftime('%d/%m/%Y %H:%M')} WIB")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Error makro: {str(e)}"

    def get_sentiment(self):
        try:
            headlines = []
            sources = [
                ("https://www.cnbcindonesia.com/market", "CNBC"),
                ("https://bisnis.com/finansial", "Bisnis"),
            ]
            for url, source in sources:
                try:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    resp = requests.get(url, headers=headers, timeout=8)
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    for tag in soup.find_all(['h1','h2','h3'], limit=5):
                        text = tag.get_text().strip()
                        if 20 < len(text) < 200:
                            headlines.append((source, text))
                except:
                    continue

            positive_words = ['naik','positif','bullish','rebound','rally','untung','tumbuh','menguat']
            negative_words = ['turun','negatif','bearish','koreksi','jatuh','rugi','melemah','anjlok']

            pos, neg = 0, 0
            lines = ["📰 *Sentimen Berita Pasar Indonesia*\n"]

            for source, headline in headlines[:8]:
                hl = headline.lower()
                p = sum(1 for w in positive_words if w in hl)
                n = sum(1 for w in negative_words if w in hl)
                pos += p; neg += n
                icon = "🟢" if p > n else ("🔴" if n > p else "⚪")
                lines.append(f"{icon} [{source}] {headline[:100]}")

            total = pos + neg
            if total > 0:
                score = (pos - neg) / total * 100
                overall = "🟢 BULLISH" if score > 20 else ("🔴 BEARISH" if score < -20 else "⚪ NETRAL")
                lines.append(f"\n📊 *Skor Sentimen: {score:+.0f}%*")
                lines.append(f"🎯 *Overall: {overall}*")

            lines.append(f"\n🕐 {datetime.now(WIB).strftime('%d/%m/%Y %H:%M')} WIB")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Error sentimen: {str(e)}"

    def run_full_scan(self):
        logger.info(f"Scan {len(IDX_TICKERS)} ticker...")
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
                    time.sleep(1)
            except Exception as e:
                logger.warning(f"Skip {ticker}: {e}")
                continue

        arb = self.find_correlations(data_cache)
        signals.extend(arb)
        signals.sort(key=lambda x: x['probability'], reverse=True)
        logger.info(f"Scan selesai. {len(signals)} sinyal.")
        return signals
            
