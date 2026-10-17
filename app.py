import streamlit as st, requests, pandas as pd, numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import json, time

st.set_page_config(page_title="Pro Scanner", layout="wide")
st.markdown("<style>.stApp{background:#0b0f17;color:#e5e7eb}.card{background:#111827;border-radius:12px;padding:12px;border:1px solid #1f2937;margin:6px 0}.buy{color:#22c55e;font-weight:800}.sell{color:#ef4444;font-weight:800}.llm{background:#1e1b4b;border-radius:10px;padding:10px;margin:6px 0;border-left:4px solid #a855f7}.sig{background:#1e293b;border-radius:10px;padding:12px;margin:8px 0;border-left:5px solid #22c55e}.sigS{border-left-color:#ef4444}</style>", unsafe_allow_html=True)

OK = "https://www.okx.com/api/v5"
BY = "https://api.bybit.com/v5/market"
TFO = {"15m":"15m","1h":"1H","4h":"4H","1d":"1D"}
TFB = {"15m":"15","1h":"60","4h":"240","1d":"D"}
FEE_PCT = 0.25

def PKT(): return (datetime.utcnow() + timedelta(hours=5)).strftime("%I:%M:%S %p")
def PKTDT(): return (datetime.utcnow() + timedelta(hours=5)).strftime("%Y-%m-%d %I:%M:%S %p")

def V(text):
    try:
        s = text.replace("'", "").replace('"', '')
        components.html("<script>var u=new SpeechSynthesisUtterance('" + s + "');u.rate=0.9;window.speechSynthesis.speak(u);</script>", height=0)
    except: pass

try:
    from groq import Groq
    import os
    GK = ""
    try: GK = st.secrets["GROQ_API_KEY"]
    except: GK = os.environ.get("GROQ_API_KEY", "")
    cl = Groq(api_key=GK) if GK else None
    MD = "openai/gpt-oss-120b" if GK else None
except:
    cl = None; GK = ""; MD = None

def LLM(sp, up, mt=200):
    if cl is None: return None, "No key"
    try:
        r = cl.chat.completions.create(model=MD, messages=[{"role":"system","content":sp},{"role":"user","content":up}], temperature=0.3, max_tokens=mt)
        return r.choices[0].message.content, None
    except Exception as e: return None, str(e)[:100]

def PJ(r):
    if not r: return None
    try:
        t = r.strip()
        if "```" in t:
            p = t.split("```")
            if len(p) >= 2: t = p[1].replace("json", "").strip()
        return json.loads(t)
    except: return {"verdict": r[:25], "score": 0, "reason": r[:60]}

def OID(s, m): return s[:-4] + "-USDT" if m == "SPOT" and s.endswith("USDT") else (s[:-4] + "-USDT-SWAP" if m == "FUTURES" and s.endswith("USDT") else s)
def BID(s): return s if s.endswith("USDT") else s + "USDT"

@st.cache_data(ttl=600)
def COINS(m="SPOT"):
    try:
        it = "SPOT" if m == "SPOT" else "SWAP"
        r = requests.get(OK + "/market/tickers", params={"instType": it}, timeout=10).json()
        if r.get("code") != "0": return ["BTCUSDT","ETHUSDT","SOLUSDT"]
        out = []
        for d in r["data"]:
            i = d.get("instId","")
            if m == "SPOT" and (not i.endswith("-USDT") or "USDC" in i or "DAI" in i): continue
            if m == "FUTURES" and not i.endswith("-USDT-SWAP"): continue
            s = i.replace("-","") if m == "SPOT" else i.replace("-USDT-SWAP","USDT")
            try: v = float(d.get("volCcy24h", 0))
            except: v = 0
            if v > 500000: out.append(s)
        return out[:100] if out else ["BTCUSDT","ETHUSDT","SOLUSDT"]
    except: return ["BTCUSDT","ETHUSDT","SOLUSDT"]

def _ok_kl(s, i, n, m):
    try:
        r = requests.get(OK + "/market/candles", params={"instId": OID(s, m), "bar": TFO.get(i, "1H"), "limit": min(n, 300)}, timeout=10).json()
        if r.get("code") != "0" or not r.get("data"): return pd.DataFrame()
        d = r["data"]
        df = pd.DataFrame(d, columns=["t","o","h","l","c","v","vq","vc","x"])
        df = df[df["x"] == "1"] if not df[df["x"] == "1"].empty else df
        for c in ["o","h","l","c","v"]: df[c] = pd.to_numeric(df[c], errors="coerce")
        df["t"] = pd.to_datetime(df["t"], errors="coerce", unit="ms")
        df = df.dropna(subset=["t","o","h","l","c","v"])
        return df[["t","o","h","l","c","v"]].sort_values("t").reset_index(drop=True)
    except: return pd.DataFrame()

