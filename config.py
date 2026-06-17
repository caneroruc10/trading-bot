"""
Sistem Konfigürasyonu
=====================
Tüm parametreler burada — Railway'de environment variable olarak set edilir.
Default değerler Pine v6 indikatörü ile aynı.
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

# ─── PMAX PARAMETRELERİ (Pine v6 default: 12 / 7 / 4.0)
ATR_PERIOD  = int(os.getenv('ATR_PERIOD',  '12'))
EMA_PERIOD  = int(os.getenv('EMA_PERIOD',  '7'))
COEFFICIENT = float(os.getenv('COEFFICIENT', '4.0'))
MA_TIPI     = os.getenv('MA_TIPI', 'EMA')  # EMA veya VAR

# ─── TREND SKORU (Pine v6 default: 4 / 4 / 2 / 44)
PIVOT_LEFT   = int(os.getenv('PIVOT_LEFT',   '4'))
PIVOT_RIGHT  = int(os.getenv('PIVOT_RIGHT',  '4'))
PIVOT_COUNT  = int(os.getenv('PIVOT_COUNT',  '2'))
SCORE_THRESH = int(os.getenv('SCORE_THRESH', '44'))

# ─── FAKE SİNYAL SAYACI (Pine v6 default: 3)
# Pozisyon açıkken, ters yönde gelen ve skor yetersiz olan PMAX cross'ları sayılır.
# Sayaç FAKE_ESIK'e ulaştıktan sonra gelen ilk ters PMAX yönü, skor yetersiz olsa da
# pozisyonu kapatır ve TERS YÖNDE yeni pozisyon açar (zorla ters dönüş).
FAKE_ESIK = int(os.getenv('FAKE_ESIK', '3'))

# ─── VOLATİLİTE NORMALIZASYON
VOL_MIN = float(os.getenv('VOL_MIN', '0.3'))
VOL_MAX = float(os.getenv('VOL_MAX', '1.5'))

# ─── STOP LOSS / TAKE PROFIT (bilgi amaçlı; SL/TP emir gönderilmez —
#  pozisyon PMAX ters dönüşü / zorla ters dönüş ile yönetilir)
HARD_STOP_ATR  = float(os.getenv('HARD_STOP_ATR',  '5.0'))
TRAIL_STOP_ATR = float(os.getenv('TRAIL_STOP_ATR', '1.5'))
KAR_AL_ATR     = float(os.getenv('KAR_AL_ATR',     '5.5'))

# ─── GÖSTERİM AYARLARI (Pine v6 ile aynı)
LONG_ONLY = os.getenv('LONG_ONLY', 'false').lower() == 'true'

# ─── SİSTEM
TEST_MODU = os.getenv('TEST_MODU', 'true').lower() == 'true'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
