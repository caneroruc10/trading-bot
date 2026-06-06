"""
ETH PMAX BOT — Ana Program
===========================
Railway'de çalışır.
- Her saatin :05'inde sinyal kontrolü
- Her 4 saatte bir durum raporu (00:05, 04:05, 08:05, 12:05, 16:05, 20:05)
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
# DURUM RAPORU
# ─────────────────────────────────────────────────────────────

def durum_raporu():
    """4 saatte bir Telegram'a durum raporu gönder"""
    log.info("Durum raporu hazırlanıyor...")
    try:
        df = borsa.ohlcv_cek(sembol=cfg.SEMBOL, timeframe=cfg.TIMEFRAME, limit=500)
        son = df.iloc[-1]

        # Strateji hesapla
        import numpy as np
        from collections import deque
        from strateji import (hesapla_atr, hesapla_ema, hesapla_pmax,
                              pivot_yuksek_mi, pivot_alcak_mi,
                              fiyat_yapisi_puani, volatilite_puani,
                              rejim_hesapla)

        close = df['close'].values
        high  = df['high'].values
        low   = df['low'].values

        atr      = hesapla_atr(high, low, close, cfg.ATR_PERIOD)
        ema      = hesapla_ema(close, cfg.EMA_PERIOD)
        pmax_line, pmax_bull = hesapla_pmax(close, ema, atr, cfg.COEFFICIENT)

        ph = deque(maxlen=cfg.PIVOT_COUNT)
        pl = deque(maxlen=cfg.PIVOT_COUNT)
        min_bar = cfg.ATR_PERIOD + cfg.PIVOT_RIGHT + cfg.PIVOT_LEFT

        for i in range(len(close)):
            if i < min_bar: continue
            pb = i - cfg.PIVOT_RIGHT
            if pb >= cfg.PIVOT_LEFT:
                if pivot_yuksek_mi(high, pb, cfg.PIVOT_LEFT, cfg.PIVOT_RIGHT):
                    ph.appendleft(high[pb])
                if pivot_alcak_mi(low, pb, cfg.PIVOT_LEFT, cfg.PIVOT_RIGHT):
                    pl.appendleft(low[pb])

        ss = fiyat_yapisi_puani(list(ph), list(pl), pmax_bull[-1])
        vs = volatilite_puani(atr[-1], close[-1])
        trend_skoru = ss * 0.6 + vs * 0.4
        trend_aktif = trend_skoru >= cfg.SCORE_THRESH

        rejim = rejim_hesapla(close)

        # PMAX yön
        yon_emoji = '🟢 BULL' if pmax_bull[-1] else '🔴 BEAR'

        # Skor bar (10 blok)
        dolu = int(trend_skoru / 10)
        bos  = 10 - dolu
        skor_bar = '█' * dolu + '░' * bos

        # Rejim emoji
        rejim_emoji = {'Sakin': '🟦', 'Geçiş': '🟨', 'Kriz': '🟥'}.get(rejim, '⬜')

        # Pozisyon durumu
        poz = borsa.pozisyon_bilgisi()
        if poz:
            poz_metin = (f"\n💼 Açık Pozisyon: {poz['yon']} "
                        f"@ {poz['giris_fiyat']:.2f} "
                        f"| K/Z: {poz['kar_zarar']:+.2f} USDT")
        else:
            poz_metin = "\n💼 Açık Pozisyon: Yok"

        metin = f"""📊 <b>PMAX — {cfg.SEMBOL} 4 Saatlik Durum</b>
{datetime.now().strftime('%d.%m.%Y %H:%M')} UTC+3

💰 Fiyat     : <code>{close[-1]:.2f}</code> USDT
📈 PMAX Yön  : {yon_emoji}
{rejim_emoji} Rejim     : <b>{rejim}</b>

📉 Trend Skoru : {trend_skoru:.1f}/100
<code>{skor_bar}</code>
{'✅ AKTİF' if trend_aktif else f'❌ PASİF (eşik: {cfg.SCORE_THRESH})'}

🔧 ATR       : {atr[-1]:.2f}
🏗 Yapı Skoru: {ss:.1f}
⚡ Vol Skoru : {vs:.1f}
{poz_metin}"""

        telegram.mesaj_gonder(metin)
        log.info("Durum raporu gönderildi ✅")

    except Exception as e:
        log.error(f"Durum raporu hatası: {e}")

# ─────────────────────────────────────────────────────────────
# SİNYAL KONTROLÜ
# ─────────────────────────────────────────────────────────────

def kontrol_et():
    log.info("─" * 50)
    log.info(f"Kontrol: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    try:
        df = borsa.ohlcv_cek(sembol=cfg.SEMBOL, timeframe=cfg.TIMEFRAME, limit=500)
        log.info(f"Veri OK: {len(df)} bar")

        sinyal = strateji.sinyal_uret(df)

        if sinyal is None:
            log.info("Sinyal yok — bekleniyor")
            return

        log.info(f"Sinyal: {sinyal['yon']} @ {sinyal['fiyat']:.2f} | "
                 f"SL:{sinyal['sl']:.2f} | Rejim:{sinyal['rejim']}")

        if cfg.TEST_MODU:
            log.info("[TEST MODU] Emir gönderilmedi")
            telegram.sinyal_bildirimi(sinyal, True)
            return

        # Açık pozisyon var mı?
        if borsa.acik_pozisyon_var_mi():
            poz = borsa.pozisyon_bilgisi()
            if poz:
                log.info(f"Açık pozisyon: {poz['yon']} K/Z:{poz['kar_zarar']:+.2f}")
            return

        basarili = borsa.emir_gonder(sinyal=sinyal)
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
    log.info(f"PMAX BOT BAŞLATILDI — {cfg.SEMBOL}")
    log.info(f"Sembol: {cfg.SEMBOL} | TF: {cfg.TIMEFRAME} | Test: {cfg.TEST_MODU}")
    log.info("═" * 50)

    telegram.durum_bildirimi(
        f"🤖 PMAX Bot başlatıldı — {cfg.SEMBOL}\n"
        f"{'⚠️ TEST MODU' if cfg.TEST_MODU else '🔴 CANLI MOD'}\n"
        f"Sembol: {cfg.SEMBOL} | TF: {cfg.TIMEFRAME}\n"
        f"Pozisyon: {cfg.POZISYON_USDT} USDT | Kaldıraç: {cfg.KALDIRAC}x"
    )
    kontrol_et()
    durum_raporu()  # Başlangıçta bir kez gönder

def main():
    baslangic()

    # Her 5 dakikada bir sinyal kontrolü — cross kaçırılmasın
    schedule.every(5).minutes.do(kontrol_et)

    # Her 4 saatte bir durum raporu
    for saat in ["00:05", "04:05", "08:05", "12:05", "16:05", "20:05"]:
        schedule.every().day.at(saat).do(durum_raporu)

    log.info("Scheduler aktif")
    log.info("  Sinyal kontrolü: her 5 dakikada bir")
    log.info("  Durum raporu: 00:05, 04:05, 08:05, 12:05, 16:05, 20:05")

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == '__main__':
    main()
