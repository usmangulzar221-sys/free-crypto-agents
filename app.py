import streamlit as st, requests, pandas as pd, numpy as np, plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time, os, json

st.set_page_config(page_title="Scanner Pro", layout="wide")
st.markdown("<style>.stApp{background:#0b0f17;color:#e5e7eb}.card{background:#111827;border-radius:12px;padding:14px;border:1px solid #1f2937;margin:8px 0}.buy{color:#22c55e;font-weight:800}.sell{color:#ef4444;font-weight:800}.llm{background:#1e1b4b;border-radius:10px;padding:12px;margin:8px 0;border-left:4px solid #a855f7}</style>", unsafe_allow_html=True)

try:
    from groq import Groq
    GA = True
except:
    GA = False

def gkey():
    try: return st.secrets["GROQ_API_KEY"]
    except: return os.environ.get("GROQ_API_KEY", "")

GK = gkey()
cl = None
MD = None
if GA and GK:
    try:
        cl = Groq(api_key=GK)
        MD = "openai/gpt-oss-120b"
    except: cl = None

def L(sys_p, usr_p):
    if cl is None: return None, "No key"
    try:
        r = cl.chat.completions.create(model=MD, messages=[{"role":"system","content":sys_p},{"role":"user","content":usr_p}], temperature=0.3, max_tokens=350)
        return r.choices[0].message.content, None
    except Exception as e: return None, str(e)[:120]

def PJ(r):
    if not r: return None
    try:
        t = r.strip()
        if "```" in t:
            p = t.split("```")
            if len(p) >= 2: t = p[1].replace("json","").strip()
        return json.loads(t)
    except: return {"verdict": r[:25], "score": 0, "reason": r[:70]}

OK = "https://www.okx.com/api/v5"
TFM = {"15m":"15m","1h":"1H","4h":"4H","1d":"1D"}

@st.cache_data(ttl=3600)
def get_coins():
    try:
        r = requests.get(OK+"/market/tickers", params={"instType":"SPOT"}, timeout=12).json()
        if r.get("code") != "0": return []
        o = []
        for d in r["data"]:
            i = d.get("instId","")
            if not i.endswith("-USDT") or "USDC" in i or "DAI" in i: continue
            try: v = float(d.get("volCcy24h",0))
            except: v = 0
            if v < 50000: continue
            o.append({"s": i.replace("-",""), "v": v})
        o.sort(key=lambda x: x["v"], reverse=True)
        return o[:700]
    except: return []

@st.cache_data(ttl=20)
def KL(s, i="1h", n=300):
    try:
        iid = s[:-4]+"-USDT" if s.endswith("USDT") else s
        r = requests.get(OK+"/market/candles", params={"instId":iid, "bar":TFM.get(i,"1H"), "limit":min(n,300)}, timeout=10).json()
        if r.get("code") != "0" or not r.get("data"): return pd.DataFrame()
        d = r["data"]
        df = pd.DataFrame(d, columns=["t","o","h","l","c","v","vq","vc","x"])
        for c in ["o","h","l","c","v"]: df[c] = df[c].astype(float)
        df["t"] = pd.to_datetime(df["t"].astype(float), unit="ms")
        return df[["t","o","h","l","c","v"]].sort_values("t").reset_index(drop=True)
    except: return pd.DataFrame()

@st.cache_data(ttl=15)
def TX(s):
    try:
        iid = s[:-4]+"-USDT" if s.endswith("USDT") else s
        r = requests.get(OK+"/market/ticker", params={"instId":iid}, timeout=8).json()
        if r.get("code") != "0" or not r.get("data"): return {}
        d = r["data"][0]
        la = float(d["last"]); op = float(d["open24h"])
        cg = (la-op)/op*100 if op else 0
        try: vl = float(d.get("volCcy24h",0))
        except: vl = 0
        return {"p": la, "c": cg, "v": vl}
    except: return {}