def _by_kl(s, i, n, m):
    try:
        cat = "spot" if m == "SPOT" else "linear"
        r = requests.get(BY + "/kline", params={"category": cat, "symbol": BID(s), "interval": TFB.get(i,"60"), "limit": min(n,300)}, timeout=10).json()
        if r.get("retCode") != 0 or not r.get("result",{}).get("list"): return pd.DataFrame()
        d = r["result"]["list"]
        df = pd.DataFrame(d, columns=["t","o","h","l","c","v","tn"])
        for c in ["o","h","l","c","v"]: df[c] = pd.to_numeric(df[c], errors="coerce")
        df["t"] = pd.to_datetime(df["t"], errors="coerce", unit="ms")
        df = df.dropna(subset=["t","o","h","l","c","v"])
        return df[["t","o","h","l","c","v"]].sort_values("t").reset_index(drop=True)
    except: return pd.DataFrame()

@st.cache_data(ttl=20)
def KL(s, i="1h", n=300, m="SPOT"):
    df = _ok_kl(s, i, n, m)
    return df if not df.empty and len(df) >= 30 else (_by_kl(s, i, n, m) if not _by_kl(s, i, n, m).empty else df)

def _ok_tx(s, m):
    try:
        r = requests.get(OK + "/market/ticker", params={"instId": OID(s,m)}, timeout=8).json()
        if r.get("code") != "0" or not r.get("data"): return {}
        d = r["data"][0]
        la = float(d["last"]); op = float(d["open24h"])
        return {"p": la, "c": (la-op)/op*100 if op else 0, "h24": float(d.get("high24h", la)), "l24": float(d.get("low24h", la))}
    except: return {}

def _by_tx(s, m):
    try:
        cat = "spot" if m == "SPOT" else "linear"
        r = requests.get(BY + "/tickers", params={"category": cat, "symbol": BID(s)}, timeout=8).json()
        if r.get("retCode") != 0 or not r.get("result",{}).get("list"): return {}
        d = r["result"]["list"][0]
        la = float(d.get("lastPrice", 0))
        return {"p": la, "c": float(d.get("price24hPcnt",0))*100, "h24": float(d.get("highPrice24h", la)), "l24": float(d.get("lowPrice24h", la))}
    except: return {}

@st.cache_data(ttl=10)
def TX(s, m="SPOT"): return _ok_tx(s, m) or _by_tx(s, m)

@st.cache_data(ttl=300)
def FG():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6).json()
        return {"v": int(r["data"][0]["value"]), "l": r["data"][0]["value_classification"]}
    except: return {"v": 50, "l": "Neutral"}

@st.cache_data(ttl=300)
def GM():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=8).json()
        d = r["data"]
        return {"btc": round(d["market_cap_percentage"].get("btc",0),2), "eth": round(d["market_cap_percentage"].get("eth",0),2), "mc": d["total_market_cap"]["usd"]}
    except: return {"btc":0,"eth":0,"mc":0}

