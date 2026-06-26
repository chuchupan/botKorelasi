import os
import logging
import asyncio
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from scanner import MarketScanner
from datetime import datetime
import pytz

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

WIB = pytz.timezone('Asia/Jakarta')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

scanner = MarketScanner()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 *RenTech IDX Bot Aktif!*\n\n"
        "Metode Renaissance Technologies:\n"
        "📊 Z-Score & Moving Average\n"
        "🔄 Korelasi & Arbitrage antar saham\n"
        "🌤 Data cuaca BMKG\n"
        "📈 Google Trends Indonesia\n"
        "🌐 Makro: kurs, komoditas global\n"
        "📰 Berita + NLP scoring\n\n"
        "*Perintah:*\n"
        "/scan - Scan semua saham IDX\n"
        "/top - Top 10 sinyal terkuat\n"
        "/status - Status pasar\n"
        "/macro - Data makro ekonomi\n"
        "/alternatif - Laporan data alternatif\n"
        "/sentiment - Sentimen berita\n"
        "/help - Bantuan\n\n"
        "⏰ Auto-scan setiap 30 menit (09.00-16.00 WIB)"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📖 *Panduan RenTech IDX Bot*\n\n"
        "*/scan* - Scan manual semua saham IDX\n"
        "*/top* - Top 10 sinyal statistik terkuat\n"
        "*/status* - Status pasar & sistem\n"
        "*/macro* - Data makro: IHSG, kurs, komoditas\n"
        "*/alternatif* - Cuaca BMKG, Google Trends, NLP berita\n"
        "*/sentiment* - Sentimen berita keuangan\n\n"
        "*Cara baca sinyal:*\n"
        "🟢 BUY - Probabilitas naik tinggi\n"
        "🔴 SELL - Probabilitas koreksi tinggi\n"
        "⚡ ARBITRAGE - Divergensi pasangan saham terkorelasi\n\n"
        "📌 Semua sinyal berbasis probabilitas statistik + data alternatif."
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(WIB)
    market_open = now.weekday() < 5 and 9 <= now.hour < 16
    icon = "🟢" if market_open else "🔴"
    msg = (
        f"📊 *Status Sistem RenTech Bot*\n\n"
        f"🕐 Waktu: {now.strftime('%d/%m/%Y %H:%M')} WIB\n"
        f"{icon} Bursa IDX: {'BUKA' if market_open else 'TUTUP'}\n"
        f"🔄 Auto-scan: Setiap 30 menit jam bursa\n"
        f"📈 Universe: 70+ saham IDX\n"
        f"🧮 Metode: Z-Score, MA, Korelasi, NLP\n"
        f"🌤 Data alternatif: BMKG, Trends, BPS, Berita\n\n"
        f"Ketik /scan untuk scan manual."
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Memulai scan... harap tunggu 30-60 detik.")
    try:
        signals = await asyncio.get_event_loop().run_in_executor(None, scanner.run_full_scan)
        if signals:
            for msg in format_signals(signals[:10]):
                await update.message.reply_text(msg, parse_mode='Markdown')
        else:
            await update.message.reply_text("✅ Scan selesai. Tidak ada sinyal kuat saat ini.")
    except Exception as e:
        logger.error(f"Scan error: {e}")
        await update.message.reply_text(f"❌ Error saat scan: {str(e)}")

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Mengambil top sinyal...")
    try:
        signals = await asyncio.get_event_loop().run_in_executor(None, scanner.run_full_scan)
        if signals:
            for msg in format_signals(signals[:10]):
                await update.message.reply_text(msg, parse_mode='Markdown')
        else:
            await update.message.reply_text("Tidak ada sinyal kuat saat ini.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def macro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌐 Mengambil data makro...")
    try:
        data = await asyncio.get_event_loop().run_in_executor(None, scanner.get_macro_data)
        await update.message.reply_text(data, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def alternatif_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌍 Menganalisis data alternatif (BMKG, Trends, NLP)...")
    try:
        data = await asyncio.get_event_loop().run_in_executor(None, scanner.get_alternative_report)
        # Split jika terlalu panjang
        if len(data) > 4000:
            parts = [data[i:i+4000] for i in range(0, len(data), 4000)]
            for part in parts:
                await update.message.reply_text(part, parse_mode='Markdown')
        else:
            await update.message.reply_text(data, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def sentiment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📰 Menganalisis sentimen berita...")
    try:
        data = await asyncio.get_event_loop().run_in_executor(None, scanner.get_sentiment)
        await update.message.reply_text(data, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

def format_signals(signals):
    messages = []
    for s in signals:
        icon = "🟢" if s['type'] == 'BUY' else ("🔴" if s['type'] == 'SELL' else "⚡")
        alt = f"\n🌍 Data alternatif boost: +{s['alt_boost']}%" if s.get('alt_boost', 0) > 0 else ""
        if s['type'] == 'ARBITRAGE':
            msg = (
                f"{icon} *ARBITRAGE — {s['ticker']}*\n"
                f"📊 Korelasi: {s['volume_ratio']:.3f}\n"
                f"📉 Divergensi: {s['momentum_5d']*100:.1f}%\n"
                f"🎯 Probabilitas: {s['probability']:.1f}%\n"
                f"📝 {s['reason']}\n"
                f"🕐 {s['time']}"
            )
        else:
            msg = (
                f"{icon} *{s['type']} — {s['ticker']}*\n"
                f"💰 Harga: Rp {s['price']:,.0f}\n"
                f"📊 Z-Score: {s['zscore']:.2f}\n"
                f"📈 MA20: Rp {s['ma20']:,.0f}\n"
                f"📉 MA50: Rp {s['ma50']:,.0f}\n"
                f"🎯 Probabilitas: {s['probability']:.1f}%{alt}\n"
                f"📝 {s['reason']}\n"
                f"🕐 {s['time']}"
            )
        messages.append(msg)
    return messages

async def auto_scan(bot: Bot):
    now = datetime.now(WIB)
    if now.weekday() >= 5 or not (9 <= now.hour < 16):
        return
    logger.info("Auto-scan berjalan...")
    try:
        signals = await asyncio.get_event_loop().run_in_executor(None, scanner.run_full_scan)
        if signals and CHAT_ID:
            for msg in format_signals(signals[:5]):
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Auto-scan error: {e}")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN tidak ditemukan!")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("macro", macro_command))
    app.add_handler(CommandHandler("alternatif", alternatif_command))
    app.add_handler(CommandHandler("sentiment", sentiment_command))

    scheduler = AsyncIOScheduler(timezone=WIB)
    scheduler.add_job(
        lambda: asyncio.create_task(auto_scan(app.bot)),
        'cron', minute='*/30', hour='9-15', day_of_week='mon-fri'
    )
    scheduler.start()

    logger.info("Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
    
