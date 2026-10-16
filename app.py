import streamlit as st, requests, pandas as pd, numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import json

st.set_page_config(page_title="Pro Scanner", layout="wide")
st.markdown("<style>.stApp{background:#0b0f17;color:#e5e7eb}.card{background:#111827;border-radius:12px;padding:12px;border:1px solid #1f2937;margin:6px 0}.buy{color:#22c55e;font-weight:800}.sell{color:#ef4444;font-weight:800}.hold{color:#f59e0b;font-weight:800}.llm{background:#1e1b4b;border-radius:10px;padding:10px;margin:6px 0;border-left:4px solid #a855f7}.sig{background:#1e293b;border-radius:10px;padding:12px;margin:8px 0;border-left:5px solid #22c55e}.sigS{border-left-color:#ef4444}.big{font-size:30px;font-weight:900}.prog{height:10px;background:#1f2937;border-radius:5px;margin-top:8px;overflow:hidden}.prog>div{height:100%}.zone{background:#1e293b;border-radius:8px;padding:6px;margin:4px 0;display:flex;justify-content:space-between;font-size:13px}</style>", unsafe_allow_html=True)

OK = "https://www.okx.com/api/v5"
BY = "https://api.bybit.com/v5/market"
TFO = {"15m":"15m","1h":"1H","4h":"4H","1d":"1D"}
TFB = {"15m":"15","1h":"60","4h":"240","1d":"D"}

def PKT():
    return (datetime.utcnow() + timedelta(hours=5)).strftime("%I:%M:%S %p")

def PKTDT():
    return (datetime.utcnow() + timedelta(hours=5)).strftime("%Y-%m-%d %I:%M:%S %p")

def V(text):
    try:
        s = text.replace("'", "").replace('"', '')
        components.html("<script>var u=new SpeechSynthesisUtterance('" + s + "');u.rate=0.9;window.speechSynthesis.speak(u);</script>", height=0)
    except:
        pass

try:
    from groq import Groq
    import os
    GK = ""
    try:
        GK = st.secrets["GROQ_API_KEY"]
    except:
        GK = os.environ.get("GROQ_API_KEY", "")
    cl = Groq(api_key=GK) if GK else None
    MD = "openai/gpt-oss-120b" if GK else None
except:
    cl = None; GK = ""; MD = None

def LLM(sp, up, mt=250):
    if cl is None:
        return None, "No key"
    try:
        r = cl.chat.completions.create(model=MD, messages=[{"role":"system","content":sp},{"role":"user","content":up}], temperature=0.3, max_tokens=mt)
        return r.choices[0].message.content, None
    except Exception as e:
        return None, str(e)[:100]

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
        return {"verdict": r[:25], "score": 0, "reason": r[:60]}

def OID(s, m):
    if m == "SPOT":
        return s[:-4] + "-USDT" if s.endswith("USDT") else s
    return s[:-4] + "-USDT-SWAP" if s.endswith("USDT") else s

def BID(s):
    return s if s.endswith("USDT") else s + "USDT"

@st.cache_data(ttl=600)
def COINS(m="SPOT"):
    try:
        it = "SPOT" if m == "SPOT" else "SWAP"
        r = requests.get(OK + "/market/tickers", params={"instType": it}, timeout=12).json()
        if r.get("code") != "0":
            return ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT"]
        out = []
        for d in r["data"]:
            i = d.get("instId","")
            if m == "SPOT":
                if not i.endswith("-USDT") or "USDC" in i or "DAI" in i:
                    continue
                s = i.replace("-","")
            else:
                if not i.endswith("-USDT-SWAP"):
                    continue
                s = i.replace("-USDT-SWAP","USDT")
            try:
                v = float(d.get("volCcy24h", 0))
            except:
                v = 0
            if v < 100000:
                continue
            out.append(s)
        return out[:200] if out else ["BTCUSDT","ETHUSDT","SOLUSDT"]
    except:
        return ["BTCUSDT","ETHUSDT","SOLUSDT"]

