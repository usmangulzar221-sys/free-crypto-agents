import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="Pro Trading Scanner", page_icon="📊", layout="wide")

st.markdown("""
<style>
.stApp{background:#0b0f17;color:#e5e7eb}
.card{background:#111827;border-radius:12px;padding:14px;border:1px solid #1f2937;margin:8px 0}
.buy{color:#22c55e;font-weight:800}
.sell{color:#ef4444;font-weight:800}
.hold{color:#f59e0b;font-weight:800}
.zone-sup{background:rgba(34,197,94,0.15);padding:4px 8px;border-radius:6px}
.zone-res{background:rgba(239,68,68,0.15);padding:4px 8px;border-radius:6px}
.llm-box{background:#1e1b4b;border-radius:10px;padding:12px;margin:8px 0;border-left:4px solid #a855f7}
.stat-box{background:#111827;border-radius:10px;padding:12px;text-align:center;border:1px solid #1f2937}
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
client = None
LLM_MODEL = None
if GROQ_AVAILABLE and GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        LLM_MODEL = "openai/gpt-oss-120b"
    except Exception:
        client = None

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
        return None, f"LLM: {str(e)[:180]}"

# ============ OKX DATA (Best for Streamlit Cloud) ============
OKX_BASE = "https://www.okx.com/api/v5"
TF_MAP = {"5m":"5m","15m":"15m","1h":"1H","4h":"4H","1d":"1D"}

@st.cache_data(ttl=3600)
def get_all_coins():
    """Fetch all USDT spot pairs from OKX, sorted by volume"""
    try:
        r = requests.get(f"{OKX_BASE}/market/tickers",
                         params={"instType":"SPOT"}, timeout=10).json()
        if r.get("code") != "0": return []
        coins = []
        for d in r["data"]:
            inst = d.get("instId","")
            if not inst.endswith("-USDT"): continue
            if "USDC" in inst or "DAI" in inst: continue
            try:
                vol = float(d.get("volCcy24h", 0))
            except Exception:
                vol = 0
            if vol < 10000: continue
            coins.append({"symbol": inst.replace("-",""),
                          "instId": inst,
                          "vol": vol,
                          "last": d.get("last","0"),
                          "chg": d.get("sodUtc8","0")})
        coins.sort(key=lambda x: x["vol"], reverse=True)
        return coins[:1000]
    except Exception:
        return []

@st.cache_data(ttl=20)
def klines(sym, itv="1h", lim=300):
    try:
        bar = TF_MAP.get(itv, "1H")
        r = requests.get(f"{OKX_BASE}/market/candles",
                         params={"instId": f"{sym[:len(sym)-4]}-USDT", "bar": bar, "limit": min(lim,300)},
                         timeout=8).json()
        if r.get("code") != "0" or not r.get("data"): return pd.DataFrame()
        d = r["data"]
        df = pd.DataFrame(d, columns=["t","o","h","l","c","v","vq","vc","confirm"])
        for col in ["o","h","l","c","v"]: df[col] = df[col].astype(float)
        df["t"] = pd.to_datetime(df["t"].astype(float), unit="ms")
        return df[["t","o","h","l","c","v"]].sort_values("t").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=15)
def ticker(sym):
    try:
        r = requests.get(f"{OKX_BASE}/market/ticker",
                         params={"instId": f"{sym[:len(sym)-4]}-USDT"}, timeout=6).json()
        if r.get("code") != "0" or not r.get("data"): return {}
        d = r["data"][0]
        last = float(d["last"]); op = float(d["open24h"])
        chg = (last-op)/op*100 if op else 0
        try: vol = float(d.get("volCcy24h", 0))
        except Exception: vol = 0
        return {"lastPrice": last, "chg24h": chg,
                "high24h": d.get("high24h","—"), "low24h": d.get("low24h","—"),
                "volUSDT": vol}
    except Exception:
        return {}

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

def find_zones(df, lb=5, max_zones=3):
    H = df["h"].values; L = df["l"].values; T = df["t"].values
    res = []; sup = []
    for i in range(lb, len(df)-lb):
        if H[i] == max(H[i-lb:i+lb+1]): res.append((T[i], H[i]))
        if L[i] == min(L[i-lb:i+lb+1]): sup.append((T[i], L[i]))
    return sup[-max_zones:], res[-max_zones:]

# ============ SIGNAL DETECTION ============
def detect_signals(df):
    """Detect BUY/SELL signals with EMA cross + RSI filter"""
    sigs = []
    for i in range(1, len(df)):
        pf, ps = df["ema20"].iloc[i-1], df["ema50"].iloc[i-1]
        cf, cs = df["ema20"].iloc[i], df["ema50"].iloc[i]
        r = df["rsi"].iloc[i]
        if pd.isna(pf) or pd.isna(r): continue
        if pf <= ps and cf > cs and r < 70:
            sigs.append({"i": i, "time": df["t"].iloc[i], "price": float(df["c"].iloc[i]),
                         "type": "BUY", "rsi": float(r)})
        elif pf >= ps and cf < cs and r > 30:
            sigs.append({"i": i, "time": df["t"].iloc[i], "price": float(df["c"].iloc[i]),
                         "type": "SELL", "rsi": float(r)})
    return sigs

def track_signal(df, sig, atr):
    """Track what happened after signal — TP/SL hits, max up/down, duration"""
    i = sig["i"]; entry = sig["price"]
    fut = df.iloc[i+1:]
    if fut.empty:
        return {"cur": entry, "max_up": 0, "max_down": 0, "dur": 0,
                "live": True, "tp1": False, "tp2": False, "sl": False,
                "first_hit": None, "first_hit_time": None}

    if sig["type"] == "BUY":
        tp1 = entry + 1.5*atr
        tp2 = entry + 3*atr
        sl = entry - 2*atr
    else:
        tp1 = entry - 1.5*atr
        tp2 = entry - 3*atr
        sl = entry + 2*atr

    tp1_hit = tp2_hit = sl_hit = False
    first_hit = None; first_time = None
    for idx, row in fut.iterrows():
        if sig["type"] == "BUY":
            if row["h"] >= tp1 and not tp1_hit:
                tp1_hit = True
                if first_hit is None: first_hit = "TP1"; first_time = row["t"]
            if row["h"] >= tp2 and not tp2_hit:
                tp2_hit = True
            if row["l"] <= sl and not sl_hit:
                sl_hit = True
                if first_hit is None: first_hit = "SL"; first_time = row["t"]
        else:
            if row["l"] <= tp1 and not tp1_hit:
                tp1_hit = True
                if first_hit is None: first_hit = "TP1"; first_time = row["t"]
            if row["l"] <= tp2 and not tp2_hit:
                tp2_hit = True
            if row["h"] >= sl and not sl_hit:
                sl_hit = True
                if first_hit is None: first_hit = "SL"; first_time = row["t"]

    max_up = (float(fut["h"].max()) - entry)/entry*100
    max_down = (float(fut["l"].min()) - entry)/entry*100
    dur = (df["t"].iloc[-1] - df["t"].iloc[i]).total_seconds()/3600

    return {"cur": float(df["c"].iloc[-1]), "max_up": max_up, "max_down": max_down,
            "dur": dur, "live": True, "tp1": tp1_hit, "tp2": tp2_hit, "sl": sl_hit,
            "first_hit": first_hit, "first_hit_time": first_time,
            "tp1_price": tp1, "tp2_price": tp2, "sl_price": sl}

# ============ MULTI-COIN SCANNER ============
def analyze_coin(sym):
    """Full analysis for one coin - returns dict"""
    try:
        df = klines(sym, "1h", 200)
        if df.empty or len(df) < 100: return None
        df = add_indicators(df)
        last = df.iloc[-1]
        px = float(last["c"])
        rsi = float(last["rsi"]) if not pd.isna(last["rsi"]) else 50
        vr = float(last["vr"]) if not pd.isna(last["vr"]) else 0
        atr = float(last["atr"]) if not pd.isna(last["atr"]) else px*0.01
        ema20 = float(last["ema20"]); ema50 = float(last["ema50"])
        trend = "BULL" if ema20 > ema50 else "BEAR"
        t = ticker(sym)
        chg = t.get("chg24h", 0) if t else 0
        vol_usdt = t.get("volUSDT", 0) if t else 0

        # Signal logic
        if trend == "BULL" and rsi < 65 and rsi > 40:
            signal = "LONG"
        elif trend == "BEAR" and rsi > 35 and rsi < 60:
            signal = "SHORT"
        else:
            signal = "WAIT"

        # Entry/SL/TP
        if signal == "LONG":
            entry = px; sl = px - 2*atr
            tp1 = px + 1.5*atr; tp2 = px + 3*atr; tp3 = px + 5*atr
        elif signal == "SHORT":
            entry = px; sl = px + 2*atr
            tp1 = px - 1.5*atr; tp2 = px - 3*atr; tp3 = px - 5*atr
        else:
            entry = sl = tp1 = tp2 = tp3 = px

        # Strength score
        strength = 0
        if trend == "BULL" and signal == "LONG": strength += 30
        if trend == "BEAR" and signal == "SHORT": strength += 30
        if 45 < rsi < 60: strength += 15
        if vr > 1.5: strength += 20
        if vr > 1.2: strength += 10
        strength += min(int(chg), 20) if signal == "LONG" and chg > 0 else 0
        strength += min(int(-chg), 20) if signal == "SHORT" and chg < 0 else 0

        return {
            "Symbol": sym, "Price": px, "Chg24h": round(chg,2),
            "VolUSDT_M": round(vol_usdt/1e6, 1),
            "Trend": trend, "RSI": round(rsi,1),
            "VolRatio": round(vr,2), "ATR_pct": round(atr/px*100,2),
            "Signal": signal, "Strength": min(strength, 100),
            "Entry": round(entry,6), "SL": round(sl,6),
            "TP1": round(tp1,6), "TP2": round(tp2,6), "TP3": round(tp3,6),
            "RR": round(abs(tp2-entry)/abs(sl-entry),2) if sl != entry else 0,
            "EMA20": round(ema20,6), "EMA50": round(ema50,6),
            "PriceTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception:
        return None

# ============ SIDEBAR ============
with st.sidebar:
    st.markdown("### 🔑 Groq API Key (Optional)")
    if GROQ_API_KEY:
        st.success("✅ Key loaded")
    else:
        uk = st.text_input("Groq API key (for LLM Agents)", type="password")
        if uk:
            try:
                client = Groq(api_key=uk); LLM_MODEL = "openai/gpt-oss-120b"
                st.success("✅ Key set!")
            except Exception as e:
                st.error(f"Invalid: {e}")
        else:
            st.info("Free key: [console.groq.com](https://console.groq.com/keys)")
    st.markdown("---")
    st.markdown(f"**Model:** `{LLM_MODEL or 'not set'}`")
    st.markdown("**Data:** OKX Spot (1000+ coins)")
    st.caption("LLM optional — scanner works without it")

# ============ HEADER ============
btc_p = ticker("BTCUSDT")
btc_last = btc_p.get("lastPrice", 0) if btc_p else 0
btc_chg = btc_p.get("chg24h", 0) if btc_p else 0
eth_p = ticker("ETHUSDT")
sol_p = ticker("SOLUSDT")

c1,c2,c3,c4 = st.columns(4)
c1.metric("BTC/USDT", f"${btc_last:,.2f}", f"{btc_chg:+.2f}%")
c2.metric("ETH/USDT", f"${eth_p.get('lastPrice',0):,.2f}" if eth_p else "—",
          f"{eth_p.get('chg24h',0):+.2f}%" if eth_p else None)
c3.metric("SOL/USDT", f"${sol_p.get('lastPrice',0):,.2f}" if sol_p else "—",
          f"{sol_p.get('chg24h',0):+.2f}%" if sol_p else None)
c4.metric("Time", datetime.now().strftime("%H:%M:%S"))

st.title("📊 Pro Trading Scanner — 1000+ Coins")

# ============ TABS ============
tab_chart, tab_scanner, tab_history, tab_llm = st.tabs([
    "📈 Chart + Zones",
    "🔔 Live Scanner",
    "📜 Signal History",
    "🧠 LLM Agents"
])

# ============ TAB 1: CHART ============
with tab_chart:
    st.markdown("### 📈 TradingView-Style Chart")
    col1, col2, col3 = st.columns([2,1,1])
    all_coins = get_all_coins()
    coin_options = [c["symbol"] for c in all_coins[:500]] if all_coins else ["BTCUSDT","ETHUSDT","SOLUSDT"]
    sym = col1.selectbox("Coin", coin_options, index=0, key="chart_sym")
    itv = col2.selectbox("Timeframe", ["15m","1h","4h","1d"], index=1, key="chart_tf")
    show_zones = col3.checkbox("Zones", value=True)

    df = klines(sym, itv, 300)
    if df.empty:
        st.error(f"❌ Data nahi mila: {sym}. Dusra coin try karo.")
    else:
        df = add_indicators(df)
        sup, res = find_zones(df)
        sigs = detect_signals(df)
        last = df.iloc[-1]; atr = float(last["atr"])

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                            row_heights=[0.62, 0.16, 0.22],
                            subplot_titles=("","Volume","RSI"))

        # Candlesticks
        fig.add_trace(go.Candlestick(
            x=df["t"], open=df["o"], high=df["h"], low=df["l"], close=df["c"],
            name=sym,
            increasing_line_color="#22c55e", increasing_fillcolor="#22c55e",
            decreasing_line_color="#ef4444", decreasing_fillcolor="#ef4444"),
            row=1, col=1)

        # EMAs
        fig.add_trace(go.Scatter(x=df["t"], y=df["ema20"],
            line=dict(color="#22d3ee", width=1.5), name="EMA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["ema50"],
            line=dict(color="#fbbf24", width=1.5), name="EMA50"), row=1, col=1)
        if not df["ema200"].isna().all():
            fig.add_trace(go.Scatter(x=df["t"], y=df["ema200"],
                line=dict(color="#a855f7", width=1, dash="dot"), name="EMA200"), row=1, col=1)

        # Support/Resistance ZONES (like TradingView sample)
        if show_zones:
            for t, p in res[-3:]:
                fig.add_hrect(y0=p*0.995, y1=p*1.005, fillcolor="#ef4444",
                              opacity=0.18, line_width=0, row=1, col=1,
                              annotation_text=f"Resistance", annotation_position="left")
            for t, p in sup[-3:]:
                fig.add_hrect(y0=p*0.995, y1=p*1.005, fillcolor="#22c55e",
                              opacity=0.18, line_width=0, row=1, col=1,
                              annotation_text=f"Support", annotation_position="left")

        # Buy/Sell signals markers
        for s in sigs:
            col = "#22c55e" if s["type"] == "BUY" else "#ef4444"
            ypos = s["price"]*0.997 if s["type"]=="BUY" else s["price"]*1.003
            fig.add_trace(go.Scatter(
                x=[s["time"]], y=[ypos],
                mode="markers+text",
                marker=dict(symbol="triangle-up" if s["type"]=="BUY" else "triangle-down",
                            size=14, color=col, line=dict(color="white", width=1.5)),
                text=[s["type"]], textposition="bottom center",
                textfont=dict(color=col, size=10),
                showlegend=False,
                hovertemplate=f"<b>{s['type']}</b><br>Price: ${s['price']:,.6f}<br>"
                              f"RSI: {s['rsi']:.1f}<br>Time: {s['time'].strftime('%m-%d %H:%M')}<extra></extra>"),
                row=1, col=1)

        # Volume
        vc = ["#22c55e" if c >= o else "#ef4444" for c, o in zip(df["c"], df["o"])]
        fig.add_trace(go.Bar(x=df["t"], y=df["v"], marker_color=vc,
                             name="Volume", opacity=0.85), row=2, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["vavg"],
            line=dict(color="#fbbf24", width=1), name="Vol Avg"), row=2, col=1)

        # RSI
        fig.add_trace(go.Scatter(x=df["t"], y=df["rsi"],
            line=dict(color="#a78bfa", width=1.5), name="RSI"), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", opacity=0.6, row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", opacity=0.6, row=3, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="#64748b", opacity=0.3, row=3, col=1)

        fig.update_layout(
            template="plotly_dark", height=850,
            paper_bgcolor="#0b0f17", plot_bgcolor="#0b0f17",
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", y=1.02, bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=10, r=80, t=60, b=10),
            title=f"{sym} • {itv} • Binance-style S/R + Signals")
        fig.update_xaxes(showgrid=True, gridcolor="#1f2937", row=1, col=1)
        fig.update_xaxes(showgrid=True, gridcolor="#1f2937", row=2, col=1)
        fig.update_xaxes(showgrid=True, gridcolor="#1f2937", row=3, col=1)
        fig.update_yaxes(showgrid=True, gridcolor="#1f2937", row=1, col=1)
        fig.update_yaxes(showgrid=True, gridcolor="#1f2937", row=2, col=1)
        fig.update_yaxes(showgrid=True, gridcolor="#1f2937", row=3, col=1)
        st.plotly_chart(fig, use_container_width=True)

        # Live info
        rsi_v = float(last["rsi"]) if not pd.isna(last["rsi"]) else 50
        vr = float(last["vr"]) if not pd.isna(last["vr"]) else 0
        trend_col = "#22c55e" if last["ema20"] > last["ema50"] else "#ef4444"
        rsi_col = "#ef4444" if rsi_v > 70 else "#22c55e" if rsi_v < 30 else "#f59e0b"

        st.markdown(f"""
        <div class='card'>
        <b>Price:</b> ${last['c']:,.6f} &nbsp;|&nbsp;
        <b>EMA20:</b> ${last['ema20']:,.6f} &nbsp;|&nbsp;
        <b>EMA50:</b> ${last['ema50']:,.6f} &nbsp;|&nbsp;
        <b>RSI:</b> <span style='color:{rsi_col}'>{rsi_v:.1f}</span> &nbsp;|&nbsp;
        <b>ATR:</b> {atr/last['c']*100:.2f}% &nbsp;|&nbsp;
        <b>VolRatio:</b> {vr:.2f}x &nbsp;|&nbsp;
        <b>Trend:</b> <span style='color:{trend_col}'>{'BULLISH' if last['ema20']>last['ema50'] else 'BEARISH'}</span>
        </div>
        """, unsafe_allow_html=True)

        # Recent signals on this chart
        if sigs:
            st.markdown("#### 📜 Recent Signals on Chart")
            recent_sigs = []
            for s in sigs[-10:][::-1]:
                t = track_signal(df, s, atr)
                recent_sigs.append({
                    "Time": s["time"].strftime("%m-%d %H:%M"),
                    "Type": s["type"], "Entry": round(s["price"],6),
                    "RSI": round(s["rsi"],1),
                    "Max Up %": round(t["max_up"],2),
                    "Max Down %": round(t["max_down"],2),
                    "First Hit": t["first_hit"] or "—",
                    "Dur": f"{t['dur']:.1f}h"
                })
            st.dataframe(pd.DataFrame(recent_sigs), use_container_width=True, hide_index=True)

# ============ TAB 2: SCANNER ============
with tab_scanner:
    st.markdown("### 🔔 Multi-Coin Live Scanner")
    c1, c2, c3 = st.columns([1, 1, 2])
    scan_count = c1.slider("Coins to scan", 20, 200, 50, 10)
    min_strength = c2.slider("Min strength", 0, 100, 30, 5)
    scan_btn = c3.button("🚀 Start Scan", type="primary")

    if "scan_results" not in st.session_state:
        st.session_state.scan_results = []
        st.session_state.scan_time = None

    if scan_btn:
        all_coins = get_all_coins()
        if not all_coins:
            st.error("❌ OKX se coins load nahi hue. Retry karo.")
        else:
            scan_list = all_coins[:scan_count]
            st.info(f"Scanning {len(scan_list)} coins (by volume)...")
            prog = st.progress(0)
            results = []
            with ThreadPoolExecutor(max_workers=10) as ex:
                futures = {ex.submit(analyze_coin, c["symbol"]): c["symbol"] for c in scan_list}
                done = 0
                for f in as_completed(futures):
                    done += 1
                    prog.progress(done/len(scan_list))
                    r = f.result()
                    if r and r["Strength"] >= min_strength:
                        results.append(r)
            prog.empty()
            st.session_state.scan_results = results
            st.session_state.scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.success(f"✅ Scanned {len(scan_list)} coins in {done}s")

    if st.session_state.scan_results:
        results = st.session_state.scan_results
        df_res = pd.DataFrame(results).sort_values("Strength", ascending=False)

        longs = df_res[df_res["Signal"]=="LONG"]
        shorts = df_res[df_res["Signal"]=="SHORT"]
        waits = df_res[df_res["Signal"]=="WAIT"]

        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Total Scanned", len(df_res))
        m2.metric("LONG 🟢", len(longs))
        m3.metric("SHORT 🔴", len(shorts))
        m4.metric("WAIT ⏸️", len(waits))
        st.caption(f"Last scan: {st.session_state.scan_time}")

        st.markdown("#### 🟢 LONG Signals")
        if not longs.empty:
            st.dataframe(longs, use_container_width=True, hide_index=True)
        else:
            st.info("No LONG signals right now")

        st.markdown("#### 🔴 SHORT Signals")
        if not shorts.empty:
            st.dataframe(shorts, use_container_width=True, hide_index=True)
        else:
            st.info("No SHORT signals right now")

        st.markdown("#### ⏸️ WAIT (No clear signal)")
        if not waits.empty:
            st.dataframe(waits.head(30), use_container_width=True, hide_index=True)

# ============ TAB 3: SIGNAL HISTORY ============
with tab_history:
    st.markdown("### 📜 Signal History & Performance")
    c1, c2 = st.columns([2,1])
    all_coins = get_all_coins()
    coin_options = [c["symbol"] for c in all_coins[:300]] if all_coins else ["BTCUSDT"]
    hist_sym = c1.selectbox("Coin", coin_options, index=0, key="hist_sym")
    hist_itv = c2.selectbox("TF", ["15m","1h","4h"], index=1, key="hist_tf")

    df_h = klines(hist_sym, hist_itv, 500)
    if df_h.empty:
        st.error("Data nahi mila")
    else:
        df_h = add_indicators(df_h)
        sigs = detect_signals(df_h)
        if not sigs:
            st.info("Koi signal nahi mila is coin par")
        else:
            rows = []
            wins = losses = 0
            for s in sigs[-50:][::-1]:
                atr = float(df_h["atr"].iloc[s["i"]]) if not pd.isna(df_h["atr"].iloc[s["i"]]) else s["price"]*0.01
                t = track_signal(df_h, s, atr)
                if s["type"] == "BUY":
                    result = "WIN ✅" if t["max_up"] > 1 else "LOSS ❌" if t["max_down"] < -1 else "OPEN ⏳"
                else:
                    result = "WIN ✅" if t["max_down"] < -1 else "LOSS ❌" if t["max_up"] > 1 else "OPEN ⏳"
                if "WIN" in result: wins += 1
                elif "LOSS" in result: losses += 1

                rows.append({
                    "Time": s["time"].strftime("%Y-%m-%d %H:%M"),
                    "Type": s["type"],
                    "Entry": round(s["price"],6),
                    "SL": round(t.get("sl_price",0),6),
                    "TP1": round(t.get("tp1_price",0),6),
                    "TP2": round(t.get("tp2_price",0),6),
                    "Max Up %": round(t["max_up"],2),
                    "Max Down %": round(t["max_down"],2),
                    "TP1 Hit": "✅" if t["tp1"] else "—",
                    "TP2 Hit": "✅" if t["tp2"] else "—",
                    "SL Hit": "🔴" if t["sl"] else "—",
                    "First Hit": t["first_hit"] or "—",
                    "Duration": f"{t['dur']:.1f}h",
                    "Result": result
                })

            total = wins + losses
            wr = (wins/total*100) if total > 0 else 0
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("Total Signals", len(sigs))
            m2.metric("Wins ✅", wins)
            m3.metric("Losses ❌", losses)
            m4.metric("Win Rate", f"{wr:.1f}%")

            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ============ TAB 4: LLM AGENTS ============
with tab_llm:
    st.markdown("### 🧠 LLM Agent Discussion (Real AI)")
    if not GROQ_API_KEY:
        st.warning("⚠️ Groq API key daalo sidebar me (free from console.groq.com)")
    else:
        all_coins = get_all_coins()
        coin_options = [c["symbol"] for c in all_coins[:300]] if all_coins else ["BTCUSDT"]
        c1, c2 = st.columns([2,1])
        llm_sym = c1.selectbox("Coin", coin_options, index=0, key="llm_sym")
        llm_itv = c2.selectbox("TF", ["15m","1h","4h"], index=1, key="llm_tf")

        if st.button("🚀 Run 5 LLM Agents", type="primary"):
            df_l = klines(llm_sym, llm_itv, 200)
            if df_l.empty:
                st.error("Data nahi mila")
            else:
                df_l = add_indicators(df_l)
                last = df_l.iloc[-1]
                px = float(last["c"])
                atr = float(last["atr"])
                snap_str = (f"Symbol: {llm_sym}\nTimeframe: {llm_itv}\nPrice: {px:.6f}\n"
                            f"EMA20: {float(last['ema20']):.6f}\nEMA50: {float(last['ema50']):.6f}\n"
                            f"RSI: {float(last['rsi']):.2f}\nMACD: {float(last['macd']):.6f}\n"
                            f"VolRatio: {float(last['vr']):.2f}\nATR: {atr:.6f}")

                with st.spinner("5 LLM agents analyzing..."):
                    t0 = time.time()
                    agents = [
                        ("📈 Trend Analyst", "You analyze trend. Reply JSON: {\"verdict\":\"BULLISH|BEARISH|SIDEWAYS\",\"score\":-3 to 3,\"reason\":\"1 line\"}"),
                        ("⚡ Momentum Analyst", "You analyze momentum. Reply JSON: {\"verdict\":\"STRONG|WEAK|NEUTRAL\",\"score\":-3 to 3,\"reason\":\"1 line\"}"),
                        ("🐳 Volume Analyst", "You analyze volume. Reply JSON: {\"verdict\":\"HIGH|NORMAL|LOW\",\"score\":-3 to 3,\"reason\":\"1 line\"}"),
                        ("🛡️ Risk Manager", "You assess risk. Reply JSON: {\"verdict\":\"LOW|MEDIUM|HIGH\",\"score\":-3 to 3,\"sl_price\":number,\"reason\":\"1 line\"}"),
                        ("🎯 S/R Analyst", "You analyze support/resistance. Reply JSON: {\"verdict\":\"NEAR_SUPPORT|NEAR_RESISTANCE|MID\",\"score\":-3 to 3,\"reason\":\"1 line\"}"),
                    ]
                    results = []
                    for name, sys_prompt in agents:
                        resp, err = llm_call(sys_prompt, snap_str, max_tokens=180)
                        if err:
                            results.append({"name": name, "verdict": "ERROR",
                                            "score": 0, "reason": err, "sl_price": None})
                            continue
                        try:
                            txt = resp.strip()
                            if "```" in txt: txt = txt.split("```")[1].replace("json","").strip()
                            d = json.loads(txt)
                            results.append({"name": name, "verdict": d.get("verdict","?"),
                                            "score": int(d.get("score",0)),
                                            "reason": d.get("reason",""),
                                            "sl_price": d.get("sl_price")})
                        except Exception:
                            results.append({"name": name, "verdict": "PARSE_ERR",
                                            "score": 0, "reason": resp[:100], "sl_price": None})

                    for a in results:
                        vcol = "#22c55e" if a['score']>0 else "#ef4444" if a['score']<0 else "#f59e0b"
                        sl_txt = f"<br>SL: ${a['sl_price']}" if a.get('sl_price') else ""
                        st.markdown(f"""
                        <div class='llm-box' style='border-left-color:{vcol}'>
                        <b>{a['name']}</b> → <b style='color:{vcol}'>{a['verdict']}</b>
                        (score {a['score']:+d})<br>
                        <span style='color:#cbd5e1;font-size:13px'>{a['reason']}</span>{sl_txt}
                        </div>
                        """, unsafe_allow_html=True)

                    # Chief consensus
                    summary = "\n".join([f"{a['name']}: {a['verdict']} ({a['score']:+d})" for a in results])
                    chief_prompt = f"{snap_str}\n\nAnalyst reports:\n{summary}\n\nGive final decision."
                    chief_sys = "You are Chief Trader. Reply JSON: {\"decision\":\"BUY|SELL|HOLD\",\"confidence\":0-100,\"entry\":number,\"sl\":number,\"tp1\":number,\"tp2\":number,\"tp3\":number,\"reasoning\":\"2 lines\"}"
                    resp, err = llm_call(chief_sys, chief_prompt, max_tokens=400)
                    if not err:
                        try:
                            txt = resp.strip()
                            if "```" in txt: txt = txt.split("```")[1].replace("json","").strip()
                            cons = json.loads(txt)
                            dec = cons.get("decision","HOLD")
                            dcol = "#22c55e" if dec=="BUY" else "#ef4444" if dec=="SELL" else "#f59e0b"
                            st.markdown(f"""
                            <div class='card' style='border:3px solid {dcol};text-align:center'>
                            <div style='color:#94a3b8;font-size:13px'>FINAL DECISION</div>
                            <div style='color:{dcol};font-size:36px;font-weight:900;margin:8px 0'>{dec}</div>
                            <div>Confidence: <b>{cons.get('confidence',0)}%</b></div>
                            <div style='margin-top:14px'>
                            <b>Entry:</b> ${cons.get('entry','—')} |
                            <b>SL:</b> <span class='sell'>${cons.get('sl','—')}</span> |
                            <b>TP1:</b> <span class='buy'>${cons.get('tp1','—')}</span> |
                            <b>TP2:</b> <span class='buy'>${cons.get('tp2','—')}</span> |
                            <b>TP3:</b> <span class='buy'>${cons.get('tp3','—')}</span>
                            </div>
                            <div style='margin-top:12px;color:#cbd5e1;font-style:italic'>"{cons.get('reasoning','')}"</div>
                            </div>
                            """, unsafe_allow_html=True)
                        except Exception:
                            st.error(f"Chief parse failed: {resp[:200]}")
                    st.caption(f"✅ {time.time()-t0:.1f}s • 6 LLM calls")
