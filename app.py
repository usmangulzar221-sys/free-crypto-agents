import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time, os, json

st.set_page_config(page_title="Pro Scanner", layout="wide")
st.markdown("<style>.stApp{background:#0b0f17;color:#e5e7eb}.card{background:#111827;border-radius:12px;padding:14px;border:1px solid #1f2937;margin:8px 0}.buy{color:#22c55e;font-weight:800}.sell{color:#ef4444;font-weight:800}.llm{background:#1e1b4b;border-radius:10px;padding:12px;margin:8px 0;border-left:4px solid #a855f7}</style>", unsafe_allow_html=True)

try:
    from groq import Groq
    GA = True
except:
    GA = False

def gk():
    try:
        return st.secrets["GROQ_API_KEY"]
    except:
        return os.environ.get("GROQ_API_KEY", "")

GK = gk()
cl = None
MD = None
if GA and GK:
    try:
        cl = Groq(api_key=GK)
        MD = "openai/gpt-oss-120b"
    except:
        cl = None

def llm(sys_p, usr_p):
    if cl is None:
        return None, "No key"
    try:
        r = cl.chat.completions.create(model=MD, messages=[{"role":"system","content":sys_p},{"role":"user","content":usr_p}], temperature=0.3, max_tokens=400)
        return r.choices[0].message.content, None
    except Exception as e:
        return None, str(e)[:150]

def pj(resp):
    if not resp:
        return None
    try:
        t = resp.strip()
        if "```" in t:
            p = t.split("```")
            if len(p) >= 2:
                t = p[1].replace("json", "").strip()
        return json.loads(t)
    except:
        return {"verdict": resp[:30], "score": 0, "reason": resp[:80]}

OK = "https://www.okx.com/api/v5"
TF = {"15m":"15m","1h":"1H","4h":"4H","1d":"1D"}

@st.cache_data(ttl=3600)
def coins():
    try:
        r = requests.get(OK + "/market/tickers", params={"instType":"SPOT"}, timeout=12).json()
        if r.get("code") != "0":
            return []
        out = []
        for d in r["data"]:
            i = d.get("instId","")
            if not i.endswith("-USDT") or "USDC" in i or "DAI" in i:
                continue
            try:
                v = float(d.get("volCcy24h", 0))
            except:
                v = 0
            if v < 50000:
                continue
            out.append({"s": i.replace("-",""), "v": v})
        out.sort(key=lambda x: x["v"], reverse=True)
        return out[:800]
    except:
        return []

@st.cache_data(ttl=20)
def kl(sym, itv="1h", lim=300):
    try:
        iid = sym[:-4] + "-USDT" if sym.endswith("USDT") else sym
        r = requests.get(OK + "/market/candles", params={"instId": iid, "bar": TF.get(itv,"1H"), "limit": min(lim,300)}, timeout=10).json()
        if r.get("code") != "0" or not r.get("data"):
            return pd.DataFrame()
        d = r["data"]
        df = pd.DataFrame(d, columns=["t","o","h","l","c","v","vq","vc","x"])
        for c in ["o","h","l","c","v"]:
            df[c] = df[c].astype(float)
        df["t"] = pd.to_datetime(df["t"].astype(float), unit="ms")
        return df[["t","o","h","l","c","v"]].sort_values("t").reset_index(drop=True)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=15)
def tk(sym):
    try:
        iid = sym[:-4] + "-USDT" if sym.endswith("USDT") else sym
        r = requests.get(OK + "/market/ticker", params={"instId": iid}, timeout=8).json()
        if r.get("code") != "0" or not r.get("data"):
            return {}
        d = r["data"][0]
        la = float(d["last"])
        op = float(d["open24h"])
        cg = (la-op)/op*100 if op else 0
        try:
            vl = float(d.get("volCcy24h", 0))
        except:
            vl = 0
        return {"p": la, "c": cg, "v": vl}
    except:
        return {}

@st.cache_data(ttl=300)
def fg():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6).json()
        d = r["data"][0]
        return {"v": int(d["value"]), "l": d["value_classification"]}
    except:
        return {"v": 50, "l": "Neutral"}

@st.cache_data(ttl=300)
def gm():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=8).json()
        d = r["data"]
        return {"btc": round(d["market_cap_percentage"].get("btc",0),2), "eth": round(d["market_cap_percentage"].get("eth",0),2), "mc": d["total_market_cap"]["usd"], "tv": d["total_volume"]["usd"]}
    except:
        return {"btc":0,"eth":0,"mc":0,"tv":0}

