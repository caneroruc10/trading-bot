"""
Borsa Modülü — Bitget Futures
================================
- Veri çekme (public API)
- Pozisyon sorgulama
- Emir gönderme
"""

import logging
import pandas as pd
import urllib.request
import ssl
import json
import time
import hmac
import hashlib
import base64
from datetime import datetime, timezone
import config as cfg

log = logging.getLogger(__name__)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

BITGET_BASE = "https://api.bitget.com"

# ─────────────────────────────────────────────────────────────
# İMZA
# ─────────────────────────────────────────────────────────────

def _timestamp():
    return str(int(datetime.now(timezone.utc).timestamp() * 1000))

def _imza(timestamp, method, path, body=''):
    msg = f"{timestamp}{method.upper()}{path}{body}"
    mac = hmac.new(
        cfg.BITGET_API_SECRET.encode('utf-8'),
        msg.encode('utf-8'),
        hashlib.sha256
    )
    return base64.b64encode(mac.digest()).decode()

def _headers(method, path, body=''):
    ts = _timestamp()
    return {
        'ACCESS-KEY':        cfg.BITGET_API_KEY,
        'ACCESS-SIGN':       _imza(ts, method, path, body),
        'ACCESS-TIMESTAMP':  ts,
        'ACCESS-PASSPHRASE': cfg.BITGET_PASSPHRASE,
        'Content-Type':      'application/json',
        'locale':            'en-US',
    }

def _get(path, params=None):
    qs = ''
    if params:
        qs = '?' + '&'.join(f"{k}={v}" for k,v in params.items())
    url = BITGET_BASE + path + qs
    req = urllib.request.Request(
        url,
        headers=_headers('GET', path + qs),
    )
    with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
        return json.loads(r.read())

def _post(path, body: dict):
    body_str = json.dumps(body)
    url = BITGET_BASE + path
    req = urllib.request.Request(
        url,
        data=body_str.encode('utf-8'),
        headers=_headers('POST', path, body_str),
        method='POST',
    )
    with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
        return json.loads(r.read())

# ─────────────────────────────────────────────────────────────
# VERİ ÇEKME — Public API
# ─────────────────────────────────────────────────────────────

def _bitget_veri(sembol, timeframe, limit):
    """Bitget public kline verisi"""
    # Bitget timeframe formatı
    tf_map = {
        '1m':'1m', '3m':'3m', '5m':'5m', '15m':'15m',
        '30m':'30m', '1h':'1H', '2h':'2H', '4h':'4H',
        '6h':'6H', '12h':'12H', '1d':'1D',
    }
    bg_tf = tf_map.get(timeframe, '1H')
    # Bitget sembol formatı: ETHUSDT → ETHUSDT (aynı)
    url = (f"https://api.bitget.com/api/v2/mix/market/candles"
           f"?symbol={sembol}&granularity={bg_tf}"
           f"&limit={limit}&productType=usdt-futures")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
        data = json.loads(r.read())

    if data.get('code') != '00000':
        raise Exception(f"Bitget hata: {data.get('msg')}")

    bars = data['data']
    rows = []
    for b in bars:
        rows.append({
            'timestamp': pd.Timestamp(int(b[0]), unit='ms'),
            'open':   float(b[1]),
            'high':   float(b[2]),
            'low':    float(b[3]),
            'close':  float(b[4]),
            'volume': float(b[5]),
        })
    df = pd.DataFrame(rows).set_index('timestamp').sort_index()
    return df[['open','high','low','close','volume']].iloc[:-1]

