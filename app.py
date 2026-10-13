import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time, os, json

st.set_page_config(page_title="LLM Agent Scanner PRO", page_icon="🧠", layout="wide")

st.markdown("""
<style>
.stApp{background:#0b0f17;color:#e5e7eb}
.card{background:#111827;border-radius:12px;padding:14px;border:1px solid #1f2937;margin:8px 0}
.buy{color:#22c55e;font-weight:800}
.sell{color:#ef4444;font-weight:800}
.hold{color:#f59e0b;font-weight:800}
.agent{background:#0f172a;border-radius:10px;padding:12px;margin:8px 0;border-left:4px solid #3b82f6}
.llm-box{background:#1e1b4b;border-radius:10px;padding:12px;margin:8px 0;border-left:4px solid #a855f7}
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
if GROQ_AVAILABLE and GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)
    LLM_MODEL = "llama-3.3-70b-versatile"
else:
    client = None
    LLM_MODEL = None

def llm_call(system_prompt, user_prompt, max_tokens=500):
    if client is None: return None, "❌ Groq API key missing"
    try:
        c = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role":"system","content":system_prompt},
                      {"role":"user","content":user_prompt}],
            temperature=0.3, max_tokens=max_tokens, top_p=0.9)
        return c.choices[0].message.content, None
    except Exception as e:
        return None, f"LLM error: {str(e)[:200]}"

# ============ MULTI-SOURCE DATA (OKX → Bybit → CoinGecko) ============
COINS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT",
         "ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","LTCUSDT","BCHUSDT",
         "UNIUSDT","SUIUSDT","TRXUSDT","APTUSDT","ATOMUSDT","NEARUSDT",
         "INJUSDT","MATICUSDT","SHIBUSDT","PEPEUSDT","OPUSDT","ARBUSDT",
         "TIAUSDT","FILUSDT","ETCUSDT","HBARUSDT","VETUSDT","RUNEUSDT"]

CG_MAP = {"BTCUSDT":"bitcoin","ETHUSDT":"ethereum","SOLUSDT":"solana",
    "BNBUSDT":"binancecoin","XRPUSDT":"ripple","DOGEUSDT":"dogecoin",
    "ADAUSDT":"cardano","AVAXUSDT":"avalanche-2","LINKUSDT":"chainlink",
    "DOTUSDT":"polkadot","LTCUSDT":"litecoin","BCHUSDT":"bitcoin-cash",
    "UNIUSDT":"uniswap","SUIUSDT":"sui","TRXUSDT":"tron","APTUSDT":"aptos",
    "ATOMUSDT":"cosmos","NEARUSDT":"near","INJUSDT":"injective-protocol",
    "MATICUSDT":"matic-network","SHIBUSDT":"shiba-inu","PEPEUSDT":"pepe",
    "OPUSDT":"optimism","ARBUSDT":"arbitrum","TIAUSDT":"celestia",
    "FILUSDT":"filecoin","ETCUSDT":"ethereum-classic",
    "HBARUSDT":"hedera-hashgraph","VETUSDT":"vechain","RUNEUSDT":"thorchain"}

DATA_SOURCE = {"klines":"?", "price":"?"}

# ---- OKX ----
def _okx_klines(sym, itv, lim):
    try:
        s = sym.replace("USDT","-USDT")
        bar = {"15m":"15m","1h":"1H","4h":"4H","1d":"1D"}.get(itv,"1H")
        r = requests.get("https://www.okx.com/api/v5/market/candles",
                         params={"instId":s,"bar":bar,"limit":min(lim,300)},
                         timeout=8).json()
        if r.get("code") != "0" or not r.get("data"): return pd.DataFrame()
        d = r["data"]
        df = pd.DataFrame(d, columns=["t","o","h","l","c","v","vq","vc","confirm"])
        for col in ["o","h","l","c","v"]: df[col] = df[col].astype(float)
        df["t"] = pd.to_datetime(df["t"].astype(float), unit="ms")
        return df[["t","o","h","l","c","v"]].sort_values("t").reset_index(drop=True)
    except Exception: return pd.DataFrame()

def _okx_ticker(sym):
    try:
        s = sym.replace("USDT","-USDT")
        r = requests.get("https://www.okx.com/api/v5/market/ticker",
                         params={"instId":s}, timeout=6).json()
        if r.get("code") != "0" or not r.get("data"): return {}
        d = r["data"][0]
        last = float(d["last"]); op = float(d["open24h"])
        chg = (last-op)/op*100 if op else 0
        return {"lastPrice":str(last),"priceChangePercent":chg,
                "highPrice":d.get("high24h","—"),"lowPrice":d.get("low24h","—"),
                "quoteVolume":d.get("volCcy24h","0")}
    except Exception: return {}

# ---- Bybit ----
def _bybit_klines(sym, itv, lim):
    try:
        interval = {"15m":"15","1h":"60","4h":"240","1d":"D"}.get(itv,"60")
        r = requests.get("https://api.bybit.com/v5/market/kline",
                         params={"category":"spot","symbol":sym,"interval":interval,"limit":min(lim,300)},
                         timeout=8).json()
        if r.get("retCode") != 0 or not r.get("result",{}).get("list"): return pd.DataFrame()
        d = r["result"]["list"]
        df = pd.DataFrame(d, columns=["t","o","h","l","c","v","turnover"])
        for col in ["o","h","l","c","v"]: df[col] = df[col].astype(float)
        df["t"] = pd.to_datetime(df["t"].astype(float), unit="ms")
        return df[["t","o","h","l","c","v"]].sort_values("t").reset_index(drop=True)
    except Exception: return pd.DataFrame()

def _bybit_ticker(sym):
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers",
                         params={"category":"spot","symbol":sym}, timeout=6).json()
        if r.get("retCode") != 0: return {}
        d = r["result"]["list"][0]
        return {"lastPrice":d.get("lastPrice","0"),
                "priceChangePercent":float(d.get("price24hPcnt",0))*100,
                "highPrice":d.get("highPrice24h","—"),"lowPrice":d.get("lowPrice24h","—"),
                "quoteVolume":d.get("turnover24h","0")}
    except Exception: return {}

# ---- CoinGecko (price only) ----
def _cg_price(sym):
    try:
        cg = CG_MAP.get(sym)
        if not cg: return None
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                         params={"ids":cg,"vs_currencies":"usd","include_24hr_change":"true"},
                         timeout=8).json()
        if cg not in r: return None
        d = r[cg]
        return {"lastPrice":str(d["usd"]),
                "priceChangePercent":d.get("usd_24h_change",0),
                "highPrice":"—","lowPrice":"—","quoteVolume":"0"}
    except Exception: return None

# ---- Master fetchers with fallback ----
@st.cache_data(ttl=30)
def klines(sym, itv="1h", lim=300):
    df = _okx_klines(sym, itv, lim)
    if not df.empty:
        DATA_SOURCE["klines"] = "OKX ✅"
        return df
    df = _bybit_klines(sym, itv, lim)
    if not df.empty:
        DATA_SOURCE["klines"] = "Bybit ✅"
        return df
    DATA_SOURCE["klines"] = "FAILED ❌"
    return pd.DataFrame()

@st.cache_data(ttl=15)
def ticker24(sym):
    t = _okx_ticker(sym)
    if t:
        DATA_SOURCE["price"] = "OKX ✅"
        return t
    t = _bybit_ticker(sym)
    if t:
        DATA_SOURCE["price"] = "Bybit ✅"
        return t
    t = _cg_price(sym)
    if t:
        DATA_SOURCE["price"] = "CoinGecko ✅"
        return t
    DATA_SOURCE["price"] = "FAILED ❌"
    return {}

@st.cache_data(ttl=15)
def price_now(sym):
    t = ticker24(sym)
    if t and t.get("lastPrice"):
        try: return float(t["lastPrice"])
        except Exception: return None
    return None

# ============ INDICATORS ============
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
    return df

def find_zones(df, lb=5):
    H = df["h"].values; L = df["l"].values; T = df["t"].values
    res = []; sup = []
    for i in range(lb, len(df)-lb):
        if H[i] == max(H[i-lb:i+lb+1]): res.append((T[i], H[i]))
        if L[i] == min(L[i-lb:i+lb+1]): sup.append((T[i], L[i]))
    return sup[-3:], res[-3:]

# ============ REAL LLM AGENTS ============
def build_market_snapshot(sym, itv):
    df = klines(sym, itv, 200)
    if df.empty: return None, None
    df = add_indicators(df)
    sup, res = find_zones(df)
    last = df.iloc[-1]
    t24 = ticker24(sym)
    px = float(last["c"])
    snap = {"symbol":sym,"timeframe":itv,"price":round(px,4),
        "ema20":round(float(last["ema20"]),4),"ema50":round(float(last["ema50"]),4),
        "ema200":round(float(last["ema200"]),4) if not pd.isna(last["ema200"]) else None,
        "rsi":round(float(last["rsi"]),2) if not pd.isna(last["rsi"]) else None,
        "atr":round(float(last["atr"]),4) if not pd.isna(last["atr"]) else None,
        "macd":round(float(last["macd"]),4) if not pd.isna(last["macd"]) else None,
        "macd_signal":round(float(last["macd_sig"]),4) if not pd.isna(last["macd_sig"]) else None,
        "volume_ratio":round(float(last["vr"]),2) if not pd.isna(last["vr"]) else None,
        "high_24h":t24.get("highPrice"),"low_24h":t24.get("lowPrice"),
        "change_24h":round(t24.get("priceChangePercent",0),2),
        "supports":[round(float(p),4) for _,p in sup],
        "resistances":[round(float(p),4) for _,p in res],
        "recent_candles":df.tail(10)[["t","o","h","l","c","v"]].astype(str).to_dict("records")}
    return snap, df

AGENTS = [
    {"name":"📈 Trend Analyst","system":"You are a professional crypto trend analyst. Reply JSON only: {\"verdict\":\"BULLISH|BEARISH|SIDEWAYS\",\"score\":-3 to +3,\"reason\":\"1 short line\"}."},
    {"name":"⚡ Momentum Analyst","system":"You are a momentum specialist. Reply JSON only: {\"verdict\":\"STRONG|WEAK|OVERSOLD|OVERBOUGHT|NEUTRAL\",\"score\":-3 to +3,\"reason\":\"1 short line\"}."},
    {"name":"🐳 Volume Analyst","system":"You are a volume expert. Reply JSON only: {\"verdict\":\"HIGH_VOLUME|NORMAL|LOW_VOLUME\",\"score\":-3 to +3,\"reason\":\"1 short line\"}."},
    {"name":"🛡️ Risk Manager","system":"You are a risk manager. Reply JSON only: {\"verdict\":\"LOW_RISK|MEDIUM_RISK|HIGH_RISK\",\"score\":-3 to +3,\"sl_price\":number,\"reason\":\"1 short line\"}."},
    {"name":"🎯 S/R Analyst","system":"You are an S/R expert. Reply JSON only: {\"verdict\":\"NEAR_SUPPORT|NEAR_RESISTANCE|MID_RANGE\",\"score\":-3 to +3,\"reason\":\"1 short line\"}."}
]

def run_real_agents(sym, itv):
    snap, df = build_market_snapshot(sym, itv)
    if snap is None: return None, "Data fetch failed"
    out = []
    for a in AGENTS:
        prompt = (f"Analyze {snap['symbol']} {snap['timeframe']}:\n"
                  f"Price: {snap['price']}\nEMA20: {snap['ema20']}\nEMA50: {snap['ema50']}\n"
                  f"EMA200: {snap['ema200']}\nRSI: {snap['rsi']}\nMACD: {snap['macd']}\n"
                  f"MACD Sig: {snap['macd_signal']}\nVolRatio: {snap['volume_ratio']}\n"
                  f"24h Chg: {snap['change_24h']}%\nSupports: {snap['supports']}\n"
                  f"Resistances: {snap['resistances']}\nRecent: {snap['recent_candles']}")
        resp, err = llm_call(a["system"], prompt, max_tokens=200)
        if err:
            out.append({"name":a["name"],"verdict":"ERROR","score":0,"reason":err,"raw":err}); continue
        try:
            txt = resp.strip()
            if "```" in txt: txt = txt.split("```")[1].replace("json","").strip()
            d = json.loads(txt)
            out.append({"name":a["name"],"verdict":d.get("verdict","UNKNOWN"),
                        "score":int(d.get("score",0)),"reason":d.get("reason",""),
                        "sl_price":d.get("sl_price"),"raw":resp})
        except Exception:
            out.append({"name":a["name"],"verdict":"PARSE_ERROR","score":0,
                        "reason":resp[:120] if resp else "Empty","raw":resp or ""})
    return out, None

def llm_consensus(snap, results):
    summary = "\n".join([f"{a['name']}: {a['verdict']} ({a['score']:+d}) — {a['reason']}" for a in results])
    system = 'You are the Chief Trading Officer. Reply JSON only: {"decision":"BUY|SELL|HOLD","confidence":0-100,"entry":number,"sl":number,"tp1":number,"tp2":number,"tp3":number,"reasoning":"2 lines"}.'
    prompt = (f"Market: {snap['symbol']} {snap['timeframe']}\nPrice: {snap['price']}\n"
              f"ATR: {snap['atr']}\nRSI: {snap['rsi']}\nVolRatio: {snap['volume_ratio']}\n"
              f"Supports: {snap['supports']}\nResistances: {snap['resistances']}\n\n"
              f"Analyst Reports:\n{summary}\n\nGive final trading decision.")
    resp, err = llm_call(system, prompt, max_tokens=400)
    if err: return None, err
    try:
        txt = resp.strip()
        if "```" in txt: txt = txt.split("```")[1].replace("json","").strip()
        return json.loads(txt), None
    except Exception:
        return None, f"Parse failed: {resp[:200]}"

# ============ SIDEBAR ============
with st.sidebar:
    st.markdown("### 🔑 Groq API Key")
    if GROQ_API_KEY: st.success("✅ Key loaded")
    else:
        uk = st.text_input("Paste Groq API key", type="password")
        if uk:
            GROQ_API_KEY = uk
            try:
                client = Groq(api_key=uk); LLM_MODEL = "llama-3.3-70b-versatile"
                st.success("✅ Key set!")
            except Exception as e: st.error(f"Invalid: {e}")
        else: st.warning("Free key: [console.groq.com](https://console.groq.com/keys)")
    st.markdown("---")
    st.markdown(f"**Model:** `{LLM_MODEL or 'not set'}`")
    st.markdown("**Data:** OKX → Bybit → CoinGecko")
    st.caption("3-source fallback = no failure")

# ============ HEADER ============
btc_p = price_now("BTCUSDT")
btc_24 = ticker24("BTCUSDT")
btc_chg = btc_24.get("priceChangePercent",0) if btc_24 else 0

c1,c2,c3,c4 = st.columns(4)
c1.metric("BTC/USDT", f"${btc_p:,.2f}" if btc_p else "—", f"{btc_chg:+.2f}%" if btc_24 else None)
eth_p = price_now("ETHUSDT"); c2.metric("ETH/USDT", f"${eth_p:,.2f}" if eth_p else "—")
sol_p = price_now("SOLUSDT"); c3.metric("SOL/USDT", f"${sol_p:,.2f}" if sol_p else "—")
c4.metric("Time", datetime.now().strftime("%H:%M:%S"))

st.title("🧠 Real LLM Agent Scanner")
if not GROQ_API_KEY:
    st.error("⚠️ Groq key missing! Sidebar me paste karo.")
else:
    st.success(f"✅ Real LLM: **{LLM_MODEL}** — 5 Agents, Real AI Calls")
st.caption(f"Data: {DATA_SOURCE['price']} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ============ TABS ============
tab1, tab2, tab3 = st.tabs(["🧠 LLM Agents","📈 Chart","📊 Signals"])

# ---------- TAB 1 ----------
with tab1:
    st.markdown("### 🧠 Real LLM Agent Discussion")
    if not GROQ_API_KEY:
        st.warning("Pehle sidebar me Groq API key daalo.")
    else:
        c1,c2 = st.columns([2,1])
        sym = c1.selectbox("Coin", COINS, index=0, key="llm_sym")
        itv = c2.selectbox("TF", ["15m","1h","4h"], index=1, key="llm_tf")
        if st.button("🚀 Run LLM Agents", type="primary"):
            with st.spinner(f"5 LLM agents analyzing {sym}..."):
                t0 = time.time()
                snap, df = build_market_snapshot(sym, itv)
                if snap is None:
                    st.error(f"❌ Data nahi mila. Source: {DATA_SOURCE['klines']}. Dusra coin try karo.")
                else:
                    st.markdown(f"""<div class='card'><b>Price:</b> ${snap['price']} | <b>EMA20:</b> {snap['ema20']} | <b>EMA50:</b> {snap['ema50']} | <b>RSI:</b> {snap['rsi']} | <b>ATR:</b> {snap['atr']} | <b>Vol:</b> {snap['volume_ratio']}x | <b>24h:</b> {snap['change_24h']}% <span style='color:#94a3b8'>[{DATA_SOURCE['klines']}]</span></div>""", unsafe_allow_html=True)
                    results, err = run_real_agents(sym, itv)
                    if err: st.error(f"❌ {err}")
                    else:
                        st.markdown("#### 🗣️ Agent Verdicts")
                        for a in results:
                            vcol = "#22c55e" if a['score']>0 else "#ef4444" if a['score']<0 else "#f59e0b"
                            sl = f"<br><b>Suggested SL:</b> ${a['sl_price']}" if a.get('sl_price') else ""
                            st.markdown(f"<div class='llm-box' style='border-left-color:{vcol}'><b>{a['name']}</b> → <b style='color:{vcol};font-size:16px'>{a['verdict']}</b> <span style='color:#94a3b8'>(score: {a['score']:+d})</span><br><span style='color:#cbd5e1;font-size:13px'>{a['reason']}</span>{sl}</div>", unsafe_allow_html=True)
                        st.markdown("#### 👑 Chief LLM Consensus")
                        with st.spinner("Chief LLM deciding..."):
                            cons, cerr = llm_consensus(snap, results)
                            if cerr: st.error(f"❌ {cerr}")
                            else:
                                dec = cons.get("decision","HOLD"); conf = cons.get("confidence",0)
                                dcol = "#22c55e" if dec=="BUY" else "#ef4444" if dec=="SELL" else "#f59e0b"
                                st.markdown(f"""<div class='card' style='border:3px solid {dcol};text-align:center'><div style='color:#94a3b8;font-size:13px'>FINAL DECISION</div><div style='color:{dcol};font-size:36px;font-weight:900;margin:8px 0'>{dec}</div><div style='color:white'>Confidence: <b>{conf}%</b></div><div style='margin-top:14px;font-size:15px'><b>Entry:</b> ${cons.get('entry',snap['price'])} | <b>SL:</b> <span class='sell'>${cons.get('sl','—')}</span> | <b>TP1:</b> <span class='buy'>${cons.get('tp1','—')}</span> | <b>TP2:</b> <span class='buy'>${cons.get('tp2','—')}</span> | <b>TP3:</b> <span class='buy'>${cons.get('tp3','—')}</span></div><div style='margin-top:12px;color:#cbd5e1;font-style:italic'>"{cons.get('reasoning','')}"</div></div>""", unsafe_allow_html=True)
                        st.caption(f"✅ {time.time()-t0:.1f}s — {len(AGENTS)+1} real LLM calls")

# ---------- TAB 2 ----------
with tab2:
    st.markdown("### 📈 Chart + Zones")
    c1,c2 = st.columns([2,1])
    sym2 = c1.selectbox("Coin", COINS, index=0, key="chart_sym")
    itv2 = c2.selectbox("TF", ["15m","1h","4h","1d"], index=1, key="chart_tf")
    df = klines(sym2, itv2, 300)
    if df.empty:
        st.error(f"❌ Data nahi mila. Source: {DATA_SOURCE['klines']}")
    else:
        df = add_indicators(df)
        sup, res = find_zones(df)
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                            row_heights=[0.6,0.18,0.22], subplot_titles=("","Volume","RSI"))
        fig.add_trace(go.Candlestick(x=df["t"],open=df["o"],high=df["h"],low=df["l"],close=df["c"],
            name=sym2.replace("USDT",""),increasing_line_color="#22c55e",increasing_fillcolor="#22c55e",
            decreasing_line_color="#ef4444",decreasing_fillcolor="#ef4444"), row=1,col=1)
        fig.add_trace(go.Scatter(x=df["t"],y=df["ema20"],line=dict(color="#22d3ee",width=1.5),name="EMA20"),row=1,col=1)
        fig.add_trace(go.Scatter(x=df["t"],y=df["ema50"],line=dict(color="#fbbf24",width=1.5),name="EMA50"),row=1,col=1)
        for t,p in res:
            fig.add_hrect(y0=p*0.997,y1=p*1.003,fillcolor="#ef4444",opacity=0.12,line_width=0,row=1,col=1)
            fig.add_hline(y=p,line_dash="dash",line_color="#ef4444",annotation_text=f"RES {p:,.2f}",annotation_position="right",row=1,col=1)
        for t,p in sup:
            fig.add_hrect(y0=p*0.997,y1=p*1.003,fillcolor="#22c55e",opacity=0.12,line_width=0,row=1,col=1)
            fig.add_hline(y=p,line_dash="dash",line_color="#22c55e",annotation_text=f"SUP {p:,.2f}",annotation_position="right",row=1,col=1)
        