@st.cache_data(ttl=300)
def FG():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6).json()
        d = r["data"][0]
        return {"v": int(d["value"]), "l": d["value_classification"]}
    except: return {"v": 50, "l": "Neutral"}

@st.cache_data(ttl=300)
def GM():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=8).json()
        d = r["data"]
        return {"btc": round(d["market_cap_percentage"].get("btc",0),2), "eth": round(d["market_cap_percentage"].get("eth",0),2), "mc": d["total_market_cap"]["usd"], "tv": d["total_volume"]["usd"]}
    except: return {"btc":0,"eth":0,"mc":0,"tv":0}

@st.cache_data(ttl=60)
def MP():
    try:
        r1 = requests.get("https://mempool.space/api/mempool", timeout=6).json()
        r2 = requests.get("https://mempool.space/api/v1/fees/recommended", timeout=6).json()
        r3 = requests.get("https://mempool.space/api/blocks/tip/height", timeout=6).text
        return {"h": int(r3), "c": r1.get("count",0), "ff": r2.get("fastestFee",0), "f30": r2.get("halfHourFee",0), "f1h": r2.get("hourFee",0)}
    except: return {"h":0,"c":0,"ff":0,"f30":0,"f1h":0}

def IND(df):
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
    return df

def ZN(df, lb=5):
    H = df["h"].values; L = df["l"].values
    rs = []; sp = []
    for i in range(lb, len(df)-lb):
        if H[i] == max(H[i-lb:i+lb+1]): rs.append(H[i])
        if L[i] == min(L[i-lb:i+lb+1]): sp.append(L[i])
    return sp[-3:], rs[-3:]

def SG(df):
    out = []
    for i in range(1, len(df)):
        pf = df["e20"].iloc[i-1]; ps = df["e50"].iloc[i-1]
        cf = df["e20"].iloc[i]; cs = df["e50"].iloc[i]
        r = df["rsi"].iloc[i]
        if pd.isna(pf) or pd.isna(r): continue
        if pf <= ps and cf > cs and r < 70:
            out.append({"i":i,"t":df["t"].iloc[i],"p":float(df["c"].iloc[i]),"ty":"BUY","r":float(r)})
        elif pf >= ps and cf < cs and r > 30:
            out.append({"i":i,"t":df["t"].iloc[i],"p":float(df["c"].iloc[i]),"ty":"SELL","r":float(r)})
    return out

def TRK(df, s, atr):
    i = s["i"]; e = s["p"]
    f = df.iloc[i+1:]
    if f.empty: return {"mu":0,"md":0,"du":0,"tp1":False,"tp2":False,"sl":False,"fh":None,"cur":e,"slp":0,"tp1p":0,"tp2p":0}
    tp1p = e + 1.5*atr if s["ty"]=="BUY" else e - 1.5*atr
    tp2p = e + 3*atr if s["ty"]=="BUY" else e - 3*atr
    slp = e - 2*atr if s["ty"]=="BUY" else e + 2*atr
    t1 = t2 = sh = False; fh = None
    for _, row in f.iterrows():
        if s["ty"] == "BUY":
            if row["h"] >= tp1p and not t1:
                t1 = True
                if fh is None: fh = "TP1"
            if row["h"] >= tp2p and not t2: t2 = True
            if row["l"] <= slp and not sh:
                sh = True
                if fh is None: fh = "SL"
        else:
            if row["l"] <= tp1p and not t1:
                t1 = True
                if fh is None: fh = "TP1"
            if row["l"] <= tp2p and not t2: t2 = True
            if row["h"] >= slp and not sh:
                sh = True
                if fh is None: fh = "SL"
    mu = (float(f["h"].max())-e)/e*100
    md = (float(f["l"].min())-e)/e*100
    du = (df["t"].iloc[-1]-df["t"].iloc[i]).total_seconds()/3600
    return {"mu":mu,"md":md,"du":du,"tp1":t1,"tp2":t2,"sl":sh,"fh":fh,"cur":float(df["c"].iloc[-1]),"slp":slp,"tp1p":tp1p,"tp2p":tp2p}

