"""
Strateji Modülü
===============
PMAX + Trend Skoru + Rejim Filtresi

Giriş : OHLCV DataFrame
Çıkış : Sinyal dict veya None

Değişiklik: EMA → VAR (Variable Index Dynamic Average)
  - Yatay piyasada yavaşlar → daha az sahte sinyal
  - Trend piyasasında hızlanır → geç kalma azalır
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

def hesapla_ema(close, period):
    ema = np.zeros(len(close))
    ema[period-1] = np.mean(close[:period])
    k = 2 / (period+1)
    for i in range(period, len(close)):
        ema[i] = close[i]*k + ema[i-1]*(1-k)
    return ema

def hesapla_var(close, period):
    """
    VAR — Variable Index Dynamic Average (Pine Script ile birebir aynı mantık)
    
    Çalışma prensibi:
      - CMO (Chande Momentum Oscillator) ile trendin gücünü ölçer
      - Güçlü trendde: alpha yükselir → fiyata hızlı yaklaşır
      - Yatay piyasada: alpha düşer → yavaş hareket eder, gürültüyü filtreler
    
    Parametreler:
      close  : fiyat dizisi (numpy array)
      period : EMA_PERIOD ile aynı değer kullanılır
    """
    n      = len(close)
    valpha = 2.0 / (period + 1)

    # Yukarı / aşağı hareketler
    vud = np.zeros(n)
    vdd = np.zeros(n)
    for i in range(1, n):
        diff = close[i] - close[i - 1]
        if diff > 0:
            vud[i] = diff
        else:
            vdd[i] = -diff

    var = np.zeros(n)
    # İlk 9 bar için warmup: fiyatı doğrudan ata
    for i in range(min(9, n)):
        var[i] = close[i]

    for i in range(9, n):
        vUD   = np.sum(vud[i-9:i])
        vDD   = np.sum(vdd[i-9:i])
        denom = vUD + vDD
        vCMO  = (vUD - vDD) / denom if denom > 0 else 0.0
        # Pine: VAR := nz(valpha*abs(vCMO)*src) + (1 - valpha*abs(vCMO))*nz(VAR[1])
        var[i] = (valpha * abs(vCMO) * close[i]
                  + (1.0 - valpha * abs(vCMO)) * var[i - 1])

    return var

def hesapla_pmax(close, ma, atr, coeff):
    """
    PMAX hesabı — ma parametresi EMA ya da VAR olabilir (Pine ile aynı mantık)
    """
    n     = len(close)
    upper = ma + coeff * atr
    lower = ma - coeff * atr
    pmax  = np.zeros(n)
    pmax[0] = close[0]
    for i in range(1, n):
        if close[i] > pmax[i-1]:
            pmax[i] = max(lower[i], pmax[i-1])
        else:
            pmax[i] = min(upper[i], pmax[i-1])
    pmax_bull = ma > pmax
    return pmax, pmax_bull

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
    max_pairs = max(len(pivot_highs)-1, 1) + max(len(pivot_lows)-1, 1)
    bull = ((hh+hl)/max_pairs)*50 if max_pairs > 0 else 0
    bear = ((lh+ll)/max_pairs)*50 if max_pairs > 0 else 0
    return bull if bull_yon else bear

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
    pi    = np.ones(3) / 3

    for _ in range(100):
        resp  = np.column_stack([pi[k]*norm.pdf(log_vol, mu[k], sigma[k])
                                 for k in range(3)])
        resp  = resp / (resp.sum(axis=1, keepdims=True) + 1e-12)
        Nk    = resp.sum(axis=0)
        pi    = Nk / len(log_vol)
        mu    = (resp * log_vol[:,None]).sum(axis=0) / Nk
        sigma = np.sqrt((resp * (log_vol[:,None]-mu)**2).sum(axis=0) / Nk)
        sigma = np.maximum(sigma, 0.01)

    son_vol     = log_vol[-1]
    olasliklar  = np.array([pi[k]*norm.pdf(son_vol, mu[k], sigma[k]) for k in range(3)])
    olasliklar /= olasliklar.sum()
    rejim_idx   = np.argmax(olasliklar)

    sirali      = np.argsort(mu)
    isim_map    = {sirali[0]:'Sakin', sirali[1]:'Geçiş', sirali[2]:'Kriz'}
    rejim       = isim_map[rejim_idx]

    log.info(f"Rejim: {rejim} | Vol: %{vol[-1]*100:.1f} | "
             f"Sakin:%{olasliklar[sirali[0]]*100:.0f} "
             f"Geçiş:%{olasliklar[sirali[1]]*100:.0f} "
             f"Kriz:%{olasliklar[sirali[2]]*100:.0f}")

    return rejim

# ─────────────────────────────────────────────────────────────
# PMAX TERS DÖNÜŞ TESPİTİ
# ─────────────────────────────────────────────────────────────

def pmax_ters_mi(df: pd.DataFrame, mevcut_yon: str) -> bool:
    """
    Mevcut pozisyon yönüne göre PMAX ters döndü mü kontrol eder.
    LONG pozisyonda PMAX BEAR'a geçtiyse → True
    SHORT pozisyonda PMAX BULL'a geçtiyse → True
    """
    close = df['close'].values
    high  = df['high'].values
    low   = df['low'].values

    atr          = hesapla_atr(high, low, close, cfg.ATR_PERIOD)
    var          = hesapla_var(close, cfg.EMA_PERIOD)          # EMA → VAR
    _, pmax_bull = hesapla_pmax(close, var, atr, cfg.COEFFICIENT)

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

    atr                  = hesapla_atr(high, low, close, cfg.ATR_PERIOD)
    var                  = hesapla_var(close, cfg.EMA_PERIOD)          # EMA → VAR
    pmax_line, pmax_bull = hesapla_pmax(close, var, atr, cfg.COEFFICIENT)

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
             f"ATR: {atr[-1]:.2f} | MA: VAR({cfg.EMA_PERIOD})")

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

    log.info(f"✅ SİNYAL: {yon} @ {giris_fiyat:.2f} | "
             f"SL:{sl:.2f} | TP:{tp} | Trail:%{trail_pct} | "
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
