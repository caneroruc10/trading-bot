"""
Strateji Modülü
===============
PMAX + Trend Skoru + Fake Sinyal Sayacı (Pine v6 ile birebir)

Mimari:
- Her kontrolde, geçmiş tüm bar'lar üzerinde state machine sıfırdan çalışır.
- Pine her bar'ı deterministik olarak yeniden hesapladığı gibi, bot da geçmişten
  yeniden inşa eder. Bu sayede Railway redeploy'unda state kaybı yoktur.
- Son bar'ın pozisyon/fake_sayac/esik_asildi/son_sinyal durumu döndürülür.
- main.py bu durumu borsadaki gerçek pozisyonla karşılaştırıp aksiyon alır.
"""

import numpy as np
import pandas as pd
from collections import deque
import config as cfg
import logging

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# TEMEL HESAPLAMALAR
# ─────────────────────────────────────────────────────────────

def hesapla_atr(high, low, close, period):
    """Wilder ATR — Pine Script ta.atr() ile aynı"""
    n = len(close)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i]-low[i],
                    abs(high[i]-close[i-1]),
                    abs(low[i]-close[i-1]))
    atr = np.zeros(n)
    atr[period-1] = np.mean(tr[:period])
    for i in range(period, n):
        atr[i] = (atr[i-1]*(period-1) + tr[i]) / period
    return atr

def hesapla_ema(src, period):
    """EMA — Pine Script ta.ema() ile aynı"""
    ema = np.zeros(len(src))
    ema[period-1] = np.mean(src[:period])
    k = 2 / (period+1)
    for i in range(period, len(src)):
        ema[i] = src[i]*k + ema[i-1]*(1-k)
    return ema

def hesapla_var(src, period):
    """VAR — Pine Script VAR ile birebir aynı (hl2 üzerinde)"""
    n = len(src)
    valpha = 2.0 / (period + 1)

    vud1 = np.zeros(n)
    vdd1 = np.zeros(n)
    for i in range(1, n):
        if src[i] > src[i-1]:
            vud1[i] = src[i] - src[i-1]
        else:
            vdd1[i] = src[i-1] - src[i]

    var = np.zeros(n)
    for i in range(n):
        start = max(0, i-8)
        vUD = np.sum(vud1[start:i+1])
        vDD = np.sum(vdd1[start:i+1])
        denom = vUD + vDD
        vCMO = (vUD - vDD) / denom if denom > 0 else 0.0
        if i == 0:
            var[i] = valpha * abs(vCMO) * src[i]
        else:
            var[i] = (valpha * abs(vCMO) * src[i] +
                      (1.0 - valpha * abs(vCMO)) * var[i-1])
    return var

def hesapla_pmax(src, ma, atr, coeff):
    """
    PMAX — Pine Script mantığıyla birebir aynı
    pmax_bull[i] = (dir[i] == 1)
    """
    n = len(src)
    longStop  = np.zeros(n)
    shortStop = np.zeros(n)
    direction = np.ones(n, dtype=int)
    pmax      = np.zeros(n)

    for i in range(n):
        ls = ma[i] - coeff * atr[i]
        ss = ma[i] + coeff * atr[i]

        if i == 0:
            longStop[i]  = ls
            shortStop[i] = ss
            direction[i] = 1
        else:
            lsprev = longStop[i-1]
            if ma[i] > lsprev:
                longStop[i] = max(ls, lsprev)
            else:
                longStop[i] = ls

            ssprev = shortStop[i-1]
            if ma[i] < ssprev:
                shortStop[i] = min(ss, ssprev)
            else:
                shortStop[i] = ss

            prev_dir = direction[i-1]
            if prev_dir == -1 and ma[i] > shortStop[i-1]:
                direction[i] = 1
            elif prev_dir == 1 and ma[i] < longStop[i-1]:
                direction[i] = -1
            else:
                direction[i] = prev_dir

        pmax[i] = longStop[i] if direction[i] == 1 else shortStop[i]

    pmax_bull = direction == 1
    return pmax, pmax_bull, direction

def pivot_yuksek_mi(high, i, left, right):
    if i < left or i+right >= len(high): return False
    x = high[i]
    for k in range(1, left+1):
        if high[i-k] >= x: return False
    for k in range(1, right+1):
        if high[i+k] >= x: return False
    return True

