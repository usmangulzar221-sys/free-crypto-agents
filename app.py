import streamlit as st, requests, pandas as pd, numpy as np, plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time, os, json
import streamlit.components.v1 as components

st.set_page_config(page_title="Auto LLM Scanner", layout="wide")
st.markdown("<style>.stApp{background:#0b0f17;color:#e5e7eb}.card{background:#111827;border-radius:12px;padding:14px;border:1px solid #1f2937;margin:8px 0}.buy{color:#22c55e;font-weight:800}.sell{color:#ef4444;font-weight:800}.hold{color:#f59e0b;font-weight:800}.llm{background:#1e1b4b;border-radius:10px;padding:12px;margin:8px 0;border-left:4px solid #a855f7}.sig{background:#1e293b;border-radius:10px;padding:12px;margin:8px 0;border-left:5px solid #22c55e}.sigS{border-left-color:#ef4444}.alert{background:#1e293b;border-radius:8px;padding:10px;margin:6px 0;border-left:4px solid #22c55e}.badge{display:inline-block;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:700}</style>", unsafe_allow_html=True)

try:
    from groq import Groq
    GA = True
except:
    GA = False

def gkey():
    try:
        return st.secrets["GROQ_API_KEY"]
    except:
        return os.environ.get("GROQ_API_KEY", "")

GK = gkey()
cl = None
MD = None
if GA and GK:
    try:
        cl = Groq(api_key=GK)
        MD = "openai/gpt-oss-120b"
    except:
        cl = None

def L(sp, up, mt=400):
    if cl is None:
        return None, "No key"
    try:
        r = cl.chat.completions.create(model=MD, messages=[{"role": "system", "content": sp}, {"role": "user", "content": up}], temperature=0.3, max_tokens=mt)
        return r.choices[0].message.content, None
    except Exception as e:
        return None, str(e)[:150]

def PJ(r):
    if not r:
        return None
    try:
        t = r.strip()
        if "```" in t:
            p = t.split("```")
            if len(p) >= 2:
                t = p[1].replace("json", "").strip()
        return json.loads(t)
    except:
        return {"verdict": r[:25], "score": 0, "reason": r[:70]}

OK = "https://www.okx.com/api/v5"
TFM = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}

def VOICE(text):
    try:
        safe = text.replace("'", "").replace('"', '')
        components.html("<script>var u=new SpeechSynthesisUtterance('" + safe + "');u.rate=0.95;u.pitch=1;window.speechSynthesis.speak(u);</script>", height=0)
    except:
        pass

@st.cache_data(ttl=3600)
def COINS(market="SPOT"):
    try:
        it = "SPOT" if market == "SPOT" else "SWAP"
        r = requests.get(OK + "/market/tickers", params={"instType": it}, timeout=12).json()
        if r.get("code") != "0":
            return []
        o = []
        for d in r["data"]:
            i = d.get("instId", "")
            if market == "SPOT":
                if not i.endswith("-USDT") or "USDC" in i or "DAI" in i:
                    continue
                sym = i.replace("-", "")
            else:
                if not i.endswith("-USDT-SWAP"):
                    continue
                sym = i.replace("-USDT-SWAP", "USDT")
            try:
                v = float(d.get("volCcy24h", 0))
            except:
                v = 0
            if v < 50000:
                continue
            o.append({"s": sym, "iid": i, "v": v})
        o.sort(key=lambda x: x["v"], reverse=True)
        return o[:500]
    except:
        return []

def IID(s, market):
    if market == "SPOT":
        return s[:-4] + "-USDT" if s.endswith("USDT") else s
    else:
        return s[:-4] + "-USDT-SWAP" if s.endswith("USDT") else s

@st.cache_data(ttl=20)
def KL(s, i="1h", n=300, market="SPOT"):
    try:
        r = requests.get(OK + "/market/candles", params={"instId": IID(s, market), "bar": TFM.get(i, "1H"), "limit": min(n, 300)}, timeout=10).json()
        if r.get("code") != "0" or not r.get("data"):
            return pd.DataFrame()
        d = r["data"]
        df = pd.DataFrame(d, columns=["t", "o", "h", "l", "c", "v", "vq", "vc", "x"])
        for c in ["o", "h", "l", "c", "v"]:
            df[c] = df[c].astype(float)
        df["t"] = pd.to_datetime(df["t"].astype(float), unit="ms")
        return df[["t", "o", "h", "l", "c", "v"]].sort_values("t").reset_index(drop=True)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=15)
def TX(s, market="SPOT"):
    try:
        r = requests.get(OK + "/market/ticker", params={"instId": IID(s, market)}, timeout=8).json()
        if r.get("code") != "0" or not r.get("data"):
            return {}
        d = r["data"][0]
        la = float(d["last"])
        op = float(d["open24h"])
        cg = (la - op) / op * 100 if op else 0
        try:
            vl = float(d.get("volCcy24h", 0))
        except:
            vl = 0
        return {"p": la, "c": cg, "v": vl}
    except:
        return {}

@st.cache_data(ttl=300)
def FG():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6).json()
        d = r["data"][0]
        return {"v": int(d["value"]), "l": d["value_classification"]}
    except:
        return {"v": 50, "l": "Neutral"}