@st.cache_data(ttl=60)
def mp():
    try:
        r1 = requests.get("https://mempool.space/api/mempool", timeout=6).json()
        r2 = requests.get("https://mempool.space/api/v1/fees/recommended", timeout=6).json()
        r3 = requests.get("https://mempool.space/api/blocks/tip/height", timeout=6).text
        return {"h": int(r3), "c": r1.get("count",0), "ff": r2.get("fastestFee",0), "f30": r2.get("halfHourFee",0), "f1h": r2.get("hourFee",0)}
    except:
        return {"h":0,"c":0,"ff":0,"f30":0,"f1h":0}

def ind(df):
    df = df.copy()
    df["e20"] = df["c"].ewm(span=20, adjust=False).mean()
    df["e50"] = df["c"].ewm(span=50, adjust=False).mean()
    df["e200"] = df["c"].ewm(span=200, adjust=False).mean()
    d = df["c"].diff()
    g = d.clip(lower=0).rolling(14).mean()
    l = (-d.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - 100/(1 + g/l.replace(0, np.nan))
    tr = pd.concat([df["h"]-df["l"], (df["h"]-df["c"].shift()).abs(), (df["l"]-df["c"].shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["va"] = df["v"].rolling(20).mean()
    df["vr"] = df["v"]/df["va"]
    e1 = df["c"].ewm(span=12, adjust=False).mean()
    e2 = df["c"].ewm(span=26, adjust=False).mean()
    df["macd"] = e1-e2
    df["msig"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["bbm"] = df["c"].rolling(20).mean()
    sd = df["c"].rolling(20).std()
    df["bbu"] = df["bbm"]+2*sd
    df["bbl"] = df["bbm"]-2*sd
    return df

def zones(df, lb=5):
    H = df["h"].values
    L = df["l"].values
    rs = []
    sp = []
    for i in range(lb, len(df)-lb):
        if H[i] == max(H[i-lb:i+lb+1]):
            rs.append(H[i])
        if L[i] == min(L[i-lb:i+lb+1]):
            sp.append(L[i])
    return sp[-3:], rs[-3:]

def sigs(df):
    out = []
    for i in range(1, len(df)):
        pf = df["e20"].iloc[i-1]
        ps = df["e50"].iloc[i-1]
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

def trk(df, s, atr):
    i = s["i"]
    e = s["p"]
    f = df.iloc[i+1:]
    if f.empty:
        return {"mu":0,"md":0,"du":0,"tp1":False,"tp2":False,"sl":False,"fh":None,"cur":e}
    tp1p = e + 1.5*atr if s["ty"] == "BUY" else e - 1.5*atr
    tp2p = e + 3*atr if s["ty"] == "BUY" else e - 3*atr
    slp = e - 2*atr if s["ty"] == "BUY" else e + 2*atr
    t1 = t2 = sh = False
    fh = None
    for _, row in f.iterrows():
        if s["ty"] == "BUY":
            if row["h"] >= tp1p and not t1:
                t1 = True
                if fh is None:
                    fh = "TP1"
            if row["h"] >= tp2p and not t2:
                t2 = True
            if row["l"] <= slp and not sh:
                sh = True
                if fh is None:
                    fh = "SL"
        else:
            if row["l"] <= tp1p and not t1:
                t1 = True
                if fh is None:
                    fh = "TP1"
            if row["l"] <= tp2p and not t2:
                t2 = True
            if row["h"] >= slp and not sh:
                sh = True
                if fh is None:
                    fh = "SL"
    mu = (float(f["h"].max())-e)/e*100
    md = (float(f["l"].min())-e)/e*100
    du = (df["t"].iloc[-1]-df["t"].iloc[i]).total_seconds()/3600
    return {"mu":mu,"md":md,"du":du,"tp1":t1,"tp2":t2,"sl":sh,"fh":fh,"cur":float(df["c"].iloc[-1]),"tp1p":tp1p,"tp2p":tp2p,"slp":slp}

def scn(sym):
    try:
        df = kl(sym, "1h", 200)
        if df.empty or len(df) < 100:
            return None
        df = ind(df)
        la = df.iloc[-1]
        p = float(la["c"])
        r = float(la["rsi"]) if not pd.isna(la["rsi"]) else 50
        v = float(la["vr"]) if not pd.isna(la["vr"]) else 0
        a = float(la["atr"]) if not pd.isna(la["atr"]) else p*0.01
        e20 = float(la["e20"])
        e50 = float(la["e50"])
        tr = "BULL" if e20 > e50 else "BEAR"
        t = tk(sym)
        cg = t.get("c", 0) if t else 0
        vl = t.get("v", 0) if t else 0
        if tr == "BULL" and 40 < r < 65:
            s = "LONG"
        elif tr == "BEAR" and 35 < r < 60:
            s = "SHORT"
        else:
            s = "WAIT"
        if s == "LONG":
            e = p
            sl = p - 2*a
            tp1 = p + 1.5*a
            tp2 = p + 3*a
        elif s == "SHORT":
            e = p
            sl = p + 2*a
            tp1 = p - 1.5*a
            tp2 = p - 3*a
        else:
            e = sl = tp1 = tp2 = p
        st = 0
        if tr == "BULL" and s == "LONG":
            st += 30
        if tr == "BEAR" and s == "SHORT":
            st += 30
        if 45 < r < 60:
            st += 15
        if v > 1.5:
            st += 20
        elif v > 1.2:
            st += 10
        st += min(int(abs(cg)), 20)
        st = min(st, 100)
        return {"Sym":sym,"Px":round(p,6),"Cg":round(cg,2),"Vm":round(vl/1e6,1),"Tr":tr,"RSI":round(r,1),"VR":round(v,2),"Sig":s,"Str":st,"E":round(e,6),"SL":round(sl,6),"TP1":round(tp1,6),"TP2":round(tp2,6)}
    except:
        return None

AG = [
    ("Trend Analyst", "You are a crypto trend analyst. Reply JSON only with keys verdict (BULLISH or BEARISH or SIDEWAYS), score (-3 to 3), reason (one line)."),
    ("Momentum Analyst", "You are a momentum analyst. Reply JSON only with keys verdict (STRONG or WEAK or OVERSOLD or OVERBOUGHT or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Volume Analyst", "You are a volume analyst. Reply JSON only with keys verdict (HIGH_VOLUME or NORMAL or LOW_VOLUME), score (-3 to 3), reason (one line)."),
    ("Risk Manager", "You are a risk manager. Reply JSON only with keys verdict (LOW_RISK or MEDIUM_RISK or HIGH_RISK), score (-3 to 3), sl_price (number), reason (one line)."),
    ("SR Analyst", "You are a support resistance analyst. Reply JSON only with keys verdict (NEAR_SUPPORT or NEAR_RESISTANCE or MID_RANGE), score (-3 to 3), reason (one line)."),
    ("Pattern Analyst", "You are a candle pattern analyst. Reply JSON only with keys verdict (BULLISH_PATTERN or BEARISH_PATTERN or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Sentiment Analyst", "You are a sentiment analyst. Reply JSON only with keys verdict (GREEDY or FEARFUL or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Indicator Analyst", "You are an indicator analyst. Reply JSON only with keys verdict (BULLISH or BEARISH or NEUTRAL), score (-3 to 3), reason (one line)."),
]

def snap(sym, itv):
    df = kl(sym, itv, 250)
    if df.empty:
        return None, None
    df = ind(df)
    sp, rs = zones(df)
    la = df.iloc[-1]
    f = fg()
    g = gm()
    s = {"sym": sym, "tf": itv, "p": round(float(la["c"]),6), "e20": round(float(la["e20"]),6), "e50": round(float(la["e50"]),6), "e200": round(float(la["e200"]),6) if not pd.isna(la["e200"]) else None, "rsi": round(float(la["rsi"]),2) if not pd.isna(la["rsi"]) else 50, "atr": round(float(la["atr"]),6) if not pd.isna(la["atr"]) else None, "macd": round(float(la["macd"]),6) if not pd.isna(la["macd"]) else 0, "msig": round(float(la["msig"]),6) if not pd.isna(la["msig"]) else 0, "vr": round(float(la["vr"]),2) if not pd.isna(la["vr"]) else 0, "bbu": round(float(la["bbu"]),6) if not pd.isna(la["bbu"]) else None, "bbl": round(float(la["bbl"]),6) if not pd.isna(la["bbl"]) else None, "sp": [round(float(x),6) for x in sp], "rs": [round(float(x),6) for x in rs], "fg": f, "btc": g["btc"]}
    return s, df

def pr(s):
    return "Symbol: " + s["sym"] + "\nTimeframe: " + s["tf"] + "\nPrice: " + str(s["p"]) + "\nEMA20: " + str(s["e20"]) + "\nEMA50: " + str(s["e50"]) + "\nEMA200: " + str(s["e200"]) + "\nRSI: " + str(s["rsi"]) + "\nATR: " + str(s["atr"]) + "\nMACD: " + str(s["macd"]) + " Signal: " + str(s["msig"]) + "\nVolume Ratio: " + str(s["vr"]) + "\nBB Upper: " + str(s["bbu"]) + " BB Lower: " + str(s["bbl"]) + "\nSupports: " + str(s["sp"]) + "\nResistances: " + str(s["rs"]) + "\nFear Greed: " + str(s["fg"]["v"]) + " " + s["fg"]["l"] + "\nBTC Dominance: " + str(s["btc"]) + "%"

def run_agents(sym, itv):
    s, df = snap(sym, itv)
    if s is None:
        return None, "No data"
    res = []
    pt = pr(s)
    for name, sys_p in AG:
        r, e = llm(sys_p, pt)
        if e:
            res.append({"n":name, "v":"ERR", "s":0, "r":e[:60], "sl":None})
            continue
        d = pj(r)
        if d is None:
            res.append({"n":name, "v":"?", "s":0, "r":(r or "")[:60], "sl":None})
        else:
            res.append({"n":name, "v":d.get("verdict","?"), "s":int(d.get("score",0)), "r":d.get("reason",""), "sl":d.get("sl_price")})
    return res, None

def chief(s, res):
    sm = "\n".join([r["n"] + ": " + str(r["v"]) + " score " + str(r["s"]) + " - " + str(r["r"]) for r in res])
    sys_p = "You are the Chief Trader. Reply JSON only with keys decision (BUY or SELL or HOLD), confidence (0-100), entry (number), sl (number), tp1 (number), tp2 (number), tp3 (number), reasoning (2 lines)."
    p = pr(s) + "\n\nAnalysts:\n" + sm + "\n\nGive final decision."
    r, e = llm(sys_p, p)
    if e:
        return None, e
    d = pj(r)
    if d is None:
        return None, "Parse: " + (r or "")[:120]
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
            st.info("Get free: https://console.groq.com/keys")
    st.markdown("Model: " + str(MD or "-"))
    st.markdown("Data: OKX")

bp = tk("BTCUSDT")
ep = tk("ETHUSDT")
sp2 = tk("SOLUSDT")
c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC", "${:,.2f}".format(bp.get("p",0)) if bp else "-", "{:+.2f}%".format(bp.get("c",0)) if bp else None)
c2.metric("ETH", "${:,.2f}".format(ep.get("p",0)) if ep else "-")
c3.metric("SOL", "${:,.2f}".format(sp2.get("p",0)) if sp2 else "-")
c4.metric("Time", datetime.now().strftime("%H:%M:%S"))
st.title("Pro Scanner")

with st.expander("Global Market and Bitcoin Network"):
    f = fg()
    g = gm()
    m = mp()
    k1, k2, k3, k4 = st.columns(4)
    fc = "#ef4444" if f["v"] > 70 else "#22c55e" if f["v"] < 30 else "#f59e0b"
    k1.markdown("<div class='card'><b>Fear Greed</b><br><span style='color:" + fc + ";font-size:24px;font-weight:900'>" + str(f["v"]) + "</span><br>" + f["l"] + "</div>", unsafe_allow_html=True)
    k2.markdown("<div class='card'><b>BTC Dominance</b><br><span style='font-size:24px;font-weight:900'>" + str(g["btc"]) + "%</span><br>ETH: " + str(g["eth"]) + "%</div>", unsafe_allow_html=True)
    k3.markdown("<div class='card'><b>Total MCap</b><br><span style='font-size:24px;font-weight:900'>${:.2f}T</span></div>".format(g["mc"]/1e12), unsafe_allow_html=True)
    k4.markdown("<div class='card'><b>24h Volume</b><br><span style='font-size:24px;font-weight:900'>${:.1f}B</span></div>".format(g["tv"]/1e9), unsafe_allow_html=True)
    st.markdown("##### Bitcoin Network")
    n1, n2, n3, n4, n5 = st.columns(5)
    n1.metric("Height", "{:,}".format(m["h"]))
    n2.metric("Mempool", "{:,}".format(m["c"]))
    n3.metric("Fast Fee", str(m["ff"]) + " sat/vB")
    n4.metric("30m Fee", str(m["f30"]))
    n5.metric("1h Fee", str(m["f1h"]))

t1, t2, t3, t4 = st.tabs(["Chart", "Scanner", "History", "LLM Agents"])

with t1:
    al = coins()
    opt = [c["s"] for c in al[:500]] if al else ["BTCUSDT","ETHUSDT"]
    c1, c2 = st.columns([2,1])
    s = c1.selectbox("Coin", opt, index=0, key="cs")
    iv = c2.selectbox("TF", ["15m","1h","4h","1d"], index=1, key="ct")
    df = kl(s, iv, 300)
    if df.empty:
        st.error("No data")
    else:
        df = ind(df)
        sp, rs = zones(df)
        sg = sigs(df)
        la = df.iloc[-1]
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.6,0.18,0.22], subplot_titles=("","Vol","RSI"))
        fig.add_trace(go.Candlestick(x=df["t"], open=df["o"], high=df["h"], low=df["l"], close=df["c"], name=s, increasing_line_color="#22c55e", decreasing_line_color="#ef4444"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["e20"], line=dict(color="#22d3ee", width=1.5), name="EMA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["e50"], line=dict(color="#fbbf24", width=1.5), name="EMA50"), row=1, col=1)
        for p in rs:
            fig.add_hrect(y0=p*0.995, y1=p*1.005, fillcolor="#ef4444", opacity=0.15, line_width=0, row=1, col=1)
        for p in sp:
            fig.add_hrect(y0=p*0.995, y1=p*1.005, fillcolor="#22c55e", opacity=0.15, line_width=0, row=1, col=1)
        for x in sg:
            cl2 = "#22c55e" if x["ty"] == "BUY" else "#ef4444"
            yp = x["p"]*0.997 if x["ty"] == "BUY" else x["p"]*1.003
            fig.add_trace(go.Scatter(x=[x["t"]], y=[yp], mode="markers", marker=dict(symbol="triangle-up" if x["ty"]=="BUY" else "triangle-down", size=12, color=cl2), showlegend=False), row=1, col=1)
        vc = ["#22c55e" if c >= o else "#ef4444" for c, o in zip(df["c"], df["o"])]
        fig.add_trace(go.Bar(x=df["t"], y=df["v"], marker_color=vc, name="Vol"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["va"], line=dict(color="#fbbf24", width=1), name="Avg"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["rsi"], line=dict(color="#a78bfa", width=1.5), name="RSI"), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", row=3, col=1)
        fig.update_layout(template="plotly_dark", height=780, paper_bgcolor="#0b0f17", plot_bgcolor="#0b0f17", xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.02), margin=dict(l=10, r=80, t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)
        rv = float(la["rsi"]) if not pd.isna(la["rsi"]) else 50
        vv = float(la["vr"]) if not pd.isna(la["vr"]) else 0
        trc = "BULL" if la["e20"] > la["e50"] else "BEAR"
        tc = "#22c55e" if trc == "BULL" else "#ef4444"
        rc = "#ef4444" if rv > 70 else "#22c55e" if rv < 30 else "#f59e0b"
        st.markdown("<div class='card'><b>Price:</b> $" + "{:,.6f}".format(la["c"]) + " <b>RSI:</b> <span style='color:" + rc + "'>" + "{:.1f}".format(rv) + "</span> <b>Vol:</b> " + "{:.2f}".format(vv) + "x <b>Trend:</b> <span style='color:" + tc + "'>" + trc + "</span></div>", unsafe_allow_html=True)

with t2:
    st.markdown("### Scanner")
    c1, c2 = st.columns([1,3])
    n = c1.slider("Coins", 20, 200, 50, 10)
    go = c2.button("Start Scan", type="primary")
    if "sr" not in st.session_state:
        st.session_state.sr = []
    if go:
        al = coins()
        if not al:
            st.error("No coins")
        else:
            lst = al[:n]
            prog = st.progress(0)
            res = []
            for i, c in enumerate(lst):
                prog.progress((i+1)/len(lst))
                r = scn(c["s"])
                if r and r["Str"] >= 30:
                    res.append(r)
            prog.empty()
            st.session_state.sr = res
            st.success("Done: " + str(len(r