def SCN(s):
    try:
        df = KL(s, "1h", 200)
        if df.empty or len(df) < 100: return None
        df = IND(df)
        la = df.iloc[-1]
        p = float(la["c"])
        r = float(la["rsi"]) if not pd.isna(la["rsi"]) else 50
        v = float(la["vr"]) if not pd.isna(la["vr"]) else 0
        a = float(la["atr"]) if not pd.isna(la["atr"]) else p*0.01
        e20 = float(la["e20"]); e50 = float(la["e50"])
        tr = "BULL" if e20 > e50 else "BEAR"
        t = TX(s)
        cg = t.get("c",0) if t else 0
        vl = t.get("v",0) if t else 0
        if tr=="BULL" and 40<r<65: sg = "LONG"
        elif tr=="BEAR" and 35<r<60: sg = "SHORT"
        else: sg = "WAIT"
        if sg=="LONG":
            e = p; sl = p-2*a; tp1 = p+1.5*a; tp2 = p+3*a
        elif sg=="SHORT":
            e = p; sl = p+2*a; tp1 = p-1.5*a; tp2 = p-3*a
        else: e = sl = tp1 = tp2 = p
        st2 = 0
        if tr=="BULL" and sg=="LONG": st2 += 30
        if tr=="BEAR" and sg=="SHORT": st2 += 30
        if 45<r<60: st2 += 15
        if v>1.5: st2 += 20
        elif v>1.2: st2 += 10
        st2 += min(int(abs(cg)),20)
        st2 = min(st2,100)
        return {"Sym":s,"Px":round(p,6),"Cg":round(cg,2),"Vm":round(vl/1e6,1),"Tr":tr,"RSI":round(r,1),"VR":round(v,2),"Sig":sg,"Str":st2,"E":round(e,6),"SL":round(sl,6),"TP1":round(tp1,6),"TP2":round(tp2,6)}
    except: return None

AGS = [
    ("Trend Analyst","You are a trend analyst. Reply JSON only with keys verdict (BULLISH or BEARISH or SIDEWAYS), score (-3 to 3), reason (one line)."),
    ("Momentum Analyst","You are a momentum analyst. Reply JSON only with keys verdict (STRONG or WEAK or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Volume Analyst","You are a volume analyst. Reply JSON only with keys verdict (HIGH or NORMAL or LOW), score (-3 to 3), reason (one line)."),
    ("Risk Manager","You are a risk manager. Reply JSON only with keys verdict (LOW_RISK or MEDIUM_RISK or HIGH_RISK), score (-3 to 3), sl_price (number), reason (one line)."),
    ("SR Analyst","You are a support resistance analyst. Reply JSON only with keys verdict (NEAR_SUPPORT or NEAR_RESISTANCE or MID_RANGE), score (-3 to 3), reason (one line)."),
    ("Sentiment Analyst","You analyze sentiment. Reply JSON only with keys verdict (GREEDY or FEARFUL or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Indicator Analyst","You analyze indicators. Reply JSON only with keys verdict (BULLISH or BEARISH or NEUTRAL), score (-3 to 3), reason (one line)."),
]

def SNAP(s, i):
    df = KL(s, i, 250)
    if df.empty: return None, None
    df = IND(df)
    sp, rs = ZN(df)
    la = df.iloc[-1]
    f = FG(); g = GM()
    d = {"sym":s,"tf":i,"p":round(float(la["c"]),6),"e20":round(float(la["e20"]),6),"e50":round(float(la["e50"]),6),"e200":round(float(la["e200"]),6) if not pd.isna(la["e200"]) else None,"rsi":round(float(la["rsi"]),2) if not pd.isna(la["rsi"]) else 50,"atr":round(float(la["atr"]),6) if not pd.isna(la["atr"]) else None,"macd":round(float(la["macd"]),6) if not pd.isna(la["macd"]) else 0,"vr":round(float(la["vr"]),2) if not pd.isna(la["vr"]) else 0,"sp":[round(float(x),6) for x in sp],"rs":[round(float(x),6) for x in rs],"fg":f,"btc":g["btc"]}
    return d, df