def _kraken_veri(sembol, timeframe, limit):
    """Yedek: Kraken"""
    tf_map = {'1m':1,'5m':5,'15m':15,'30m':30,'1h':60,'4h':240,'1d':1440}
    interval = tf_map.get(timeframe, 60)
    kraken_sembol = 'XETHZUSD' if 'ETH' in sembol else 'XXBTZUSD'
    url = (f"https://api.kraken.com/0/public/OHLC"
           f"?pair={kraken_sembol}&interval={interval}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
        data = json.loads(r.read())
    bars = list(data['result'].values())[0][-limit:]
    rows = [{'timestamp': pd.Timestamp(b[0], unit='s'),
             'open': float(b[1]), 'high': float(b[2]),
             'low': float(b[3]), 'close': float(b[4]),
             'volume': float(b[6])} for b in bars]
    df = pd.DataFrame(rows).set_index('timestamp')
    return df[['open','high','low','close','volume']].iloc[:-1]

def ohlcv_cek(client=None, sembol=None, timeframe=None, limit=500) -> pd.DataFrame:
    sembol    = sembol    or cfg.SEMBOL
    timeframe = timeframe or cfg.TIMEFRAME

    kaynaklar = [
        ('Bitget', lambda: _bitget_veri(sembol, timeframe, limit)),
        ('Kraken', lambda: _kraken_veri(sembol, timeframe, limit)),
    ]
    son_hata = None
    for ad, fn in kaynaklar:
        try:
            df = fn()
            log.info(f"Veri çekildi ({ad}): {len(df)} bar | "
                     f"{df.index[0]} → {df.index[-1]}")
            return df
        except Exception as e:
            log.warning(f"{ad} başarısız: {e}")
            son_hata = e
            time.sleep(1)
    raise Exception(f"Tüm veri kaynakları başarısız: {son_hata}")

# ─────────────────────────────────────────────────────────────
# POZİSYON SORGULAMA
# ─────────────────────────────────────────────────────────────

def acik_pozisyon_var_mi(client=None, sembol=None) -> bool:
    sembol = sembol or cfg.SEMBOL
    try:
        r = _get('/api/v2/mix/position/single-position', {
            'symbol': sembol,
            'productType': 'USDT-FUTURES',
            'marginCoin': 'USDT',
        })
        if r.get('code') != '00000':
            log.error(f"Pozisyon sorgu hatası: {r.get('msg')}")
            return False
        pozlar = r.get('data', [])
        for p in pozlar:
            if float(p.get('total', 0)) > 0:
                log.info(f"Açık pozisyon: {p['holdSide']} {p['total']} @ {p.get('openPriceAvg', p.get('averageOpenPrice', 0))}")
                return True
        return False
    except Exception as e:
        log.error(f"Pozisyon sorgu hatası: {e}")
        return False

def pozisyon_bilgisi(client=None, sembol=None) -> dict | None:
    sembol = sembol or cfg.SEMBOL
    try:
        r = _get('/api/v2/mix/position/single-position', {
            'symbol': sembol,
            'productType': 'USDT-FUTURES',
            'marginCoin': 'USDT',
        })
        pozlar = r.get('data', [])
        for p in pozlar:
            if float(p.get('total', 0)) > 0:
                return {
                    'yon':         'LONG' if p['holdSide'] == 'long' else 'SHORT',
                    'miktar':      float(p['total']),
                    'giris_fiyat': float(p.get('openPriceAvg', p.get('averageOpenPrice', 0))),
                    'kar_zarar':   float(p.get('unrealizedPL', 0)),
                }
        return None
    except Exception as e:
        log.error(f"Pozisyon bilgisi hatası: {e}")
        return None

# ─────────────────────────────────────────────────────────────
# EMİR GÖNDERİM
# ─────────────────────────────────────────────────────────────

def _kaldirac_ayarla(sembol):
    try:
        r = _post('/api/v2/mix/account/set-leverage', {
            'symbol':      sembol,
            'productType': 'USDT-FUTURES',
            'marginCoin':  'USDT',
            'leverage':    str(cfg.KALDIRAC),
            'holdSide':    'long',
        })
        _post('/api/v2/mix/account/set-leverage', {
            'symbol':      sembol,
            'productType': 'USDT-FUTURES',
            'marginCoin':  'USDT',
            'leverage':    str(cfg.KALDIRAC),
            'holdSide':    'short',
        })
        log.info(f"Kaldıraç ayarlandı: {cfg.KALDIRAC}x")
    except Exception as e:
        log.warning(f"Kaldıraç ayar uyarısı: {e}")

def _miktar_hesapla(fiyat):
    """USDT miktarını kontrat sayısına çevir"""
    # Bitget'te 1 kontrat = 1 coin (ETH için 0.01 ETH minimum)
    miktar = cfg.POZISYON_USDT / fiyat
    return round(miktar, 4)

def emir_gonder(client=None, sinyal: dict = None, sembol=None) -> bool:
    sembol = sembol or cfg.SEMBOL
    yon    = sinyal['yon']
    fiyat  = sinyal['fiyat']
    sl     = sinyal['sl']
    tp     = sinyal['tp']

    if cfg.TEST_MODU:
        log.info(f"[TEST] {yon} {sembol} @ {fiyat:.2f} | "
                 f"SL:{sl:.2f} | Kaldıraç:{cfg.KALDIRAC}x")
        return True

    try:
        # Kaldıraç ayarla
        _kaldirac_ayarla(sembol)

        miktar = _miktar_hesapla(fiyat)
        side   = 'buy'  if yon == 'LONG'  else 'sell'

        log.info(f"Emir gönderiliyor: {side.upper()} {miktar} {sembol}")

        # Market emir
        r = _post('/api/v2/mix/order/place-order', {
            'symbol':      sembol,
            'productType': 'USDT-FUTURES',
            'marginMode':  'isolated',
            'marginCoin':  'USDT',
            'size':        str(miktar),
            'side':        side,
            'orderType':   'market',
            'tradeSide':   'open',
        })
        if r.get('code') != '00000':
            log.error(f"Market emir hatası: {r.get('msg')}")
            return False
        log.info(f"Market emir OK: {r['data'].get('orderId')}")

        # Stop-Loss
        holdSide = 'long' if yon == 'LONG' else 'short'
        sl_body = {
            'symbol':        sembol,
            'productType':   'USDT-FUTURES',
            'marginCoin':    'USDT',
            'planType':      'loss_plan',
            'triggerPrice':  str(round(sl, 2)),
            'triggerType':   'mark_price',
            'size':          str(miktar),
            'holdSide':      holdSide,
        }
        log.info(f"SL gönderiliyor: {sl_body}")
        r_sl = _post('/api/v2/mix/order/place-tpsl-order', sl_body)
        if r_sl.get('code') != '00000':
            log.warning(f"SL emir uyarısı: {r_sl.get('msg')} | Tam yanıt: {r_sl}")
        else:
            log.info(f"Stop-Loss ayarlandı: {sl} ✅")

        # Take-Profit
        if tp:
            tp_body = {
                'symbol':        sembol,
                'productType':   'USDT-FUTURES',
                'marginCoin':    'USDT',
                'planType':      'profit_plan',
                'triggerPrice':  str(round(tp, 2)),
                'triggerType':   'mark_price',
                'size':          str(miktar),
                'holdSide':      holdSide,
            }
            log.info(f"TP gönderiliyor: {tp_body}")
            r_tp = _post('/api/v2/mix/order/place-tpsl-order', tp_body)
            if r_tp.get('code') != '00000':
                log.warning(f"TP emir uyarısı: {r_tp.get('msg')} | Tam yanıt: {r_tp}")
            else:
                log.info(f"Take-Profit ayarlandı: {tp} ✅")

        return True

    except Exception as e:
        log.error(f"Emir hatası: {e}")
        return False

def pozisyon_kapat(client=None, sembol=None) -> bool:
    sembol = sembol or cfg.SEMBOL
    if cfg.TEST_MODU:
        return True
    try:
        poz = pozisyon_bilgisi(sembol=sembol)
        if not poz:
            return True
        side = 'sell' if poz['yon'] == 'LONG' else 'buy'
        r = _post('/api/v2/mix/order/place-order', {
            'symbol':      sembol,
            'productType': 'USDT-FUTURES',
            'marginMode':  'isolated',
            'marginCoin':  'USDT',
            'size':        str(poz['miktar']),
            'side':        side,
            'orderType':   'market',
            'tradeSide':   'close',
        })
        if r.get('code') == '00000':
            log.info("Pozisyon kapatıldı ✅")
            return True
        log.error(f"Pozisyon kapatma hatası: {r.get('msg')}")
        return False
    except Exception as e:
        log.error(f"Kapatma hatası: {e}")
        return False

# Eski Binance client uyumluluğu için
def client_olustur():
    return None
