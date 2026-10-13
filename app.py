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
.metric-box{background:#111827;border-radius:10px;padding:12px;border:1px solid #1f2937;text-align:center}
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
    """Priority: Streamlit secrets > environment variable"""
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
    """Real LLM call to Groq"""
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

# ============ BINANCE DATA ============
API = "https://api.binance.com/api/v3"
COINS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT",
         "ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","LTCUSDT","BCHUSDT",
         "UNIUSDT","SUIUSDT","TRXUSDT","APTUSDT","ATOMUSDT","NEARUSDT",
         "INJUSDT","MATICUSDT","SHIBUSDT","PEPEUSDT","OPUSDT","ARBUSDT",
         "TIAUSDT","FILUSDT","ETCUSDT","HBARUSDT","VETUSDT","RUNEUSDT"]

@st.cache_data(ttl=20)
def klines(sym, itv="1h", lim=300):
    try:
        r = requests.get(f"{API}/klines",
                         params={"symbol": sym, "interval": itv, "limit": lim},
                         timeout=8)
        d = r.json()
        if not isinstance(d, list) or len(d) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(d, columns=["t","o","h","l","c","v","ct","qv","n","tb","tq","ig"])
        for col in ["o","h","l","c","v","qv"]:
            df[col] = df[col].astype(float)
        df["t"] = pd.to_datetime(df["t"], unit="ms")
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=15)
def ticker24(sym):
    try:
        r = requests.get(f"{API}/ticker/24hr", params={"symbol": sym}, timeout=6)
        return r.json()
    except Exception:
        return {}

@st.cache_data(ttl=15)
def price_now(sym):
    try:
        r = requests.get(f"{API}/ticker/price", params={"symbol": sym}, timeout=5)
        return float(r.json()["price"])
    except Exception:
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
    df["macd_hist"] = df["macd"] - df["macd_sig"]
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
    """Real Binance data snapshot for LLM"""
    df = klines(sym, itv, 200)
    if df.empty:
        return None, None
    df = add_indicators(df)
    sup, res = find_zones(df)
    last = df.iloc[-1]
    t24 = ticker24(sym)
    px = float(last["c"])
    snapshot = {
        "symbol": sym,
        "timeframe": itv,
        "price": round(px, 4),
        "ema20": round(float(last["ema20"]), 4),
        "ema50": round(float(last["ema50"]), 4),
        "ema200": round(float(last["ema200"]), 4) if not pd.isna(last["ema200"]) else None,
        "rsi": round(float(last["rsi"]), 2) if not pd.isna(last["rsi"]) else None,
        "atr": round(float(last["atr"]), 4) if not pd.isna(last["atr"]) else None,
        "macd": round(float(last["macd"]), 4) if not pd.isna(last["macd"]) else None,
        "macd_signal": round(float(last["macd_sig"]), 4) if not pd.isna(last["macd_sig"]) else None,
        "volume_ratio": round(float(last["vr"]), 2) if not pd.isna(last["vr"]) else None,
        "high_24h": t24.get("highPrice"),
        "low_24h": t24.get("lowPrice"),
        "change_24h": t24.get("priceChangePercent"),
        "supports": [round(float(p), 4) for _, p in sup],
        "resistances": [round(float(p), 4) for _, p in res],
        "recent_candles": df.tail(10)[["t","o","h","l","c","v"]].to_dict("records")
    }
    return snapshot, df