def PR(s):
    return "Symbol: " + s["sym"] + "\nTF: " + s["tf"] + "\nPrice: " + str(s["p"]) + "\nEMA20: " + str(s["e20"]) + "\nEMA50: " + str(s["e50"]) + "\nRSI: " + str(s["rsi"]) + "\nATR: " + str(s["atr"]) + "\nMACD: " + str(s["macd"]) + "\nVolRatio: " + str(s["vr"]) + "\nSupports: " + str(s["sp"]) + "\nResistances: " + str(s["rs"]) + "\nFearGreed: " + str(s["fg"]["v"]) + " " + s["fg"]["l"] + "\nBTCDom: " + str(s["btc"]) + "%"

def RUN(sym, itv):
    s, df = SNAP(sym, itv)
    if s is None: return None, "No data"
    res = []; pt = PR(s)
    for nm, sy in AGS:
        r, e = L(sy, pt)
        if e:
            res.append({"n":nm,"v":"ERR","s":0,"r":e[:50],"sl":None}); continue
        d = PJ(r)
        if d is None:
            res.append({"n":nm,"v":"?","s":0,"r":(r or "")[:50],"sl":None})
        else:
            res.append({"n":nm,"v":d.get("verdict","?"),"s":int(d.get("score",0)),"r":d.get("reason",""),"sl":d.get("sl_price")})
    return res, None

def CHIEF(s, res):
    sm = "\n".join([r["n"]+": "+str(r["v"])+" score "+str(r["s"]) for r in res])
    sy = "You are the Chief Trader. Reply JSON only with keys decision (BUY or SELL or HOLD), confidence (0-100), entry (number), sl (number), tp1 (number), tp2 (number), tp3 (number), reasoning (2 lines)."
    p = PR(s) + "\n\nAnalysts:\n" + sm + "\n\nFinal decision."
    r, e = L(sy, p)
    if e: return None, e
    d = PJ(r)
    if d is None: return None, "Parse: " + (r or "")[:100]
    return d, None

with st.sidebar:
    st.markdown("### Groq API Key")
    if GK: st.success("Loaded")
    else:
        uk = st.text_input("API key", type="password")
        if uk:
            try:
                cl = Groq(api_key=uk); MD = "openai/gpt-oss-120b"
                st.success("Set!")
            except: st.error("Invalid")
        else: st.info("Free: https://console.groq.com/keys")
    st.markdown("Model: " + str(MD or "-"))
    st.markdown("Data: OKX Live")

bp = TX("BTCUSDT"); ep = TX("ETHUSDT"); s2p = TX("SOLUSDT")
c1,c2,c3,c4 = st.columns(4)
c1.metric("BTC","${:,.2f}".format(bp.get("p",0)) if bp else "-","{:+.2f}%".format(bp.get("c",0)) if bp else None)
c2.metric("ETH","${:,.2f}".format(ep.get("p",0)) if ep else "-")
c3.metric("SOL","${:,.2f}".format(s2p.get("p",0)) if s2p else "-")
c4.metric("Time", datetime.now().strftime("%H:%M:%S"))
st.title("Scanner Pro - Live")