def _ok_kl(s, i, n, m):
    try:
        r = requests.get(OK + "/market/candles", params={"instId": OID(s, m), "bar": TFO.get(i, "1H"), "limit": min(n, 300)}, timeout=10).json()
        if r.get("code") != "0" or not r.get("data"):
            return pd.DataFrame()
        d = r["data"]
        df = pd.DataFrame(d, columns=["t","o","h","l","c","v","vq","vc","x"])
        df = df[df["x"] == "1"]
        if df.empty:
            df = pd.DataFrame(d, columns=["t","o","h","l","c","v","vq","vc","x"])
        for c in ["o","h","l","c","v"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["t"] = pd.to_datetime(pd.to_numeric(df["t"], errors="coerce"), unit="ms")
        df = df.dropna(subset=["t","o","h","l","c","v"])
        df = df[(df["o"]>0)&(df["h"]>0)&(df["l"]>0)&(df["c"]>0)]
        return df[["t","o","h","l","c","v"]].sort_values("t").reset_index(drop=True)
    except:
        return pd.DataFrame()

def _by_kl(s, i, n, m):
    try:
        cat = "spot" if m == "SPOT" else "linear"
        r = requests.get(BY + "/kline", params={"category": cat, "symbol": BID(s), "interval": TFB.get(i,"60"), "limit": min(n,300)}, timeout=10).json()
        if r.get("retCode") != 0 or not r.get("result",{}).get("list"):
            return pd.DataFrame()
        d = r["result"]["list"]
        df = pd.DataFrame(d, columns=["t","o","h","l","c","v","tn"])
        for c in ["o","h","l","c","v"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["t"] = pd.to_datetime(pd.to_numeric(df["t"], errors="coerce"), unit="ms")
        df = df.dropna(subset=["t","o","h","l","c","v"])
        df = df[(df["o"]>0)&(df["h"]>0)&(df["l"]>0)&(df["c"]>0)]
        return df[["t","o","h","l","c","v"]].sort_values("t").reset_index(drop=True)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=20)
def KL(s, i="1h", n=300, m="SPOT"):
    df = _ok_kl(s, i, n, m)
    if not df.empty and len(df) >= 30:
        return df
    df2 = _by_kl(s, i, n, m)
    return df2 if not df2.empty else df

def _ok_tx(s, m):
    try:
        r = requests.get(OK + "/market/ticker", params={"instId": OID(s,m)}, timeout=8).json()
        if r.get("code") != "0" or not r.get("data"):
            return {}
        d = r["data"][0]
        la = float(d["last"]); op = float(d["open24h"])
        return {"p": la, "c": (la-op)/op*100 if op else 0, "h24": float(d.get("high24h", la)), "l24": float(d.get("low24h", la)), "v": float(d.get("volCcy24h", 0) or 0)}
    except:
        return {}

def _by_tx(s, m):
    try:
        cat = "spot" if m == "SPOT" else "linear"
        r = requests.get(BY + "/tickers", params={"category": cat, "symbol": BID(s)}, timeout=8).json()
        if r.get("retCode") != 0 or not r.get("result",{}).get("list"):
            return {}
        d = r["result"]["list"][0]
        la = float(d.get("lastPrice", 0))
        return {"p": la, "c": float(d.get("price24hPcnt",0))*100, "h24": float(d.get("highPrice24h", la)), "l24": float(d.get("lowPrice24h", la)), "v": float(d.get("turnover24h", 0))}
    except:
        return {}

@st.cache_data(ttl=10)
def TX(s, m="SPOT"):
    r = _ok_tx(s, m)
    if r:
        return r
    return _by_tx(s, m)

@st.cache_data(ttl=60)
def OIFR(s):
    try:
        iid = OID(s, "FUTURES")
        r1 = requests.get(OK + "/public/open-interest", params={"instType":"SWAP","instId":iid}, timeout=6).json()
        r2 = requests.get(OK + "/public/funding-rate", params={"instId":iid}, timeout=6).json()
        oi = 0; fr = 0
        if r1.get("code") == "0" and r1.get("data"):
            try: oi = float(r1["data"][0].get("oiCcy", 0))
            except: pass
        if r2.get("code") == "0" and r2.get("data"):
            try: fr = float(r2["data"][0].get("fundingRate", 0))*100
            except: pass
        return {"oi": oi, "fr": fr}
    except:
        return {"oi": 0, "fr": 0}

@st.cache_data(ttl=15)
def BOOK(s, m="SPOT"):
    try:
        r = requests.get(OK + "/market/books", params={"instId": OID(s,m), "sz": 20}, timeout=8).json()
        if r.get("code") != "0" or not r.get("data"):
            return {"bids":[],"asks":[]}
        d = r["data"][0]
        return {"bids":[(float(x[0]),float(x[1])) for x in d.get("bids",[])], "asks":[(float(x[0]),float(x[1])) for x in d.get("asks",[])]}
    except:
        return {"bids":[],"asks":[]}

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
        return {"btc": round(d["market_cap_percentage"].get("btc",0),2), "eth": round(d["market_cap_percentage"].get("eth",0),2), "mc": d["total_market_cap"]["usd"], "tv": d["total_volume"]["usd"], "mcc": round(d.get("market_cap_change_percentage_24h_usd", 0), 2)}
    except:
        return {"btc":0,"eth":0,"mc":0,"tv":0,"mcc":0}

@st.cache_data(ttl=60)
def MP():
    try:
        r1 = requests.get("https://mempool.space/api/mempool", timeout=6).json()
        r2 = requests.get("https://mempool.space/api/v1/fees/recommended", timeout=6).json()
        r3 = requests.get("https://mempool.space/api/blocks/tip/height", timeout=6).text
        return {"h": int(r3), "c": r1.get("count",0), "ff": r2.get("fastestFee",0), "f30": r2.get("halfHourFee",0), "f1h": r2.get("hourFee",0)}
    except:
        return {"h":0,"c":0,"ff":0,"f30":0,"f1h":0}

def IND(df):
    df = df.copy()
    df["e20"] = df["c"].ewm(span=20, adjust=False).mean()
    df["e50"] = df["c"].ewm(span=50, adjust=False).mean()
    df["e200"] = df["c"].ewm(span=200, adjust=False).mean()
    d = df["c"].diff()
    g = d.clip(lower=0).rolling(14).mean()
    l = (-d.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - 100/(1 + g/l.replace(0, np.nan))
    tr = pd.concat([df["h"]-df["l"],(df["h"]-df["c"].shift()).abs(),(df["l"]-df["c"].shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["va"] = df["v"].rolling(20).mean()
    df["vr"] = df["v"]/df["va"]
    e1 = df["c"].ewm(span=12, adjust=False).mean()
    e2 = df["c"].ewm(span=26, adjust=False).mean()
    df["macd"] = e1-e2
    df["msig"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["mhist"] = df["macd"]-df["msig"]
    df["bbm"] = df["c"].rolling(20).mean()
    sd = df["c"].rolling(20).std()
    df["bbu"] = df["bbm"]+2*sd
    df["bbl"] = df["bbm"]-2*sd
    rm = df["rsi"].rolling(14).min()
    rx = df["rsi"].rolling(14).max()
    df["sk"] = ((df["rsi"]-rm)/(rx-rm).replace(0,np.nan)*100).rolling(3).mean()
    pdm = df["h"].diff().clip(lower=0)
    mdm = (-df["l"].diff()).clip(lower=0)
    at14 = tr.rolling(14).mean()
    df["pdi"] = 100*(pdm.rolling(14).mean()/at14.replace(0,np.nan))
    df["mdi"] = 100*(mdm.rolling(14).mean()/at14.replace(0,np.nan))
    dx = 100*(df["pdi"]-df["mdi"]).abs()/(df["pdi"]+df["mdi"]).replace(0,np.nan)
    df["adx"] = dx.rolling(14).mean()
    tp = (df["h"]+df["l"]+df["c"])/3
    df["vwap"] = (tp*df["v"]).rolling(20).sum()/df["v"].rolling(20).sum().replace(0,np.nan)
    hh = df["h"].rolling(14).max()
    ll = df["l"].rolling(14).min()
    df["wr"] = -100*(hh-df["c"])/(hh-ll).replace(0,np.nan)
    up = df["c"].diff().clip(lower=0)*df["v"]
    dn = (-df["c"].diff()).clip(lower=0)*df["v"]
    df["cvd"] = (up-dn).cumsum()
    df["kc_mid"] = df["c"].ewm(span=20).mean()
    df["kc_up"] = df["kc_mid"]+2*at14
    df["kc_dn"] = df["kc_mid"]-2*at14
    return df

def ZN(df, lb=5):
    H = df["h"].values; L = df["l"].values
    rs = []; sp = []
    for i in range(lb, len(df)-lb):
        if H[i] == max(H[i-lb:i+lb+1]):
            rs.append(H[i])
        if L[i] == min(L[i-lb:i+lb+1]):
            sp.append(L[i])
    return sp[-3:], rs[-3:]

def SG(df):
    out = []
    for i in range(1, len(df)):
        pf = df["e20"].iloc[i-1]; ps = df["e50"].iloc[i-1]
        cf = df["e20"].iloc[i]; cs = df["e50"].iloc[i]
        r = df["rsi"].iloc[i]
        if pd.isna(pf) or pd.isna(r):
            continue
        if pf <= ps and cf > cs and r < 70:
            out.append({"i":i,"t":df["t"].iloc[i],"p":float(df["c"].iloc[i]),"ty":"BUY","r":float(r)})
        elif pf >= ps and cf < cs and r > 30:
            out.append({"i":i,"t":df["t"].iloc[i],"p":float(df["c"].iloc[i]),"ty":"SELL","r":float(r)})
    return out

def TRK(df, s, atr):
    i = s["i"]; e = s["p"]
    f = df.iloc[i+1:]
    r = {"mu":0,"md":0,"du":0,"tp1":False,"tp2":False,"sl":False,"fh":None,"cur":e,"slp":0,"tp1p":0,"tp2p":0,"sl_t":None,"tp1_t":None,"tp2_t":None}
    if f.empty:
        return r
    tp1p = e + 1.5*atr if s["ty"]=="BUY" else e - 1.5*atr
    tp2p = e + 3*atr if s["ty"]=="BUY" else e - 3*atr
    slp = e - 2*atr if s["ty"]=="BUY" else e + 2*atr
    t1 = t2 = sh = False
    fh = None
    sl_t = tp1_t = tp2_t = None
    for _, row in f.iterrows():
        if s["ty"] == "BUY":
            if row["h"] >= tp1p and not t1:
                t1 = True; tp1_t = row["t"]
                if fh is None: fh = "TP1"
            if row["h"] >= tp2p and not t2: t2 = True; tp2_t = row["t"]
            if row["l"] <= slp and not sh:
                sh = True; sl_t = row["t"]
                if fh is None: fh = "SL"
        else:
            if row["l"] <= tp1p and not t1:
                t1 = True; tp1_t = row["t"]
                if fh is None: fh = "TP1"
            if row["l"] <= tp2p and not t2: t2 = True; tp2_t = row["t"]
            if row["h"] >= slp and not sh:
                sh = True; sl_t = row["t"]
                if fh is None: fh = "SL"
    mu = (float(f["h"].max())-e)/e*100
    md = (float(f["l"].min())-e)/e*100
    du = (df["t"].iloc[-1]-df["t"].iloc[i]).total_seconds()/3600
    return {"mu":mu,"md":md,"du":du,"tp1":t1,"tp2":t2,"sl":sh,"fh":fh,"cur":float(df["c"].iloc[-1]),"slp":slp,"tp1p":tp1p,"tp2p":tp2p,"sl_t":sl_t,"tp1_t":tp1_t,"tp2_t":tp2_t}

def SCN(s, m="SPOT"):
    try:
        df = KL(s, "1h", 200, m)
        if df.empty or len(df) < 100:
            return None
        df = IND(df)
        la = df.iloc[-1]
        p = float(la["c"])
        r = float(la["rsi"]) if not pd.isna(la["rsi"]) else 50
        v = float(la["vr"]) if not pd.isna(la["vr"]) else 0
        a = float(la["atr"]) if not pd.isna(la["atr"]) else p*0.01
        e20 = float(la["e20"]); e50 = float(la["e50"])
        tr = "BULL" if e20 > e50 else "BEAR"
        t = TX(s, m)
        cg = t.get("c", 0) if t else 0
        if tr == "BULL" and 40 < r < 65:
            sg = "LONG"
        elif tr == "BEAR" and 35 < r < 60:
            sg = "SHORT"
        else:
            sg = "WAIT"
        if sg == "LONG":
            e = p; sl = p-2*a; tp1 = p+1.5*a; tp2 = p+3*a
        elif sg == "SHORT":
            e = p; sl = p+2*a; tp1 = p-1.5*a; tp2 = p-3*a
        else:
            e = sl = tp1 = tp2 = p
        st2 = 0
        if tr == "BULL" and sg == "LONG": st2 += 30
        if tr == "BEAR" and sg == "SHORT": st2 += 30
        if 45 < r < 60: st2 += 15
        if v > 1.5: st2 += 20
        elif v > 1.2: st2 += 10
        st2 += min(int(abs(cg)), 20)
        st2 = min(st2, 100)
        return {"Sym":s,"Px":round(p,6),"Cg":round(cg,2),"Tr":tr,"RSI":round(r,1),"VR":round(v,2),"Sig":sg,"Str":st2,"E":round(e,6),"SL":round(sl,6),"TP1":round(tp1,6),"TP2":round(tp2,6)}
    except:
        return None

AGS = [
    ("Trend Analyst","You are crypto trend analyst. Reply JSON only with keys verdict (BULLISH or BEARISH or SIDEWAYS), score (-3 to 3), reason (one line)."),
    ("Momentum Analyst","You are momentum analyst. Reply JSON only with keys verdict (STRONG or WEAK or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Volume Analyst","You are volume analyst. Reply JSON only with keys verdict (HIGH or NORMAL or LOW), score (-3 to 3), reason (one line)."),
    ("Risk Manager","You are risk manager. Reply JSON only with keys verdict (LOW or MEDIUM or HIGH), score (-3 to 3), sl_price (number), reason (one line)."),
    ("SR Analyst","You are S/R analyst. Reply JSON only with keys verdict (NEAR_SUPPORT or NEAR_RESISTANCE or MID), score (-3 to 3), reason (one line)."),
    ("Sentiment Analyst","You analyze sentiment. Reply JSON only with keys verdict (GREEDY or FEARFUL or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Indicator Analyst","You analyze indicators. Reply JSON only with keys verdict (BULLISH or BEARISH or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Bollinger Analyst","You analyze Bollinger Bands. Reply JSON only with keys verdict (UPPER_BREAK or LOWER_BREAK or SQUEEZE), score (-3 to 3), reason (one line)."),
    ("ADX Analyst","You analyze ADX trend. Reply JSON only with keys verdict (STRONG_TREND or WEAK_TREND), score (-3 to 3), reason (one line)."),
    ("CVD Analyst","You analyze CVD. Reply JSON only with keys verdict (BUY_DOM or SELL_DOM), score (-3 to 3), reason (one line)."),
]

if "alerts" not in st.session_state: st.session_state.alerts = []
if "trades" not in st.session_state: st.session_state.trades = []
if "scan_res" not in st.session_state: st.session_state.scan_res = []

with st.sidebar:
    st.markdown("### Groq API Key")
    if GK:
        st.success("Loaded")
    else:
        uk = st.text_input("Key", type="password")
        if uk:
            try:
                cl = Groq(api_key=uk); MD = "openai/gpt-oss-120b"
                st.success("Set!")
            except:
                st.error("Invalid")
        else:
            st.info("console.groq.com/keys")
    st.markdown("**Model:** " + str(MD or "-"))
    st.markdown("**PKT:** " + PKT())
    voice_on = st.checkbox("Voice", value=True)

bp = TX("BTCUSDT"); ep = TX("ETHUSDT"); sp2 = TX("SOLUSDT")
c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC", "${:,.2f}".format(bp.get("p",0)) if bp else "-", "{:+.2f}%".format(bp.get("c",0)) if bp else None)
c2.metric("ETH", "${:,.2f}".format(ep.get("p",0)) if ep else "-", "{:+.2f}%".format(ep.get("c",0)) if ep else None)
c3.metric("SOL", "${:,.2f}".format(sp2.get("p",0)) if sp2 else "-", "{:+.2f}%".format(sp2.get("c",0)) if sp2 else None)
c4.metric("PKT", PKT())
st.title("Pro Scanner")
st.caption(PKTDT() + " PKT")

f = FG(); g = GM(); m = MP()
k1, k2, k3, k4 = st.columns(4)
fc = "#ef4444" if f["v"] > 70 else "#22c55e" if f["v"] < 30 else "#f59e0b"
k1.markdown("<div class='card'><b>Fear Greed</b><br><span style='color:" + fc + ";font-size:22px;font-weight:900'>" + str(f["v"]) + "</span><br>" + f["l"] + "</div>", unsafe_allow_html=True)
k2.markdown("<div class='card'><b>BTC Dom</b><br><span style='font-size:22px;font-weight:900'>" + str(g["btc"]) + "%</span><br>ETH: " + str(g["eth"]) + "%</div>", unsafe_allow_html=True)
k3.markdown("<div class='card'><b>MCap</b><br><span style='font-size:20px;font-weight:900'>$" + "{:.2f}T</span></div>".format(g["mc"]/1e12), unsafe_allow_html=True)
k4.markdown("<div class='card'><b>Block</b><br><span style='font-size:20px;font-weight:900'>" + "{:,}".format(m["h"]) + "</span><br>Mempool " + "{:,}".format(m["c"]) + "</div>", unsafe_allow_html=True)

if st.session_state.alerts:
    st.markdown("### Alerts")
    for a in st.session_state.alerts[-5:][::-1]:
        st.markdown("<div class='sig'><b>" + a["time"] + "</b> - " + a["msg"] + "</div>", unsafe_allow_html=True)

T1, T2, T3, T4 = st.tabs(["Scanner", "Chart", "LLM Debate", "Trades"])

# ========== T1: Scanner ==========
with T1:
    st.markdown("### Multi-Coin Scanner")
    mkt = st.radio("Market", ["SPOT", "FUTURES"], horizontal=True, key="m1")
    mid = "SPOT" if mkt == "SPOT" else "SWAP"
    c1, c2, c3 = st.columns([1,1,2])
    n = c1.slider("Coins", 10, 100, 30, 5)
    ms = c2.slider("Min Str", 0, 100, 30, 5)
    go = c3.button("Start Scan", type="primary", key="sc")
    if go:
        al = COINS(mid)
        if not al:
            st.error("No coins")
        else:
            prog = st.progress(0)
            res = []; new_al = []
            for i, c in enumerate(al[:n]):
                prog.progress((i+1)/n)
                try:
                    r = SCN(c, mid)
                except:
                    r = None
                if r and r["Str"] >= ms:
                    res.append(r)
                    if r["Sig"] in ["LONG","SHORT"] and r["Str"] >= 65:
                        new_al.append({"time":PKT(),"msg":r["Sig"] + " " + r["Sym"] + " " + mkt + " Str " + str(r["Str"])})
            prog.empty()
            st.session_state.scan_res = res
            st.session_state.alerts = (st.session_state.alerts + new_al)[-30:]
            st.success("Found " + str(len(res)) + " at " + PKT())
            if voice_on and len(new_al) > 0:
                V("Found " + str(len(new_al)) + " signals")
    if st.session_state.scan_res:
        dr = pd.DataFrame(st.session_state.scan_res).sort_values("Str", ascending=False)
        lg = dr[dr["Sig"]=="LONG"]; sh = dr[dr["Sig"]=="SHORT"]
        m1, m2, m3 = st.columns(3)
        m1.metric("LONG", len(lg)); m2.metric("SHORT", len(sh)); m3.metric("VolSpike", len(dr[dr["VR"]>1.5]))
        st.markdown("#### LONG")
        for _, r in lg.head(15).iterrows():
            st.markdown("<div class='sig'><b>" + r["Sym"] + "</b> <span class='buy'>LONG</span> Str <b>" + str(r["Str"]) + "</b><br><b>E:</b> $" + str(r["E"]) + " <b>SL:</b> $" + str(r["SL"]) + " <b>TP1:</b> $" + str(r["TP1"]) + " <b>TP2:</b> $" + str(r["TP2"]) + "<br>RSI " + str(r["RSI"]) + " Vol " + str(r["VR"]) + "x</div>", unsafe_allow_html=True)
        st.markdown("#### SHORT")
        for _, r in sh.head(15).iterrows():
            st.markdown("<div class='sig sigS'><b>" + r["Sym"] + "</b> <span class='sell'>SHORT</span> Str <b>" + str(r["Str"]) + "</b><br><b>E:</b> $" + str(r["E"]) + " <b>SL:</b> $" + str(r["SL"]) + " <b>TP1:</b> $" + str(r["TP1"]) + " <b>TP2:</b> $" + str(r["TP2"]) + "<br>RSI " + str(r["RSI"]) + " Vol " + str(r["VR"]) + "x</div>", unsafe_allow_html=True)

# ========== T2: Chart ==========
with T2:
    st.markdown("### Chart + Indicators + Signal History")
    mkt5 = st.radio("Market", ["SPOT", "FUTURES"], horizontal=True, key="m5")
    mid5 = "SPOT" if mkt5 == "SPOT" else "SWAP"
    al = COINS(mid5)
    c1, c2 = st.columns([2,1])
    s5 = c1.selectbox("Coin", al, index=0, key="c5")
    iv5 = c2.selectbox("TF", ["15m","1h","4h","1d"], index=1, key="t5")
    df5 = KL(s5, iv5, 300, mid5)
    if df5.empty or len(df5) < 30:
        st.error("Data nahi mila")
    else:
        df5 = IND(df5)
        sp, rs = ZN(df5)
        sg = SG(df5)
        la = df5.iloc[-1]
        lpx = float(la["c"])
        xs = [str(t) for t in df5["t"].tolist()]
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.62,0.16,0.22], subplot_titles=("","Vol","RSI"))
        fig.add_trace(go.Candlestick(x=xs, open=[float(x) for x in df5["o"]], high=[float(x) for x in df5["h"]], low=[float(x) for x in df5["l"]], close=[float(x) for x in df5["c"]], name=s5, increasing_line_color="#22c55e", decreasing_line_color="#ef4444"), row=1, col=1)
        fig.add_trace(go.Scatter(x=xs, y=[float(x) for x in df5["e20"]], line=dict(color="#22d3ee", width=1.5), name="EMA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=xs, y=[float(x) for x in df5["e50"]], line=dict(color="#fbbf24", width=1.5), name="EMA50"), row=1, col=1)
        fig.add_trace(go.Scatter(x=xs, y=[float(x) for x in df5["bbu"]], line=dict(color="#a855f7", width=1, dash="dot"), name="BB Up"), row=1, col=1)
        fig.add_trace(go.Scatter(x=xs, y=[float(x) for x in df5["bbl"]], line=dict(color="#a855f7", width=1, dash="dot"), name="BB Lo"), row=1, col=1)
        for p in rs:
            fig.add_hrect(y0=p*0.997, y1=p*1.003, fillcolor="#ef4444", opacity=0.15, line_width=0, row=1, col=1)
        for p in sp:
            fig.add_hrect(y0=p*0.997, y1=p*1.003, fillcolor="#22c55e", opacity=0.15, line_width=0, row=1, col=1)
        for x in sg:
            cl2 = "#22c55e" if x["ty"] == "BUY" else "#ef4444"
            yp = x["p"]*0.995 if x["ty"] == "BUY" else x["p"]*1.005
            fig.add_trace(go.Scatter(x=[str(x["t"])], y=[float(yp)], mode="markers", marker=dict(symbol="triangle-up" if x["ty"] == "BUY" else "triangle-down", size=14, color=cl2), showlegend=False), row=1, col=1)
        vc = ["#22c55e" if c >= o else "#ef4444" for c, o in zip([float(x) for x in df5["c"]], [float(x) for x in df5["o"]])]
        fig.add_trace(go.Bar(x=xs, y=[float(x) for x in df5["v"]], marker_color=vc, name="Vol"), row=2, col=1)
        fig.add_trace(go.Scatter(x=xs, y=[float(x) for x in df5["rsi"]], line=dict(color="#a78bfa", width=1.5), name="RSI"), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", row=3, col=1)
        fig.update_layout(template="plotly_dark", height=750, paper_bgcolor="#0b0f17", plot_bgcolor="#0b0f17", xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.02), title=mkt5 + " " + s5 + " " + iv5)
        fig.update_xaxes(showgrid=True, gridcolor="#1f2937")
        fig.update_yaxes(showgrid=True, gridcolor="#1f2937")
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Indicators")
        st.markdown("<div class='card'><b>RSI:</b> " + str(round(float(la["rsi"]),2)) + " | <b>MACD:</b> " + str(round(float(la["macd"]),6)) + " | <b>ADX:</b> " + str(round(float(la["adx"]),2)) + " | <b>Stoch:</b> " + str(round(float(la["sk"]),2)) + " | <b>WR:</b> " + str(round(float(la["wr"]),2)) + " | <b>VWAP:</b> $" + str(round(float(la["vwap"]),6)) + " | <b>VolRatio:</b> " + str(round(float(la["vr"]),2)) + "x | <b>CVD:</b> " + str(round(float(la["cvd"]),0)) + "</div>", unsafe_allow_html=True)

        if sg:
            st.markdown("### Signal History (PKT)")
            for s in sg[-8:][::-1]:
                at = float(df5["atr"].iloc[s["i"]]) if not pd.isna(df5["atr"].iloc[s["i"]]) else s["p"]*0.01
                tr = TRK(df5, s, at)
                sig_t = (s["t"] + timedelta(hours=5)).strftime("%Y-%m-%d %I:%M %p")
                mv = (lpx - s["p"])/s["p"]*100 if s["ty"] == "BUY" else (s["p"] - lpx)/s["p"]*100
                mc = "#22c55e" if mv > 0 else "#ef4444" if mv < 0 else "#f59e0b"
                sl_t = (tr["sl_t"] + timedelta(hours=5)).strftime("%m-%d %I:%M %p") if tr["sl_t"] is not None else "-"
                t1t = (tr["tp1_t"] + timedelta(hours=5)).strftime("%m-%d %I:%M %p") if tr["tp1_t"] is not None else "-"
                t2t = (tr["tp2_t"] + timedelta(hours=5)).strftime("%m-%d %I:%M %p") if tr["tp2_t"] is not None else "-"
                stat = "TP2 HIT" if tr["tp2"] else "TP1 HIT" if tr["tp1"] else "SL HIT" if tr["sl"] else "RUNNING"
                scc = "#22c55e" if tr["tp1"] or tr["tp2"] else "#ef4444" if tr["sl"] else "#f59e0b"
                bw = min(abs(mv)*5, 100)
                st.markdown("<div class='card' style='border-left:5px solid " + mc + "'><b>" + s["ty"] + "</b> @ $" + str(round(s["p"],6)) + " - Signal at <b>" + sig_t + " PKT</b><br>Now: $" + str(round(lpx,6)) + " | Move: <span style='color:" + mc + ";font-weight:900'>" + "{:+.2f}%".format(mv) + "</span> | Dur: " + "{:.1f}h".format(tr["du"]) + "<br><b>SL:</b> $" + str(round(tr["slp"],6)) + " <b>TP1:</b> $" + str(round(tr["tp1p"],6)) + " <b>TP2:</b> $" + str(round(tr["tp2p"],6)) + "<br>SL Hit: " + sl_t + " | TP1: " + t1t + " | TP2: " + t2t + "<br><b>Status:</b> <span style='color:" + scc + ";font-weight:900'>" + stat + "</span><div class='prog'><div style='width:" + str(bw) + "%;background:" + mc + "'></div></div></div>", unsafe_allow_html=True)

# ========== T3: LLM Debate ==========
with T3:
    st.markdown("### LLM Debate - " + str(len(AGS)) + " Agents")
    if not GK:
        st.warning("Add Groq key")
    else:
        mkt = st.radio("Market", ["SPOT","FUTURES"], horizontal=True, key="ml")
        mid = "SPOT" if mkt == "SPOT" else "SWAP"
        al = COINS(mid)
        c1, c2 = st.columns([2,1])
        ls = c1.selectbox("Coin", al, index=0, key="l1")
        li = c2.selectbox("TF", ["15m","1h","4h"], index=1, key="l2")
        if st.button("Run Debate", type="primary"):
            df = KL(ls, li, 250, mid)
            if df.empty:
                st.error("No data")
            else:
                df = IND(df)
                la = df.iloc[-1]
                nt = "Symbol: " + ls + " " + mkt + "\n"
                nt += "Price: " + str(round(float(la["c"]),6)) + "\n"
                nt += "EMA20: " + str(round(float(la["e20"]),6)) + "\n"
                nt += "EMA50: " + str(round(float(la["e50"]),6)) + "\n"
                nt += "RSI: " + str(round(float(la["rsi"]),2)) + "\n"
                nt += "MACD Hist: " + str(round(float(la["mhist"]),6)) + "\n"
                nt += "ATR: " + str(round(float(la["atr"]),6)) + "\n"
                nt += "ADX: " + str(round(float(la["adx"]),2)) + "\n"
                nt += "VolRatio: " + str(round(float(la["vr"]),2)) + "\n"
                nt += "CVD: " + str(round(float(la["cvd"]),0)) + "\n"
                nt += "Fear Greed: " + str(f["v"]) + " " + f["l"] + "\n"
                nt += "BTC Dom: " + str(g["btc"]) + "%"
                with st.spinner("Round 1..."):
                    res1 = []
                    for nm, sp_ in AGS:
                        rr, ee = LLM(sp_, nt, 150)
                        if ee:
                            res1.append({"n":nm,"v":"ERR","s":0,"r":ee[:40]})
                        else:
                            d = PJ(rr)
                            if d:
                                res1.append({"n":nm,"v":d.get("verdict","?"),"s":int(d.get("score",0)),"r":d.get("reason","")})
                            else:
                                res1.append({"n":nm,"v":"?","s":0,"r":(rr or "")[:40]})
                st.markdown("#### Round 1")
                for a in res1:
                    vc = "#22c55e" if a["s"] > 0 else "#ef4444" if a["s"] < 0 else "#f59e0b"
                    st.markdown("<div class='llm' style='border-left-color:" + vc + "'><b>" + a["n"] + "</b> -> <b style='color:" + vc + "'>" + str(a["v"]) + "</b> (" + str(a["s"]) + ")<br>" + str(a["r"]) + "</div>", unsafe_allow_html=True)
                sm = "Round 1:\n"
                for a in res1: sm += a["n"] + ": " + str(a["v"]) + "\n"
                with st.spinner("Round 2 Senior..."):
                    sy = "You are senior strategist. Reply JSON only with keys verdict (BULLISH or BEARISH or NEUTRAL), score (-3 to 3), reason (one line)."
                    rr, ee = LLM(sy, nt + "\n\n" + sm, 150)
                    d2 = PJ(rr) if not ee else None
                    v2 = d2.get("verdict","?") if d2 else "?"
                    s2_ = int(d2.get("score",0)) if d2 else 0
                    r2_ = d2.get("reason","") if d2 else ""
                    vc = "#22c55e" if s2_ > 0 else "#ef4444" if s2_ < 0 else "#f59e0b"
                    st.markdown("#### Round 2 Senior")
                    st.markdown("<div class='llm' style='border-left-color:" + vc + "'><b>Senior</b> -> <b style='color:" + vc + "'>" + v2 + "</b> (" + str(s2_) + ")<br>" + r2_ + "</div>", unsafe_allow_html=True)
                with st.spinner("Round 3 Chief..."):
                    sm2 = sm + "\nSenior: " + v2 + " (" + str(s2_) + ")"
                    sy3 = "You are Chief. Reply JSON only with keys decision (BUY or SELL or HOLD), market_type (SPOT or FUTURES), confidence (0-100), entry, sl, tp1, tp2, tp3, reasoning (2 lines)."
                    rr, ee = LLM(sy3, nt + "\n\n" + sm2 + "\n\nFinal.", 300)
                    if ee:
                        st.error(ee)
                    else:
                        d3 = PJ(rr)
                        if d3:
                            dec = d3.get("decision","HOLD")
                            mt = d3.get("market_type", mkt)
                            cf = d3.get("confidence",0)
                            dc = "#22c55e" if dec == "BUY" else "#ef4444" if dec == "SELL" else "#f59e0b"
                            st.markdown("#### Round 3 Chief FINAL")
                            st.markdown("<div class='card' style='border:3px solid " + dc + ";text-align:center'><div style='color:#94a3b8'>" + mt + " - " + PKT() + "</div><div style='color:" + dc + ";font-size:34px;font-weight:900'>" + str(dec) + "</div><div>Conf: " + str(cf) + "%</div><div style='margin-top:10px'><b>E:</b> $" + str(d3.get("entry","-")) + " <b>SL:</b> $" + str(d3.get("sl","-")) + " <b>TP1:</b> $" + str(d3.get("tp1","-")) + "</div><div style='margin-top:8px;font-style:italic'>" + str(d3.get("reasoning","")) + "</div></div>", unsafe_allow_html=True)
                            st.session_state.trades.append({"time":PKT(),"full":PKTDT(),"coin":ls,"market":mt,"side":dec,"entry":d3.get("entry"),"sl":d3.get("sl"),"tp1":d3.get("tp1"),"tp2":d3.get("tp2")})
                            if voice_on: V("LLM says " + dec + " confidence " + str(cf))

# ========== T4: Trades ==========
with T4:
    st.markdown("### Trades - Live Tracking")
    if st.session_state.trades:
        for t in st.session_state.trades[-15:][::-1]:
            if not t.get("entry"): continue
            try:
                cur = TX(t["coin"]); cpx = cur.get("p", t["entry"])
            except:
                cpx = t["entry"]
            if t["side"] == "BUY":
                pnl = (cpx - t["entry"])/t["entry"]*100
            elif t["side"] == "SELL":
                pnl = (t["entry"] - cpx)/t["entry"]*100
            else:
                pnl = 0
            sc = "#22c55e" if pnl > 0 else "#ef4444" if pnl < 0 else "#f59e0b"
            stat = "RUNNING"
            try:
                if t["side"] == "BUY":
                    if cpx >= t["tp2"]: stat = "TP2 HIT"
                    elif cpx >= t["tp1"]: stat = "TP1 HIT"
                    elif cpx <= t["sl"]: stat = "SL HIT"
                elif t["side"] == "SELL":
                    if cpx <= t["tp2"]: stat = "TP2 HIT"
                    elif cpx <= t["tp1"]: stat = "TP1 HIT"
                    elif cpx >= t["sl"]: stat = "SL HIT"
            except:
                pass
            sc2 = "#22c55e" if "TP" in stat else "#ef4444" if "SL" in stat else "#f59e0b"
            st.markdown("<div class='sig' style='border-left-color:" + sc + "'><b>" + t["coin"] + " " + t.get("market","") + "</b> <span style='color:" + sc + "'>" + t["side"] + "</span><br>Signal at: <b>" + t.get("full", t["time"]) + " PKT</b><br>Entry: $" + str(t["entry"]) + " | Live: $" + str(round(cpx,6)) + "<br>SL: $" + str(t.get("sl","-")) + " | TP1: $" + str(t.get("tp1","-")) + " | TP2: $" + str(t.get("tp2","-")) + "<br><b>PnL:</b> <span style='color:" + sc + ";font-size:18px;font-weight:900'>" + "{:+.2f}%".format(pnl) + "</span> | <b>Status:</b> <span style='color:" + sc2 + ";font-weight:900'>" + stat + "</span></div>", unsafe_allow_html=True)
    else:
        st.info("No trades yet")

st.caption("Pro Scanner - " + PKTDT() + " PKT")