# 5 REAL LLM AGENTS
AGENTS = [
    {
        "name": "📈 Trend Analyst",
        "system": "You are a professional crypto trend analyst. Analyze the given market data and give a clear verdict: BULLISH, BEARISH, or SIDEWAYS. Reply in this exact JSON format: {\"verdict\":\"BULLISH|BEARISH|SIDEWAYS\",\"score\":-3 to +3,\"reason\":\"short 1-line reason\"}. No extra text.",
        "prompt_template": "Analyze this {symbol} {timeframe} market data:\nPrice: {price}\nEMA20: {ema20}\nEMA50: {ema50}\nEMA200: {ema200}\nRecent candles: {recent_candles}\n\nGive trend verdict."
    },
    {
        "name": "⚡ Momentum Analyst",
        "system": "You are a momentum specialist. Analyze RSI, MACD, and price action. Reply in JSON: {\"verdict\":\"STRONG|WEAK|OVERSOLD|OVERBOUGHT|NEUTRAL\",\"score\":-3 to +3,\"reason\":\"short reason\"}. No extra text.",
        "prompt_template": "Analyze momentum for {symbol}:\nRSI: {rsi}\nMACD: {macd}\nMACD Signal: {macd_signal}\nPrice: {price}\nEMA20: {ema20}\nEMA50: {ema50}\n\nGive momentum verdict."
    },
    {
        "name": "🐳 Volume Analyst",
        "system": "You are a volume analysis expert. Analyze volume ratio and 24h data. Reply in JSON: {\"verdict\":\"HIGH_VOLUME|NORMAL|LOW_VOLUME\",\"score\":-3 to +3,\"reason\":\"short reason\"}. No extra text.",
        "prompt_template": "Analyze volume for {symbol}:\nVolume ratio vs 20avg: {volume_ratio}\n24h change: {change_24h}%\n24h high: {high_24h}\n24h low: {low_24h}\nPrice: {price}\n\nGive volume verdict."
    },
    {
        "name": "🛡️ Risk Manager",
        "system": "You are a risk manager. Analyze volatility and support/resistance. Reply in JSON: {\"verdict\":\"LOW_RISK|MEDIUM_RISK|HIGH_RISK\",\"score\":-3 to +3,\"sl_price\":number,\"reason\":\"short reason\"}. No extra text.",
        "prompt_template": "Analyze risk for {symbol}:\nPrice: {price}\nATR: {atr}\nSupports: {supports}\nResistances: {resistances}\nVolume ratio: {volume_ratio}\nRSI: {rsi}\n\nGive risk verdict and suggested SL price."
    },
    {
        "name": "🎯 S/R Analyst",
        "system": "You are a support/resistance expert. Analyze zones and current price position. Reply in JSON: {\"verdict\":\"NEAR_SUPPORT|NEAR_RESISTANCE|MID_RANGE\",\"score\":-3 to +3,\"reason\":\"short reason\"}. No extra text.",
        "prompt_template": "Analyze S/R for {symbol}:\nPrice: {price}\nSupports: {supports}\nResistances: {resistances}\nATR: {atr}\n\nGive S/R verdict."
    }
]

def run_real_agents(sym, itv):
    """Run all 5 agents via REAL LLM calls"""
    snapshot, df = build_market_snapshot(sym, itv)
    if snapshot is None:
        return None, "Data fetch failed"

    results = []
    for agent in AGENTS:
        prompt = agent["prompt_template"].format(**snapshot)
        response, err = llm_call(agent["system"], prompt, max_tokens=200)
        if err:
            results.append({
                "name": agent["name"],
                "verdict": "ERROR",
                "score": 0,
                "reason": err,
                "raw": err
            })
            continue
        # Parse JSON from LLM response
        try:
            txt = response.strip()
            if "```" in txt:
                txt = txt.split("```")[1].replace("json","").strip()
            data = json.loads(txt)
            results.append({
                "name": agent["name"],
                "verdict": data.get("verdict", "UNKNOWN"),
                "score": int(data.get("score", 0)),
                "reason": data.get("reason", ""),
                "sl_price": data.get("sl_price"),
                "raw": response
            })
        except Exception:
            results.append({
                "name": agent["name"],
                "verdict": "PARSE_ERROR",
                "score": 0,
                "reason": response[:120] if response else "Empty",
                "raw": response or ""
            })
    return results, None

def llm_consensus(snapshot, agent_results):
    """Real LLM decides final consensus based on agents' opinions"""
    summary = "\n".join([
        f"{a['name']}: {a['verdict']} (score {a['score']}) — {a['reason']}"
        for a in agent_results
    ])
    system = """You are the Chief Trading Officer. You see 5 analyst reports. Give final decision.
Reply in JSON only: {"decision":"BUY|SELL|HOLD","confidence":0-100,"entry":number,"sl":number,"tp1":number,"tp2":number,"tp3":number,"reasoning":"2-line explanation"}. No extra text."""
    prompt = f"""Market: {snapshot['symbol']} {snapshot['timeframe']}
Price: {snapshot['price']}
ATR: {snapshot['atr']}
RSI: {snapshot['rsi']}
Volume ratio: {snapshot['volume_ratio']}
Supports: {snapshot['supports']}
Resistances: {snapshot['resistances']}

Analyst Reports:
{summary}

Give final trading decision."""
    response, err = llm_call(system, prompt, max_tokens=400)
    if err:
        return None, err
    try:
        txt = response.strip()
        if "```" in txt:
            txt = txt.split("```")[1].replace("json","").strip()
        return json.loads(txt), None
    except Exception:
        return None, f"Parse failed: {response[:200]}"

# ============ SIDEBAR ============
with st.sidebar:
    st.markdown("### 🔑 Groq API Key")
    if GROQ_API_KEY:
        st.success("✅ Key loaded")
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
            st.caption("No credit card needed. 30 req/min free.")

    st.markdown("---")
    st.markdown(f"**LLM Model:** `{LLM_MODEL or 'not set'}`")
    st.markdown(f"**Agents:** {len(AGENTS)} real LLM agents")
    st.caption("Each agent = 1 LLM call")

