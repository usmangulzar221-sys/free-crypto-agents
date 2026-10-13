import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time
import os
import json

st.set_page_config(page_title="LLM Agent Scanner PRO", page_icon="🧠", layout="wide")

st.markdown("""
<style>
.stApp{background:#0b0f17;color:#e5e7eb}
.card{background:#111827;border-radius:12px;padding:14px;border:1px solid #1f2937;margin:8px 0}
.buy{color:#22c55e;font-weight:800}
.sell{color:#ef4444;font-weight:800}
.hold{color:#f59e0b;font-weight:800}
.agent{background:#0f172a;border-radius:10px;padding:12px;margin:8px 0;border-left:4px solid #3b82f6}
.bar{height:10px;border-radius:5px;background:#1f2937;overflow:hidden;margin-top:6px}
.bar>div{height:100%;transition:width .3s}
.llm-box{background:#1e1b4b;border-radius:10px;padding:12px;margin:8px 0;border-left:4px solid #a855f7}
</style>
""", unsafe_allow_html=True)

# ============ GROQ LLM SETUP ============
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

def get_groq_key():
    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return os.environ.get("GROQ_API_KEY", "")

GROQ_API_KEY = get_groq_key()

if GROQ_AVAILABLE and GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)
    LLM_MODEL = "llama-3.3-70b-versatile"
else:
    client = None
    LLM_MODEL = None

def llm_call(system_prompt, user_prompt, max_tokens=500):
    if client is None:
        return None, "❌ Groq API key missing. Sidebar me daalo."
    try:
        completion = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=max_tokens,
            top_p=0.9,
        )
        return completion.choices[0].message.content, None
    except Exception as e:
        return None, f"LLM error: {str(e)[:200]}"

# ============ BYBIT API (Reliable on Streamlit Cloud) ============
BASE = "https://api.bybit.com/v5/market"
TF_MAP = {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}
COINS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT",
         "ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","LTCUSDT","BCHUSDT",
         "UNIUSDT","SUIUSDT","TRXUSDT","APTUSDT","ATOMUSDT","NEARUSDT",
         "INJUSDT","MATICUSDT","SHIBUSDT","PEPEUSDT","OPUSDT","ARBUSDT",
         "TIAUSDT","FILUSDT","ETCUSDT","HBARUSDT","VETUSDT","RUNEUSDT"]

@st.cache_data(ttl=20)
def klines(sym, itv="1h", lim=300):
    try:
        interval = TF_MAP.get(itv, "60")
        r = requests.get(f"{BASE}/kline",
                         params={"category": "spot", "symbol": sym, "interval": interval, "limit": lim},
                         timeout=8).json()
        if r.get("retCode") != 0: return pd.DataFrame()
        data = r["result"]["list"]
        df = pd.DataFrame(data, columns=["t","o","h","l","c","v","turnover"])
        for col in ["o","h","l","c","v"]:
            df[col] = df[col].astype(float)
        df["t"] = pd.to_datetime(df["t"].astype(float), unit="ms")
        df = df.sort_values("t").reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=15)
def ticker24(sym):
    try:
        r = requests.get(f"{BASE}/tickers",
                         params={"category": "spot", "symbol": sym},
                         timeout=6).json()
        if r.get("retCode") != 0: return {}
        d = r["result"]["list"][0]
        return {
            "lastPrice": d.get("lastPrice"),
            "priceChangePercent": float(d.get("price24hPcnt", 0)) * 100, # Convert to %
            "highPrice": d.get("highPrice24h"),
            "lowPrice": d.get("lowPrice24h"),
            "quoteVolume": d.get("turnover24h")
        }
    except Exception:
        return {}

