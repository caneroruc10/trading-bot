"""
Sistem Konfigürasyonu
=====================
Tüm parametreler burada — Railway'de environment variable olarak set edilir.
"""
import os

# ─── BORSA
BINANCE_API_KEY    = os.getenv('BINANCE_API_KEY', '')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '')

# ─── TELEGRAM
TELEGRAM_TOKEN   = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# ─── SEMBOL
SEMBOL     = os.getenv('SEMBOL', 'ETHUSDT')
TIMEFRAME  = os.getenv('TIMEFRAME', '1h')
POZISYON_USDT = float(os.getenv('POZISYON_USDT', '100'))  # Her işlemde kaç USDT
KALDIRAC     = int(os.getenv('KALDIRAC', '3'))                  # Kaldıraç oranı

# ─── PMAX PARAMETRELERİ (TradingView değerleri)
ATR_PERIOD   = int(os.getenv('ATR_PERIOD', '18'))
EMA_PERIOD   = int(os.getenv('EMA_PERIOD', '4'))
COEFFICIENT  = float(os.getenv('COEFFICIENT', '1.0'))

# ─── TREND SKORU
PIVOT_LEFT   = int(os.getenv('PIVOT_LEFT', '2'))
PIVOT_RIGHT  = int(os.getenv('PIVOT_RIGHT', '2'))
PIVOT_COUNT  = int(os.getenv('PIVOT_COUNT', '2'))
SCORE_THRESH = int(os.getenv('SCORE_THRESH', '40'))

# ─── STOP LOSS (Binance stop-loss emir olarak gönderilir)
HARD_STOP_ATR   = float(os.getenv('HARD_STOP_ATR', '5.0'))    # 5x ATR
TRAIL_STOP_ATR  = float(os.getenv('TRAIL_STOP_ATR', '1.5'))   # 1.5x ATR (callback)
KAR_AL_ATR      = float(os.getenv('KAR_AL_ATR', '5.5'))       # 5.5x ATR (0 = kapalı)

# ─── VOLATİLİTE NORMALIZASYON (Matriks versiyonu)
VOL_MIN = float(os.getenv('VOL_MIN', '0.3'))
VOL_MAX = float(os.getenv('VOL_MAX', '1.5'))

# ─── REJİM FİLTRESİ — elenen kombinasyonlar
# Format: "Sakin:LONG,Gecis:SHORT"
ELENEN_KOMBINASYONLAR = [
    ('Sakin', 'LONG'),
    ('Geçiş', 'SHORT'),
]

# ─── PMAX GECİKME (Matriks = 3 bar gecikme)
SINYAL_GECIKME = int(os.getenv('SINYAL_GECIKME', '3'))

# ─── SİSTEM
TEST_MODU = os.getenv('TEST_MODU', 'true').lower() == 'true'  # True = emir gönderme, sadece log
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ─── ÖZET
def ayarlari_yazdir():
    print(f"""
╔══════════════════════════════════════╗
║  ETH PMAX BOT — Konfigürasyon       ║
╠══════════════════════════════════════╣
║  Sembol     : {SEMBOL:<22}║
║  Timeframe  : {TIMEFRAME:<22}║
║  Pozisyon   : {POZISYON_USDT:<22}USDT
║  Test modu  : {str(TEST_MODU):<22}║
╠══════════════════════════════════════╣
║  ATR        : {ATR_PERIOD:<22}║
║  EMA        : {EMA_PERIOD:<22}║
║  Coeff      : {COEFFICIENT:<22}║
║  Skor eşiği : {SCORE_THRESH:<22}║
╠══════════════════════════════════════╣
║  Hard SL    : {HARD_STOP_ATR}x ATR{'':<16}║
║  Trail SL   : {TRAIL_STOP_ATR}x ATR{'':<16}║
║  Kar Al     : {KAR_AL_ATR}x ATR{'':<16}║
╚══════════════════════════════════════╝
""")
