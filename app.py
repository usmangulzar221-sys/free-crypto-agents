import streamlit as st, requests, pandas as pd, numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import streamlit.components.v1 as components

st.set_page_config(page_title="Crypto Agent Scanner", page_icon="🚀", layout="wide")

st.markdown("""
<style>
.stApp{background:#0b0f17;color:#e5e7eb}
.card{background:#111827;border-radius:12px;padding:14px;border:1px solid #1f2937;margin:8px 0}
.buy{color:#22c55e;font-weight:800}
.sell{color:#ef4444;font-weight:800}
.hold{color:#f59e0b;font-weight:800}
.agent{background:#0f172a;border-radius:10px;padding:10px;margin:6px 0;border-left:4px solid #3b82f6}
.bar{height:8px;border-radius:4px;background:#1f2937;overflow:hidden}
.bar>div{height:100%}
</style>
""", unsafe_allow_html=True)

API = "https://api.binance.com/api/v3"
COINS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT",
         "ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","LTCUSDT","BCHUSDT",
         "UNIUSDT","SUIUSDT","TRXUSDT","APTUSDT","ATOMUSDT","NEARUSDT",
         "INJUSDT","MATICUSDT","SHIBUSDT","PEPEUSDT","OPUSDT","ARBUSDT","TIAUSDT"]


@st.cache_data(ttl=20)
def kl(sym, itv="1h", lim=300):
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


@st.cache_data(ttl=10)
def price(sym):
    try:
        r = requests.get(f"{API}/ticker/price", params={"symbol": sym}, timeout=5)
        return float(r.json()["price"])
    except Exception:
        return None


@st.cache_data(ttl=10)
def tick24(sym):
    try:
        r = requests.get(f"{API}/ticker/24hr", params={"symbol": sym}, timeout=6)
        return r.json()
    except Exception:
        return {}


def ind(df):
    df = df.copy()
    df["ema20"] = df["c"].ewm(span=20).mean()
    df["ema50"] = df["c"].ewm(span=50).mean()
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
    return df


def zones(df, lb=5):
    H = df["h"].values; L = df["l"].values; T = df["t"].values
    res = []; sup = []
    for i in range(lb, len(df) - lb):
        if H[i] == max(H[i-lb:i+lb+1]): res.append((T[i], H[i]))
        if L[i] == min(L[i-lb:i+lb+1]): sup.append((T[i], L[i]))
    return sup[-3:], res[-3:]


def signals(df):
    out = []
    for i in range(1, len(df)):
        pf, ps = df["ema20"].iloc[i-1], df["ema50"].iloc[i-1]
        cf, cs = df["ema20"].iloc[i], df["ema50"].iloc[i]
        r = df["rsi"].iloc[i]
        if pd.isna(pf) or pd.isna(r):
            continue
        if pf <= ps and cf > cs and r < 70:
            out.append({"i":i,"time":df["t"].iloc[i],"price":df["c"].iloc[i],"type":"BUY","rsi":r})
        elif pf >= ps and cf < cs and r > 30:
            out.append({"i":i,"time":df["t"].iloc[i],"price":df["c"].iloc[i],"type":"SELL","rsi":r})
    return out


def track(df, s):
    i = s["i"]; e = s["price"]
    fut = df.iloc[i+1:]
    if fut.empty:
        return {"up":0.0,"down":0.0,"cur":e,"hrs":0.0,"live":True}
    cur = df["c"].iloc[-1]
    hrs = (df["t"].iloc[-1] - df["t"].iloc[i]).total_seconds() / 3600
    return {"up":(fut["h"].max()-e)/e*100,
            "down":(fut["l"].min()-e)/e*100,
            "cur":cur, "hrs":hrs, "live":False}


# ============ HEADER ============
btc_p = price("BTCUSDT")
if btc_p:
    st.title(f"🚀 Crypto Agent Scanner — BTC ${btc_p:,.2f}")
else:
    st.title("🚀 Crypto Agent Scanner")
