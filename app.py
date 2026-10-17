import streamlit as st, requests, pandas as pd, numpy as np
import plotly.graph_objects as go
import json, os
from datetime import datetime, timedelta
from groq import Groq

st.set_page_config(page_title="Auto LLM Scanner", layout="wide")
st.markdown("<style>.stApp{background:#0b0f17;color:#e5e7eb}.card{background:#111827;padding:12px;border-radius:10px;margin:8px 0;border-left:5px solid #3b82f6}.buy{border-left-color:#22c55e}.sell{border-left-color:#ef4444}.win{border-left-color:#22c55e}.loss{border-left-color:#ef4444}</style>", unsafe_allow_html=True)

# --- Setup ---
GK = st.secrets.get("GROQ_API_KEY", "") if hasattr(st, "secrets") else os.environ.get("GROQ_API_KEY", "")
if not GK:
    GK = st.sidebar.text_input("Groq API Key", type="password")
cl = Groq(api_key=GK) if GK else None

OK = "https://www.okx.com/api/v5"

if "signals" not in st.session_state:
    st.session_state.signals = []

# --- Data Functions ---
@st.cache_data(ttl=300)
def get_coins():
    try:
        r = requests.get(f"{OK}/market/tickers?instType=SPOT").json()
        return [d["instId"].replace("-","") for d in r["data"] if d["instId"].endswith("-USDT") and float(d.get("volCcy24h",0))>2000000][:30]
    except: return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

@st.cache_data(ttl=60)
def get_klines(sym):
    try:
        r = requests.get(f"{OK}/market/candles?instId={sym[:-4]}-USDT&bar=1H&limit=100").json()
        if r.get("code") != "0": return pd.DataFrame()
        df = pd.DataFrame(r["data"], columns=["t","o","h","l","c","v","vq","vc","x"])
        for c in ["o","h","l","c","v"]: df[c] = df[c].astype(float)
        df["t"] = pd.to_datetime(df["t"].astype(float), unit="ms")
        return df.sort_values("t").reset_index(drop=True)
    except: return pd.DataFrame()

def get_price(sym):
    try:
        r = requests.get(f"{OK}/market/ticker?instId={sym[:-4]}-USDT").json()
        return float(r["data"][0]["last"]) if r.get("code")=="0" else 0
    except: return 0