def pivot_alcak_mi(low, i, left, right):
    if i < left or i+right >= len(low): return False
    x = low[i]
    for k in range(1, left+1):
        if low[i-k] <= x: return False
    for k in range(1, right+1):
        if low[i+k] <= x: return False
    return True

def fiyat_yapisi_puani(pivot_highs, pivot_lows, bull_yon):
    """Pine'daki structScore — 0-50 arası"""
    hh = lh = hl = ll = 0
    for i in range(len(pivot_highs)-1):
        if pivot_highs[i] > pivot_highs[i+1]: hh += 1
        else: lh += 1
    for i in range(len(pivot_lows)-1):
        if pivot_lows[i] > pivot_lows[i+1]: hl += 1
        else: ll += 1
    toplam = max(len(pivot_highs)-1, 0) + max(len(pivot_lows)-1, 0)
    if toplam == 0: return 0
    if bull_yon:
        return ((hh + hl) / toplam) * 50
    else:
        return ((lh + ll) / toplam) * 50

def volatilite_puani(atr_val, fiyat):
    """Pine'daki volScore — 0-50 arası"""
    if fiyat <= 0: return 0
    atr_pct = (atr_val/fiyat)*100
    score = (atr_pct - cfg.VOL_MIN) / (cfg.VOL_MAX - cfg.VOL_MIN) * 50
    return min(max(score, 0), 50)

def _ma_hesapla(src, period, ma_tipi='EMA'):
    if ma_tipi == 'VAR':
        return hesapla_var(src, period)
    else:
        return hesapla_ema(src, period)

# ─────────────────────────────────────────────────────────────
# STATE MACHINE (Pine v6 ile birebir)
# ─────────────────────────────────────────────────────────────

