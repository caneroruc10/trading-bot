"""
Sistem Konfigürasyonu
=====================
Tüm parametreler burada — Railway'de environment variable olarak set edilir.
"""
import os

# ─── BORSA — Bitget
BITGET_API_KEY    = os.getenv('BITGET_API_KEY', '')
BITGET_API_SECRET = os.getenv('BITGET_API_SECRET', '')
BITGET_PASSPHRASE = os.getenv('BITGET_PASSPHRASE', '')

# ─── TELEGRAM
TELEGRAM_TOKEN   = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# ─── SEMBOL
SEMBOL        = os.getenv('SEMBOL', 'ETHUSDT')
TIMEFRAME     = os.getenv('TIMEFRAME', '1h')
POZISYON_USDT = float(os.getenv('POZISYON_USDT', '100'))
KALDIRAC      = int(os.getenv('KALDIRAC', '3'))

# ─── PMAX PARAMETRELERİ
ATR_PERIOD  = int(os.getenv('ATR_PERIOD',  '10'))
EMA_PERIOD  = int(os.getenv('EMA_PERIOD',  '9'))
COEFFICIENT = float(os.getenv('COEFFICIENT', '1.0'))
MA_TIPI     = os.getenv('MA_TIPI', 'EMA')  # EMA veya VAR

# ─── TREND SKORU
PIVOT_LEFT   = int(os.getenv('PIVOT_LEFT',   '2'))
PIVOT_RIGHT  = int(os.getenv('PIVOT_RIGHT',  '2'))
PIVOT_COUNT  = int(os.getenv('PIVOT_COUNT',  '2'))
SCORE_THRESH = int(os.getenv('SCORE_THRESH', '30'))

# ─── STOP LOSS
HARD_STOP_ATR  = float(os.getenv('HARD_STOP_ATR',  '5.0'))
TRAIL_STOP_ATR = float(os.getenv('TRAIL_STOP_ATR', '1.5'))
KAR_AL_ATR     = float(os.getenv('KAR_AL_ATR',     '5.5'))

# ─── VOLATİLİTE NORMALIZASYON
VOL_MIN = float(os.getenv('VOL_MIN', '0.3'))
VOL_MAX = float(os.getenv('VOL_MAX', '1.5'))

# ─── REJİM FİLTRESİ
def _parse_elenenler(env_str):
    if not env_str:
        return set()
    sonuc = set()
    for kombinasyon in env_str.split(','):
        kombinasyon = kombinasyon.strip()
        if '+' in kombinasyon:
            parcalar = kombinasyon.split('+')
            rejim = parcalar[0].strip()
            yon   = parcalar[1].strip().lower()
            rejim = rejim.replace('Gecis', 'Geçiş').replace('Gecış', 'Geçiş')
            sonuc.add((rejim, yon))
    return sonuc

_env_elenenler = os.getenv('ELENEN_KOMBINASYONLAR', '')
ELENEN_KOMBINASYONLAR = _parse_elenenler(_env_elenenler) if _env_elenenler else {
    ('Sakin', 'long'), ('Geçiş', 'short')
}

# ─── PMAX GECİKME
SINYAL_GECIKME = int(os.getenv('SINYAL_GECIKME', '3'))

# ─── SİSTEM
TEST_MODU = os.getenv('TEST_MODU', 'true').lower() == 'true'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
