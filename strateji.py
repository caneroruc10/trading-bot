"""
Strateji Modülü
===============
PMAX + Trend Skoru + Rejim Filtresi
Pine Script ile birebir aynı PMAX hesabı
"""

import numpy as np
import pandas as pd
from collections import deque
from scipy.stats import norm
import config as cfg
import logging

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# HESAPLAMALAR
# ─────────────────────────────────────────────────────────────

def hesapla_atr(high, low, close, period):
    """Wilder ATR — Pine Script atr() ile aynı"""
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
    """EMA — Pine Script ema() ile aynı"""
    ema = np.zeros(len(src))
    ema[period-1] = np.mean(src[:period])
    k = 2 / (period+1)
    for i in range(period, len(src)):
        ema[i] = src[i]*k + ema[i-1]*(1-k)
    return ema

def hesapla_var(src, period):
    """VAR — Pine Script VAR ile birebir aynı
    src = hl2 (Pine'daki gibi)
    """
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
        # Pine: vUD=sum(vud1,9), vDD=sum(vdd1,9)
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
    
    Pine Script:
        longStop = MAvg - Multiplier*atr
        longStopPrev = nz(longStop[1], longStop)
        longStop = MAvg > longStopPrev ? max(longStop, longStopPrev) : longStop
        
        shortStop = MAvg + Multiplier*atr
        shortStopPrev = nz(shortStop[1], shortStop)
        shortStop = MAvg < shortStopPrev ? min(shortStop, shortStopPrev) : shortStop
        
        dir = 1
        dir = dir==-1 and MAvg > shortStopPrev ? 1 : dir==1 and MAvg < longStopPrev ? -1 : dir
        PMax = dir==1 ? longStop : shortStop
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
            # longStop
            lsprev = longStop[i-1]
            if ma[i] > lsprev:
                longStop[i] = max(ls, lsprev)
            else:
                longStop[i] = ls

            # shortStop
            ssprev = shortStop[i-1]
            if ma[i] < ssprev:
                shortStop[i] = min(ss, ssprev)
            else:
                shortStop[i] = ss

            # direction
            prev_dir = direction[i-1]
            if prev_dir == -1 and ma[i] > shortStop[i-1]:
                direction[i] = 1
            elif prev_dir == 1 and ma[i] < longStop[i-1]:
                direction[i] = -1
            else:
                direction[i] = prev_dir

        pmax[i] = longStop[i] if direction[i] == 1 else shortStop[i]

    pmax_bull = ma > pmax
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
    if fiyat <= 0: return 0
    atr_pct = (atr_val/fiyat)*100
    score = (atr_pct - cfg.VOL_MIN) / (cfg.VOL_MAX - cfg.VOL_MIN) * 50
    return min(max(score, 0), 50)

# ─────────────────────────────────────────────────────────────
# REJİM TESPİTİ (GMM)
# ─────────────────────────────────────────────────────────────

def rejim_hesapla(close_arr, pencere=168):
    n = len(close_arr)
    if n < pencere + 10:
        return 'Bilinmiyor'
    log_r = np.diff(np.log(close_arr + 1e-12))
    vol = []
    for i in range(pencere, len(log_r)+1):
        vol.append(np.std(log_r[i-pencere:i]) * np.sqrt(24*365))
    vol = np.array(vol)
    if len(vol) < 10:
        return 'Bilinmiyor'
    log_vol = np.log(vol + 1e-9)
    q33, q67 = np.percentile(log_vol, [33, 67])
    mu    = np.array([np.mean(log_vol[log_vol < q33]),
                      np.mean(log_vol[(log_vol>=q33)&(log_vol<q67)]),
                      np.mean(log_vol[log_vol >= q67])])
    sigma = np.array([max(np.std(log_vol[log_vol < q33]), 0.01),
                      max(np.std(log_vol[(log_vol>=q33)&(log_vol<q67)]), 0.01),
                      max(np.std(log_vol[log_vol >= q67]), 0.01)])
    pi = np.ones(3) / 3
    for _ in range(100):
        resp  = np.column_stack([pi[k]*norm.pdf(log_vol, mu[k], sigma[k]) for k in range(3)])
        resp  = resp / (resp.sum(axis=1, keepdims=True) + 1e-12)
        Nk    = resp.sum(axis=0)
        pi    = Nk / len(log_vol)
        mu    = (resp * log_vol[:,None]).sum(axis=0) / Nk
        sigma = np.sqrt((resp * (log_vol[:,None]-mu)**2).sum(axis=0) / Nk)
        sigma = np.maximum(sigma, 0.01)
    son_vol     = log_vol[-1]
    olasliklar  = np.array([pi[k]*norm.pdf(son_vol, mu[k], sigma[k]) for k in range(3)])
    olasliklar /= olasliklar.sum()
    sirali      = np.argsort(mu)
    isim_map    = {sirali[0]:'Sakin', sirali[1]:'Geçiş', sirali[2]:'Kriz'}
    rejim       = isim_map[np.argmax(olasliklar)]
    log.info(f"Rejim: {rejim} | Vol: %{vol[-1]*100:.1f} | "
             f"Sakin:%{olasliklar[sirali[0]]*100:.0f} "
             f"Geçiş:%{olasliklar[sirali[1]]*100:.0f} "
             f"Kriz:%{olasliklar[sirali[2]]*100:.0f}")
    return rejim

# ─────────────────────────────────────────────────────────────
# MA SEÇİMİ — config'den gelen MA tipine göre
# ─────────────────────────────────────────────────────────────

def _ma_hesapla(src, period, ma_tipi='EMA'):
    if ma_tipi == 'VAR':
        return hesapla_var(src, period)
    else:
        return hesapla_ema(src, period)

