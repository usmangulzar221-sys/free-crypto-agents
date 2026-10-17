import streamlit as st
import requests
import pandas as pd
import json
import os

st.set_page_config(page_title="LLM Signal", layout="wide")
st.title("🧠 Real LLM Signal Generator")

# --- Groq Setup ---
try:
    from groq import Groq
    key = ""
    try: key = st.secrets["GROQ_API_KEY"]
    except: key = os.environ.get("GROQ_API_KEY", "")
    client = Groq(api_key=key) if key else None
except:
    client = None

with st.sidebar:
    if not key:
        uk = st.text_input("Groq Key", type="password")
        if uk: client = Groq(api_key=uk); st.success("Loaded")
    else: st.success("Key Loaded")
    coin = st.selectbox("Coin", ["BTC-USDT", "ETH-USDT", "SOL-USDT"])
    tf = st.selectbox("TF", ["15m", "1H", "4H"], index=1)

# --- Data + Indicators ---
@st.cache_data(ttl=60)
def get_data(sym, t):
    try:
        r = requests.get(f"https://www.okx.com/api/v5/market/candles?instId={sym}&bar={t}&limit=100").json()
        if r.get("code") != "0": return None
        df = pd.DataFrame(r["data"], columns=["t","o","h","l","c","v","vq","vc","x"])
        for col in ["o","h","l","c","v"]: df[col] = df[col].astype(float)
        df = df.sort_values("t")
        
        df["ema20"] = df["c"].ewm(span=20).mean()
        df["ema50"] = df["c"].ewm(span=50).mean()
        delta = df["c"].diff()
        gain = (delta.where(delta>0,0)).rolling(14).mean()
        loss = (-delta.where(delta<0,0)).rolling(14).mean()
        df["rsi"] = 100 - (100 / (1 + gain/loss))
        tr = pd.concat([df["h"]-df["l"], (df["h"]-df["c"].shift()).abs(), (df["l"]-df["c"].shift()).abs()], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()
        last = df.iloc[-1]
        return {"price": last["c"], "rsi": last["rsi"], "ema20": last["ema20"], "ema50": last["ema50"], "atr": last["atr"], "vol": last["v"] / df["v"].rolling(20).mean().iloc[-1]}
    except: return None

# --- Main App ---
if st.button("🚀 Generate Signal", type="primary", use_container_width=True):
    if not client: st.error("Add Groq Key")
    else:
        with st.spinner("Fetching & Analyzing..."):
            d = get_data(coin, tf)
            if not d: st.error("Failed to fetch OKX data")
            else:
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Price", f"${d['price']:,.4f}")
                c2.metric("RSI", f"{d['rsi']:.1f}")
                c3.metric("Trend", "Bull" if d['ema20']>d['ema50'] else "Bear")
                c4.metric("Vol", f"{d['vol']:.2f}x")
                st.divider()
                
                prompt = f"Analyze {coin} {tf}. Price: {d['price']:.4f}, RSI: {d['rsi']:.1f}, EMA20: {d['ema20']:.4f}, EMA50: {d['ema50']:.4f}, VolRatio: {d['vol']:.2f}. Reply in JSON: {{\"decision\": \"BUY|SELL|HOLD\", \"confidence\": 1-100, \"reason\": \"1 line\"}}"
                
                try:
                    # Yahan naya model use ho raha hai
                    res = client.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                        response_format={"type": "json_object"}
                    )
                    result = json.loads(res.choices[0].message.content)
                    dec, conf, reason = result.get("decision"), result.get("confidence"), result.get("reason")
                    
                    if dec == "BUY": st.success(f"### 🟢 BUY ({conf}%)")
                    elif dec == "SELL": st.error(f"### 🔴 SELL ({conf}%)")
                    else: st.warning(f"### 🟡 HOLD ({conf}%)")
                    st.info(f"**Reason:** {reason}")
                    
                    if dec in ["BUY", "SELL"]:
                        st.subheader("🎯 Trade Setup (ATR Based)")
                        entry, atr = d['price'], d['atr']
                        sl = entry - 2*atr if dec=="BUY" else entry + 2*atr
                        tp1 = entry + 2*atr if dec=="BUY" else entry - 2*atr
                        tp2 = entry + 4*atr if dec=="BUY" else entry - 4*atr
                        
                        t1,t2,t3,t4 = st.columns(4)
                        t1.metric("Entry", f"${entry:,.4f}")
                        t2.metric("Stop Loss", f"${sl:,.4f}")
                        t3.metric("TP1", f"${tp1:,.4f}")
                        t4.metric("TP2", f"${tp2:,.4f}")
                except Exception as e:
                    st.error(f"LLM Error: {e}")
