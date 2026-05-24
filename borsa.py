"""
Borsa Modülü — Binance Futures
================================
- Veri çekme
- Pozisyon sorgulama
- Emir gönderme
"""

import logging
import pandas as pd
import numpy as np
from binance.client import Client
from binance.exceptions import BinanceAPIException
import config as cfg

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# BAĞLANTI
# ─────────────────────────────────────────────────────────────

def client_olustur():
    return Client(cfg.BINANCE_API_KEY, cfg.BINANCE_API_SECRET)

# ─────────────────────────────────────────────────────────────
# VERİ ÇEKME
# ─────────────────────────────────────────────────────────────

def ohlcv_cek(client, sembol=None, timeframe=None, limit=500) -> pd.DataFrame:
    """Binance'den OHLCV verisi çek"""
    sembol    = sembol    or cfg.SEMBOL
    timeframe = timeframe or cfg.TIMEFRAME

    interval_map = {
        '1m':  Client.KLINE_INTERVAL_1MINUTE,
        '5m':  Client.KLINE_INTERVAL_5MINUTE,
        '15m': Client.KLINE_INTERVAL_15MINUTE,
        '30m': Client.KLINE_INTERVAL_30MINUTE,
        '1h':  Client.KLINE_INTERVAL_1HOUR,
        '4h':  Client.KLINE_INTERVAL_4HOUR,
        '1d':  Client.KLINE_INTERVAL_1DAY,
    }
    interval = interval_map.get(timeframe, Client.KLINE_INTERVAL_1HOUR)

    try:
        klines = client.futures_klines(
            symbol=sembol,
            interval=interval,
            limit=limit
        )
        df = pd.DataFrame(klines, columns=[
            'timestamp','open','high','low','close','volume',
            'close_time','quote_vol','trades','tb_base','tb_quote','ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.set_index('timestamp')
        for col in ['open','high','low','close','volume']:
            df[col] = df[col].astype(float)
        df = df[['open','high','low','close','volume']]
        # Son bar henüz kapanmamış olabilir — çıkar
        df = df.iloc[:-1]
        log.info(f"Veri çekildi: {len(df)} bar | {df.index[0]} → {df.index[-1]}")
        return df
    except BinanceAPIException as e:
        log.error(f"Binance API hatası (veri): {e}")
        raise

# ─────────────────────────────────────────────────────────────
# POZİSYON SORGULAMA
# ─────────────────────────────────────────────────────────────

def acik_pozisyon_var_mi(client, sembol=None) -> bool:
    """Açık pozisyon var mı?"""
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
        return True  # Hata durumunda güvenli taraf

def pozisyon_bilgisi(client, sembol=None) -> dict | None:
    """Mevcut pozisyon detayı"""
    sembol = sembol or cfg.SEMBOL
    try:
        pozisyonlar = client.futures_position_information(symbol=sembol)
        for poz in pozisyonlar:
            amt = float(poz['positionAmt'])
            if amt != 0:
                return {
                    'yon':          'LONG' if amt > 0 else 'SHORT',
                    'miktar':       abs(amt),
                    'giris_fiyat':  float(poz['entryPrice']),
                    'kar_zarar':    float(poz['unrealizedProfit']),
                }
        return None
    except BinanceAPIException as e:
        log.error(f"Pozisyon bilgisi hatası: {e}")
        return None

# ─────────────────────────────────────────────────────────────
# EMİR GÖNDERİM
# ─────────────────────────────────────────────────────────────

def pozisyon_miktari_hesapla(client, usdt_miktar, fiyat, sembol=None) -> float:
    """USDT miktarını coin miktarına çevir"""
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
    """
    Market emir + Stop-Loss gönder.
    sinyal: strateji.sinyal_uret() çıktısı
    """
    sembol = sembol or cfg.SEMBOL
    yon    = sinyal['yon']
    fiyat  = sinyal['fiyat']
    sl     = sinyal['sl']
    tp     = sinyal['tp']

    if cfg.TEST_MODU:
        log.info(f"[TEST MODU] Emir gönderilmedi: {yon} {sembol} @ {fiyat:.2f} | SL:{sl:.2f}")
        return True

    try:
        # Miktar hesapla
        miktar = pozisyon_miktari_hesapla(client, cfg.POZISYON_USDT, fiyat, sembol)
        if miktar <= 0:
            log.error("Miktar hesaplanamadı")
            return False

        side      = 'BUY'  if yon == 'LONG'  else 'SELL'
        sl_side   = 'SELL' if yon == 'LONG'  else 'BUY'

        log.info(f"Emir gönderiliyor: {side} {miktar} {sembol} @ MARKET")

        # 1. Market emir
        emir = client.futures_create_order(
            symbol   = sembol,
            side     = side,
            type     = 'MARKET',
            quantity = miktar,
        )
        log.info(f"Market emir: {emir['orderId']} ✅")

        # 2. Stop-Loss
        sl_emir = client.futures_create_order(
            symbol        = sembol,
            side          = sl_side,
            type          = 'STOP_MARKET',
            stopPrice     = sl,
            closePosition = True,
        )
        log.info(f"Stop-Loss: {sl} ✅")

        # 3. Take-Profit (varsa)
        if tp:
            tp_emir = client.futures_create_order(
                symbol        = sembol,
                side          = sl_side,
                type          = 'TAKE_PROFIT_MARKET',
                stopPrice     = tp,
                closePosition = True,
            )
            log.info(f"Take-Profit: {tp} ✅")

        return True

    except BinanceAPIException as e:
        log.error(f"Emir gönderim hatası: {e}")
        return False

def pozisyon_kapat(client, sembol=None) -> bool:
    """Açık pozisyonu kapat"""
    sembol = sembol or cfg.SEMBOL
    if cfg.TEST_MODU:
        log.info("[TEST MODU] Pozisyon kapatılmadı")
        return True
    try:
        poz = pozisyon_bilgisi(client, sembol)
        if not poz:
            log.info("Kapatılacak pozisyon yok")
            return True
        side = 'SELL' if poz['yon'] == 'LONG' else 'BUY'
        client.futures_create_order(
            symbol        = sembol,
            side          = side,
            type          = 'MARKET',
            quantity      = poz['miktar'],
            reduceOnly    = True,
        )
        log.info(f"Pozisyon kapatıldı ✅")
        return True
    except BinanceAPIException as e:
        log.error(f"Pozisyon kapatma hatası: {e}")
        return False
