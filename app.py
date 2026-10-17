import streamlit as st, requests, pandas as pd, numpy as np
import plotly.graph_objects as go
import json, os
from datetime import datetime
from groq import Groq

st.set_page_config(page_title="Pro Scanner", layout="wide")
st.markdown("<style>.stApp{background:#0b0f17;color:#e5e7eb}.card{background:#111827;padding:12px;border-radius:10px;margin:8px 0;border-left:5px solid #3b82f6}.win{border-left-color:#22c55e}.loss{border-left-color:#ef4444}.wait{border-left-color:#f59e0b}</style>", unsafe_allow_html=True)

# --- Setup API Keys ---
GK = st.secrets.get("GROQ_API_KEY", "") if hasattr(st, "secrets") else os.environ.get("GROQ_API_KEY", "")
if not GK:
    GK = st.sidebar.text_input("Groq API Key", type="password")
cl = Groq(api_key=GK) if GK else None

# --- Session State ---
if "signals" not in st.session_state: st.session_state.signals = []

# --- Data Fetching ---
OK = "https://www.okx.com/api/v5"

@st.cache_data(ttl=300)
def get_top_coins():
    try:
        r = requests.get(f"{OK}/market/tickers?instType=SPOT").json()
        coins = [d["instId"].replace("-","") for d in r["data"] if d["instId"].endswith("-USDT") and float(d.get("volCcy24h",0))>3000000]
        return coins[:20] # Top 20 high volume
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

def get_live_price(sym):
    try:
        r = requests.get(f"{OK}/market/ticker?instId={sym[:-4]}-USDT").json()
        return float(r["data"][0]["last"]) if r.get("code")=="0" else 0
    except: return 0

# --- Indicators ---
def calc_ind(df):
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

# --- LLM Brain ---
def ask_llm(sym, price, rsi, trend, vol):
    if not cl: return "HOLD", "No API Key"
    prompt = f"Act as pro trader. Coin: {sym}, Price: {price}, RSI: {rsi:.1f}, Trend: {trend}, VolRatio: {vol:.2f}. Technicals are good for {trend}. Reply strictly JSON: {{\"decision\": \"BUY\" or \"SELL\" or \"HOLD\", \"reason\": \"short reason\"}}"
    try:
        res = cl.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        d = json.loads(res.choices[0].message.content)
        return d.get("decision", "HOLD"), d.get("reason", "")
    except Exception as e:
        return "HOLD", f"LLM Error: {e}"

# --- UI ---
st.title("🎯 AI Auto-Scanner & Signal Tracker")

tab_scan, tab_track = st.tabs(["🔍 Auto Scan & Signal", "📊 Signal History (SL/TP Tracker)"])

# ================= TAB 1: SCANNER =================
with tab_scan:
    st.write("Scan top coins, find technical setups, and let AI verify the final signal.")
    
    if st.button("🚀 Start Auto Scan", type="primary", use_container_width=True):
        if not cl: st.error("Please enter Groq Key in sidebar.")
        else:
            with st.spinner("Scanning top 20 coins..."):
                coins = get_top_coins()
                best_setup = None
                max_score = 0
                
                for sym in coins:
                    df = get_klines(sym)
                    if len(df) < 50: continue
                    df = calc_ind(df)
                    last = df.iloc[-1]
                    
                    trend = "BUY" if last["e20"] > last["e50"] else "SELL"
                    rsi, vol = last["rsi"], last["vol_ratio"]
                    
                    # Tech Score
                    score = 0
                    if trend == "BUY" and 45 < rsi < 65: score += 40
                    if trend == "SELL" and 35 < rsi < 55: score += 40
                    if vol > 1.2: score += 30
                    
                    if score > max_score:
                        max_score = score
                        best_setup = {"sym": sym, "type": trend, "rsi": rsi, "vol": vol, "atr": last["atr"], "price": last["c"]}
                
                if best_setup:
                    st.info(f"Top Technical Match: **{best_setup['sym']}** (Score: {max_score})")
                    with st.spinner("AI is verifying..."):
                        decision, reason = ask_llm(best_setup["sym"], best_setup["price"], best_setup["rsi"], best_setup["type"], best_setup["vol"])
                        
                        if decision in ["BUY", "SELL"]:
                            entry = best_setup["price"]
                            atr = best_setup["atr"]
                            sl = entry - (1.5*atr) if decision=="BUY" else entry + (1.5*atr)
                            tp = entry + (3.0*atr) if decision=="BUY" else entry - (3.0*atr)
                            
                            st.session_state.signals.append({
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "coin": best_setup["sym"],
                                "decision": decision,
                                "entry": entry, "sl": sl, "tp": tp,
                                "status": "RUNNING"
                            })
                            
                            cls = "win" if decision=="BUY" else "loss"
                            st.markdown(f"<div class='card {cls}'><h3>✅ {decision} {best_setup['sym']}</h3><p><b>AI Reason:</b> {reason}</p><p><b>Entry:</b> ${entry:.4f} | <b>SL:</b> ${sl:.4f} | <b>TP:</b> ${tp:.4f}</p></div>", unsafe_allow_html=True)
                        else:
                            st.warning(f"AI Rejected: **{decision}**. Reason: {reason}. (Market conditions not perfect).")
                else:
                    st.warning("No good technical setups found right now.")

# ================= TAB 2: TRACKER =================
with tab_track:
    st.write("Tracks open signals. Checks price live to see if TP or SL hit, and calculates duration.")
    
    if not st.session_state.signals:
        st.info("No signals generated yet.")
    else:
        for sig in st.session_state.signals:
            if sig["status"] == "RUNNING":
                cur_px = get_live_price(sig["coin"])
                if cur_px > 0:
                    if sig["decision"] == "BUY":
                        if cur_px >= sig["tp"]: sig["status"] = "WIN (TP)"; sig["hit_time"] = datetime.now()
                        elif cur_px <= sig["sl"]: sig["status"] = "LOSS (SL)"; sig["hit_time"] = datetime.now()
                    elif sig["decision"] == "SELL":
                        if cur_px <= sig["tp"]: sig["status"] = "WIN (TP)"; sig["hit_time"] = datetime.now()
                        elif cur_px >= sig["sl"]: sig["status"] = "LOSS (SL)"; sig["hit_time"] = datetime.now()

        for sig in reversed(st.session_state.signals):
            cur_px = get_live_price(sig["coin"])
            status_cls = "wait"
            if "WIN" in sig["status"]: status_cls = "win"
            elif "LOSS" in sig["status"]: status_cls = "loss"
            
            time_html = f"<b>Signal Generated:</b> {sig['time']}<br>"
            
            if "hit_time" in sig:
                t1 = datetime.strptime(sig["time"], "%Y-%m-%d %H:%M:%S")
                hrs = (sig["hit_time"] - t1).total_seconds() / 3600
                time_html += f"<b>Result Time:</b> {sig['hit_time'].strftime('%Y-%m-%d %H:%M:%S')} (After {hrs:.1f} hours)<br>"
            
            st.markdown(f"""
            <div class='card {status_cls}'>
                <h4 style='margin:0;'>{sig['coin']} {sig['decision']} - {sig['status']}</h4>
                {time_html}
                <b>Entry:</b> ${sig['entry']:.4f} | <b>SL:</b> ${sig['sl']:.4f} | <b>TP:</b> ${sig['tp']:.4f}<br>
                <b>Live Price:</b> ${cur_px:.4f}
            </div>
            """, unsafe_allow_html=True)
            
        if st.button("Clear History"):
            st.session_state.signals = []
            st.rerun()