def durum_makinesini_calistir(df: pd.DataFrame, long_only: bool = False) -> dict:
    """
    Pine v6'daki sinyal/pozisyon state machine'ini geçmiş tüm bar'lar üzerinde
    sıfırdan simüle eder. Son bar'ın durumunu ve aksiyonunu döndürür.

    Returns:
        pozisyon:    'LONG'|'SHORT'|'YOK'   son bar sonrası bot'a göre olması gereken pozisyon
        fake_sayac:  int                     son bar sonrası fake sayaç değeri
        esik_asildi: bool                    fake eşik aşıldı bayrağı
        son_sinyal:  'AL'|'SAT'|None         son bar'da üretilen sinyal (varsa)
        zorla_ters:  bool                    son sinyal zorla ters dönüş mü?
        fiyat:       float                   son bar kapanış
        atr:         float                   son bar ATR
        trend_skoru: float                   son bar trend skoru
        pmax_yon:    'BULL'|'BEAR'           son bar PMAX yönü
        yapi_skoru:  float
        vol_skoru:   float
    """
    close = df['close'].values
    high  = df['high'].values
    low   = df['low'].values
    src   = (high + low) / 2  # Pine: src = hl2
    n     = len(close)

    min_bar = cfg.ATR_PERIOD + cfg.PIVOT_RIGHT + cfg.PIVOT_LEFT + 10
    if n < min_bar:
        raise ValueError(f"Yetersiz veri: {n} bar (en az {min_bar} gerek)")

    atr     = hesapla_atr(high, low, close, cfg.ATR_PERIOD)
    ma_tipi = getattr(cfg, 'MA_TIPI', 'EMA')
    ma      = _ma_hesapla(src, cfg.EMA_PERIOD, ma_tipi)
    _, pmax_bull, _ = hesapla_pmax(src, ma, atr, cfg.COEFFICIENT)

    # State değişkenleri (Pine'daki var string/int/bool ile aynı)
    pozisyon    = 'YOK'
    fake_sayac  = 0
    esik_asildi = False

    # Pivot listesi — bar bar build edilecek (Pine'daki array.unshift + array.pop)
    ph = deque(maxlen=cfg.PIVOT_COUNT)
    pl = deque(maxlen=cfg.PIVOT_COUNT)

    # Son bar için kayıt
    son_sinyal       = None
    zorla_ters       = False
    son_trend_skoru  = 0.0
    son_yapi_skoru   = 0.0
    son_vol_skoru    = 0.0

    fake_artma_barlari = []   # log için
    zorla_ters_barlari = []   # log için

    for i in range(n):
        # ─── Pivot tespit (i bar'ında, pb = i - PIVOT_RIGHT pivot konfirme olur)
        if i >= cfg.PIVOT_RIGHT:
            pb = i - cfg.PIVOT_RIGHT
            if pb >= cfg.PIVOT_LEFT:
                if pivot_yuksek_mi(high, pb, cfg.PIVOT_LEFT, cfg.PIVOT_RIGHT):
                    ph.appendleft(high[pb])
                if pivot_alcak_mi(low, pb, cfg.PIVOT_LEFT, cfg.PIVOT_RIGHT):
                    pl.appendleft(low[pb])

        # ─── PMAX yön & cross
        is_bull = bool(pmax_bull[i])
        is_bear = not is_bull
        if i == 0:
            bull_cross = False
            bear_cross = False
        else:
            bull_cross = is_bull and not bool(pmax_bull[i-1])
            bear_cross = is_bear and bool(pmax_bull[i-1])

        # ─── Trend skoru (Pine'da her bar yeniden hesaplanıyor, yön'e göre)
        yapi  = fiyat_yapisi_puani(list(ph), list(pl), is_bull)
        vol   = volatilite_puani(atr[i], close[i])
        skor  = yapi * 0.6 + vol * 0.4
        aktif = skor >= cfg.SCORE_THRESH

        # ─── Bu bar'ın çıktıları (sadece son bar için saklanacak)
        bu_buy   = False
        bu_sell  = False
        bu_zorla = False

        # ─── State machine — Pine v6 mantığı birebir
        if pozisyon == 'YOK':
            fake_sayac  = 0
            esik_asildi = False
            if bull_cross and aktif:
                pozisyon = 'LONG'
                bu_buy   = True
            elif bear_cross and aktif and not long_only:
                pozisyon = 'SHORT'
                bu_sell  = True

        elif pozisyon == 'LONG':
            if is_bear:
                if aktif or esik_asildi:
                    bu_zorla    = esik_asildi and not aktif
                    pozisyon    = 'SHORT'
                    bu_sell     = True
                    fake_sayac  = 0
                    esik_asildi = False
                elif bear_cross:
                    fake_sayac += 1
                    fake_artma_barlari.append(i)
                    if fake_sayac >= cfg.FAKE_ESIK:
                        esik_asildi = True

        elif pozisyon == 'SHORT':
            if is_bull:
                if aktif or esik_asildi:
                    bu_zorla    = esik_asildi and not aktif
                    pozisyon    = 'LONG'
                    bu_buy      = True
                    fake_sayac  = 0
                    esik_asildi = False
                elif bull_cross:
                    fake_sayac += 1
                    fake_artma_barlari.append(i)
                    if fake_sayac >= cfg.FAKE_ESIK:
                        esik_asildi = True

        if bu_zorla:
            zorla_ters_barlari.append(i)

        # Son bar ise sinyali sakla
        if i == n - 1:
            if bu_buy:
                son_sinyal = 'AL'
                zorla_ters = bu_zorla
            elif bu_sell:
                son_sinyal = 'SAT'
                zorla_ters = bu_zorla
            son_trend_skoru = skor
            son_yapi_skoru  = yapi
            son_vol_skoru   = vol

    log.info(f"Geçmişte toplam {len(fake_artma_barlari)} fake artışı, "
             f"{len(zorla_ters_barlari)} zorla ters dönüş tespit edildi")

    return {
        'pozisyon':    pozisyon,
        'fake_sayac':  fake_sayac,
        'esik_asildi': esik_asildi,
        'son_sinyal':  son_sinyal,
        'zorla_ters':  zorla_ters,
        'fiyat':       float(close[-1]),
        'atr':         float(atr[-1]),
        'trend_skoru': float(son_trend_skoru),
        'pmax_yon':    'BULL' if pmax_bull[-1] else 'BEAR',
        'yapi_skoru':  float(son_yapi_skoru),
        'vol_skoru':   float(son_vol_skoru),
    }