def IND(df):
    df = df.copy()
    df["e20"] = df["c"].ewm(span=20, adjust=False).mean()
    df["e50"] = df["c"].ewm(span=50, adjust=False).mean()
    d = df["c"].diff(); g = d.clip(lower=0).rolling(14).mean(); l = (-d.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - 100/(1 + g/l.replace(0, np.nan))
    tr = pd.concat([df["h"]-df["l"],(df["h"]-df["c"].shift()).abs(),(df["l"]-df["c"].shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["va"] = df["v"].rolling(20).mean(); df["vr"] = df["v"]/df["va"]
    e1 = df["c"].ewm(span=12, adjust=False).mean(); e2 = df["c"].ewm(span=26, adjust=False).mean()
    df["macd"] = e1-e2; df["msig"] = df["macd"].ewm(span=9, adjust=False).mean(); df["mhist"] = df["macd"]-df["msig"]
    df["bbm"] = df["c"].rolling(20).mean(); sd = df["c"].rolling(20).std(); df["bbu"] = df["bbm"]+2*sd; df["bbl"] = df["bbm"]-2*sd
    rm = df["rsi"].rolling(14).min(); rx = df["rsi"].rolling(14).max()
    df["sk"] = ((df["rsi"]-rm)/(rx-rm).replace(0,np.nan)*100).rolling(3).mean()
    tp = (df["h"]+df["l"]+df["c"])/3; df["vwap"] = (tp*df["v"]).rolling(20).sum()/df["v"].rolling(20).sum().replace(0,np.nan)
    return df

def BACKTEST(df, initial_cap=1000):
    trades = []; cap = initial_cap; pos = None
    for i in range(1, len(df)):
        c = float(df["c"].iloc[i]); a = float(df["atr"].iloc[i]) if not pd.isna(df["atr"].iloc[i]) else c*0.01
        pf = df["e20"].iloc[i-1]; ps = df["e50"].iloc[i-1]
        cf = df["e20"].iloc[i]; cs = df["e50"].iloc[i]
        
        if pos:
            hit_sl = (c <= pos["sl"]) if pos["type"] == "LONG" else (c >= pos["sl"])
            hit_tp = (c >= pos["tp1"]) if pos["type"] == "LONG" else (c <= pos["tp1"])
            if hit_sl or hit_tp:
                pnl = (pos["tp1"] - pos["entry"]) * pos["size"] if hit_tp and pos["type"] == "LONG" else \
                      (pos["entry"] - pos["tp1"]) * pos["size"] if hit_tp and pos["type"] == "SHORT" else \
                      (pos["sl"] - pos["entry"]) * pos["size"] if hit_sl and pos["type"] == "LONG" else \
                      (pos["entry"] - pos["sl"]) * pos["size"]
                cap += pnl - (pos["entry"]*pos["size"]*(FEE_PCT/100))
                trades.append({"pnl": pnl, "win": 1 if pnl > 0 else 0})
                pos = None
        else:
            if pf <= ps and cf > cs: # BUY
                pos = {"type": "LONG", "entry": c, "sl": c-2*a, "tp1": c+1.5*a, "size": cap/c}
            elif pf >= ps and cf < cs: # SELL
                pos = {"type": "SHORT", "entry": c, "sl": c+2*a, "tp1": c-1.5*a, "size": cap/c}
                
    if not trades: return None
    df_t = pd.DataFrame(trades)
    wins = df_t[df_t["win"] == 1]
    losses = df_t[df_t["win"] == 0]
    win_rate = len(wins)/len(df_t)*100
    pf = abs(wins["pnl"].sum() / losses["pnl"].sum()) if not losses.empty and losses["pnl"].sum() != 0 else 0
    return {"trades": len(trades), "wr": round(win_rate, 1), "pf": round(pf, 2), "ret": round((cap/initial_cap-1)*100, 2)}

AGS = [
    ("RSI Agent","You are RSI expert. Reply JSON only: {\"verdict\":\"OVERBOUGHT|OVERSOLD|NEUTRAL\",\"score\":-3 to 3,\"reason\":\"1 line\"}."),
    ("MACD Agent","You are MACD expert. Reply JSON only: {\"verdict\":\"BULL_CROSS|BEAR_CROSS|FLAT\",\"score\":-3 to 3,\"reason\":\"1 line\"}."),
    ("BB Agent","You are Bollinger expert. Reply JSON only: {\"verdict\":\"UPPER_BREAK|LOWER_BREAK|SQUEEZE\",\"score\":-3 to 3,\"reason\":\"1 line\"}."),
    ("EMA Agent","You are Trend expert. Reply JSON only: {\"verdict\":\"BULLISH|BEARISH|SIDEWAYS\",\"score\":-3 to 3,\"reason\":\"1 line\"}."),
    ("Vol Agent","You are Volume expert. Reply JSON only: {\"verdict\":\"HIGH|LOW|NORMAL\",\"score\":-3 to 3,\"reason\":\"1 line\"}."),
    ("VWAP Agent","You are VWAP expert. Reply JSON only: {\"verdict\":\"ABOVE_VWAP|BELOW_VWAP\",\"score\":-3 to 3,\"reason\":\"1 line\"}."),
    ("Stoch Agent","You are Stochastic expert. Reply JSON only: {\"verdict\":\"CROSS_UP|CROSS_DOWN|NEUTRAL\",\"score\":-3 to 3,\"reason\":\"1 line\"}."),
]

if "alerts" not in st.session_state: st.session_state.alerts = []
if "trades" not in st.session_state: st.session_state.trades = []
if "scan_res" not in st.session_state: st.session_state.scan_res = []

with st.sidebar:
    st.markdown("### Groq API Key")
    if GK: st.success("Loaded")
    else:
        uk = st.text_input("Key", type="password")
        if uk:
            try: cl = Groq(api_key=uk); MD = "openai/gpt-oss-120b"; st.success("Set!")
            except: st.error("Invalid")
        else: st.info("console.groq.com/keys")
    st.markdown("**PKT:** " + PKT())
    voice_on = st.checkbox("Voice", value=True)

bp = TX("BTCUSDT"); ep = TX("ETHUSDT")
c1, c2, c3 = st.columns(3)
c1.metric("BTC", "${:,.2f}".format(bp.get("p",0)) if bp else "-", "{:+.2f}%".format(bp.get("c",0)) if bp else None)
c2.metric("ETH", "${:,.2f}".format(ep.get("p",0)) if ep else "-", "{:+.2f}%".format(ep.get("c",0)) if ep else None)
c3.metric("PKT", PKT())
st.title("Pro Scanner + Backtest + LLM")

if st.session_state.alerts:
    st.markdown("### Alerts")
    for a in st.session_state.alerts[-3:][::-1]: st.markdown("<div class='sig'><b>" + a["time"] + "</b> - " + a["msg"] + "</div>", unsafe_allow_html=True)

T1, T2, T3, T4, T5 = st.tabs(["Scanner", "Chart", "Backtest", "LLM Debate", "Trades"])

with T1:
    st.markdown("### Scanner")
    mkt = st.radio("Market", ["SPOT", "FUTURES"], horizontal=True, key="m1")
    mid = "SPOT" if mkt == "SPOT" else "SWAP"
    n = st.slider("Coins", 10, 100, 30, 5)
    if st.button("Start Scan", type="primary"):
        al = COINS(mid); prog = st.progress(0); res = []
        for i, c in enumerate(al[:n]):
            prog.progress((i+1)/n)
            try:
                df = KL(c, "1h", 200, mid)
                if df.empty or len(df) < 100: continue
                df = IND(df); la = df.iloc[-1]
                p = float(la["c"]); r = float(la["rsi"]); v = float(la["vr"]); a = float(la["atr"])
                tr = "BULL" if la["e20"] > la["e50"] else "BEAR"
                t = TX(c, mid); cg = t.get("c", 0) if t else 0
                if tr == "BULL" and 40 < r < 65: sg = "LONG"
                elif tr == "BEAR" and 35 < r < 60: sg = "SHORT"
                else: sg = "WAIT"
                if sg == "LONG": e = p; sl = p-2*a; tp1 = p+1.5*a
                elif sg == "SHORT": e = p; sl = p+2*a; tp1 = p-1.5*a
                else: e = sl = tp1 = p
                st2 = (30 if sg != "WAIT" else 0) + (15 if 45 < r < 60 else 0) + (20 if v > 1.5 else 10 if v > 1.2 else 0) + min(int(abs(cg)), 20)
                if st2 >= 30: res.append({"Sym":c,"Px":round(p,6),"Tr":tr,"RSI":round(r,1),"VR":round(v,2),"Sig":sg,"Str":min(st2,100),"E":round(e,6),"SL":round(sl,6),"TP1":round(tp1,6)})
            except: pass
        prog.empty(); st.session_state.scan_res = sorted(res, key=lambda x: x["Str"], reverse=True)
    
    if st.session_state.scan_res:
        for r in st.session_state.scan_res[:10]:
            c = "#22c55e" if r["Sig"]=="LONG" else "#ef4444" if r["Sig"]=="SHORT" else "#f59e0b"
            st.markdown("<div class='sig' style='border-left-color:" + c + "'><b>" + r["Sym"] + " " + r["Sig"] + "</b> Score: " + str(r["Str"]) + "<br>E: $" + str(r["E"]) + " | SL: $" + str(r["SL"]) + " | TP1: $" + str(r["TP1"]) + "</div>", unsafe_allow_html=True)

with T2:
    st.markdown("### Chart")
    al = COINS("SPOT"); s = st.selectbox("Coin", al); iv = st.selectbox("TF", ["15m","1h","4h"])
    df = KL(s, iv, 300)
    if not df.empty:
        df = IND(df); df = df.dropna(subset=["o","h","l","c","e20","e50"])
        xs = [x.strftime("%Y-%m-%d %H:%M") if hasattr(x, "strftime") else str(x) for x in df["t"]]
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=xs, open=df["o"], high=df["h"], low=df["l"], close=df["c"], name=s), row=1, col=1)
        fig.add_trace(go.Scatter(x=xs, y=df["e20"], line=dict(color="cyan"), name="EMA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=xs, y=df["e50"], line=dict(color="yellow"), name="EMA50"), row=1, col=1)
        fig.add_trace(go.Bar(x=xs, y=df["v"], name="Vol"), row=2, col=1)
        fig.update_layout(template="plotly_dark", height=600, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

with T3:
    st.markdown("### Backtesting (EMA Cross + ATR SL/TP)")
    al = COINS("SPOT"); s_bt = st.selectbox("Coin (Backtest)", al, key="bt_c")
    iv_bt = st.selectbox("TF (Backtest)", ["15m","1h","4h"], key="bt_t")
    if st.button("Run Backtest"):
        df_bt = KL(s_bt, iv_bt, 500)
        if not df_bt.empty:
            df_bt = IND(df_bt)
            res = BACKTEST(df_bt)
            if res:
                st.success("Backtest Complete")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Trades", res["trades"])
                c2.metric("Win Rate", str(res["wr"]) + "%")
                c3.metric("Profit Factor", res["pf"])
                c4.metric("Total Return", str(res["ret"]) + "%")
            else: st.warning("Not enough trades generated.")
            
with T4:
    st.markdown("### LLM Debate (7 Indicator Agents)")
    if not GK: st.warning("Add Groq key")
    else:
        mkt = st.radio("Market", ["SPOT","FUTURES"], horizontal=True, key="ml")
        mid = "SPOT" if mkt == "SPOT" else "SWAP"
        ls = st.selectbox("Coin", COINS(mid), key="l1")
        if st.button("Run Debate", type="primary"):
            df = KL(ls, "1h", 200, mid)
            if not df.empty:
                df = IND(df); la = df.iloc[-1]
                nt = f"Price: {la['c']:.4f} | RSI: {la['rsi']:.2f} | MACD: {la['mhist']:.4f} | BBU: {la['bbu']:.4f} | BBL: {la['bbl']:.4f} | EMA20: {la['e20']:.4f} | EMA50: {la['e50']:.4f} | VolRatio: {la['vr']:.2f} | VWAP: {la['vwap']:.4f} | Stoch: {la['sk']:.2f}"
                res1 = []
                for nm, sp_ in AGS:
                    rr, ee = LLM(sp_, nt, 150)
                    if not ee:
                        d = PJ(rr)
                        if d: res1.append({"n":nm,"v":d.get("verdict","?"),"s":d.get("score",0),"r":d.get("reason","")})
                for a in res1:
                    vc = "#22c55e" if a["s"] > 0 else "#ef4444" if a["s"] < 0 else "#f59e0b"
                    st.markdown(f"<div class='llm' style='border-left-color:{vc}'><b>{a['n']}</b> -> <b style='color:{vc}'>{a['v']}</b> ({a['s']})<br>{a['r']}</div>", unsafe_allow_html=True)
                
                sm = "\n".join([f"{a['n']}: {a['v']}" for a in res1])
                sy3 = "You are Chief. Reply JSON: {\"decision\":\"BUY|SELL|HOLD\",\"confidence\":0-100,\"reasoning\":\"2 lines\"}."
                rr, ee = LLM(sy3, nt + "\n\n" + sm, 200)
                if not ee:
                    d3 = PJ(rr)
                    if d3:
                        dec = d3.get("decision","HOLD")
                        st.markdown(f"### Chief Decision: {dec} ({d3.get('confidence',0)}%)")
                        st.write(d3.get("reasoning",""))

with T5:
    st.markdown("### Trades")
    for t in st.session_state.trades[-10:][::-1]:
        st.write(f"{t['coin']} {t['side']} @ {t['entry']} | PnL: (after fees)")

st.caption("Pro Scanner - " + PKTDT() + " PKT")
