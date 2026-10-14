import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="Pro LLM Trading Scanner", page_icon="📊", layout="wide")

st.markdown("""
<style>
.stApp{background:#0b0f17;color:#e5e7eb}
.card{background:#111827;border-radius:12px;padding:14px;border:1px solid #1f2937;margin:8px 0}
.buy{color:#22c55e;font-weight:800}
.sell{color:#ef4444;font-weight:800}
.hold{color:#f59e0b;font-weight:800}
.llm-box{background:#1e1b4b;border-radius:10px;padding:12px;margin:8px 0;border-left:4px solid #a855f7}
.stat-box{background:#111827;border-radius:10px;padding:12px;text-align:center;border:1px solid #1f2937}
</style>
""", unsafe_allow_html=True)

# ============ GROQ LLM ============
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

def get_groq_key():
    try: return st.secrets["GROQ_API_KEY"]
    except Exception: return os.environ.get("GROQ_API_KEY", "")

GROQ_API_KEY = get_groq_key()
client = None
LLM_MODEL = None
if GROQ_AVAILABLE and GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        LLM_MODEL = "openai/gpt-oss-120b"
    except Exception:
        client = None

def llm_call(system_prompt, user_prompt, max_tokens=400):
    if client is None: return None, "❌ Groq API key missing"
    try:
        c = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role":"system","content":system_prompt},
                      {"role":"user","content":user_prompt}],
            temperature=0.3, max_tokens=max_tokens, top_p=0.9)
        return c.choices[0].message.content, None
    except Exception as e:
        return None, f"LLM: {str(e)[:180]}"

def safe_parse_json(resp):
    if not resp: return None
    try:
        txt = resp.strip()
        if "```" in txt:
            parts = txt.split("```")
            if len(parts) >= 2:
                txt = parts[1].replace("json","").strip()
        return json.loads(txt)
    except Exception:
        return None

# ============ OKX DATA ============
OKX_BASE = "https://www.okx.com/api/v5"
TF_MAP = {"5m":"5m","15m":"15m","1h":"1H","4h":"4H","1d":"1D"}

def _okx_inst(sym):
    if "-" in sym: return sym
    if sym.endswith("USDT"): return f"{sym[:-4]}-USDT"
    return sym

@st.cache_data(ttl=3600)
def get_all_coins():
    try:
        r = requests.get(f"{OKX_BASE}/market/tickers",
                         params={"instType":"SPOT"}, timeout=12).json()
        if r.get("code") != "0": return []
        coins = []
        for d in r["data"]:
            inst = d.get("instId","")
            if not inst.endswith("-USDT"): continue
            if "USDC" in inst or "DAI" in inst or "TUSD" in inst: continue
            try: vol = float(d.get("volCcy24h", 0))
            except Exception: vol = 0
            if vol < 50000: continue
            coins.append({"symbol": inst.replace("-",""), "instId": inst, "vol": vol})
        coins.sort(key=lambda x: x["vol"], reverse=True)
        return coins[:1000]
    except Exception:
        return []

@st.cache_data(ttl=20)
def klines(sym, itv="1h", lim=300):
    try:
        bar = TF_MAP.get(itv, "1H")
        r = requests.get(f"{OKX_BASE}/market/candles",
                         params={"instId": _okx_inst(sym), "bar": bar, "limit": min(lim,300)},
                         timeout=10).json()
        if r.get("code") != "0" or not r.get("data"): return pd.DataFrame()
        d = r["data"]
        df = pd.DataFrame(d, columns=["t","o","h","l","c","v","vq","vc","confirm"])
        for col in ["o","h","l","c","v"]: df[col] = df[col].astype(float)
        df["t"] = pd.to_datetime(df["t"].astype(float), unit="ms")
        return df[["t","o","h","l","c","v"]].sort_values("t").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=15)
def ticker(sym):
    try:
        r = requests.get(f"{OKX_BASE}/market/ticker",
                         params={"instId": _okx_inst(sym)}, timeout=8).json()
        if r.get("code") != "0" or not r.get("data"): return {}
        d = r["data"][0]
        last = float(d["last"]); op = float(d["open24h"])
        chg = (last-op)/op*100 if op else 0
        try: vol = float(d.get("volCcy24h", 0))
        except Exception: vol = 0
        return {"lastPrice": last, "chg24h": chg,
                "high24h": float(d.get("high24h", last)), "low24h": float(d.get("low24h", last)),
                "volUSDT": vol}
    except Exception:
        return {}

