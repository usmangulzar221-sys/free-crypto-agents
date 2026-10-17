import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime

st.set_page_config(page_title="LLM Signal Generator", page_icon="🧠", layout="wide")
st.title("🧠 Real LLM Signal Generator")
st.write("Live OKX Data + Groq AI Analysis")

# --- API Setup ---
try:
    from groq import Groq
    key = ""
    try: key = st.secrets["GROQ_API_KEY"]
    except: key = os.environ.get("GROQ_API_KEY", "")
    client = Groq(api_key=key) if key else None
except:
    client = None

with st.sidebar:
    st.header("Settings")
    if not key:
        user_key = st.text_input("Enter Groq API Key", type="password")
        if user_key:
            client = Groq(api_key=user_key)
            st.success("Key Loaded")
    else:
        st.success("Key Loaded")
    
    coin = st.selectbox("Select Coin", ["BTC-USDT", "ETH-USDT", "SOL-USDT", "DOGE-USDT", "XRP-USDT"])
    tf = st.selectbox("Timeframe", ["15m", "1H", "4H"], index=1)

# --- Data Fetching ---
@st.cache_data(ttl=60)
def get_data(symbol, timeframe):
    try:
        url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar={timeframe}&limit=100"
        r = requests.get(url).json()
        if r.get("code") != "0": return None
        
        df = pd.DataFrame(r["data"], columns=["t","o","h","l","c","v","vq","vc","x"])
        for col in ["o","h","l","c","v"]:
            df[col] = df[col].astype(float)
        df = df.sort_values("t")
        
        # Indicators (Real Math)
        df["ema20"] = df["c"].ewm(span=20).mean()
        df["ema50"] = df["c"].ewm(span=50).mean()
        
        delta = df["c"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))
        
        e1 = df["c"].ewm(span=12).mean()
        e2 = df["c"].ewm(span=26).mean()
        df["macd"] = e1 - e2
        df["signal"] = df["macd"].ewm(span=9).mean()
        
        tr = pd.concat([df["h"]-df["l"], (df["h"]-df["c"].shift()).abs(), (df["l"]-df["c"].shift()).abs()], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()
        
        last = df.iloc[-1]
        return {
            "price": last["c"],
            "rsi": last["rsi"],
            "ema20": last["ema20"],
            "ema50": last["ema50"],
            "macd": last["macd"],
            "atr": last["atr"],
            "vol_ratio": last["v"] / df["v"].rolling(20).mean().iloc[-1]
        }
    except Exception as e:
        return None

# --- Main Logic ---
if st.button("🚀 Generate LLM Signal", type="primary", use_container_width=True):
    if not client:
        st.error("Please enter Groq API Key in sidebar!")
    else:
        with st.spinner("Fetching live data & asking AI..."):
            data = get_data(coin, tf)
            
            if not data:
                st.error("Failed to fetch data from OKX.")
            else:
                # Show Real Data
                st.subheader("📊 Real Market Data")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Price", f"${data['price']:,.4f}")
                c2.metric("RSI", f"{data['rsi']:.1f}")
                c3.metric("EMA Trend", "Bullish" if data['ema20'] > data['ema50'] else "Bearish")
                c4.metric("Vol Ratio", f"{data['vol_ratio']:.2f}x")
                
                st.divider()
                
                # LLM Prompt
                prompt = f"""
                Analyze this crypto data for {coin} ({tf} timeframe):
                - Current Price: {data['price']}
                - RSI: {data['rsi']:.2f}
                - EMA20: {data['ema20']:.2f}
                - EMA50: {data['ema50']:.2f}
                - MACD: {data['macd']:.4f}
                - Volume Ratio: {data['vol_ratio']:.2f}x
                
                Based on this, should I BUY, SELL, or HOLD?
                Reply ONLY in this JSON format: 
                {{"decision": "BUY" or "SELL" or "HOLD", "confidence": 1-100, "reason": "1 line reasoning"}}
                """
                
                try:
                    response = client.chat.completions.create(
                        model="llama3-70b-8192", # Fast & Smart
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                        response_format={"type": "json_object"}
                    )
                    
                    raw_text = response.choices[0].message.content
                    result = json.loads(raw_text)
                    
                    decision = result.get("decision", "HOLD")
                    conf = result.get("confidence", 0)
                    reason = result.get("reason", "No reason provided")
                    
                    # Display Result
                    if decision == "BUY":
                        st.success(f"### 🟢 Decision: {decision} (Confidence: {conf}%)")
                    elif decision == "SELL":
                        st.error(f"### 🔴 Decision: {decision} (Confidence: {conf}%)")
                    else:
                        st.warning(f"### 🟡 Decision: {decision} (Confidence: {conf}%)")
                        
                    st.info(f"**AI Reasoning:** {reason}")
                    
                    # Python Calculates SL/TP (NO LLM HALLUCINATION)
                    if decision in ["BUY", "SELL"]:
                        st.subheader("🎯 Trade Setup (Math Based)")
                        
                        entry = data['price']
                        atr = data['atr']
                        
                        if decision == "BUY":
                            sl = entry - (2 * atr)
                            tp1 = entry + (2 * atr)
                            tp2 = entry + (4 * atr)
                        else: # SELL
                            sl = entry + (2 * atr)
                            tp1 = entry - (2 * atr)
                            tp2 = entry - (4 * atr)
                            
                        t1, t2, t3, t4 = st.columns(4)
                        t1.metric("Entry", f"${entry:,.4f}")
                        t2.metric("Stop Loss", f"${sl:,.4f}")
                        t3.metric("Take Profit 1", f"${tp1:,.4f}")
                        t4.metric("Take Profit 2", f"${tp2:,.4f}")
                        
                        st.caption("SL and TP are calculated using ATR (Average True Range). The AI only provided the direction.")
                        
                except Exception as e:
                    st.error(f"LLM Error: {e}")
