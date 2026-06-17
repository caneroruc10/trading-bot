"""
PMAX BOT — Ana Program
=======================
Railway'de çalışır.
- Her saat :05'te sinyal kontrolü (bar kapanışından 5dk sonra)
- 6 saatte bir durum raporu (Telegram)
- Pine v6 state machine ile birebir: PMAX + Trend Skoru + Fake Sayaç + Zorla Ters
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
# YARDIMCI
# ─────────────────────────────────────────────────────────────

def _sinyal_obj(durum: dict, hedef_yon: str) -> dict:
    """Telegram bildirimi için sinyal nesnesi hazırla"""
    fiyat   = durum['fiyat']
    atr_val = durum['atr']
    if hedef_yon == 'LONG':
        sl = round(fiyat - atr_val * cfg.HARD_STOP_ATR, 4)
        tp = round(fiyat + atr_val * cfg.KAR_AL_ATR, 4) if cfg.KAR_AL_ATR > 0 else None
    else:
        sl = round(fiyat + atr_val * cfg.HARD_STOP_ATR, 4)
        tp = round(fiyat - atr_val * cfg.KAR_AL_ATR, 4) if cfg.KAR_AL_ATR > 0 else None
    return {
        'yon':         hedef_yon,
        'fiyat':       fiyat,
        'atr':         atr_val,
        'sl':          sl,
        'tp':          tp,
        'trend_skoru': durum['trend_skoru'],
        'zorla_ters':  durum['zorla_ters'],
    }

# ─────────────────────────────────────────────────────────────
# SİNYAL KONTROLÜ
# ─────────────────────────────────────────────────────────────

def kontrol_et():
    log.info("─" * 50)
    log.info(f"Kontrol: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    try:
        df = borsa.ohlcv_cek(sembol=cfg.SEMBOL, timeframe=cfg.TIMEFRAME, limit=500)
        log.info(f"Veri OK: {len(df)} bar")

        # State machine'i tüm geçmiş üzerinde çalıştır
        durum = strateji.durum_makinesini_calistir(df, long_only=cfg.LONG_ONLY)

        log.info(f"State → poz={durum['pozisyon']} "
                 f"fake={durum['fake_sayac']}/{cfg.FAKE_ESIK} "
                 f"esik_asildi={durum['esik_asildi']} "
                 f"son_sinyal={durum['son_sinyal']} "
                 f"zorla_ters={durum['zorla_ters']}")
        log.info(f"Skor: {durum['trend_skoru']:.1f}/100 "
                 f"(Yapı:{durum['yapi_skoru']:.1f} Vol:{durum['vol_skoru']:.1f}) "
                 f"PMAX:{durum['pmax_yon']} ATR:{durum['atr']:.4f}")

        # Borsadaki gerçek pozisyonu sorgula
        poz = borsa.pozisyon_bilgisi()
        gercek_yon = poz['yon'] if poz else 'YOK'
        log.info(f"Borsa: {gercek_yon}" +
                 (f" K/Z:{poz['kar_zarar']:+.2f}" if poz else ""))

        # Tutarsızlık varsa uyar (ama düzeltmeye çalışma — sadece bilgi)
        if durum['pozisyon'] != gercek_yon:
            log.warning(f"⚠️ Bot/Borsa tutarsızlığı: "
                        f"bot={durum['pozisyon']} borsa={gercek_yon}")

        # Bu bar'da sinyal üretilmedi mi? Bekle.
        if not durum['son_sinyal']:
            log.info("Sinyal yok — bekleniyor")
            return

        hedef_yon = 'LONG' if durum['son_sinyal'] == 'AL' else 'SHORT'
        zorla_etiket = ' [ZORLA TERS]' if durum['zorla_ters'] else ''
        log.info(f"🎯 Sinyal: {hedef_yon}{zorla_etiket}")

        # Zaten aynı yönde pozisyondaysak hiçbir şey yapma
        if gercek_yon == hedef_yon:
            log.info(f"Zaten {hedef_yon} pozisyonda — bekle")
            return

        sinyal_obj = _sinyal_obj(durum, hedef_yon)

        # Karşı yönde pozisyon varsa önce kapat
        if gercek_yon != 'YOK':
            log.info(f"Önce {gercek_yon} pozisyon kapatılıyor")
            if cfg.TEST_MODU:
                log.info(f"[TEST] {gercek_yon} kapatılırdı")
                telegram.durum_bildirimi(
                    f"{'⚡ <b>ZORLA TERS</b>' if durum['zorla_ters'] else '🔄'} "
                    f"{cfg.SEMBOL}: {gercek_yon} kapatıldı [TEST]\n"
                    f"K/Z: {poz['kar_zarar']:+.2f} USDT"
                )
            else:
                kapandi = borsa.pozisyon_kapat()
                if not kapandi:
                    log.error("Pozisyon kapatılamadı — yeni emir gönderilmiyor")
                    telegram.hata_bildirimi(f"{gercek_yon} kapatılamadı!")
                    return
                log.info(f"{gercek_yon} kapatıldı ✅")
                telegram.durum_bildirimi(
                    f"{'⚡ <b>ZORLA TERS DÖNÜŞ</b>' if durum['zorla_ters'] else '🔄'} "
                    f"{cfg.SEMBOL}: {gercek_yon} kapatıldı\n"
                    f"K/Z: {poz['kar_zarar']:+.2f} USDT"
                )

        # Yeni pozisyon aç
        log.info(f"{hedef_yon} pozisyon açılıyor: @ {sinyal_obj['fiyat']:.4f}")
        if cfg.TEST_MODU:
            log.info("[TEST MODU] Emir gönderilmedi")
            telegram.sinyal_bildirimi(sinyal_obj, True)
            return

        basarili = borsa.emir_gonder(sinyal=sinyal_obj)
        telegram.sinyal_bildirimi(sinyal_obj, basarili)
        if basarili:
            log.info(f"✅ {hedef_yon} açıldı")
        else:
            log.error(f"❌ {hedef_yon} açılamadı")
            telegram.hata_bildirimi(f"{hedef_yon} emir gönderilemedi!")

    except Exception as e:
        log.error(f"Hata: {e}", exc_info=True)
        telegram.hata_bildirimi(str(e)[:200])

# ─────────────────────────────────────────────────────────────
# DURUM RAPORU
# ─────────────────────────────────────────────────────────────

def durum_raporu():
    log.info("Durum raporu hazırlanıyor...")
    try:
        df = borsa.ohlcv_cek(sembol=cfg.SEMBOL, timeframe=cfg.TIMEFRAME, limit=500)
        durum = strateji.durum_makinesini_calistir(df, long_only=cfg.LONG_ONLY)

        yon_emoji   = '🟢 BULL' if durum['pmax_yon'] == 'BULL' else '🔴 BEAR'
        dolu        = int(durum['trend_skoru'] / 10)
        skor_bar    = '█' * dolu + '░' * (10 - dolu)
        trend_aktif = durum['trend_skoru'] >= cfg.SCORE_THRESH

        poz = borsa.pozisyon_bilgisi()
        if poz:
            poz_metin = (f"\n💼 Açık Pozisyon: {poz['yon']} "
                         f"@ {poz['giris_fiyat']:.4f} "
                         f"| K/Z: {poz['kar_zarar']:+.2f} USDT")
        else:
            poz_metin = "\n💼 Açık Pozisyon: Yok"

        if durum['esik_asildi']:
            fake_metin = "⚠️ EŞİK AŞILDI (sıradaki ters PMAX'ta zorla kapatır+ters açar)"
        else:
            fake_metin = f"Fake Sayaç : {durum['fake_sayac']}/{cfg.FAKE_ESIK}"

        metin = f"""📊 <b>PMAX — {cfg.SEMBOL} Durum Raporu</b>
{datetime.now().strftime('%d.%m.%Y %H:%M')} UTC+3