with st.expander("Global Market + Bitcoin Network"):
    f = FG(); g = GM(); m = MP()
    k1,k2,k3,k4 = st.columns(4)
    fc = "#ef4444" if f["v"]>70 else "#22c55e" if f["v"]<30 else "#f59e0b"
    k1.markdown("<div class='card'><b>Fear Greed</b><br><span style='color:"+fc+";font-size:24px;font-weight:900'>"+str(f["v"])+"</span><br>"+f["l"]+"</div>", unsafe_allow_html=True)
    k2.markdown("<div class='card'><b>BTC Dom</b><br><span style='font-size:24px;font-weight:900'>"+str(g["btc"])+"%</span><br>ETH: "+str(g["eth"])+"%</div>", unsafe_allow_html=True)
    k3.markdown("<div class='card'><b>Total MCap</b><br><span style='font-size:22px;font-weight:900'>${:.2f}T</span></div>".format(g["mc"]/1e12), unsafe_allow_html=True)
    k4.markdown("<div class='card'><b>24h Vol</b><br><span style='font-size:22px;font-weight:900'>${:.1f}B</span></div>".format(g["tv"]/1e9), unsafe_allow_html=True)
    st.markdown("##### Bitcoin Network")
    n1,n2,n3,n4,n5 = st.columns(5)
    n1.metric("Height","{:,}".format(m["h"]))
    n2.metric("Mempool","{:,}".format(m["c"]))
    n3.metric("Fast Fee",str(m["ff"])+" sat/vB")
    n4.metric("30m",str(m["f30"]))
    n5.metric("1h",str(m["f1h"]))

T1,T2,T3,T4 = st.tabs(["Chart","Scanner","History","LLM Agents"])

with T1:
    al = get_coins()
    opt = [c["s"] for c in al[:500]] if al else ["BTCUSDT","ETHUSDT"]
    cc1,cc2 = st.columns([2,1])
    s = cc1.selectbox("Coin", opt, index=0, key="cs")
    iv = cc2.selectbox("TF",["15m","1h","4h","1d"], index=1, key="ct")
    df = KL(s, iv, 300)
    if df.empty: st.error("No data")
    else:
        df = IND(df)
        sp, rs = ZN(df)
        sg = SG(df)
        la = df.iloc[-1]
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.6,0.18,0.22], subplot_titles=("","Vol","RSI"))
        fig.add_trace(go.Candlestick(x=df["t"],open=df["o"],high=df["h"],low=df["l"],close=df["c"],name=s,increasing_line_color="#22c55e",decreasing_line_color="#ef4444"),row=1,col=1)
        fig.add_trace(go.Scatter(x=df["t"],y=df["e20"],line=dict(color="#22d3ee",width=1.5),name="EMA20"),row=1,col=1)
        fig.add_trace(go.Scatter(x=df["t"],y=df["e50"],line=dict(color="#fbbf24",width=1.5),name="EMA50"),row=1,col=1)
        for p in rs: fig.add_hrect(y0=p*0.995,y1=p*1.005,fillcolor="#ef4444",opacity=0.15,line_width=0,row=1,col=1)
        for p in sp: fig.add_hrect(y0=p*0.995,y1=p*1.005,fillcolor="#22c55e",opacity=0.15,line_width=0,row=1,col=1)
        for x in sg:
            cl2 = "#22c55e" if x["ty"]=="BUY" else "#ef4444"
            yp = x["p"]*0.997 if x["ty"]=="BUY" else x["p"]*1.003
            fig.add_trace(go.Scatter(x=[x["t"]],y=[yp],mode="markers",marker=dict(symbol="triangle-up" if x["ty"]=="BUY" else "triangle-down",size=12,color=cl2),showlegend=False),row=1,col=1)
        vc = ["#22c55e" if c>=o else "#ef4444" for c,o in zip(df["c"],df["o"])]
        fig.add_trace(go.Bar(x=df["t"],y=df["v"],marker_color=vc,name="Vol"),row=2,col=1)
        fig.add_trace(go.Scatter(x=df["t"],y=df["va"],line=dict(color="#fbbf24",width=1),name="Avg"),row=2,col=1)
        fig.add_trace(go.Scatter(x=df["t"],y=df["rsi"],line=dict(color="#a78bfa",width=1.5),name="RSI"),row=3,col=1)
        fig.add_hline(y=70,line_dash="dot",line_color="#ef4444",row=3,col=1)
        fig.add_hline(y=30,line_dash="dot",line_color="#22c55e",row=3,col=1)
        fig.update_layout(template="plotly_dark",height=760,paper_bgcolor="#0b0f17",plot_bgcolor="#0b0f17",xaxis_rangeslider_visible=False,legend=dict(orientation="h",y=1.02),margin=dict(l=10,r=80,t=50,b=10))
        st.plotly_chart(fig, use_container_width=True)
        rv = float(la["rsi"]) if not pd.isna(la["rsi"]) else 50
        vv = float(la["vr"]) if not pd.isna(la["vr"]) else 0
        trc = "BULL" if la["e20"]>la["e50"] else "BEAR"
        tc = "#22c55e" if trc=="BULL" else "#ef4444"
        rc = "#ef4444" if rv>70 else "#22c55e" if rv<30 else "#f59e0b"
        st.markdown("<div class='card'><b>Price:</b> $"+ "{:,.6f}".format(la["c"]) +" <b>RSI:</b> <span style='color:"+rc+"'>"+ "{:.1f}".format(rv) +"</span> <b>Vol:</b> "+ "{:.2f}".format(vv) +"x <b>Trend:</b> <span style='color:"+tc+"'>"+trc+"</span></div>", unsafe_allow_html=True)