st.caption(f"Live Binance data • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

tab1, tab2, tab3, tab4 = st.tabs([
    "📈 Chart + Zones",
    "📡 Signals (Time + Move)",
    "🤖 Agents Discussion",
    "🔔 Scanner + Volume Alerts"
])

# ============ TAB 1 : CHART ============
with tab1:
    c1, c2 = st.columns([1, 1])
    sym = c1.selectbox("Coin", COINS, index=0)
    itv = c2.selectbox("Timeframe", ["15m","1h","4h","1d"], index=1)

    df = kl(sym, itv, 300)
    if df.empty:
        st.error("Binance se data nahi mila. Network check karo.")
    else:
        df = ind(df)
        sup, res = zones(df)
        sigs = signals(df)
        last = df.iloc[-1]

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                            vertical_spacing=0.03,
                            row_heights=[0.6, 0.18, 0.22],
                            subplot_titles=("", "Volume", "RSI"))

        fig.add_trace(go.Candlestick(
            x=df["t"], open=df["o"], high=df["h"], low=df["l"], close=df["c"],
            name=sym, increasing_line_color="#22c55e",
            decreasing_line_color="#ef4444"), row=1, col=1)

        fig.add_trace(go.Scatter(x=df["t"], y=df["ema20"],
            line=dict(color="#22d3ee", width=1.5), name="EMA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["ema50"],
            line=dict(color="#fbbf24", width=1.5), name="EMA50"), row=1, col=1)

        # Resistance zones (red)
        for t, p in res:
            fig.add_hrect(y0=p*0.998, y1=p*1.002, fillcolor="#ef4444",
                          opacity=0.15, line_width=0, row=1, col=1)
            fig.add_hline(y=p, line_dash="dash", line_color="#ef4444",
                          annotation_text=f"RES ${p:,.2f}", row=1, col=1)
        # Support zones (green)
        for t, p in sup:
            fig.add_hrect(y0=p*0.998, y1=p*1.002, fillcolor="#22c55e",
                          opacity=0.15, line_width=0, row=1, col=1)
            fig.add_hline(y=p, line_dash="dash", line_color="#22c55e",
                          annotation_text=f"SUP ${p:,.2f}", row=1, col=1)

        # Buy/Sell triangles
        for s in sigs:
            col = "#22c55e" if s["type"] == "BUY" else "#ef4444"
            fig.add_trace(go.Scatter(
                x=[s["time"]], y=[s["price"]*0.998 if s["type"]=="BUY" else s["price"]*1.002],
                mode="markers+text",
                marker=dict(symbol="triangle-up" if s["type"]=="BUY" else "triangle-down",
                            size=16, color=col),
                text=[s["type"]], textposition="bottom center",
                textfont=dict(color=col, size=10),
                showlegend=False, hovertext=f"{s['type']} @ ${s['price']:,.4f}<br>RSI {s['rsi']:.1f}"),
                row=1, col=1)

        # Volume with color
        vc = ["#22c55e" if c >= o else "#ef4444" for c, o in zip(df["c"], df["o"])]
        fig.add_trace(go.Bar(x=df["t"], y=df["v"], marker_color=vc, name="Vol"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df["t"], y=df["vavg"],
            line=dict(color="#fbbf24", width=1), name="Vol Avg"), row=2, col=1)

        # RSI
        fig.add_trace(go.Scatter(x=df["t"], y=df["rsi"],
            line=dict(color="#a78bfa", width=1.5), name="RSI"), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", row=3, col=1)

        fig.update_layout(
            template="plotly_dark", height=750,
            paper_bgcolor="#0b0f17", plot_bgcolor="#0b0f17",
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", y=1.02),
            margin=dict(l=10, r=10, t=40, b=10),
            title=f"{sym} — {itv} • TradingView-style Zones + Signals")
        st.plotly_chart(fig, use_container_width=True)

        # Info strip
        vr = float(last["vr"]) if not pd.isna(last["vr"]) else 0
        tag = "🐳 VOLUME SPIKE" if vr > 1.5 else "Normal Volume"
        rsi_col = "#ef4444" if last["rsi"] > 70 else "#22c55e" if last["rsi"] < 30 else "#f59e0b"
        st.markdown(f"""
        <div class='card'>
        <b>Price:</b> ${last['c']:,.4f} | 
        <b>EMA20:</b> ${last['ema20']:,.2f} | <b>EMA50:</b> ${last['ema50']:,.2f} |
        <b>RSI:</b> <span style='color:{rsi_col}'>{last['rsi']:.1f}</span> |
        <b>ATR:</b> ${last['atr']:.4f} |
        <b>Vol:</b> {vr:.2f}x <span class='hold'>{tag}</span>
        </div>
        """, unsafe_allow_html=True)

# ============ TAB 2 : SIGNALS ============
with tab2:
    st.markdown("### Live Signals — Time + Entry + Current Move")
    sym2 = st.selectbox("Coin for signals", COINS, index=0, key="sig_sym")
    df2 = kl(sym2, "1h", 500)
    if df2.empty:
        st.error("Data nahi mila.")
    else:
        df2 = ind(df2)
        sg = signals(df2)
        if not sg:
            st.info("Is coin me koi signal nahi mila. Doosra coin try karo.")
        else:
            rows = []
            for s in sg[-15:]:
                t = track(df2, s)
                move = t["up"] if s["type"] == "BUY" else abs(t["down"])
                dur = f"{t['hrs']:.1f}h" if not t["live"] else "LIVE"
                rows.append({
                    "Time": s["time"].strftime("%Y-%m-%d %H:%M"),
                    "Type": s["type"],
                    "Entry $": round(s["price"], 4),
                    "RSI@Entry": round(s["rsi"], 1),
                    "Current $": round(t["cur"], 4),
                    "Max Up %": round(t["up"], 2),
                    "Max Down %": round(t["down"], 2),
                    "Duration": dur,
                    "Result": ("WIN ✅" if move > 1 else "OPEN ⏳" if t["live"] else "LOSS ❌")
                })
            ddf = pd.DataFrame(rows).iloc[::-1]
            st.dataframe(ddf, use_container_width=True, hide_index=True)

            # Signal cards with graphical bars
            st.markdown("### 📊 Graphical Signal Tracking")
            for s, r in zip(sg[-5:], rows[-5:]):
                t = track(df2, s)
                move = t["up"] if s["type"] == "BUY" else abs(t["down"])
                bar_col = "#22c55e" if move > 1 else "#ef4444" if move < 0 else "#f59e0b"
                bar_w = min(abs(move) * 10, 100)
                side_col = "buy" if s["type"] == "BUY" else "sell"
                st.markdown(f"""
                <div class='card'>
                <b class='{side_col}'>{s['type']}</b> @ <b>${s['price']:,.4f}</b> 
                — {s['time'].strftime('%d %b %H:%M')} (RSI {s['rsi']:.1f})<br>
                Now: <b>${t['cur']:,.4f}</b> | Max Up: <b class='buy'>{t['up']:+.2f}%</b> | 
                Max Down: <b class='sell'>{t['down']:+.2f}%</b> | 
                Duration: <b>{t['hrs']:.1f}h</b> {'<span class="hold">LIVE</span>' if t["live"] else ''}
                <div class='bar' style='margin-top:6px'><div style='width:{bar_w}%;background:{bar_col}'></div></div>
                </div>
                """, unsafe_allow_html=True)

# ============ TAB 3 : AGENTS ============
with tab3:
    st.markdown("### 🤖 Agent Discussion — Real Indicator based")
    sym3 = st.selectbox("Coin for agents", COINS, index=0, key="ag_sym")
    df3 = kl(sym3, "1h", 200)
    if df3.empty:
        st.error("Data nahi mila.")
    else:
        df3 = ind(df3)
        last = df3.iloc[-1]
        rsi = float(last["rsi"]); vr = float(last["vr"])
        trend = "BULLISH" if last["ema20"] > last["ema50"] else "BEARISH"
        atr = float(last["atr"]); px = float(last["c"])

        agents = [
            ("Trend Agent", "EMA 20/50", trend,
             f"EMA20 {last['ema20']:.2f} {'>' if trend=='BULLISH' else '<'} EMA50 {last['ema50']:.2f}"),
            ("Momentum Agent", "RSI-14",
             "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL",
             f"RSI {rsi:.1f}"),
            ("Volume Agent", "VSA / Volume Ratio",
             f"{vr:.2f}x",
             f"{'SPIKE — strong participation' if vr>1.5 else 'NORMAL volume'}"),
            ("Volatility Agent", "ATR-14",
             f"${atr:.4f}",
             f"Suggested SL: ${px-2*atr:.4f} | TP: ${px+3*atr:.4f}"),
            ("Risk Manager", "Position Sizing",
             "LOW RISK" if vr > 1.2 and 40 < rsi < 65 else "CAUTION",
             f"SL distance {2*atr/px*100:.2f}%"),
        ]

        votes_buy = 0; votes_sell = 0
        for name, role, verdict, msg in agents:
            if "BULLISH" in verdict or "OVERSOLD" in verdict: votes_buy += 1
            elif "BEARISH" in verdict or "OVERBOUGHT" in verdict: votes_sell += 1
            col = "#22c55e" if ("BULL" in verdict or "OVER" not in verdict and "SELL" not in verdict) else "#ef4444"
            st.markdown(f"""
            <div class='agent'>
            <b>🤖 {name}</b> <span style='color:#94a3b8'>({role})</span><br>
            Verdict: <b style='color:{col}'>{verdict}</b><br>
            <span style='color:#94a3b8'>{msg}</span>
            </div>
            """, unsafe_allow_html=True)

        # Consensus
        if votes_buy > votes_sell:
            consensus = "BUY / LONG"
            ccol = "#22c55e"
        elif votes_sell > votes_buy:
            consensus = "SELL / SHORT"
            ccol = "#ef4444"
        else:
            consensus = "WAIT / NO TRADE"
            ccol = "#f59e0b"

        st.markdown(f"""
        <div class='card' style='border:2px solid {ccol}'>
        <b>🗳️ Consensus after discussion:</b>
        <span style='color:{ccol};font-size:22px;font-weight:900'>{consensus}</span><br>
        Votes — BUY: <b>{votes_buy}</b> | SELL: <b>{votes_sell}</b> | 
        RSI: <b>{rsi:.1f}</b> | Vol: <b>{vr:.2f}x</b> | Trend: <b>{trend}</b>
        </div>
        """, unsafe_allow_html=True)

# ============ TAB 4 : SCANNER ============
with tab4:
    st.markdown("### 🔔 Multi-Coin Scanner + Volume Alerts")
    c1, c2 = st.columns([1, 2])
    if c1.button("🚀 Scan All Coins"):
        st.session_state.scan = True
    scan_on = st.session_state.get("scan", False) or c2.checkbox("Auto scan", value=False)

    if "alerts" not in st.session_state:
        st.session_state.alerts = []

    if scan_on:
        rows = []
        progress = st.progress(0)
        for idx, s in enumerate(COINS):
            progress.progress((idx + 1) / len(COINS))
            t24 = tick24(s)
            if not t24 or "lastPrice" not in t24:
                continue
            lastp = float(t24["lastPrice"])
            chg = float(t24["priceChangePercent"])
            volq = float(t24["quoteVolume"])
            dfx = kl(s, "1h", 60)
            vr = 0; rsi = 50; trend = "—"
            if not dfx.empty:
                dfx = ind(dfx)
                vr = float(dfx["vr"].iloc[-1]) if not pd.isna(dfx["vr"].iloc[-1]) else 0
                rsi = float(dfx["rsi"].iloc[-1]) if not pd.isna(dfx["rsi"].iloc[-1]) else 50
                trend = "BULL" if dfx["ema20"].iloc[-1] > dfx["ema50"].iloc[-1] else "BEAR"

            signal = "—"
            if trend == "BULL" and rsi < 65: signal = "BUY"
            elif trend == "BEAR" and rsi > 35: signal = "SELL"

            rows.append({
                "Coin": s.replace("USDT", ""),
                "Price $": round(lastp, 4),
                "24h %": round(chg, 2),
                "Vol $M": round(volq / 1e6, 1),
                "Vol Ratio": round(vr, 2),
                "RSI": round(rsi, 1),
                "Trend": trend,
                "Signal": signal,
                "Alert": "🐳 VOL SPIKE" if vr > 1.5 else ""
            })

            if vr > 1.5:
                key = f"{s}-{datetime.now().strftime('%Y%m%d%H')}"
                if key not in [a["key"] for a in st.session_state.alerts]:
                    st.session_state.alerts.append({
                        "key": key,
                        "msg": f"🐳 {s.replace('USDT','')} volume spike {vr:.2f}x at ${lastp:.4f}",
                        "time": datetime.now().strftime("%H:%M:%S")
                    })

        progress.empty()
        if rows:
            rdf = pd.DataFrame(rows).sort_values("Vol Ratio", ascending=False)
            st.dataframe(rdf, use_container_width=True, hide_index=True)

    # Alerts feed
    st.markdown("### 📢 Live Alerts Feed")
    if st.session_state.alerts:
        for a in st.session_state.alerts[-10:][::-1]:
            st.markdown(f"""
            <div class='card' style='border-left:4px solid #22c55e'>
            <b>{a['time']}</b> — {a['msg']}
            </div>
            """, unsafe_allow_html=True)
        if st.button("Clear alerts"):
            st.session_state.alerts = []
            st.rerun()
    else:
        st.info("Koi alert nahi. Scan chalao.")

st.caption("✅ Real Binance Data • No Demo Values • Rule-based Agents")
