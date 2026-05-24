"""
Borsa Modülü — Çoklu veri kaynağı
===================================
Veri çekme sırası:
  1. Binance Futures public API
  2. Binance Spot public API  
  3. Kraken (yedek)
"""

import logging
import pandas as pd
import numpy as np
import urllib.request
import urllib.parse
import ssl
import json
import time
from binance.client import Client
from binance.exceptions import BinanceAPIException
import config as cfg

log = logging.getLogger(__name__)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def client_olustur():
    return Client(cfg.BINANCE_API_KEY, cfg.BINANCE_API_SECRET)

# ─────────────────────────────────────────────────────────────
# VERİ ÇEKME — Çoklu kaynak
# ─────────────────────────────────────────────────────────────

def _fetch_url(url):
    req = urllib.request.Request(
        url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
        return json.loads(r.read())

def _binance_futures(sembol, timeframe, limit):
    url = (f"https://fapi.binance.com/fapi/v1/klines"
           f"?symbol={sembol}&interval={timeframe}&limit={limit}")
    data = _fetch_url(url)
    df = pd.DataFrame(data, columns=[
        'timestamp','open','high','low','close','volume',
        'close_time','quote_vol','trades','tb_base','tb_quote','ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')
    for col in ['open','high','low','close','volume']:
        df[col] = df[col].astype(float)
    return df[['open','high','low','close','volume']].iloc[:-1]

def _binance_spot(sembol, timeframe, limit):
    url = (f"https://api.binance.com/api/v3/klines"
           f"?symbol={sembol}&interval={timeframe}&limit={limit}")
    data = _fetch_url(url)
    df = pd.DataFrame(data, columns=[
        'timestamp','open','high','low','close','volume',
        'close_time','quote_vol','trades','tb_base','tb_quote','ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')
    for col in ['open','high','low','close','volume']:
        df[col] = df[col].astype(float)
    return df[['open','high','low','close','volume']].iloc[:-1]

def _kraken(sembol, timeframe, limit):
    """Kraken API — Binance erişilemezse yedek"""
    # Timeframe dönüşümü
    tf_map = {'1m':1,'5m':5,'15m':15,'30m':30,'1h':60,'4h':240,'1d':1440}
    interval = tf_map.get(timeframe, 60)

    # Sembol dönüşümü (ETHUSDT → XETHZUSD)
    kraken_sembol = 'XETHZUSD' if 'ETH' in sembol else 'XXBTZUSD'

    url = (f"https://api.kraken.com/0/public/OHLC"
           f"?pair={kraken_sembol}&interval={interval}")
    data = _fetch_url(url)

    if data.get('error'):
        raise Exception(f"Kraken hata: {data['error']}")

    bars = list(data['result'].values())[0][-limit:]
    rows = []
    for b in bars:
        rows.append({
            'timestamp': pd.Timestamp(b[0], unit='s'),
            'open':   float(b[1]),
            'high':   float(b[2]),
            'low':    float(b[3]),
            'close':  float(b[4]),
            'volume': float(b[6]),
        })
    df = pd.DataFrame(rows).set_index('timestamp')
    return df[['open','high','low','close','volume']].iloc[:-1]

def ohlcv_cek(client=None, sembol=None, timeframe=None, limit=500) -> pd.DataFrame:
    """Veri çek — sırayla 3 kaynak dene"""
    sembol    = sembol    or cfg.SEMBOL
    timeframe = timeframe or cfg.TIMEFRAME

    kaynaklar = [
        ('Binance Futures', lambda: _binance_futures(sembol, timeframe, limit)),
        ('Binance Spot',    lambda: _binance_spot(sembol, timeframe, limit)),
        ('Kraken',          lambda: _kraken(sembol, timeframe, limit)),
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
# POZİSYON & EMİR
# ─────────────────────────────────────────────────────────────

def acik_pozisyon_var_mi(client, sembol=None) -> bool:
    sembol = sembol or cfg.SEMBOL
    try:
        pozisyonlar = client.futures_position_information(symbol=sembol)
        for poz in pozisyonlar:
            if float(poz['positionAmt']) != 0:
                log.info(f"Açık pozisyon: {poz['positionAmt']} @ {poz['entryPrice']}")
                return True
        return False
    except BinanceAPIException as e:
        log.error(f"Pozisyon sorgu hatası: {e}")
        return True

def pozisyon_bilgisi(client, sembol=None) -> dict | None:
    sembol = sembol or cfg.SEMBOL
    try:
        pozisyonlar = client.futures_position_information(symbol=sembol)
        for poz in pozisyonlar:
            amt = float(poz['positionAmt'])
            if amt != 0:
                return {
                    'yon':         'LONG' if amt > 0 else 'SHORT',
                    'miktar':      abs(amt),
                    'giris_fiyat': float(poz['entryPrice']),
                    'kar_zarar':   float(poz['unrealizedProfit']),
                }
        return None
    except BinanceAPIException as e:
        log.error(f"Pozisyon bilgisi hatası: {e}")
        return None

def pozisyon_miktari_hesapla(client, usdt_miktar, fiyat, sembol=None) -> float:
    sembol = sembol or cfg.SEMBOL
    try:
        info = client.futures_exchange_info()
        for s in info['symbols']:
            if s['symbol'] == sembol:
                for f in s['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        step = float(f['stepSize'])
                        miktar = usdt_miktar / fiyat
                        miktar = round(miktar / step) * step
                        return round(miktar, 8)
    except:
        pass
    return round(usdt_miktar / fiyat, 3)

def emir_gonder(client, sinyal: dict, sembol=None) -> bool:
    sembol = sembol or cfg.SEMBOL
    if cfg.TEST_MODU:
        log.info(f"[TEST] {sinyal['yon']} {sembol} @ {sinyal['fiyat']:.2f} | Kaldirac:{cfg.KALDIRAC}x")
        return True
    try:
        # Kaldirac ayarla
        try:
            client.futures_change_leverage(symbol=sembol, leverage=cfg.KALDIRAC)
            log.info(f"Kaldirac: {cfg.KALDIRAC}x")
        except BinanceAPIException as e:
            log.warning(f"Kaldirac uyari: {e}")
        # Margin tipi ISOLATED
        try:
            client.futures_change_margin_type(symbol=sembol, marginType='ISOLATED')
        except BinanceAPIException:
            pass
        miktar  = pozisyon_miktari_hesapla(client, cfg.POZISYON_USDT, sinyal['fiyat'])
        side    = 'BUY'  if sinyal['yon'] == 'LONG'  else 'SELL'
        sl_side = 'SELL' if sinyal['yon'] == 'LONG'  else 'BUY'
        client.futures_create_order(
            symbol=sembol, side=side, type='MARKET', quantity=miktar)
        client.futures_create_order(
            symbol=sembol, side=sl_side, type='STOP_MARKET',
            stopPrice=sinyal['sl'], closePosition=True)
        if sinyal['tp']:
            client.futures_create_order(
                symbol=sembol, side=sl_side, type='TAKE_PROFIT_MARKET',
                stopPrice=sinyal['tp'], closePosition=True)
        return True
    except BinanceAPIException as e:
        log.error(f"Emir hatası: {e}")
        return False

def pozisyon_kapat(client, sembol=None) -> bool:
    sembol = sembol or cfg.SEMBOL
    if cfg.TEST_MODU:
        return True
    try:
        poz = pozisyon_bilgisi(client, sembol)
        if not poz: return True
        side = 'SELL' if poz['yon'] == 'LONG' else 'BUY'
        client.futures_create_order(
            symbol=sembol, side=side, type='MARKET',
            quantity=poz['miktar'], reduceOnly=True)
        return True
    except BinanceAPIException as e:
        log.error(f"Kapatma hatası: {e}")
        return False