# ─────────────────────────────────────────────────────────────
# PMAX TERS DÖNÜŞ TESPİTİ
# ─────────────────────────────────────────────────────────────

def pmax_ters_mi(df: pd.DataFrame, mevcut_yon: str) -> bool:
    close = df['close'].values
    high  = df['high'].values
    low   = df['low'].values
    src   = (high + low) / 2  # Pine: src = hl2

    atr           = hesapla_atr(high, low, close, cfg.ATR_PERIOD)
    ma_tipi       = getattr(cfg, 'MA_TIPI', 'EMA')
    ma            = _ma_hesapla(src, cfg.EMA_PERIOD, ma_tipi)
    _, pmax_bull, _ = hesapla_pmax(src, ma, atr, cfg.COEFFICIENT)

    simdi_bull = pmax_bull[-1]

    if mevcut_yon == 'LONG' and not simdi_bull:
        log.info("PMAX BEAR'a döndü — LONG pozisyon kapatılacak")
        return True
    if mevcut_yon == 'SHORT' and simdi_bull:
        log.info("PMAX BULL'a döndü — SHORT pozisyon kapatılacak")
        return True
    return False

# ─────────────────────────────────────────────────────────────
# ANA STRATEJİ FONKSİYONU
# ─────────────────────────────────────────────────────────────

def sinyal_uret(df: pd.DataFrame) -> dict | None:
    if len(df) < cfg.ATR_PERIOD + cfg.PIVOT_RIGHT + cfg.PIVOT_LEFT + cfg.SINYAL_GECIKME + 10:
        log.warning("Yeterli bar yok")
        return None

    close = df['close'].values
    high  = df['high'].values
    low   = df['low'].values
    n     = len(close)
    src   = (high + low) / 2  # Pine: src = hl2

    atr               = hesapla_atr(high, low, close, cfg.ATR_PERIOD)
    ma_tipi           = getattr(cfg, 'MA_TIPI', 'EMA')
    ma                = _ma_hesapla(src, cfg.EMA_PERIOD, ma_tipi)
    pmax_line, pmax_bull, direction = hesapla_pmax(src, ma, atr, cfg.COEFFICIENT)

    ph = deque(maxlen=cfg.PIVOT_COUNT)
    pl = deque(maxlen=cfg.PIVOT_COUNT)
    min_bar = cfg.ATR_PERIOD + cfg.PIVOT_RIGHT + cfg.PIVOT_LEFT

    for i in range(n):
        if i < min_bar: continue
        pb = i - cfg.PIVOT_RIGHT
        if pb >= cfg.PIVOT_LEFT:
            if pivot_yuksek_mi(high, pb, cfg.PIVOT_LEFT, cfg.PIVOT_RIGHT):
                ph.appendleft(high[pb])
            if pivot_alcak_mi(low, pb, cfg.PIVOT_LEFT, cfg.PIVOT_RIGHT):
                pl.appendleft(low[pb])

    ss = fiyat_yapisi_puani(list(ph), list(pl), pmax_bull[-1])
    vs = volatilite_puani(atr[-1], close[-1])
    trend_skoru = ss * 0.6 + vs * 0.4

    log.info(f"Trend skoru: {trend_skoru:.1f}/100 "
             f"(Yapı:{ss:.1f} Vol:{vs:.1f}) | "
             f"PMAX: {'BULL' if pmax_bull[-1] else 'BEAR'} | "
             f"ATR: {atr[-1]:.2f} | MA: {ma_tipi}({cfg.EMA_PERIOD}) | src=hl2")

    if trend_skoru < cfg.SCORE_THRESH:
        log.info(f"Trend skoru eşik altı ({trend_skoru:.1f} < {cfg.SCORE_THRESH}) — sinyal yok")
        return None

    if pmax_bull[-1]:
        yon         = 'LONG'
        giris_fiyat = close[-1]
        giris_atr   = atr[-1]
        log.info(f"LONG sinyali — PMAX BULL | skor {trend_skoru:.1f}")
    else:
        yon         = 'SHORT'
        giris_fiyat = close[-1]
        giris_atr   = atr[-1]
        log.info(f"SHORT sinyali — PMAX BEAR | skor {trend_skoru:.1f}")

    rejim = rejim_hesapla(close)
    if (rejim, yon.lower()) in cfg.ELENEN_KOMBINASYONLAR:
        log.info(f"Rejim filtresi: {rejim}+{yon} → elenmiş kombinasyon")
        return None

    if yon == 'LONG':
        sl = round(giris_fiyat - giris_atr * cfg.HARD_STOP_ATR, 4)
        tp = round(giris_fiyat + giris_atr * cfg.KAR_AL_ATR, 4) if cfg.KAR_AL_ATR > 0 else None
    else:
        sl = round(giris_fiyat + giris_atr * cfg.HARD_STOP_ATR, 4)
        tp = round(giris_fiyat - giris_atr * cfg.KAR_AL_ATR, 4) if cfg.KAR_AL_ATR > 0 else None

    trail_pct = round((giris_atr * cfg.TRAIL_STOP_ATR / giris_fiyat) * 100, 2)

    log.info(f"✅ SİNYAL: {yon} @ {giris_fiyat:.4f} | "
             f"SL:{sl:.4f} | TP:{tp} | Trail:%{trail_pct} | "
             f"Rejim:{rejim} | Skor:{trend_skoru:.1f}")

    return {
        'yon':          yon,
        'fiyat':        giris_fiyat,
        'atr':          giris_atr,
        'sl':           sl,
        'tp':           tp,
        'trail_pct':    trail_pct,
        'trend_skoru':  trend_skoru,
        'rejim':        rejim,
    }