# ============ SENTIMENT + MEMPOOL ============
@st.cache_data(ttl=300)
def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6).json()
        d = r["data"][0]
        return {"value": int(d["value"]), "label": d["value_classification"]}
    except Exception:
        return {"value": 50, "label": "Neutral"}

@st.cache_data(ttl=300)
def get_global_market():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=8).json()
        d = r["data"]
        return {"btc_dom": round(d["market_cap_percentage"].get("btc", 0), 2),
                "eth_dom": round(d["market_cap_percentage"].get("eth", 0), 2),
                "total_mcap": d["total_market_cap"]["usd"],
                "total_vol": d["total_volume"]["usd"],
                "mcap_chg": round(d.get("market_cap_change_percentage_24h_usd", 0), 2)}
    except Exception:
        return {"btc_dom": 0, "eth_dom": 0, "total_mcap": 0, "total_vol": 0, "mcap_chg": 0}

@st.cache_data(ttl=60)
def get_mempool():
    try:
        r1 = requests.get("https://mempool.space/api/mempool", timeout=6).json()
        r2 = requests.get("https://mempool.space/api/v1/fees/recommended", timeout=6).json()
        r3 = requests.get("https://mempool.space/api/blocks/tip/height", timeout=6).text
        r4 = requests.get("https://mempool.space/api/v1/mining/hashrate/3d", timeout=8).json()
        return {"height": int(r3),
                "mempool_count": r1.get("count", 0),
                "mempool_vsize": r1.get("vsize", 0),
                "fee_fast": r2.get("fastestFee", 0),
                "fee_30m": r2.get("halfHourFee", 0),
                "fee_1h": r2.get("hourFee", 0),
                "hashrate": r4.get("currentHashrate", 0),
                "difficulty": r4.get("currentDifficulty", 0)}
    except Exception:
        return {"height": 0, "mempool_count": 0, "mempool_vsize": 0,
                "fee_fast": 0, "fee_30m": 0, "fee_1h": 0,
                "hashrate": 0, "difficulty": 0}