with T2:
    st.markdown("### Multi-Coin Scanner")
    cc1,cc2 = st.columns([1,3])
    n = cc1.slider("Coins",20,200,50,10)
    go = cc2.button("Start Scan", type="primary")
    if "sr" not in st.session_state: st.session_state.sr = []
    if go:
        al = get_coins()
        if not al: st.error("No coins")
        else:
            lst = al[:n]
            prog = st.progress(0)
            res = []
            for i, c in enumerate(lst):
                prog.progress((i+1)/len(lst))
                r = SCN(c["s"])
                if r and r["Str"] >= 30: res.append(r)
            prog.empty()
            st.session_state.sr = res
            st.success("Found " + str(len(res)) + " signals")
    if st.session_state.sr:
        dr = pd.DataFrame(st.session_state.sr).sort_values("Str", ascending=False)
        lg = dr[dr["Sig"]=="LONG"]; sh = dr[dr["Sig"]=="SHORT"]
        m1,m2,m3 = st.columns(3)
        m1.metric("LONG", len(lg)); m2.metric("SHORT", len(sh)); m3.metric("Vol Spikes", len(dr[dr["VR"]>1.5]))
        st.markdown("#### LONG Signals")
        if not lg.empty: st.dataframe(lg, use_container_width=True, hide_index=True)
        else: st.info("None")
        st.markdown("#### SHORT Signals")
        if not sh.empty: st.dataframe(sh, use_container_width=True, hide_index=True)
        else: st.info("None")