# ============ HEADER ============
btc_p = price_now("BTCUSDT")
btc_24 = ticker24("BTCUSDT")
btc_chg = float(btc_24.get("priceChangePercent", 0)) if btc_24 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("BTC/USDT", f"${btc_p:,.2f}" if btc_p else "—",
            f"{btc_chg:+.2f}%" if btc_24 else None)
eth_p = price_now("ETHUSDT")
col2.metric("ETH/USDT", f"${eth_p:,.2f}" if eth_p else "—")
sol_p = price_now("SOLUSDT")
col3.metric("SOL/USDT", f"${sol_p:,.2f}" if sol_p else "—")
col4.metric("Time", datetime.now().strftime("%H:%M:%S"))

st.title("🧠 Real LLM Agent Scanner — Powered by Groq")
if not GROQ_API_KEY:
    st.error("⚠️ Groq API key missing! Sidebar me paste karo. [Free key yahan se lo](https://console.groq.com/keys)")
else:
    st.success(f"✅ Real LLM Active: **{LLM_MODEL}** — 5 Agents, Har Agent Real AI Call")

st.caption(f"Live Binance Data • Real LLM Analysis • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ============ TABS ============
tab1, tab2, tab3, tab4 = st.tabs([
    "🧠 LLM Agent Discussion",
    "📈 Chart",
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
                    st.error("❌ Binance data nahi mila")
                else:
                    results, err = run_real_agents(sym, itv)
                    if err:
                        st.error(f"❌ {err}")
                    else:
                        st.markdown("#### 📊 Market Snapshot (Real Binance)")
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
                            if a['score'] > 0: vcol = "#22c55e"
                            elif a['score'] < 0: vcol = "#ef4444"
                            else: vcol = "#f59e0b"
                            sl_txt = f"<br><b>Suggested SL:</b> ${a['sl_price']}" if a.get('sl_price') else ""
                            st.markdown(f"""
                            <div class='llm-box' style='border-left-color:{vcol}'>
                            <b>{a['name']}</b> → <b style='color:{vcol};font-size:16px'>{a['verdict']}</b>
                            <span style='color:#94a3b8'>(score: {a['score']:+d})</span><br>
                            <span style='color:#cbd5e1;font-size:13px'>{a['reason']}</span>{sl_txt}
                            </div>
                            """, unsafe_allow_html=True)

                        # Chief consensus
                        st.markdown("#### 👑 Chief LLM Consensus")
                        with st.spinner("Chief LLM making final decision..."):
                            cons, cerr = llm_consensus(snapshot, results)
                            if cerr:
                                st.error(f"❌ {cerr}")
                            else:
                                dec = cons.get("decision", "HOLD")
                                conf = cons.get("confidence", 0)
                                if dec == "BUY": dcol = "#22c55e"
                                elif dec == "SELL": dcol = "#ef4444"
                                else: dcol = "#f59e0b"
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

                        elapsed = time.time() - start
                        st.caption(f"✅ Analysis complete in {elapsed:.1f}s — {len(AGENTS)+1} real LLM calls made")

# ================== TAB 2 : CHART ==================
with tab2:
    st.markdown("### 📈 Chart + Zones")
    c1, c2 = st.columns([2, 1])
    sym2 = c1.selectbox("Coin", COINS, index=0, key="chart_sym")
    itv2 = c2.selectbox("TF", ["15m","1h","4h","1d"], index=1, key="chart_tf")

    df = klines(sym2, itv2, 300)
    if df.empty:
        st.error("❌ Data nahi mila")
    else:
        df = add_indicators(df)
        sup, res = find_zones(df)
        last = df.iloc[-1]

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                            vertical_spacing=0.04,
                            row_heights=[0.6, 0.18, 0.22],
                            subplot_titles=("", "Volume", "RSI"))

        fig.add_trace(go.Candlestick(
            x=df["t"], open=df["o"], high=df["h"], low=df["l"], close=df["c"],
            name=sym2.replace("USDT",""),
            increasing_line_color="#22c55e", increasing_fillcolor="#22c55e",
            decreasing_line_color="#ef4444", decreasing_fillcolor="#ef4444"),
            row=1, col=1)

        fig.add_trace(go.Scatter(x=df["t"], y=df["ema20"],
            line=dict(color="#22d3ee", width=1.5), name="EMA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["ema50"],
            line=dict(color="#fbbf24", width=1.5), name="EMA50"), row=1, col=1)

        for t, p in res:
            fig.add_hrect(y0=p*0.997, y1=p*1.003, fillcolor="#ef4444",
                          opacity=0.12, line_width=0, row=1, col=1)
            fig.add_