# --- Indicators ---
def calc_ind(df):
    df = df.copy()
    df["e20"] = df["c"].ewm(span=20).mean()
    df["e50"] = df["c"].ewm(span=50).mean()
    delta = df["c"].diff()
    gain = (delta.where(delta>0,0)).rolling(14).mean()
    loss = (-delta.where(delta<0,0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + gain/loss))
    tr = pd.concat([df["h"]-df["l"], (df["h"]-df["c"].shift()).abs(), (df["l"]-df["c"].shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["vol_ratio"] = df["v"] / df["v"].rolling(20).mean()
    return df

# --- LLM Check ---
def llm_decide(sym, price, rsi, ema_trend, vol):
    if not cl: return "HOLD", "No API Key"
    prompt = f"Coin: {sym}, Price: {price}, RSI: {rsi:.1f}, Trend: {ema_trend}, VolRatio: {vol:.2f}. Reply JSON: {{\"decision\": \"BUY|SELL|HOLD\", \"confidence\": 1-100, \"reason\": \"1 line\"}}"
    try:
        res = cl.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        d = json.loads(res.choices[0].message.content)
        return d.get("decision", "HOLD"), d.get("reason", "")
    except: return "HOLD", "LLM Error"

# --- UI ---
st.title("🤖 Auto LLM Scanner & Tracker")

# Tabs
tab1, tab2 = st.tabs(["🔍 Auto Scanner", "📊 Signal Tracker (Backtest)"])

# --- Tab 1: Auto Scanner ---
with tab1:
    st.write("Click the button below. Scanner will auto-select top coins, find the best technical signal, and ask LLM for final confirmation.")
    
    if st.button("🚀 Run Auto Scan & LLM Decide", type="primary", use_container_width=True):
        if not cl: st.error("Please add Groq API Key in sidebar.")
        else:
            with st.spinner("Scanning markets..."):
                coins = get_coins()
                best_signal = None
                max_score = 0
                
                # 1. Find Best Technical Signal
                for sym in coins:
                    df = get_klines(sym)
                    if len(df) < 50: continue
                    df = calc_ind(df)
                    last = df.iloc[-1]
                    
                    trend = "BULL" if last["e20"] > last["e50"] else "BEAR"
                    rsi, vol, atr, px = last["rsi"], last["vol_ratio"], last["atr"], last["c"]
                    
                    # Scoring
                    score = 0
                    if trend == "BULL" and 40 < rsi < 65: score += 40
                    if trend == "BEAR" and 35 < rsi < 60: score += 40
                    if vol > 1.5: score += 30
                    
                    if score > max_score:
                        max_score = score
                        best_signal = {"sym": sym, "trend": trend, "rsi": rsi, "vol": vol, "atr": atr, "price": px}
                
                # 2. Ask LLM to confirm the best one
                if best_signal:
                    st.info(f"🎯 Top Technical Signal: **{best_signal['sym']}** (Score: {max_score})")
                    
                    with st.spinner("Asking LLM for final decision..."):
                        decision, reason = llm_decide(best_signal["sym"], best_signal["price"], best_signal["rsi"], best_signal["trend"], best_signal["vol"])
                        
                        if decision in ["BUY", "SELL"]:
                            entry = best_signal["price"]
                            atr = best_signal["atr"]
                            
                            if decision == "BUY":
                                sl = entry - (1.5 * atr)
                                tp = entry + (3.0 * atr)
                            else:
                                sl = entry + (1.5 * atr)
                                tp = entry - (3.0 * atr)
                                
                            new_sig = {
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "coin": best_signal["sym"],
                                "decision": decision,
                                "entry": entry,
                                "sl": sl,
                                "tp": tp,
                                "status": "RUNNING"
                            }
                            st.session_state.signals.append(new_sig)
                            
                            cls = "buy" if decision == "BUY" else "sell"
                            st.markdown(f"<div class='card {cls}'><h3>{decision} {best_signal['sym']}</h3><p><b>Reason:</b> {reason}</p><p><b>Entry:</b> ${entry:.4f} | <b>SL:</b> ${sl:.4f} | <b>TP:</b> ${tp:.4f}</p></div>", unsafe_allow_html=True)
                        else:
                            st.warning(f"LLM Decision: **{decision}**. Reason: {reason}")
                else:
                    st.warning("No strong technical signals found right now.")

# --- Tab 2: Signal Tracker ---
with tab2:
    st.write("Track signals generated by the LLM. It checks live prices to see if SL/TP hit, and calculates duration.")
    
    if not st.session_state.signals:
        st.info("No signals generated yet. Run the Auto Scanner first.")
    else:
        # Update statuses
        for sig in st.session_state.signals:
            if sig["status"] == "RUNNING":
                cur_px = get_price(sig["coin"])
                if cur_px > 0:
                    if sig["decision"] == "BUY":
                        if cur_px >= sig["tp"]:
                            sig["status"] = "WIN (TP HIT)"
                            sig["hit_time"] = datetime.now()
                        elif cur_px <= sig["sl"]:
                            sig["status"] = "LOSS (SL HIT)"
                            sig["hit_time"] = datetime.now()
                    elif sig["decision"] == "SELL":
                        if cur_px <= sig["tp"]:
                            sig["status"] = "WIN (TP HIT)"
                            sig["hit_time"] = datetime.now()
                        elif cur_px >= sig["sl"]:
                            sig["status"] = "LOSS (SL HIT)"
                            sig["hit_time"] = datetime.now()

        # Display
        for sig in reversed(st.session_state.signals):
            cur_px = get_price(sig["coin"])
            
            status_color = "#f59e0b"
            if "WIN" in sig["status"]: status_color = "#22c55e"
            elif "LOSS" in sig["status"]: status_color = "#ef4444"
            
            time_html = f"<b>Signal Time:</b> {sig['time']}<br>"
            
            if "hit_time" in sig:
                t1 = datetime.strptime(sig["time"], "%Y-%m-%d %H:%M:%S")
                t2 = sig["hit_time"]
                diff = t2 - t1
                hrs = diff.total_seconds() / 3600
                time_html += f"<b>Result Time:</b> {t2.strftime('%Y-%m-%d %H:%M:%S')} (Took {hrs:.1f} hours)<br>"
            
            st.markdown(f"""
            <div class='card' style='border-left-color:{status_color}'>
                <h4 style='color:{status_color};margin:0;'>{sig['coin']} {sig['decision']} - {sig['status']}</h4>
                {time_html}
                <b>Entry:</b> ${sig['entry']:.4f} | <b>SL:</b> ${sig['sl']:.4f} | <b>TP:</b> ${sig['tp']:.4f}<br>
                <b>Current Price:</b> ${cur_px:.4f}
            </div>
            """, unsafe_allow_html=True)
            
        if st.button("Clear History"):
            st.session_state.signals = []
            st.rerun()
