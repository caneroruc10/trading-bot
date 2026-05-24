"""
ETH PMAX BOT — Ana Program
===========================
Railway'de çalışır. Her saatin 5. dakikasında kontrol eder.
"""

import time
import logging
import schedule
from datetime import datetime

import config as cfg
import strateji
import borsa
import telegram

logging.basicConfig(
    level   = getattr(logging, cfg.LOG_LEVEL, logging.INFO),
    format  = '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt = '%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('main')

# ─────────────────────────────────────────────────────────────
# ANA KONTROL
# ─────────────────────────────────────────────────────────────

def kontrol_et():
    log.info("─" * 50)
    log.info(f"Kontrol: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    try:
        # ── 1. Veri çek (public API — client gerekmez)
        df = borsa.ohlcv_cek(sembol=cfg.SEMBOL, timeframe=cfg.TIMEFRAME, limit=500)
        log.info(f"Veri OK: {len(df)} bar")

        # ── 2. Sinyal üret
        sinyal = strateji.sinyal_uret(df)

        if sinyal is None:
            log.info("Sinyal yok — bekleniyor")
            return

        log.info(f"Sinyal: {sinyal['yon']} @ {sinyal['fiyat']:.2f} | "
                 f"SL:{sinyal['sl']:.2f} | Rejim:{sinyal['rejim']}")

        # ── 3. Test modunda sadece Telegram bildirimi
        if cfg.TEST_MODU:
            log.info("[TEST MODU] Emir gönderilmedi")
            telegram.sinyal_bildirimi(sinyal, True)
            return

        # ── 4. Canlı mod — Binance client oluştur
        client = borsa.client_olustur()

        # Açık pozisyon var mı?
        if borsa.acik_pozisyon_var_mi(client):
            poz = borsa.pozisyon_bilgisi(client)
            if poz:
                log.info(f"Açık pozisyon: {poz['yon']} K/Z:{poz['kar_zarar']:+.2f}")
            return

        # Emir gönder
        basarili = borsa.emir_gonder(client, sinyal)
        telegram.sinyal_bildirimi(sinyal, basarili)

        if basarili:
            log.info("✅ İşlem tamamlandı")
        else:
            log.error("❌ Emir gönderilemedi")
            telegram.hata_bildirimi("Emir gönderilemedi!")

    except Exception as e:
        log.error(f"Hata: {e}", exc_info=True)
        telegram.hata_bildirimi(str(e)[:200])

# ─────────────────────────────────────────────────────────────
# BAŞLANGIÇ
# ─────────────────────────────────────────────────────────────

def baslangic():
    log.info("═" * 50)
    log.info("ETH PMAX BOT BAŞLATILDI")
    log.info(f"Sembol: {cfg.SEMBOL} | TF: {cfg.TIMEFRAME} | "
             f"Test: {cfg.TEST_MODU}")
    log.info("═" * 50)

    telegram.durum_bildirimi(
        f"🤖 ETH PMAX Bot başlatıldı\n"
        f"{'⚠️ TEST MODU' if cfg.TEST_MODU else '🔴 CANLI MOD'}\n"
        f"Sembol: {cfg.SEMBOL} | TF: {cfg.TIMEFRAME}"
    )
    kontrol_et()

def main():
    baslangic()
    schedule.every().hour.at(":05").do(kontrol_et)
    log.info("Scheduler aktif — her saatin :05'inde çalışacak")
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == '__main__':
    main()