# ============ BASIC INDICATORS ============
def add_indicators(df):
    df = df.copy()
    df["ema20"] = df["c"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["c"].ewm(span=50, adjust=False).mean()
    df["ema200"] = df["c"].ewm(span=200, adjust=False).mean()
    d = df["c"].diff()
    g = d.clip(lower=0).rolling(14).mean()
    l = (-d.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - 100/(1 + g/l.replace(0,np.nan))
    tr = pd.concat([df["h"]-df["l"],(df["h"]-df["c"].shift()).abs(),
                    (df["l"]-df["c"].shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["vavg"] = df["v"].rolling(20).mean()
    df["vr"] = df["v"] / df["vavg"]
    e1 = df["c"].ewm(span=12, adjust=False).mean()
    e2 = df["c"].ewm(span=26, adjust=False).mean()
    df["macd"] = e1 - e2
    df["macd_sig"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_sig"]
    return df

def add_advanced_indicators(df):
    df = df.copy()
    df["bb_mid"] = df["c"].rolling(20).mean()
    bb_std = df["c"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2*bb_std
    df["bb_lower"] = df["bb_mid"] - 2*bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"] * 100

    rsi_min = df["rsi"].rolling(14).min()
    rsi_max = df["rsi"].rolling(14).max()
    df["stoch_rsi"] = (df["rsi"] - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan) * 100
    df["stoch_k"] = df["stoch_rsi"].rolling(3).mean()
    df["stoch_d"] = df["stoch_k"].rolling(3).mean()

    high, low, close = df["h"], df["l"], df["c"]
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr14.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr14.replace(0, np.nan))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx"] = dx.rolling(14).mean()
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    tp = (df["h"] + df["l"] + df["c"]) / 3
    df["vwap"] = (tp * df["v"]).rolling(20).sum() / df["v"].rolling(20).sum().replace(0, np.nan)

    obv = [0]
    for i in range(1, len(df)):
        if df["c"].iloc[i] > df["c"].iloc[i-1]: obv.append(obv[-1] + df["v"].iloc[i])
        elif df["c"].iloc[i] < df["c"].iloc[i-1]: obv.append(obv[-1] - df["v"].iloc[i])
        else: obv.append(obv[-1])
    df["obv"] = obv

    tp_sma = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    df["cci"] = (tp - tp_sma) / (0.015 * mad).replace(0, np.nan)

    hh = df["h"].rolling(14).max(); ll = df["l"].rolling(14).min()
    df["williams_r"] = -100 * (hh - df["c"]) / (hh - ll).replace(0, np.nan)

    tp2 = (df["h"] + df["l"] + df["c"]) / 3
    mf = tp2 * df["v"]
    pos_mf = mf.where(tp2 > tp2.shift(), 0).rolling(14).sum()
    neg_mf = mf.where(tp2 < tp2.shift(), 0).rolling(14).sum()
    mfr = pos_mf / neg_mf.replace(0, np.nan)
    df["mfi"] = 100 - 100 / (1 + mfr)

    df["aroon_up"] = df["h"].rolling(25).apply(lambda x: x.argmax()/25*100, raw=True)
    df["aroon_down"] = df["l"].rolling(25).apply(lambda x: x.argmin()/25*100, raw=True)

    atr10 = tr.rolling(10).mean()
    hl2 = (df["h"] + df["l"]) / 2
    df["st_upper"] = hl2 + 3*atr10
    df["st_lower"] = hl2 - 3*atr10

    df["tenkan"] = (df["h"].rolling(9).max() + df["l"].rolling(9).min()) / 2
    df["kijun"] = (df["h"].rolling(26).max() + df["l"].rolling(26).min()) / 2
    df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2).shift(26)
    df["senkou_b"] = ((df["h"].rolling(52).max() + df["l"].rolling(52).min()) / 2).shift(26)

    df["kc_mid"] = df["c"].ewm(span=20).mean()
    df["kc_upper"] = df["kc_mid"] + 2*atr10
    df["kc_lower"] = df["kc_mid"] - 2*atr10

    psar = [float(df["l"].iloc[0])]
    af = 0.02; ep = float(df["h"].iloc[0]); bull = True
    for i in range(1, len(df)):
        prev = psar[-1]
        if bull:
            cur = prev + af*(ep - prev)
            if df["l"].iloc[i] < cur:
                bull = False; cur = ep; ep = float(df["l"].iloc[i]); af = 0.02
            else:
                if df["h"].iloc[i] > ep: ep = float(df["h"].iloc[i]); af = min(af+0.02, 0.2)
        else:
            cur = prev + af*(ep - prev)
            if df["h"].iloc[i] > cur:
                bull = True; cur = ep; ep = float(df["h"].iloc[i]); af = 0.02
            else:
                if df["l"].iloc[i] < ep: ep = float(df["l"].iloc[i]); af = min(af+0.02, 0.2)
        psar.append(cur)
    df["psar"] = psar

    last = df.iloc[-1]
    pivot = (float(last["h"]) + float(last["l"]) + float(last["c"])) / 3
    df["pivot"] = pivot
    df["r1"] = 2*pivot - float(last["l"])
    df["s1"] = 2*pivot - float(last["h"])
    df["r2"] = pivot + (float(last["h"]) - float(last["l"]))
    df["s2"] = pivot - (float(last["h"]) - float(last["l"]))
    df["r3"] = float(last["h"]) + 2*(pivot - float(last["l"]))
    df["s3"] = float(last["l"]) - 2*(float(last["h"]) - pivot)

    recent = df.tail(50)
    sh = float(recent["h"].max()); sl = float(recent["l"].min())
    diff = sh - sl
    df["fib_236"] = sh - 0.236*diff
    df["fib_382"] = sh - 0.382*diff
    df["fib_500"] = sh - 0.500*diff
    df["fib_618"] = sh - 0.618*diff
    df["fib_786"] = sh - 0.786*diff

    return df

def find_zones(df, lb=5, max_zones=3):
    H = df["h"].values; L = df["l"].values; T = df["t"].values
    res = []; sup = []
    for i in range(lb, len(df)-lb):
        if H[i] == max(H[i-lb:i+lb+1]): res.append((T[i], H[i]))
        if L[i] == min(L[i-lb:i+lb+1]): sup.append((T[i], L[i]))
    return sup[-max_zones:], res[-max_zones:]

# ============ PATTERN + DIVERGENCE ============
def detect_patterns(df):
    patterns = []
    if len(df) < 5: return patterns
    for i in range(max(1, len(df)-20), len(df)):
        try:
            o, h, l, c = float(df["o"].iloc[i]), float(df["h"].iloc[i]), float(df["l"].iloc[i]), float(df["c"].iloc[i])
            po, pc = float(df["o"].iloc[i-1]), float(df["c"].iloc[i-1])
            body = abs(c - o); rng = h - l
            if rng == 0: continue
            uw = h - max(o, c); lw = min(o, c) - l
            t = df["t"].iloc[i].strftime("%m-%d %H:%M")
            if body/rng < 0.1: patterns.append({"Time": t, "Pattern": "Doji", "Bias": "NEUTRAL"})
            elif lw > 2*body and uw < body*0.5 and c > o: patterns.append({"Time": t, "Pattern": "Hammer", "Bias": "BULLISH"})
            elif uw > 2*body and lw < body*0.5 and c < o: patterns.append({"Time": t, "Pattern": "Shooting Star", "Bias": "BEARISH"})
            elif c > o and pc < po and c > po and o < pc: patterns.append({"Time": t, "Pattern": "Bullish Engulfing", "Bias": "BULLISH"})
            elif c < o and pc > po and c < po and o > pc: patterns.append({"Time": t, "Pattern": "Bearish Engulfing", "Bias": "BEARISH"})
            elif body/rng > 0.9:
                patterns.append({"Time": t, "Pattern": "Marubozu", "Bias": "BULLISH" if c > o else "BEARISH"})
        except Exception:
            continue
    return patterns[-10:]

def detect_divergence(df):
    divs = []
    if len(df) < 30: return divs
    recent = df.tail(30).reset_index(drop=True)
    for i in range(3, len(recent)-3):
        for j in range(i+3, len(recent)):
            try:
                if recent["c"].iloc[j] < recent["c"].iloc[i] and recent["rsi"].iloc[j] > recent["rsi"].iloc[i]:
                    if recent["rsi"].iloc[i] < 40:
                        divs.append({"Time": recent["t"].iloc[j].strftime("%m-%d %H:%M"),
                                     "Type": "Bullish RSI Div", "Bias": "BULLISH"}); break
                if recent["c"].iloc[j] > recent["c"].iloc[i] and recent["rsi"].iloc[j] < recent["rsi"].iloc[i]:
                    if recent["rsi"].iloc[i] > 60:
                        divs.append({"Time": recent["t"].iloc[j].strftime("%m-%d %H:%M"),
                                     "Type": "Bearish RSI Div", "Bias": "BEARISH"}); break
            except Exception:
                continue
    return divs[-5:]

# ============ SIGNALS ============
def detect_signals(df):
    sigs = []
    if len(df) < 50: return sigs
    for i in range(1, len(df)):
        pf, ps = df["ema20"].iloc[i-1], df["ema50"].iloc[i-1]
        cf, cs = df["ema20"].iloc[i], df["ema50"].iloc[i]
        r = df["rsi"].iloc[i]
        if pd.isna(pf) or pd.isna(r): continue
        if pf <= ps and cf > cs and r < 70:
            sigs.append({"i":i, "time":df["t"].iloc[i], "price":float(df["c"].iloc[i]),
                         "type":"BUY", "rsi":float(r)})
        elif pf >= ps and cf < cs and r > 30:
            sigs.append({"i":i, "time":df["t"].iloc[i], "price":float(df["c"].iloc[i]),
                         "type":"SELL", "rsi":float(r)})
    return sigs

def track_signal(df, sig, atr):
    i = sig["i"]; entry = sig["price"]
    fut = df.iloc[i+1:]
    if fut.empty:
        return {"cur":entry,"max_up":0,"max_down":0,"dur":0,"live":True,
                "tp1":False,"tp2":False,"sl":False,"first_hit":None,
                "tp1_price":0,"tp2_price":0,"sl_price":0}
    if sig["type"] == "BUY":
        tp1p = entry + 1.5*atr; tp2p = entry + 3*atr; slp = entry - 2*atr
    else:
        tp1p = entry - 1.5*atr; tp2p = entry - 3*atr; slp = entry + 2*atr

    tp1_hit = tp2_hit = sl_hit = False
    first_hit = None
    for idx, row in fut.iterrows():
        if sig["type"] == "BUY":
            if row["h"] >= tp1p and not tp1_hit:
                tp1_hit = True
                if first_hit is None: first_hit = "TP1"
            if row["h"] >= tp2p and not tp2_hit: tp2_hit = True
            if row["l"] <= slp and not sl_hit:
                sl_hit = True
                if first_hit is None: first_hit = "SL"
        else:
            if row["l"] <= tp1p and not tp1_hit:
                tp1_hit = True
                if first_hit is None: first_hit = "TP1"
            if row["l"] <= tp2p and not tp2_hit: tp2_hit = True
            if row["h"] >= slp and not sl_hit:
                sl_hit = True
                if first_hit is None: first_hit = "SL"

    max_up = (float(fut["h"].max()) - entry)/entry*100
    max_down = (float(fut["l"].min()) - entry)/entry*100
    dur = (df["t"].iloc[-1] - df["t"].iloc[i]).total_seconds()/3600
    return {"cur":float(df["c"].iloc[-1]), "max_up":max_up, "max_down":max_down,
            "dur":dur, "live":True, "tp1":tp1_hit, "tp2":tp2_hit, "sl":sl_hit,
            "first_hit":first_hit, "tp1_price":tp1p, "tp2_price":tp2p, "sl_price":slp}

# ============ SCANNER ============
def analyze_coin(sym):
    try:
        df = klines(sym, "1h", 200)
        if df.empty or len(df) < 100: return None
        df = add_indicators(df)
        last = df.iloc[-1]
        px = float(last["c"])
        rsi = float(last["rsi"]) if not pd.isna(last["rsi"]) else 50
        vr = float(last["vr"]) if not pd.isna(last["vr"]) else 0
        atr = float(last["atr"]) if not pd.isna(last["atr"]) else px*0.01
        ema20 = float(last["ema20"]); ema50 = float(last["ema50"])
        trend = "BULL" if ema20 > ema50 else "BEAR"
        t = ticker(sym)
        chg = t.get("chg24h", 0) if t else 0
        vol_usdt = t.get("volUSDT", 0) if t else 0

        if trend == "BULL" and 40 < rsi < 65: signal = "LONG"
        elif trend == "BEAR" and 35 < rsi < 60: signal = "SHORT"
        else: signal = "WAIT"

        if signal == "LONG":
            entry = px; sl = px - 2*atr; tp1 = px + 1.5*atr; tp2 = px + 3*atr; tp3 = px + 5*atr
        elif signal == "SHORT":
            entry = px; sl = px + 2*atr; tp1 = px - 1.5*atr; tp2 = px - 3*atr; tp3 = px - 5*atr
        else:
            entry = sl = tp1 = tp2 = tp3 = px

        strength = 0
        if trend == "BULL" and signal == "LONG": strength += 30
        if trend == "BEAR" and signal == "SHORT": strength += 30
        if 45 < rsi < 60: strength += 15
        if vr > 1.5: strength += 20
        elif vr > 1.2: strength += 10
        strength += min(int(abs(chg)), 20)
        strength = min(strength, 100)

        return {"Symbol":sym,"Price":round(px,6),"Chg24h":round(chg,2),
                "VolUSDT_M":round(vol_usdt/1e6,1),"Trend":trend,"RSI":round(rsi,1),
                "VolRatio":round(vr,2),"ATR_pct":round(atr/px*100,2),
                "Signal":signal,"Strength":strength,
                "Entry":round(entry,6),"SL":round(sl,6),
                "TP1":round(tp1,6),"TP2":round(tp2,6),"TP3":round(tp3,6),
                "RR":round(abs(tp2-entry)/abs(sl-entry),2) if sl != entry else 0,
                "ScannedAt":datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    except Exception:
        return None

# ============ AGENTS (9 + 1 CHIEF) ============
AGENTS = [
    {"name": "📈 Trend Analyst",
     "system": 'You are a professional crypto trend analyst. Reply JSON only: {"verdict":"BULLISH|BEARISH|SIDEWAYS","score":-3 to 3,"reason":"1 short line"}.'},
    {"name": "⚡ Momentum Analyst",
     "system": 'You are a momentum specialist. Reply JSON only: {"verdict":"STRONG|WEAK|OVERSOLD|OVERBOUGHT|NEUTRAL","score":-3 to 3,"reason":"1 short line"}.'},
    {"name": "🐳 Volume Analyst",
     "system": 'You 
