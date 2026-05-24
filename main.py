"""
ETH PMAX BOT — Ana Program
===========================
Railway'de çalışır. Her saatin 5. dakikasında kontrol eder.

Başlatma:
    python3 main.py

Environment variables (.env veya Railway):
    BINANCE_API_KEY, BINANCE_API_SECRET
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    TEST_MODU=true  (canlıya geçince false yap)
"""

import time
import logging
import schedule
from datetime import datetime

import config as cfg
import strateji
import borsa
import telegram

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level   = getattr(logging, cfg.LOG_LEVEL, logging.INFO),
    format  = '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt = '%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('main')

# ─────────────────────────────────────────────────────────────
# ANA KONTROL FONKSİYONU
# ─────────────────────────────────────────────────────────────

def kontrol_et():
    """Her saatte bir çalışır"""
    log.info("─" * 50)
    log.info(f"Kontrol başladı: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    try:
        client = borsa.client_olustur()

        # ── 1. Veri çek
        df = borsa.ohlcv_cek(client, limit=500)

        # ── 2. Açık pozisyon var mı?
        if borsa.acik_pozisyon_var_mi(client):
            poz = borsa.pozisyon_bilgisi(client)
            if poz:
                log.info(f"Açık pozisyon: {poz['yon']} | "
                         f"K/Z: {poz['kar_zarar']:+.2f} USDT")
            else:
                log.info("Açık pozisyon mevcut — yeni sinyal bekleniyor")
            return

        # ── 3. Sinyal üret
        sinyal = strateji.sinyal_uret(df)

        if sinyal is None:
            log.info("Sinyal yok — bekleniyor")
            return

        # ── 4. Emir gönder
        log.info(f"Sinyal: {sinyal['yon']} | Fiyat:{sinyal['fiyat']:.2f} | "
                 f"SL:{sinyal['sl']:.2f} | Rejim:{sinyal['rejim']}")

        basarili = borsa.emir_gonder(client, sinyal)

        # ── 5. Telegram bildirimi
        telegram.sinyal_bildirimi(sinyal, basarili)

        if basarili:
            log.info("✅ İşlem tamamlandı")
        else:
            log.error("❌ Emir gönderilemedi")
            telegram.hata_bildirimi("Emir gönderilemedi!")

    except Exception as e:
        log.error(f"Beklenmeyen hata: {e}", exc_info=True)
        telegram.hata_bildirimi(str(e))

# ─────────────────────────────────────────────────────────────
# BAŞLANGIÇ KONTROLÜ
# ─────────────────────────────────────────────────────────────

def baslangic_kontrolu():
    """Sistem başlarken bir kez çalışır"""
    log.info("═" * 50)
    log.info("ETH PMAX BOT BAŞLATILDI")
    log.info("═" * 50)
    cfg.ayarlari_yazdir()

    if cfg.TEST_MODU:
        log.info("⚠️  TEST MODU AÇIK — gerçek emir gönderilmeyecek")
        telegram.durum_bildirimi(
            "🤖 ETH PMAX Bot başlatıldı\n"
            "⚠️ TEST MODU — gerçek emir yok\n"
            f"Sembol: {cfg.SEMBOL} | TF: {cfg.TIMEFRAME}"
        )
    else:
        log.info("🔴 CANLI MOD — gerçek emirler gönderilecek!")
        telegram.durum_bildirimi(
            "🤖 ETH PMAX Bot başlatıldı\n"
            "🔴 CANLI MOD\n"
            f"Sembol: {cfg.SEMBOL} | TF: {cfg.TIMEFRAME}\n"
            f"Pozisyon: {cfg.POZISYON_USDT} USDT"
        )

    # İlk kontrolü hemen yap
    kontrol_et()

# ─────────────────────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────────────────────

def main():
    baslangic_kontrolu()

    # Her saatin 5. dakikasında çalış (mum kapandıktan sonra)
    schedule.every().hour.at(":05").do(kontrol_et)

    log.info("Scheduler başlatıldı — her saatin :05'inde kontrol edilecek")

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == '__main__':
    main()
