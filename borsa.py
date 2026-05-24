"""
Borsa Modülü — Binance Futures
================================
- Veri çekme (public API — key gerekmez)
- Pozisyon sorgulama
- Emir gönderme
"""

import logging
import pandas as pd
import numpy as np
import urllib.request
import ssl
import json
import time
from binance.client import Client
from binance.exceptions import BinanceAPIException
import config as cfg

log = logging.getLogger(__name__)

# SSL context
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# ─────────────────────────────────────────────────────────────
# BAĞLANTI
# ─────────────────────────────────────────────────────────────

def client_olustur():
    return Client(cfg.BINANCE_API_KEY, cfg.BINANCE_API_SECRET)

# ─────────────────────────────────────────────────────────────
# VERİ ÇEKME — Public API (key gerekmez)
# ─────────────────────────────────────────────────────────────

def ohlcv_cek(client=None, sembol=None, timeframe=None, limit=500) -> pd.DataFrame:
    """
    Binance public API'den OHLCV verisi çek.
    API key gerektirmez — coğrafi kısıtlama yok.
    """
    sembol    = sembol    or cfg.SEMBOL
    timeframe = timeframe or cfg.TIMEFRAME

    # Futures public endpoint
    url = (f"https://fapi.binance.com/fapi/v1/klines"
           f"?symbol={sembol}&interval={timeframe}&limit={limit}")

    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            klines = json.loads(r.read())

        df = pd.DataFrame(klines, columns=[
            'timestamp','open','high','low','close','volume',
            'close_time','quote_vol','trades','tb_base','tb_quote','ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.set_index('timestamp')
        for col in ['open','high','low','close','volume']:
            df[col] = df[col].astype(float)
        df = df[['open','high','low','close','volume']]
        # Son bar henüz kapanmamış — çıkar
        df = df.iloc[:-1]

        log.info(f"Veri çekildi: {len(df)} bar | {df.index[0]} → {df.index[-1]}")
        return df

    except Exception as e:
        log.error(f"Veri çekme hatası: {e}")
        # Spot API'yi dene (yedek)
        return _ohlcv_spot(sembol, timeframe, limit)

def _ohlcv_spot(sembol, timeframe, limit):
    """Yedek: Spot API"""
    url = (f"https://api.binance.com/api/v3/klines"
           f"?symbol={sembol}&interval={timeframe}&limit={limit}")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            klines = json.loads(r.read())
        df = pd.DataFrame(klines, columns=[
            'timestamp','open','high','low','close','volume',
            'close_time','quote_vol','trades','tb_base','tb_quote','ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.set_index('timestamp')
        for col in ['open','high','low','close','volume']:
            df[col] = df[col].astype(float)
        df = df[['open','high','low','close','volume']].iloc[:-1]
        log.info(f"Spot veri çekildi: {len(df)} bar")
        return df
    except Exception as e:
        log.error(f"Spot veri hatası: {e}")
        raise

# ─────────────────────────────────────────────────────────────
# POZİSYON SORGULAMA
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

# ─────────────────────────────────────────────────────────────
# EMİR GÖNDERİM
# ─────────────────────────────────────────────────────────────

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
    yon    = sinyal['yon']
    fiyat  = sinyal['fiyat']
    sl     = sinyal['sl']
    tp     = sinyal['tp']

    if cfg.TEST_MODU:
        log.info(f"[TEST MODU] Emir gönderilmedi: {yon} {sembol} @ {fiyat:.2f} | SL:{sl:.2f}")
        return True

    try:
        miktar = pozisyon_miktari_hesapla(client, cfg.POZISYON_USDT, fiyat, sembol)
        if miktar <= 0:
            log.error("Miktar hesaplanamadı")
            return False

        side    = 'BUY'  if yon == 'LONG'  else 'SELL'
        sl_side = 'SELL' if yon == 'LONG'  else 'BUY'

        # Market emir
        emir = client.futures_create_order(
            symbol=sembol, side=side, type='MARKET', quantity=miktar)
        log.info(f"Market emir: {emir['orderId']} ✅")

        # Stop-Loss
        client.futures_create_order(
            symbol=sembol, side=sl_side, type='STOP_MARKET',
            stopPrice=sl, closePosition=True)
        log.info(f"Stop-Loss: {sl} ✅")

        # Take-Profit
        if tp:
            client.futures_create_order(
                symbol=sembol, side=sl_side, type='TAKE_PROFIT_MARKET',
                stopPrice=tp, closePosition=True)
            log.info(f"Take-Profit: {tp} ✅")

        return True

    except BinanceAPIException as e:
        log.error(f"Emir gönderim hatası: {e}")
        return False

def pozisyon_kapat(client, sembol=None) -> bool:
    sembol = sembol or cfg.SEMBOL
    if cfg.TEST_MODU:
        log.info("[TEST MODU] Pozisyon kapatılmadı")
        return True
    try:
        poz = pozisyon_bilgisi(client, sembol)
        if not poz:
            return True
        side = 'SELL' if poz['yon'] == 'LONG' else 'BUY'
        client.futures_create_order(
            symbol=sembol, side=side, type='MARKET',
            quantity=poz['miktar'], reduceOnly=True)
        log.info("Pozisyon kapatıldı ✅")
        return True
    except BinanceAPIException as e:
        log.error(f"Pozisyon kapatma hatası: {e}")
        return False