💰 Fiyat     : <code>{durum['fiyat']:.4f}</code> USDT
📈 PMAX Yön  : {yon_emoji}

📉 Trend Skoru : {durum['trend_skoru']:.1f}/100
<code>{skor_bar}</code>
{'✅ AKTİF' if trend_aktif else f'❌ PASİF (eşik: {cfg.SCORE_THRESH})'}

🔧 ATR        : {durum['atr']:.4f}
🏗 Yapı Skoru : {durum['yapi_skoru']:.1f}
⚡ Vol Skoru  : {durum['vol_skoru']:.1f}
🔁 {fake_metin}

⚙️ <b>Parametreler</b>
ATR Periyodu : {cfg.ATR_PERIOD}
MA           : {cfg.MA_TIPI}({cfg.EMA_PERIOD})
Coefficient  : {cfg.COEFFICIENT}
Skor Eşiği   : {cfg.SCORE_THRESH}
Fake Eşik    : {cfg.FAKE_ESIK}
{poz_metin}"""

        telegram.mesaj_gonder(metin)
        log.info("Durum raporu gönderildi ✅")

    except Exception as e:
        log.error(f"Durum raporu hatası: {e}")

# ─────────────────────────────────────────────────────────────
# BAŞLANGIÇ
# ─────────────────────────────────────────────────────────────

def baslangic():
    log.info("═" * 50)
    log.info(f"PMAX BOT BAŞLATILDI — {cfg.SEMBOL}")
    log.info(f"Sembol: {cfg.SEMBOL} | TF: {cfg.TIMEFRAME} | Test: {cfg.TEST_MODU}")
    log.info(f"ATR:{cfg.ATR_PERIOD} MA:{cfg.MA_TIPI}({cfg.EMA_PERIOD}) "
             f"Coeff:{cfg.COEFFICIENT} SkorEşik:{cfg.SCORE_THRESH} "
             f"FakeEşik:{cfg.FAKE_ESIK} LongOnly:{cfg.LONG_ONLY}")
    log.info("═" * 50)

    telegram.durum_bildirimi(
        f"🤖 PMAX Bot başlatıldı — {cfg.SEMBOL}\n"
        f"{'⚠️ TEST MODU' if cfg.TEST_MODU else '🔴 CANLI MOD'}\n"
        f"Sembol: {cfg.SEMBOL} | TF: {cfg.TIMEFRAME}\n"
        f"Pozisyon: {cfg.POZISYON_USDT} USDT | Kaldıraç: {cfg.KALDIRAC}x"
    )
    kontrol_et()
    durum_raporu()

def main():
    baslangic()

    # Saatlik bar kapanışından 5 dakika sonra kontrol et
    schedule.every().hour.at(":05").do(kontrol_et)

    for saat in ["00:05", "04:05", "08:05", "12:05", "16:05", "20:05"]:
        schedule.every().day.at(saat).do(durum_raporu)

    log.info("Scheduler aktif")
    log.info("  Sinyal kontrolü: her saat :05'te (bar kapanışından 5dk sonra)")
    log.info("  Durum raporu: 00:05, 04:05, 08:05, 12:05, 16:05, 20:05")

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == '__main__':
    main()