@st.cache_data(ttl=15)
def price_now(sym):
    t = ticker24(sym)
    if t and t.get("lastPrice"):
        try: return float(t["lastPrice"])
        except: return None
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
    df["rsi"] = 100 - 100 / (1 + g / l.replace(0, np.nan))
    tr = pd.concat([df["h"]-df["l"],
                    (df["h"]-df["c"].shift()).abs(),
                    (df["l"]-df["c"].shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["vavg"] = df["v"].rolling(20).mean()
    df["vr"] = df["v"] / df["vavg"]
    exp1 = df["c"].ewm(span=12, adjust=False).mean()
    exp2 = df["c"].ewm(span=26, adjust=False).mean()
    df["macd"] = exp1 - exp2
    df["macd_sig"] = df["macd"].ewm(span=9, adjust=False).mean()
    return df

def find_zones(df, lb=5):
    H = df["h"].values; L = df["l"].values; T = df["t"].values
    res = []; sup = []
    for i in range(lb, len(df) - lb):
        if H[i] == max(H[i-lb:i+lb+1]): res.append((T[i], H[i]))
        if L[i] == min(L[i-lb:i+lb+1]): sup.append((T[i], L[i]))
    return sup[-3:], res[-3:]

# ============ REAL LLM AGENTS ============
def build_market_snapshot(sym, itv):
    df = klines(sym, itv, 200)
    if df.empty:
        return None, None
    df = add_indicators(df)
    sup, res = find_zones(df)
    last = df.iloc[-1]
    t24 = ticker24(sym)
    px = float(last["c"])
    snapshot = {
        "symbol": sym, "timeframe": itv, "price": round(px, 4),
        "ema20": round(float(last["ema20"]), 4),
        "ema50": round(float(last["ema50"]), 4),
        "ema200": round(float(last["ema200"]), 4) if not pd.isna(last["ema200"]) else None,
        "rsi": round(float(last["rsi"]), 2) if not pd.isna(last["rsi"]) else None,
        "atr": round(float(last["atr"]), 4) if not pd.isna(last["atr"]) else None,
        "macd": round(float(last["macd"]), 4) if not pd.isna(last["macd"]) else None,
        "macd_signal": round(float(last["macd_sig"]), 4) if not pd.isna(last["macd_sig"]) else None,
        "volume_ratio": round(float(last["vr"]), 2) if not pd.isna(last["vr"]) else None,
        "high_24h": t24.get("highPrice"), "low_24h": t24.get("lowPrice"),
        "change_24h": round(t24.get("priceChangePercent", 0), 2),
        "supports": [round(float(p), 4) for _, p in sup],
        "resistances": [round(float(p), 4) for _, p in res],
        "recent_candles": df.tail(10)[["t","o","h","l","c","v"]].astype(str).to_dict("records")
    }
    return snapshot, df

AGENTS = [
    {"name": "📈 Trend Analyst", "system": "You are a professional crypto trend analyst. Reply JSON only: {\"verdict\":\"BULLISH|BEARISH|SIDEWAYS\",\"score\":-3 to +3,\"reason\":\"1 short line\"}."},
    {"name": "⚡ Momentum Analyst", "system": "You are a momentum specialist. Reply JSON only: {\"verdict\":\"STRONG|WEAK|OVERSOLD|OVERBOUGHT|NEUTRAL\",\"score\":-3 to +3,\"reason\":\"1 short line\"}."},
    {"name": "🐳 Volume Analyst", "system": "You are a volume expert. Reply JSON only: {\"verdict\":\"HIGH_VOLUME|NORMAL|LOW_VOLUME\",\"score\":-3 to +3,\"reason\":\"1 short line\"}."},
    {"name": "🛡️ Risk Manager", "system": "You are a risk manager. Reply JSON only: {\"verdict\":\"LOW_RISK|MEDIUM_RISK|HIGH_RISK\",\"score\":-3 to +3,\"sl_price\":number,\"reason\":\"1 short line\"}."},
    {"name": "🎯 S/R Analyst", "system": "You are an S/R expert. Reply JSON only: {\"verdict\":\"NEAR_SUPPORT|NEAR_RESISTANCE|MID_RANGE\",\"score\":-3 to +3,\"reason\":\"1 short line\"}."}
]

def run_real_agents(sym, itv):
    snapshot, df = build_market_snapshot(sym, itv)
    if snapshot is None: return None, "Data fetch failed"
    results = []
    for agent in AGENTS:
        prompt = f"Analyze {snapshot['symbol']} {snapshot['timeframe']}:\nPrice: {snapshot['price']}\nEMA20: {snapshot['ema20']}\nEMA50: {snapshot['ema50']}\nEMA200: {snapshot['ema200']}\nRSI: {snapshot['rsi']}\nMACD: {snapshot['macd']}\nMACD Sig: {snapshot['macd_signal']}\nVolRatio: {snapshot['volume_ratio']}\n24h Chg: {snapshot['change_24h']}%\nSupports: {snapshot['supports']}\nResistances: {snapshot['resistances']}\nRecent: {snapshot['recent_candles']}"
        response, err = llm_call(agent["system"], prompt, max_tokens=200)
        if err:
            results.append({"name": agent["name"], "verdict": "ERROR", "score": 0, "reason": err, "raw": err})
            continue
        try:
            txt = response.strip()
            if "```" in txt: txt = txt.split("```")[1].replace("json","").strip()
            data = json.loads(txt)
            results.append({"name": agent["name"], "verdict": data.get("verdict","UNKNOWN"),
                            "score": int(data.get("score",0)), "reason": data.get("reason",""),
                            "sl_price": data.get("sl_price"), "raw": response})
        except Exception:
            results.append({"name": agent["name"], "verdict": "PARSE_ERROR", "score": 0,
                            "reason": response[:120] if response else "Empty", "raw": response or ""})
    return results, None

def llm_consensus(snapshot, agent_results):
    summary = "\n".join([f"{a['name']}: {a['verdict']} (score {a['score']}) — {a['reason']}" for a in agent_results])
    system = 'You are the Chief Trading Officer. Reply JSON only: {"decision":"BUY|SELL|HOLD","confidence":0-100,"entry":number,"sl":number,"tp1":number,"tp2":number,"tp3":number,"reasoning":"2 lines"}. No extra text.'
    prompt = f"Market: {snapshot['symbol']} {snapshot['timeframe']}\nPrice: {snapshot['price']}\nATR: {snapshot['atr']}\nRSI: {snapshot['rsi']}\nVolRatio: {snapshot['volume_ratio']}\nSupports: {snapshot['supports']}\nResistances: {snapshot['resistances']}\n\nAnalyst Reports:\n{summary}\n\nGive final decision."
    response, err = llm_call(system, prompt, max_tokens=400)
    if err: return None, err
    try:
        txt = response.strip()
        if "```" in txt: txt = txt.split("```")[1].replace("json","").strip()
        return json.loads(txt), None
    except Exception:
        return None, f"Parse failed: {response[:200]}"

# ============ SIDEBAR ============
with st.sidebar:
    st.markdown("### 🔑 Groq API Key")
    if GROQ_API_KEY:
        st.success("✅ Key loaded successfully")
    else:
        user_key = st.text_input("Paste Groq API key", type="password")
        if user_key:
            GROQ_API_KEY = user_key
            try:
                client = Groq(api_key=user_key)
                LLM_MODEL = "llama-3.3-70b-versatile"
                st.success("✅ Key set!")
            except Exception as e:
                st.error(f"Invalid key: {e}")
        else:
            st.warning("⚠️ Free key: [console.groq.com](https://console.groq.com/keys)")
    st.markdown("---")
    st.markdown(f"**LLM Model:** `{LLM_MODEL or 'not set'}`")
    st.markdown(f"**Data Source:** Bybit Public API")
    st.caption("No API key needed for market data")

# ============ HEADER ============
btc_p = price_now("BTCUSDT")
btc_24 = ticker24("BTCUSDT")
btc_chg = btc_24.get("priceChangePercent", 0) if btc_24 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("BTC/USDT", f"${btc_p:,.2f}" if btc_p else "—", f"{btc_chg:+.2f}%" if btc_24 else None)
eth_p = price_now("ETHUSDT")
col2.metric("ETH/USDT", f"${eth_p:,.2f}" if eth_p else "—")
sol_p = price_now("SOLUSDT")
col3.metric("SOL/USDT", f"${sol_p:,.2f}" if sol_p else "—")
col4.metric("Time", datetime.now().strftime("%H:%M:%S"))

st.title("🧠 Real LLM Agent Scanner — Bybit Data + Groq AI")
if not GROQ_API_KEY:
    st.error("⚠️ Groq API key missing! Sidebar me paste karo. [Free key yahan se lo](https://console.groq.com/keys)")
else:
    st.success(f"✅ Real LLM Active: **{LLM_MODEL}** — 5 Agents, Har Agent Real AI Call")

st.caption(f"Live Bybit Data • Real LLM Analysis • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ============ TABS ============
tab1, tab2, tab3, tab4 = st.tabs([
    "🧠 LLM Agent Discussion",
    "📈 Chart + Zones",
    "🔔 Multi-Coin LLM Scanner",
    "📊 Signals Tracker"
])

# ================== TAB 1 : LLM AGENTS ==================
with tab1:
    st.markdown("### 🧠 Real LLM Agent Discussion")
    if not GROQ_API_KEY:
        st.warning("Pehle sidebar me Groq API key daalo.")
    else:
        c1, c2 = st.columns([2, 1])
        sym = c1.selectbox("Coin", COINS, index=0, key="llm_sym")
        itv = c2.selectbox("Timeframe", ["15m","1h","4h"], index=1, key="llm_tf")

        if st.button("🚀 Run LLM Agents", type="primary"):
            with st.spinner(f"5 Real LLM agents analyzing {sym}... (approx 15-30s)"):
                start = time.time()
                snapshot, df = build_market_snapshot(sym, itv)
                if snapshot is None:
                    st.error("❌ Bybit data nahi mila. Dusra coin ya timeframe try karo.")
                else:
                    results, err = run_real_agents(sym, itv)
                    if err:
                        st.error(f"❌ {err}")
                    else:
                        st.markdown("#### 📊 Market Snapshot (Real Bybit Data)")
                        st.markdown(f"""
                        <div class='card'>
                        <b>Price:</b> ${snapshot['price']} &nbsp;|&nbsp;
                        <b>EMA20:</b> {snapshot['ema20']} &nbsp;|&nbsp;
                        <b>EMA50:</b> {snapshot['ema50']} &nbsp;|&nbsp;
                        <b>RSI:</b> {snapshot['rsi']} &nbsp;|&nbsp;
                        <b>ATR:</b> {snapshot['atr']} &nbsp;|&nbsp;
                        <b>Vol Ratio:</b> {snapshot['volume_ratio']}x &nbsp;|&nbsp;
                        <b>24h:</b> {snapshot['change_24h']}%
                        </div>
                        """, unsafe_allow_html=True)

                        st.markdown("#### 🗣️ Agent Verdicts (Real LLM Responses)")
                        for a in results:
                            vcol = "#22c55e" if a['score'] > 0 else "#ef4444" if a['score'] < 0 else "#f59e0b"
                            sl_txt = f"<br><b>Suggested SL:</b> ${a['sl_price']}" if a.get('sl_price') else ""
                            st.markdown(f"""
                            <div class='llm-box' style='border-left-color:{vcol}'>
                            <b>{a['name']}</b> → <b style='color:{vcol};font-size:16px'>{a['verdict']}</b>
                            <span style='color:#94a3b8'>(score: {a['score']:+d})</span><br>
                            <span style='color:#cbd5e1;font-size:13px'>{a['reason']}</span>{sl_txt}
                            </div>
                            """, unsafe_allow_html=True)

                        st.markdown("#### 👑 Chief LLM Consensus")
                        with st.spinner("Chief LLM making final decision..."):
                            cons, cerr = llm_consensus(snapshot, results)
                            if cerr:
                                st.error(f"❌ {cerr}")
                            else:
                                dec = cons.get("decision", "HOLD")
                                conf = cons.get("confidence", 0)
                                dcol = "#22c55e" if dec == "BUY" else "#ef4444" if dec == "SELL" else "#f59e0b"
                                st.markdown(f"""
                                <div class='card' style='border:3px solid {dcol};text-align:center'>
                                <div style='color:#94a3b8;font-size:13px'>FINAL LLM DECISION</div>
                                <div style='color:{dcol};font-size:36px;font-weight:900;margin:8px 0'>{dec}</div>
                                <div style='color:white'>Confidence: <b>{conf}%</b></div>
                                <div style='margin-top:14px;font-size:15px'>
                                <b>Entry:</b> ${cons.get('entry', snapshot['price'])} &nbsp;|&nbsp;
                                <b>SL:</b> <span class='sell'>${cons.get('sl', '—')}</span> &nbsp;|&nbsp;
                                <b>TP1:</b> <span class='buy'>${cons.get('tp1', '—')}</span> &nbsp;|&nbsp;
                                <b>TP2:</b> <span class='buy'>${cons.get('tp2', '—')}</span> &nbsp;|&nbsp;
                                <b>TP3:</b> <span class='buy'>${cons.get('tp3', '—')}</span>
                                </div>
                                <div style='margin-top:12px;color:#cbd5e1;font-style:italic'>
                                "{cons.get('reasoning', '')}"
                                </div>
                                </div>
                                """, unsafe_allow_html=True)
                        st.caption(f"✅ Analysis complete in {time.time()-start:.1f}s — {len(AGENTS)+1} real LLM calls made")

# ================== TAB 2 : CHART ==================
with tab2:
    st.markdown("### 📈 Chart + Zones")
    c1, c2 = st.columns([2, 1])
    sym2 = c1.selectbox("Coin", COINS, index=0, key="chart_sym")
    itv2 = c2.selectbox("TF", ["15m","1h","4h","1d"], index=1, key="chart_tf")

    df = klines(sym2, itv2, 300)
    if df.empty:
        st.error("❌ Data nahi mila. Coin ya timeframe change karo.")
    else:
        df = add_indicators(df)
        sup, res = find_zones(df)

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                            vertical_spacing=0.04, row_heights=[0.6, 0.18, 0.22],
                            subplot_titles=("", "Volume", "RSI"))
        fig.add_trace(go.Candlestick(x=df["t"], open=df["o"], high=df["h"], low=df["l"], close=df["c"],
            name=sym2.replace("USDT",""), increasing_line_color="#22c55e", increasing_fillcolor="#22c55e",
            decreasing_line_color="#ef4444", decreasing_fillcolor="#ef4444"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["ema20"], line=dict(color="#22d3ee", width=1.5), name="EMA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["ema50"], line=dict(color="#fbbf24", width=1.5), name="EMA50"), row=1, col=1)

        for t, p in res:
            fig.add_hrect(y0=p*0.997, y1=p*1.003, fillcolor="#ef4444", opacity=0.12, line_width=0, row=1, col=1)
            fig.add_hline(y=p, line_dash="dash", line_color="#ef4444", annotation_text=f"RES {p:,.2f}", annotation_position="right", row=1, col=1)
        for t, p in sup:
            fig.add_hrect(y0=p*0.997, y1=p*1.003, fillcolor="#22c55e", opacity=0.12, line_width=0, row=1, col=1)
            fig.add_hline(y=p, line_dash="dash", line_color="#22c55e", annotation_text=f"SUP {p:,.2f}", annotation_position="right", row=1, col=1)

        vc = ["#22c55e" if c >= o else "#ef4444" for c, o in zip(df["c"], df["o"])]
        fig.add_trace(go.Bar(x=df["t"], y=df["v"], marker_color=vc, name="Volume", opacity=0.8), row=2, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["vavg"], line=dict(color="#fbbf24", width=1), name="Vol Avg"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["rsi"], line=dict(color="#a78bfa", width=1.5), name="RSI"), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", opacity=0.5, row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", opacity=0.5, row=3, col=1)

        fig.update_layout(template="plotly_dark", height=800, paper_bgcolor="#0b0f17", plot_bgcolor="#0b0f17",
            xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.02),
            margin=dict(l=10, r=70, t=50, b=10), title=f"{sym2} • {itv2} • Live Bybit")
        fig.update_xaxes(showgrid=True, gridcolor="#1f2937")
        fig.update_yaxes(showgrid=True, gridcolor="#1f2937")
        st.plotly_chart(fig, use_container_width=True)

# ================== TAB 3 : LLM SCANNER ==================
with tab3:
    st.markdown("### 🔔 Multi-Coin LLM Scanner")
    st.caption("Har coin ka quick LLM analysis (1 call per coin = fast)")
    if not GROQ_API_KEY:
        st.warning("Pehle sidebar me Groq API key daalo.")
    else:
        c1, c2 = st.columns([1, 2])
        top_n = c1.slider("Top N coins", 3, 10, 5)
        if c2.button("🚀 Scan Top Coins with LLM", type="primary"):
            with st.spinner("Quick LLM scan running..."):
                rows = []
                for sym in COINS[:top_n]:
                    snap, _ = build_market_snapshot(sym, "1h")
                    if snap is None: continue
                    system = "You are a crypto analyst. Reply JSON only: {\"signal\":\"BUY|SELL|HOLD\",\"confidence\":0-100,\"reason\":\"1 short line\"}."
                    prompt = f"Quick call for {sym}: Price {snap['price']}, RSI {snap['rsi']}, EMA20 {snap['ema20']}, EMA50 {snap['ema50']}, VolRatio {snap['volume_ratio']}, 24h {snap['change_24h']}%."
                    resp, err = llm_call(system, prompt, max_tokens=120)
                    if err: continue
                    try:
                        txt = resp.strip()
                        if "```" in txt: txt = txt.split("```")[1].replace("json","").strip()
                        d = json.loads(txt)
                        rows.append({"Coin": sym.replace("USDT",""), "Price": snap["price"], "RSI": snap["rsi"],
                                     "VolRatio": snap["volume_ratio"], "24h %": snap["change_24h"],
                                     "LLM Signal": d.get("signal","—"), "Conf": f"{d.get('confidence',0)}%",
                                     "Reason": d.get("reason","")})
                    except Exception: continue
                    time.sleep(0.5)
                if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else: st.warning("Koi result nahi aaya")

# ================== TAB 4 : SIGNALS ==================
with tab4:
    st.markdown("### 📊 Signal Tracker (Indicator-based)")
    sym4 = st.selectbox("Coin", COINS, index=0, key="sig_sym")
    df4 = klines(sym4, "1h", 500)
    if not df4.empty:
        df4 = add_indicators(df4)
        sigs = []
        for i in range(1, len(df4)):
            pf, ps = df4["ema20"].iloc[i-1], df4["ema50"].iloc[i-1]
            cf, cs = df4["ema20"].iloc[i], df4["ema50"].iloc[i]
            if pd.isna(pf): continue
            if pf <= ps and cf > cs: sigs.append({"i":i,"time":df4["t"].iloc[i],"price":float(df4["c"].iloc[i]),"type":"BUY"})
            elif pf >= ps and cf < cs: sigs.append({"i":i,"time":df4["t"].iloc[i],"price":float(df4["c"].iloc[i]),"type":"SELL"})
        if sigs:
            rows = []
            for s in sigs[-15:]:
                fut = df4.iloc[s["i"]+1:]
                if fut.empty: up = down = 0; hrs = 0; live = True
                else:
                    up = (float(fut["h"].max())-s["price"])/s["price"]*100
                    down = (float(fut["l"].min())-s["price"])/s["price"]*100
                    hrs = (df4["t"].iloc[-1] - df4["t"].iloc[s["i"]]).total_seconds()/3600
                    live = False
                rows.append({"Time": s["time"].strftime("%m-%d %H:%M"), "Type": s["type"],
                             "Entry": round(s["price"],4), "Max Up %": round(up,2),
                             "Max Down %": round(down,2), "Dur": f"{hrs:.1f}h" if not live else "LIVE"})
            st.dataframe(pd.DataFrame(rows).iloc[::-1], use_container_width=True, hide_index=True)
        else:
            st.info("Koi signal nahi mila")