@st.cache_data(ttl=300)
def GM():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=8).json()
        d = r["data"]
        return {"btc": round(d["market_cap_percentage"].get("btc", 0), 2), "eth": round(d["market_cap_percentage"].get("eth", 0), 2), "mc": d["total_market_cap"]["usd"], "tv": d["total_volume"]["usd"]}
    except:
        return {"btc": 0, "eth": 0, "mc": 0, "tv": 0}

@st.cache_data(ttl=60)
def MP():
    try:
        r1 = requests.get("https://mempool.space/api/mempool", timeout=6).json()
        r2 = requests.get("https://mempool.space/api/v1/fees/recommended", timeout=6).json()
        r3 = requests.get("https://mempool.space/api/blocks/tip/height", timeout=6).text
        return {"h": int(r3), "c": r1.get("count", 0), "ff": r2.get("fastestFee", 0), "f30": r2.get("halfHourFee", 0), "f1h": r2.get("hourFee", 0)}
    except:
        return {"h": 0, "c": 0, "ff": 0, "f30": 0, "f1h": 0}

def IND(df):
    df = df.copy()
    df["e20"] = df["c"].ewm(span=20, adjust=False).mean()
    df["e50"] = df["c"].ewm(span=50, adjust=False).mean()
    df["e200"] = df["c"].ewm(span=200, adjust=False).mean()
    d = df["c"].diff()
    g = d.clip(lower=0).rolling(14).mean()
    l = (-d.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - 100 / (1 + g / l.replace(0, np.nan))
    tr = pd.concat([df["h"] - df["l"], (df["h"] - df["c"].shift()).abs(), (df["l"] - df["c"].shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["va"] = df["v"].rolling(20).mean()
    df["vr"] = df["v"] / df["va"]
    e1 = df["c"].ewm(span=12, adjust=False).mean()
    e2 = df["c"].ewm(span=26, adjust=False).mean()
    df["macd"] = e1 - e2
    df["msig"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["mhist"] = df["macd"] - df["msig"]
    return df

def ZN(df, lb=5):
    H = df["h"].values
    L = df["l"].values
    T = df["t"].values
    rs = []
    sp = []
    for i in range(lb, len(df) - lb):
        if H[i] == max(H[i - lb:i + lb + 1]):
            rs.append((T[i], H[i]))
        if L[i] == min(L[i - lb:i + lb + 1]):
            sp.append((T[i], L[i]))
    return sp[-3:], rs[-3:]

def SG(df):
    out = []
    for i in range(1, len(df)):
        pf = df["e20"].iloc[i - 1]
        ps = df["e50"].iloc[i - 1]
        cf = df["e20"].iloc[i]
        cs = df["e50"].iloc[i]
        r = df["rsi"].iloc[i]
        if pd.isna(pf) or pd.isna(r):
            continue
        if pf <= ps and cf > cs and r < 70:
            out.append({"i": i, "t": df["t"].iloc[i], "p": float(df["c"].iloc[i]), "ty": "BUY", "r": float(r)})
        elif pf >= ps and cf < cs and r > 30:
            out.append({"i": i, "t": df["t"].iloc[i], "p": float(df["c"].iloc[i]), "ty": "SELL", "r": float(r)})
    return out

def TRK(df, s, atr):
    i = s["i"]
    e = s["p"]
    f = df.iloc[i + 1:]
    if f.empty:
        return {"mu": 0, "md": 0, "du": 0, "tp1": False, "tp2": False, "sl": False, "fh": None, "cur": e, "slp": 0, "tp1p": 0, "tp2p": 0, "sl_time": None, "tp1_time": None, "tp2_time": None, "first_time": None}
    tp1p = e + 1.5 * atr if s["ty"] == "BUY" else e - 1.5 * atr
    tp2p = e + 3 * atr if s["ty"] == "BUY" else e - 3 * atr
    slp = e - 2 * atr if s["ty"] == "BUY" else e + 2 * atr
    t1 = t2 = sh = False
    fh = None
    sl_time = None
    tp1_time = None
    tp2_time = None
    first_time = None
    for idx, row in f.iterrows():
        if s["ty"] == "BUY":
            if row["h"] >= tp1p and not t1:
                t1 = True
                tp1_time = row["t"]
                if fh is None:
                    fh = "TP1"
                    first_time = row["t"]
            if row["h"] >= tp2p and not t2:
                t2 = True
                tp2_time = row["t"]
            if row["l"] <= slp and not sh:
                sh = True
                sl_time = row["t"]
                if fh is None:
                    fh = "SL"
                    first_time = row["t"]
        else:
            if row["l"] <= tp1p and not t1:
                t1 = True
                tp1_time = row["t"]
                if fh is None:
                    fh = "TP1"
                    first_time = row["t"]
            if row["l"] <= tp2p and not t2:
                t2 = True
                tp2_time = row["t"]
            if row["h"] >= slp and not sh:
                sh = True
                sl_time = row["t"]
                if fh is None:
                    fh = "SL"
                    first_time = row["t"]
    mu = (float(f["h"].max()) - e) / e * 100
    md = (float(f["l"].min()) - e) / e * 100
    du = (df["t"].iloc[-1] - df["t"].iloc[i]).total_seconds() / 3600
    return {"mu": mu, "md": md, "du": du, "tp1": t1, "tp2": t2, "sl": sh, "fh": fh, "cur": float(df["c"].iloc[-1]), "slp": slp, "tp1p": tp1p, "tp2p": tp2p, "sl_time": sl_time, "tp1_time": tp1_time, "tp2_time": tp2_time, "first_time": first_time}

def SCN(s, market="SPOT"):
    try:
        df = KL(s, "1h", 200, market)
        if df.empty or len(df) < 100:
            return None
        df = IND(df)
        la = df.iloc[-1]
        p = float(la["c"])
        r = float(la["rsi"]) if not pd.isna(la["rsi"]) else 50
        v = float(la["vr"]) if not pd.isna(la["vr"]) else 0
        a = float(la["atr"]) if not pd.isna(la["atr"]) else p * 0.01
        e20 = float(la["e20"])
        e50 = float(la["e50"])
        tr = "BULL" if e20 > e50 else "BEAR"
        t = TX(s, market)
        cg = t.get("c", 0) if t else 0
        vl = t.get("v", 0) if t else 0
        if tr == "BULL" and 40 < r < 65:
            sg = "LONG"
        elif tr == "BEAR" and 35 < r < 60:
            sg = "SHORT"
        else:
            sg = "WAIT"
        if sg == "LONG":
            e = p
            sl = p - 2 * a
            tp1 = p + 1.5 * a
            tp2 = p + 3 * a
        elif sg == "SHORT":
            e = p
            sl = p + 2 * a
            tp1 = p - 1.5 * a
            tp2 = p - 3 * a
        else:
            e = sl = tp1 = tp2 = p
        st2 = 0
        if tr == "BULL" and sg == "LONG":
            st2 += 30
        if tr == "BEAR" and sg == "SHORT":
            st2 += 30
        if 45 < r < 60:
            st2 += 15
        if v > 1.5:
            st2 += 20
        elif v > 1.2:
            st2 += 10
        st2 += min(int(abs(cg)), 20)
        st2 = min(st2, 100)
        return {"Sym": s, "Px": round(p, 6), "Cg": round(cg, 2), "Vm": round(vl / 1e6, 1), "Tr": tr, "RSI": round(r, 1), "VR": round(v, 2), "Sig": sg, "Str": st2, "E": round(e, 6), "SL": round(sl, 6), "TP1": round(tp1, 6), "TP2": round(tp2, 6), "Market": market, "Time": datetime.now().strftime("%H:%M:%S")}
    except:
        return None

def SNAP(s, i, market="SPOT"):
    df = KL(s, i, 250, market)
    if df.empty:
        return None, None
    df = IND(df)
    sp, rs = ZN(df)
    la = df.iloc[-1]
    f = FG()
    g = GM()
    m = MP()
    d = {"sym": s, "tf": i, "market": market, "p": round(float(la["c"]), 6), "e20": round(float(la["e20"]), 6), "e50": round(float(la["e50"]), 6), "e200": round(float(la["e200"]), 6) if not pd.isna(la["e200"]) else None, "rsi": round(float(la["rsi"]), 2) if not pd.isna(la["rsi"]) else 50, "atr": round(float(la["atr"]), 6) if not pd.isna(la["atr"]) else None, "macd": round(float(la["macd"]), 6) if not pd.isna(la["macd"]) else 0, "vr": round(float(la["vr"]), 2) if not pd.isna(la["vr"]) else 0, "sp": [round(float(x[1]), 6) for x in sp], "rs": [round(float(x[1]), 6) for x in rs], "fg": f, "btc": g["btc"], "bh": m["h"], "bfee": m["ff"]}
    return d, df

def PR(s):
    p = "Symbol: " + s["sym"] + " " + s["market"] + "\n"
    p += "Timeframe: " + s["tf"] + "\n"
    p += "Price: " + str(s["p"]) + "\n"
    p += "EMA20: " + str(s["e20"]) + "\n"
    p += "EMA50: " + str(s["e50"]) + "\n"
    p += "EMA200: " + str(s["e200"]) + "\n"
    p += "RSI: " + str(s["rsi"]) + "\n"
    p += "ATR: " + str(s["atr"]) + "\n"
    p += "MACD: " + str(s["macd"]) + "\n"
    p += "Volume Ratio: " + str(s["vr"]) + "\n"
    p += "Supports: " + str(s["sp"]) + "\n"
    p += "Resistances: " + str(s["rs"]) + "\n"
    p += "Fear Greed: " + str(s["fg"]["v"]) + " " + s["fg"]["l"] + "\n"
    p += "BTC Dominance: " + str(s["btc"]) + "%\n"
    p += "Bitcoin Block: " + str(s["bh"]) + "\n"
    p += "Bitcoin Fee: " + str(s["bfee"]) + " sat/vB"
    return p

AGS = [
    ("Trend Analyst", "You are a crypto trend analyst. Reply JSON only with keys verdict (BULLISH or BEARISH or SIDEWAYS), score (-3 to 3), reason (one line)."),
    ("Momentum Analyst", "You are a momentum analyst. Reply JSON only with keys verdict (STRONG or WEAK or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Volume Analyst", "You are a volume analyst. Reply JSON only with keys verdict (HIGH or NORMAL or LOW), score (-3 to 3), reason (one line)."),
    ("Risk Manager", "You are a risk manager. Reply JSON only with keys verdict (LOW_RISK or MEDIUM_RISK or HIGH_RISK), score (-3 to 3), sl_price (number), reason (one line)."),
    ("SR Analyst", "You are a support resistance analyst. Reply JSON only with keys verdict (NEAR_SUPPORT or NEAR_RESISTANCE or MID_RANGE), score (-3 to 3), reason (one line)."),
    ("Sentiment Analyst", "You analyze sentiment. Reply JSON only with keys verdict (GREEDY or FEARFUL or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Indicator Analyst", "You analyze indicators. Reply JSON only with keys verdict (BULLISH or BEARISH or NEUTRAL), score (-3 to 3), reason (one line)."),
]

def R1(s):
    res = []
    pt = PR(s)
    for nm, sy in AGS:
        r, e = L(sy, pt, 180)
        if e:
            res.append({"n": nm, "v": "ERR", "s": 0, "r": e[:50], "sl": None})
            continue
        d = PJ(r)
        if d is None:
            res.append({"n": nm, "v": "?", "s": 0, "r": (r or "")[:50], "sl": None})
        else:
            res.append({"n": nm, "v": d.get("verdict", "?"), "s": int(d.get("score", 0)), "r": d.get("reason", ""), "sl": d.get("sl_price")})
    return res

def R2(s, r1):
    sm = "Round 1 opinions:\n"
    for r in r1:
        sm += r["n"] + ": " + str(r["v"]) + " score " + str(r["s"]) + " - " + str(r["r"]) + "\n"
    sy = "You are senior market strategist. Read all 7 opinions and discuss. Reply JSON only with keys verdict (BULLISH or BEARISH or NEUTRAL), score (-3 to 3), reason (one line summarizing consensus)."
    p = PR(s) + "\n\n" + sm + "\n\nRefined opinion."
    r, e = L(sy, p, 200)
    if e:
        return {"n": "Senior Strategist", "v": "ERR", "s": 0, "r": e[:50]}
    d = PJ(r)
    if d is None:
        return {"n": "Senior Strategist", "v": "?", "s": 0, "r": (r or "")[:50]}
    return {"n": "Senior Strategist", "v": d.get("verdict", "?"), "s": int(d.get("score", 0)), "r": d.get("reason", "")}

def R3(s, r1, r2):
    sm = "Analyst opinions:\n"
    for r in r1:
        sm += r["n"] + ": " + str(r["v"]) + " (" + str(r["s"]) + ")\n"
    sm += "\nSenior Strategist: " + str(r2["v"]) + " (" + str(r2["s"]) + ") - " + str(r2["r"])
    sy = "You are Chief Trading Officer. Reply JSON only with keys decision (BUY or SELL or HOLD), confidence (0-100), entry (number), sl (number), tp1 (number), tp2 (number), tp3 (number), reasoning (2 lines)."
    p = PR(s) + "\n\n" + sm + "\n\nFinal decision."
    r, e = L(sy, p, 400)
    if e:
        return None, e
    d = PJ(r)
    if d is None:
        return None, "Parse: " + (r or "")[:100]
    return d, None

with st.sidebar:
    st.markdown("### Groq API Key")
    if GK:
        st.success("Loaded")
    else:
        uk = st.text_input("API key", type="password")
        if uk:
            try:
                cl = Groq(api_key=uk)
                MD = "openai/gpt-oss-120b"
                st.success("Set!")
            except:
                st.error("Invalid")
        else:
            st.info("Free: https://console.groq.com/keys")
    st.markdown("**Model:** " + str(MD or "-"))
    st.markdown("**Market:** OKX Spot + Futures")
    st.markdown("---")
    st.markdown("### Voice Alerts")
    voice_on = st.checkbox("Enable Voice", value=True)
    st.markdown("### Auto Scan")
    auto_on = st.checkbox("Auto every 5 min", value=False)

if "alerts" not in st.session_state:
    st.session_state.alerts = []
if "auto_sigs" not in st.session_state:
    st.session_state.auto_sigs = []
if "last_auto" not in st.session_state:
    st.session_state.last_auto = 0

bp = TX("BTCUSDT")
ep = TX("ETHUSDT")
s2 = TX("SOLUSDT")
c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC Spot", "${:,.2f}".format(bp.get("p", 0)) if bp else "-", "{:+.2f}%".format(bp.get("c", 0)) if bp else None)
c2.metric("ETH Spot", "${:,.2f}".format(ep.get("p", 0)) if ep else "-", "{:+.2f}%".format(ep.get("c", 0)) if ep else None)
c3.metric("SOL Spot", "${:,.2f}".format(s2.get("p", 0)) if s2 else "-", "{:+.2f}%".format(s2.get("c", 0)) if s2 else None)
c4.metric("Time", datetime.now().strftime("%H:%M:%S"))
st.title("Auto LLM Trading Scanner")

with st.expander("Market Data - Sentiment + Bitnode", expanded=False):
    f = FG()
    g = GM()
    m = MP()
    k1, k2, k3, k4 = st.columns(4)
    fc = "#ef4444" if f["v"] > 70 else "#22c55e" if f["v"] < 30 else "#f59e0b"
    k1.markdown("<div class='card'><b>Fear Greed</b><br><span style='color:" + fc + ";font-size:24px;font-weight:900'>" + str(f["v"]) + "</span><br>" + f["l"] + "</div>", unsafe_allow_html=True)
    k2.markdown("<div class='card'><b>BTC Dom</b><br><span style='font-size:24px;font-weight:900'>" + str(g["btc"]) + "%</span><br>ETH: " + str(g["eth"]) + "%</div>", unsafe_allow_html=True)
    k3.markdown("<div class='card'><b>MCap</b><br><span style='font-size:22px;font-weight:900'>${:.2f}T</span></div>".format(g["mc"] / 1e12), unsafe_allow_html=True)
    k4.markdown("<div class='card'><b>24h Vol</b><br><span style='font-size:22px;font-weight:900'>${:.1f}B</span></div>".format(g["tv"] / 1e9), unsafe_allow_html=True)
    st.markdown("##### Bitcoin Network")
    n1, n2, n3, n4, n5 = st.columns(5)
    n1.metric("Height", "{:,}".format(m["h"]))
    n2.metric("Mempool", "{:,}".format(m["c"]))
    n3.metric("Fast Fee", str(m["ff"]) + " sat/vB")
    n4.metric("30m", str(m["f30"]))
    n5.metric("1h", str(m["f1h"]))

if st.session_state.alerts:
    st.markdown("### Live Alerts")
    for a in st.session_state.alerts[-5:][::-1]:
        st.markdown("<div class='alert'><b>" + a["time"] + "</b> - " + a["msg"] + "</div>", unsafe_allow_html=True)

T1, T2, T3, T4 = st.tabs(["Auto Signals + LLM", "Chart (TradingView Style)", "Scanner Spot/Futures", "Signal History + SL Times"])

with T1:
    st.markdown("### Auto Signals with LLM Debate")
    st.caption("Round 1: 7 analysts | Round 2: Senior Strategist debate | Round 3: Chief final decision")
    if not GK:
        st.warning("Add Groq key in sidebar")
    else:
        mkt = st.radio("Market", ["SPOT", "FUTURES"], horizontal=True, key="mkt1")
        mkt_id = "SPOT" if mkt == "SPOT" else "SWAP"
        al = COINS(mkt_id)
        opt = [c["s"] for c in al[:200]] if al else ["BTCUSDT"]
        cc1, cc2 = st.columns([2, 1])
        ls = cc1.selectbox("Coin", opt, index=0, key="ls")
        li = cc2.selectbox("TF", ["15m", "1h", "4h"], index=1, key="li")
        b1, b2 = st.columns(2)
        run1 = b1.button("Run LLM Debate Now", type="primary", key="r1")
        run_auto = b2.button("Auto Signal (quick)", key="ra")
        if run1 or run_auto:
            with st.spinner("Analyzing..."):
                t0 = time.time()
                s, df = SNAP(ls, li, mkt_id)
                if s is None:
                    st.error("No data")
                else:
                    st.markdown("<div class='card'><b>" + mkt + " " + ls + "</b> - Price $" + str(s["p"]) + " | RSI " + str(s["rsi"]) + " | MACD " + str(s["macd"]) + " | Vol " + str(s["vr"]) + "x | F&G " + str(s["fg"]["v"]) + " | BTC.D " + str(s["btc"]) + "%</div>", unsafe_allow_html=True)
                    if run_auto:
                        r = float(s["rsi"])
                        if r < 45:
                            d = "BUY"
                        elif r > 55:
                            d = "SELL"
                        else:
                            d = "HOLD"
                        cc = 60 + int(abs(50 - r))
                        entry = s["p"]
                        atr = s["atr"] if s["atr"] else s["p"] * 0.01
                        if d == "BUY":
                            sl = entry - 2 * atr
                            tp1 = entry + 1.5 * atr
                            tp2 = entry + 3 * atr
                            tp3 = entry + 5 * atr
                        elif d == "SELL":
                            sl = entry + 2 * atr
                            tp1 = entry - 1.5 * atr
                            tp2 = entry - 3 * atr
                            tp3 = entry - 5 * atr
                        else:
                            sl = tp1 = tp2 = tp3 = entry
                        dc = "#22c55e" if d == "BUY" else "#ef4444" if d == "SELL" else "#f59e0b"
                        st.markdown("<div class='card' style='border:3px solid " + dc + ";text-align:center'><div style='color:#94a3b8'>AUTO SIGNAL</div><div style='color:" + dc + ";font-size:36px;font-weight:900'>" + d + "</div><div>Confidence: " + str(cc) + "%</div><div style='margin-top:12px'><b>Entry:</b> $" + str(round(entry, 6)) + " <b>SL:</b> $" + str(round(sl, 6)) + " <b>TP1:</b> $" + str(round(tp1, 6)) + " <b>TP2:</b> $" + str(round(tp2, 6)) + "</div></div>", unsafe_allow_html=True)
                        msg = "Auto " + d + " " + ls + " " + mkt + " Entry $" + str(round(entry, 4)) + " SL $" + str(round(sl, 4))
                        st.session_state.alerts.append({"time": datetime.now().strftime("%H:%M:%S"), "msg": msg})
                        st.session_state.auto_sigs.append({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "coin": ls, "market": mkt, "decision": d, "conf": cc, "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3, "reason": "Auto RSI-based signal"})
                        if voice_on:
                            VOICE("Auto signal " + d + " on " + ls.replace("USDT", "") + " " + mkt)
                    else:
                        res1 = R1(s)
                        st.markdown("#### Round 1 - 7 Agents")
                        for a in res1:
                            vc = "#22c55e" if a["s"] > 0 else "#ef4444" if a["s"] < 0 else "#f59e0b"
                            sl_txt = "<br>SL: $" + str(a["sl"]) if a.get("sl") else ""
                            st.markdown("<div class='llm' style='border-left-color:" + vc + "'><b>" + a["n"] + "</b> -> <b style='color:" + vc + "'>" + str(a["v"]) + "</b> (" + str(a["s"]) + ")<br><span style='color:#cbd5e1;font-size:13px'>" + str(a["r"]) + "</span>" + sl_txt + "</div>", unsafe_allow_html=True)
                        with st.spinner("Round 2: Senior strategist debating..."):
                            res2 = R2(s, res1)
                            vc = "#22c55e" if res2["s"] > 0 else "#ef4444" if res2["s"] < 0 else "#f59e0b"
                            st.markdown("#### Round 2 - Senior Strategist (after considering all)")
                            st.markdown("<div class='llm' style='border-left-color:" + vc + "'><b>Senior Strategist</b> -> <b style='color:" + vc + "'>" + str(res2["v"]) + "</b> (" + str(res2["s"]) + ")<br><span style='color:#cbd5e1;font-size:13px'>" + str(res2["r"]) + "</span></div>", unsafe_allow_html=True)
                        with st.spinner("Round 3: Chief Officer deciding..."):
                            cons, ce = R3(s, res1, res2)
                            if ce:
                                st.error(ce)
                            else:
                                d = cons.get("decision", "HOLD")
                                cf = cons.get("confidence", 0)
                                dc = "#22c55e" if d == "BUY" else "#ef4444" if d == "SELL" else "#f59e0b"
                                st.markdown("#### Round 3 - Chief FINAL DECISION")
                                st.markdown("<div class='card' style='border:3px solid " + dc + ";text-align:center'><div style='color:#94a3b8'>FINAL LLM SIGNAL</div><div style='color:" + dc + ";font-size:38px;font-weight:900'>" + str(d) + "</div><div>Confidence: " + str(cf) + "%</div><div style='margin-top:14px'><b>Entry:</b> $" + str(cons.get("entry", "-")) + " <b>SL:</b> $" + str(cons.get("sl", "-")) + " <b>TP1:</b> $" + str(cons.get("tp1", "-")) + " <b>TP2:</b> $" + str(cons.get("tp2", "-")) + " <b>TP3:</b> $" + str(cons.get("tp3", "-")) + "</div><div style='margin-top:10px;font-style:italic'>" + str(cons.get("reasoning", "")) + "</div></div>", unsafe_allow_html=True)
                                st.session_state.auto_sigs.append({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "coin": ls, "market": mkt, "decision": d, "conf": cf, "entry": cons.get("entry"), "sl": cons.get("sl"), "tp1": cons.get("tp1"), "tp2": cons.get("tp2"), "tp3": cons.get("tp3"), "reason": cons.get("reasoning", "")})
                                st.session_state.alerts.append({"time": datetime.now().strftime("%H:%M:%S"), "msg": "LLM " + d + " " + ls + " " + mkt + " Conf " + str(cf) + "%"})
                                if voice_on:
                                    VOICE("LLM says " + d + " on " + ls.replace("USDT", "") + " confidence " + str(cf) + " percent")
                    st.caption("Completed in " + "{:.1f}".format(time.time() - t0) + "s")
    if st.session_state.auto_sigs:
        st.markdown("### Auto Signals Log")
        df_auto = pd.DataFrame(st.session_state.auto_sigs[-15:][::-1])
        st.dataframe(df_auto, use_container_width=True, hide_index=True)

with T2:
    st.markdown("### Detailed Chart - TradingView Style with Zones")
    mkt2 = st.radio("Market", ["SPOT", "FUTURES"], horizontal=True, key="mkt2")
    mkt_id2 = "SPOT" if mkt2 == "SPOT" else "SWAP"
    al = COINS(mkt_id2)
    opt = [c["s"] for c in al[:500]] if al else ["BTCUSDT", "ETHUSDT"]
    cc1, cc2 = st.columns([2, 1])
    s = cc1.selectbox("Coin", opt, index=0, key="cs")
    iv = cc2.selectbox("TF", ["15m", "1h", "4h", "1d"], index=1, key="ct")
    df = KL(s, iv, 300, mkt_id2)
    if df.empty:
        st.error("No data")
    else:
        df = IND(df)
        sp, rs = ZN(df)
        sg = SG(df)
        la = df.iloc[-1]
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.62, 0.16, 0.22], subplot_titles=("", "Volume", "RSI"))
        fig.add_trace(go.Candlestick(x=df["t"], open=df["o"], high=df["h"], low=df["l"], close=df["c"], name=s, increasing_line_color="#22c55e", increasing_fillcolor="#22c55e", decreasing_line_color="#ef4444", decreasing_fillcolor="#ef4444"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["e20"], line=dict(color="#22d3ee", width=1.5), name="EMA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["e50"], line=dict(color="#fbbf24", width=1.5), name="EMA50"), row=1, col=1)
        if not df["e200"].isna().all():
            fig.add_trace(go.Scatter(x=df["t"], y=df["e200"], line=dict(color="#a855f7", width=1, dash="dot"), name="EMA200"), row=1, col=1)
        for t_, p in rs:
            fig.add_hrect(y0=p * 0.995, y1=p * 1.005, fillcolor="#ef4444", opacity=0.18, line_width=0, row=1, col=1)
            fig.add_hline(y=p, line_dash="dash", line_color="#ef4444", annotation_text="RES " + str(round(p, 4)), annotation_position="right", row=1, col=1)
        for t_, p in sp:
            fig.add_hrect(y0=p * 0.995, y1=p * 1.005, fillcolor="#22c55e", opacity=0.18, line_width=0, row=1, col=1)
            fig.add_hline(y=p, line_dash="dash", line_color="#22c55e", annotation_text="SUP " + str(round(p, 4)), annotation_position="right", row=1, col=1)
        for x in sg:
            cl2 = "#22c55e" if x["ty"] == "BUY" else "#ef4444"
            yp = x["p"] * 0.995 if x["ty"] == "BUY" else x["p"] * 1.005
            fig.add_trace(go.Scatter(x=[x["t"]], y=[yp], mode="markers+text", marker=dict(symbol="triangle-up" if x["ty"] == "BUY" else "triangle-down", size=16, color=cl2, line=dict(color="white", width=1.5)), text=[x["ty"]], textposition="bottom center", textfont=dict(color=cl2, size=10), showlegend=False), row=1, col=1)
        vc = ["#22c55e" if c >= o else "#ef4444" for c, o in zip(df["c"], df["o"])]
        fig.add_trace(go.Bar(x=df["t"], y=df["v"], marker_color=vc, name="Vol", opacity=0.85), row=2, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["va"], line=dict(color="#fbbf24", width=1), name="Avg"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["rsi"], line=dict(color="#a78bfa", width=1.5), name="RSI"), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", opacity=0.6, row=3, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="#64748b", opacity=0.3, row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", opacity=0.6, row=3, col=1)
        fig.update_layout(template="plotly_dark", height=850, paper_bgcolor="#0b0f17", plot_bgcolor="#0b0f17", xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.02, bgcolor="rgba(0,0,0,0)"), margin=dict(l=10, r=90, t=60, b=10), title=mkt2 + " " + s + " " + iv + " - Zones + Signals")
        fig.update_xaxes(showgrid=True, gridcolor="#1f2937")
        fig.update_yaxes(showgrid=True, gridcolor="#1f2937")
        st.plotly_chart(fig, use_container_width=True)
        rv = float(la["rsi"]) if not pd.isna(la["rsi"]) else 50
        vv = float(la["vr"]) if not pd.isna(la["vr"]) else 0
        trc = "BULL" if la["e20"] > la["e50"] else "BEAR"
        tc = "#22c55e" if trc == "BULL" else "#ef4444"
        rc = "#ef4444" if rv > 70 else "#22c55e" if rv < 30 else "#f59e0b"
        st.markdown("<div class='card'><b>Price:</b> $" + "{:,.6f}".format(la["c"]) + " <b>EMA20:</b> $" + "{:,.6f}".format(la["e20"]) + " <b>EMA50:</b> $" + "{:,.6f}".format(la["e50"]) + " <b>RSI:</b> <span style='color:" + rc + "'>" + "{:.1f}".format(rv) + "</span> <b>Vol:</b> " + "{:.2f}".format(vv) + "x <b>Trend:</b> <span style='color:" + tc + "'>" + trc + "</span></div>", unsafe_allow_html=True)

with T3:
    st.markdown("### Multi-Coin Scanner")
    mkt3 = st.radio("Market", ["SPOT", "FUTURES"], horizontal=True, key="mkt3")
    mkt_id3 = "SPOT" if mkt3 == "SPOT" else "SWAP"
    cc1, cc2, cc3 = st.columns([1, 1, 2])
    n = cc1.slider("Coins", 20, 200, 50, 10)
    mstr = cc2.slider("Min Strength", 0, 100, 30, 5)
    go = cc3.button("Start Scan", type="primary", key="scan3")
    if "sr" not in st.session_state:
        st.session_state.sr = []
    if go:
        al = COINS(mkt_id3)
        if not al:
            st.error("No coins")
        else:
            lst = al[:n]
            prog = st.progress(0)
            res = []
            new_alert = []
            for i, c in enumerate(lst):
                prog.progress((i + 1) / len(lst))
                r = SCN(c["s"], mkt_id3)
                if r and r["Str"] >= mstr:
                    res.append(r)
                    if r["Sig"] in ["LONG", "SHORT"] and r["Str"] >= 65:
                        msg = r["Sig"] + " " + r["Sym"] + " " + mkt3 + " Str " + str(r["Str"]) + " Entry $" + str(r["E"]) + " SL $" + str(r["SL"])
                        new_alert.append({"time": r["Time"], "msg": msg})
            prog.empty()
            st.session_state.sr = res
            st.session_state.alerts = (st.session_state.alerts + new_alert)[-30:]
            st.success("Found " + str(len(res)) + " signals in " + mkt3)
            if voice_on and len(new_alert) > 0:
                VOICE("Found " + str(len(new_alert)) + " strong signals in " + mkt3)
    if st.session_state.sr:
        dr = pd.DataFrame(st.session_state.sr).sort_values("Str", ascending=False)
        lg = dr[dr["Sig"] == "LONG"]
        sh = dr[dr["Sig"] == "SHORT"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total", len(dr))
        m2.metric("LONG", len(lg))
        m3.metric("SHORT", len(sh))
        m4.metric("Vol Spikes", len(dr[dr["VR"] > 1.5]))
        st.markdown("#### LONG Signals")
        for _, r in lg.head(20).iterrows():
            st.markdown("<div class='sig'><b>" + r["Sym"] + "</b> <span class='buy'>LONG</span> Str <b>" + str(r["Str"]) + "</b> at " + r["Time"] + "<br><b>Entry:</b> $" + str(r["E"]) + " <b>SL:</b> <span class='sell'>$" + str(r["SL"]) + "</span> <b>TP1:</b> <span class='buy'>$" + str(r["TP1"]) + "</span> <b>TP2:</b> <span class='buy'>$" + str(r["TP2"]) + "</span><br>RSI " + str(r["RSI"]) + " Vol " + str(r["VR"]) + "x Chg " + str(r["Cg"]) + "%</div>", unsafe_allow_html=True)
        st.markdown("#### SHORT Signals")
        for _, r in sh.head(20).iterrows():
            st.markdown("<div class='sig sigS'><b>" + r["Sym"] + "</b> <span class='sell'>SHORT</span> Str <b>" + str(r["Str"]) + "</b> at " + r["Time"] + "<br><b>Entry:</b> $" + str(r["E"]) + " <b>SL:</b> <span class='sell'>$" + str(r["SL"]) + "</span> <b>TP1:</b> <span class='buy'>$" + str(r["TP1"]) + "</span> <b>TP2:</b> <span class='buy'>$" + str(r["TP2"]) + "</span><br>RSI " + str(r["RSI"]) + " Vol " + str(r["VR"]) + "x Chg " + str(r["Cg"]) + "%</div>", unsafe_allow_html=True)

with T4:
    st.markdown("### Signal History with SL/TP Hit Times")
    mkt4 = st.radio("Market", ["SPOT", "FUTURES"], horizontal=True, key="mkt4")
    mkt_id4 = "SPOT" if mkt4 == "SPOT" else "SWAP"
    al = COINS(mkt_id4)
    opt = [c["s"] for c in al[:300]] if al else ["BTCUSDT"]
    cc1, cc2 = st.columns([2, 1])
    hs = cc1.selectbox("Coin", opt, index=0, key="hs")
    hi = cc2.selectbox("TF", ["15m", "1h", "4h"], index=1, key="hi")
    df = KL(hs, hi, 500, mkt_id4)
    if df.empty:
        st.error("No data")
    else:
        df = IND(df)
        sg = SG(df)
        if not sg:
            st.info("No signals")
        else:
            rows = []
            w = 0
            l2 = 0
            for s in sg[-30:][::-1]:
                at = float(df["atr"].iloc[s["i"]]) if not pd.isna(df["atr"].iloc[s["i"]]) else s["p"] * 0.01
                tr = TRK(df, s, at)
                if s["ty"] == "BUY":
                    rs2 = "WIN" if tr["mu"] > 1 else "LOSS" if tr["md"] < -1 else "OPEN"
                else:
                    rs2 = "WIN" if tr["md"] < -1 else "LOSS" if tr["mu"] > 1 else "OPEN"
                if rs2 == "WIN":
                    w += 1
                elif rs2 == "LOSS":
                    l2 += 1
                sig_time = s["t"].strftime("%m-%d %H:%M")
                sl_t = tr["sl_time"].strftime("%m-%d %H:%M") if tr["sl_time"] is not None else "-"
                tp1_t = tr["tp1_time"].strftime("%m-%d %H:%M") if tr["tp1_time"] is not None else "-"
                tp2_t = tr["tp2_time"].strftime("%m-%d %H:%M") if tr["tp2_time"] is not None else "-"
                first_t = tr["first_time"].strftime("%m-%d %H:%M") if tr["first_time"] is not None else "-"
                rows.append({"Signal Time": sig_time, "Type": s["ty"], "Entry": round(s["p"], 6), "RSI": round(s["r"], 1), "SL": round(tr.get("slp", 0), 6), "TP1": round(tr.get("tp1p", 0), 6), "TP2": round(tr.get("tp2p", 0), 6), "SL Hit At": sl_t, "TP1 Hit At": tp1_t, "TP2 Hit At": tp2_t, "First Hit": first_t, "First Type": tr["fh"] or "-", "Max Up %": round(tr["mu"], 2), "Max Down %": round(tr["md"], 2), "Dur": "{:.1f}h".format(tr["du"]), "Result": rs2})
            tot = w + l2
            wr = (w / tot * 100) if tot > 0 else 0
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total", len(sg))
            m2.metric("Wins", w)
            m3.metric("Losses", l2)
            m4.metric("Win Rate", "{:.1f}%".format(wr))
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.caption("Auto LLM Scanner - Spot + Futures - Voice Alerts - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