with T3:
    st.markdown("### Signal History")
    al = get_coins()
    opt = [c["s"] for c in al[:300]] if al else ["BTCUSDT"]
    cc1,cc2 = st.columns([2,1])
    hs = cc1.selectbox("Coin", opt, index=0, key="hs")
    hi = cc2.selectbox("TF",["15m","1h","4h"], index=1, key="hi")
    df = KL(hs, hi, 500)
    if df.empty: st.error("No data")
    else:
        df = IND(df)
        sg = SG(df)
        if not sg: st.info("No signals")
        else:
            rows = []; w = 0; l2 = 0
            for s in sg[-50:][::-1]:
                at = float(df["atr"].iloc[s["i"]]) if not pd.isna(df["atr"].iloc[s["i"]]) else s["p"]*0.01
                tr = TRK(df, s, at)
                if s["ty"]=="BUY": rs2 = "WIN" if tr["mu"]>1 else "LOSS" if tr["md"]<-1 else "OPEN"
                else: rs2 = "WIN" if tr["md"]<-1 else "LOSS" if tr["mu"]>1 else "OPEN"
                if rs2=="WIN": w += 1
                elif rs2=="LOSS": l2 += 1
                rows.append({"Time":s["t"].strftime("%m-%d %H:%M"),"Type":s["ty"],"Entry":round(s["p"],6),"RSI":round(s["r"],1),"MaxUp%":round(tr["mu"],2),"MaxDown%":round(tr["md"],2),"TP1":"Y" if tr["tp1"] else "-","TP2":"Y" if tr["tp2"] else "-","SL":"Y" if tr["sl"] else "-","First":tr["fh"] or "-","Dur":"{:.1f}h".format(tr["du"]),"Result":rs2})
            tot = w + l2; wr = (w/tot*100) if tot>0 else 0
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("Total", len(sg)); m2.metric("Wins", w); m3.metric("Losses", l2); m4.metric("WinRate", "{:.1f}%".format(wr))
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with T4:
    st.markdown("### LLM Agents")
    if not GK: st.warning("Add Groq key in sidebar")
    else:
        al = get_coins()
        opt = [c["s"] for c in al[:300]] if al else ["BTCUSDT"]
        cc1,cc2 = st.columns([2,1])
        ls = cc1.selectbox("Coin", opt, index=0, key="ls")
        li = cc2.selectbox("TF",["15m","1h","4h"], index=1, key="li")
        if st.button("Run Agents", type="primary"):
            with st.spinner("Running..."):
                t0 = time.time()
                s, df = SNAP(ls, li)
                if s is None: st.error("No data")
                else:
                    st.markdown("<div class='card'><b>Price:</b> $"+str(s["p"])+" <b>RSI:</b> "+str(s["rsi"])+" <b>VolRatio:</b> "+str(s["vr"])+"x <b>F&G:</b> "+str(s["fg"]["v"])+" <b>BTC.D:</b> "+str(s["btc"])+"%</div>", unsafe_allow_html=True)
                    res, e = RUN(ls, li)
                    if e: st.error(e)
                    else:
                        st.markdown("#### Agent Verdicts")
                        for a in res:
                            vc = "#22c55e" if a["s"]>0 else "#ef4444" if a["s"]<0 else "#f59e0b"
                            st.markdown("<div class='llm' style='border-left-color:"+vc+"'><b>"+a["n"]+"</b> -> <b style='color:"+vc+"'>"+str(a["v"])+"</b> (score "+str(a["s"])+")<br><span style='color:#cbd5e1;font-size:13px'>"+str(a["r"])+"</span></div>", unsafe_allow_html=True)
                        st.markdown("#### Chief Decision")
                        with st.spinner("Chief deciding..."):
                            cons, ce = CHIEF(s, res)
                            if ce: st.error(ce)
                            else:
                                d = cons.get("decision","HOLD"); cf = cons.get("confidence",0)
                                dc = "#22c55e" if d=="BUY" else "#ef4444" if d=="SELL" else "#f59e0b"
                                st.markdown("<div class='card' style='border:3px solid "+dc+";text-align:center'><div style='color:#94a3b8'>FINAL</div><div style='color:"+dc+";font-size:34px;font-weight:900'>"+str(d)+"</div><div>Confidence: "+str(cf)+"%</div><div style='margin-top:12px'><b>Entry:</b> $"+str(cons.get("entry","-"))+" <b>SL:</b> $"+str(cons.get("sl","-"))+" <b>TP1:</b> $"+str(cons.get("tp1","-"))+" <b>TP2:</b> $"+str(cons.get("tp2","-"))+"</div><div style='margin-top:10px;font-style:italic'>"+str(cons.get("reasoning",""))+"</div></div>", unsafe_allow_html=True)
                        st.caption("Done in {:.1f}s".format(time.time()-t0))

st.caption("Pro Scanner - Live OKX Data - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
