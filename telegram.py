"""
Telegram Bildirim Modülü
=========================
"""
import logging
import requests
import config as cfg
log = logging.getLogger(__name__)

def mesaj_gonder(metin: str) -> bool:
    """Telegram'a mesaj gönder"""
    if not cfg.TELEGRAM_TOKEN or not cfg.TELEGRAM_CHAT_ID:
        log.warning("Telegram ayarları eksik — bildirim atlandı")
        return False
    try:
        url = f"https://api.telegram.org/bot{cfg.TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, json={
            'chat_id':    cfg.TELEGRAM_CHAT_ID,
            'text':       metin,
            'parse_mode': 'HTML',
        }, timeout=10)
        if r.status_code == 200:
            log.info("Telegram bildirimi gönderildi ✅")
            return True
        else:
            log.error(f"Telegram hatası: {r.status_code} {r.text}")
            return False
    except Exception as e:
        log.error(f"Telegram bağlantı hatası: {e}")
        return False

def sinyal_bildirimi(sinyal: dict, basarili: bool) -> bool:
    emoji = '🟢' if sinyal['yon'] == 'LONG' else '🔴'
    durum = '✅ İşlem açıldı' if basarili else '❌ İşlem başarısız'
    test  = ' <b>[TEST]</b>' if cfg.TEST_MODU else ''
    zorla = ('\n⚡ <b>ZORLA TERS DÖNÜŞ</b> (fake eşik aşıldı, skor yetersiz)'
             if sinyal.get('zorla_ters') else '')
    tp_metin = f"{sinyal['tp']:.2f}" if sinyal.get('tp') else 'Kapalı'

    metin = f"""{emoji} <b>{sinyal['yon']} {cfg.SEMBOL}</b>{test}
{durum}{zorla}

💰 Giriş   : <code>{sinyal['fiyat']:.2f}</code>
🛑 Stop-L  : <code>{sinyal['sl']:.2f}</code>
🎯 Take-P  : <code>{tp_metin}</code>
📈 Skor    : {sinyal['trend_skoru']:.1f}/100
"""
    return mesaj_gonder(metin)

def durum_bildirimi(mesaj: str) -> bool:
    return mesaj_gonder(f"ℹ️ <b>BOT — {cfg.SEMBOL}</b>\n{mesaj}")

def hata_bildirimi(hata: str) -> bool:
    return mesaj_gonder(f"⚠️ <b>HATA</b>\n<code>{hata}</code>")
