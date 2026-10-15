import streamlit as st, pandas as pd, numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit.components.v1 as components
from datetime import datetime

from data_api import COINS, KL, TX, OI_FR, BOOK, FG, GM, MP, PKT, PKT24
from indicators import IND, ZN, SG, TRK, SCN
from agents import R1, R2, R3, GK, MD

st.set_page_config(page_title="AI Edge Scanner", layout="wide")

st.markdown("<style>.stApp{background:#0b0f17;color:#e5e7eb}.card{background:#111827;border-radius:12px;padding:14px;border:1px solid #1f2937;margin:8px 0}.buy{color:#22c55e;font-weight:800}.sell{color:#ef4444;font-weight:800}.llm{background:#1e1b4b;border-radius:10px;padding:12px;margin:8px 0;border-left:4px solid #a855f7}.sig{background:#1e293b;border-radius:10px;padding:12px;margin:8px 0;border-left:5px solid #22c55e}.sigS{border-left-color:#ef4444}.radar{background:#0f172a;border-radius:10px;padding:12px;margin:8px 0;border:1px solid #1f2937}.big{font-size:32px;font-weight:900}.zone{background:#1e293b;border-radius:8px;padding:8px;margin:4px 0;display:flex;justify-content:space-between}</style>", unsafe_allow_html=True)

def VOICE(text):
    try:
        s = text.replace("'", "").replace('"', '').replace("\n", " ")
        components.html("<script>var u=new SpeechSynthesisUtterance('" + s + "');u.rate=0.9;window.speechSynthesis.speak(u);</script>", height=0)
    except:
        pass

if "alerts" not in st.session_state:
    st.session_state.alerts = []
if "trades" not in st.session_state:
    st.session_state.trades = []
if "scan_res" not in st.session_state:
    st.session_state.scan_res = []

with st.sidebar:
    st.markdown("### Groq API Key")
    if GK:
        st.success("Loaded")
    else:
        uk = st.text_input("API key", type="password")
        if uk:
            try:
                import agents
                from groq import Groq
                agents.cl = Groq(api_key=uk)
                agents.MD = "openai/gpt-oss-120b"
                st.success("Set!")
            except:
                st.error("Invalid")
        else:
            st.info("Free: console.groq.com/keys")
    st.markdown("**Model:** " + str(MD or "-"))
    st.markdown("**Time:** " + PKT() + " PKT")
    voice_on = st.checkbox("Voice Alerts", value=True)

bp = TX("BTCUSDT")
ep = TX("ETHUSDT")
s2 = TX("SOLUSDT")
c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC", "${:,.2f}".format(bp.get("p", 0)) if bp else "-", "{:+.2f}%".format(bp.get("c", 0)) if bp else None)
c2.metric("ETH", "${:,.2f}".format(ep.get("p", 0)) if ep else "-", "{:+.2f}%".format(ep.get("c", 0)) if ep else None)
c3.metric("SOL", "${:,.2f}".format(s2.get("p", 0)) if s2 else "-", "{:+.2f}%".format(s2.get("c", 0)) if s2 else None)
c4.metric("Time PKT", PKT(), PKT24())
st.title("AI Edge Scanner")

if st.session_state.alerts:
    st.markdown("### Live Alerts")
    for a in st.session_state.alerts[-5:][::-1]:
        st.markdown("<div class='sig'><b>" + a["time"] + "</b> - " + a["msg"] + "</div>", unsafe_allow_html=True)

T1, T2, T3, T4, T5 = st.tabs(["Auto + LLM", "Scanner", "Trades", "Radar", "Chart"])

with T1:
    st.markdown("### Auto Signals + LLM Debate")
    if not GK:
        st.warning("Add Groq key in sidebar")
    else:
        mkt = st.radio("Market", ["SPOT", "FUTURES"], horizontal=True, key="mkt1")
        mkt_id = "SPOT" if mkt == "SPOT" else "SWAP"
        al = COINS(mkt_id)
        opt = [c["s"] for c in al[:200]] if al else ["BTCUSDT"]
        cc1, cc2 = st.columns([2, 1])
        ls = cc1.selectbox("Coin", opt, index=0, key="ls1")
        li = cc2.selectbox("TF", ["15m", "1h", "4h"], index=1, key="li1")
        b1, b2 = st.columns(2)
        run1 = b1.button("LLM Debate", type="primary", key="r1")
        run2 = b2.button("Auto Quick", key="r2")
        if run1 or run2:
            df = KL(ls, li, 250, mkt_id)
            if df.empty:
                st.error("No data")
            else:
                df = IND(df)
                la = df.iloc[-1]
                r = float(la["rsi"]) if not pd.isna(la["rsi"]) else 50
                if run2:
                    d = "BUY" if r < 45 else "SELL" if r > 55 else "HOLD"
                    cc = 60 + int(abs(50 - r))
                    e = float(la["c"])
                    a = float(la["atr"]) if not pd.isna(la["atr"]) else e * 0.01
                    if d == "BUY":
                        sl = e - 2 * a
                        tp1 = e + 1.5 * a
                        tp2 = e + 3 * a
                    elif d == "SELL":
                        sl = e + 2 * a
                        tp1 = e - 1.5 * a
                        tp2 = e - 3 * a
                    else:
                        sl = tp1 = tp2 = e
                    dc = "#22c55e" if d == "BUY" else "#ef4444" if d == "SELL" else "#f59e0b"
                    st.markdown("<div class='card' style='border:3px solid " + dc + ";text-align:center'><div style='color:#94a3b8'>AUTO " + mkt + "</div><div style='color:" + dc + ";font-size:36px;font-weight:900'>" + d + "</div><div>Conf: " + str(cc) + "%</div><div style='margin-top:12px'><b>Entry:</b> $" + str(round(e, 6)) + " <b>SL:</b> $" + str(round(sl, 6)) + " <b>TP1:</b> $" + str(round(tp1, 6)) + " <b>TP2:</b> $" + str(round(tp2, 6)) + "</div></div>", unsafe_allow_html=True)
                    st.session_state.trades.append({"time": PKT(), "coin": ls, "market": mkt, "side": d, "entry": e, "sl": sl, "tp1": tp1, "tp2": tp2})
                    st.session_state.alerts.append({"time": PKT(), "msg": "Auto " + d + " " + ls + " " + mkt})
                    if voice_on:
                        VOICE("Auto " + d + " " + ls.replace("USDT", "") + " " + mkt)
                else:
                    f = FG()
                    g = GM()
                    m2 = MP()
                    nt = "Symbol: " + ls + " " + mkt + "\n"
                    nt += "Price: " + str(round(float(la["c"]), 6)) + "\n"
                    nt += "EMA20: " + str(round(float(la["e20"]), 6)) + "\n"
                    nt += "EMA50: " + str(round(float(la["e50"]), 6)) + "\n"
                    nt += "RSI: " + str(round(r, 2)) + "\n"
                    nt += "MACD Hist: " + str(round(float(la["mhist"]), 6)) + "\n"
                    nt += "ATR: " + str(round(float(la["atr"]), 6)) + "\n"
                    nt += "BB Upper: " + str(round(float(la["bbu"]), 6)) + "\n"
                    nt += "BB Lower: " + str(round(float(la["bbl"]), 6)) + "\n"
                    nt += "ADX: " + str(round(float(la["adx"]), 2)) + "\n"
                    nt += "Stoch K: " + str(round(float(la["sk"]), 2)) + "\n"
                    nt += "Williams R: " + str(round(float(la["wr"]), 2)) + "\n"
                    nt += "VWAP: " + str(round(float(la["vwap"]), 6)) + "\n"
                    nt += "VolRatio: " + str(round(float(la["vr"]), 2)) + "\n"
                    nt += "CVD: " + str(round(float(la["cvd"]), 0)) + "\n"
                    nt += "FearGreed: " + str(f["v"]) + " " + f["l"] + "\n"
                    nt += "BTCDom: " + str(g["btc"]) + "%\n"
                    nt += "Block: " + str(m2["h"])
                    with st.spinner("Round 1: 11 agents..."):
                        res1 = R1(nt)
                    st.markdown("#### Round 1 - 11 Agents")
                    for a in res1:
                        vc = "#22c55e" if a["s"] > 0 else "#ef4444" if a["s"] < 0 else "#f59e0b"
                        st.markdown("<div class='llm' style='border-left-color:" + vc + "'><b>" + a["n"] + "</b> -> <b style='color:" + vc + "'>" + str(a["v"]) + "</b> (" + str(a["s"]) + ")<br><span style='color:#cbd5e1;font-size:13px'>" + str(a["r"]) + "</span></div>", unsafe_allow_html=True)
                    with st.spinner("Round 2: Senior debating..."):
                        res2 = R2(nt, res1)
                        vc = "#22c55e" if res2["s"] > 0 else "#ef4444" if res2["s"] < 0 else "#f59e0b"
                        st.markdown("#### Round 2 - Senior")
                        st.markdown("<div class='llm' style='border-left-color:" + vc + "'><b>Senior</b> -> <b style='color:" + vc + "'>" + str(res2["v"]) + "</b> (" + str(res2["s"]) + ")<br>" + str(res2["r"]) + "</div>", unsafe_allow_html=True)
                    with st.spinner("Round 3: Chief..."):
                        cons, ce = R3(nt, res1, res2)
                        if ce:
                            st.error(ce)
                        else:
                            dec = cons.get("decision", "HOLD")
                            mt = cons.get("market_type", mkt)
                            cf = cons.get("confidence", 0)
                            dc = "#22c55e" if dec == "BUY" else "#ef4444" if dec == "SELL" else "#f59e0b"
                            st.markdown("#### Round 3 - Chief FINAL")
                            st.markdown("<div class='card' style='border:3px solid " + dc + ";text-align:center'><div style='color:#94a3b8'>FINAL - " + mt + "</div><div style='color:" + dc + ";font-size:38px;font-weight:900'>" + str(dec) + "</div><div>Conf: " + str(cf) + "%</div><div style='margin-top:14px'><b>Entry:</b> $" + str(cons.get("entry", "-")) + " <b>SL:</b> $" + str(cons.get("sl", "-")) + " <b>TP1:</b> $" + str(cons.get("tp1", "-")) + " <b>TP2:</b> $" + str(cons.get("tp2", "-")) + "</div><div style='margin-top:10px;font-style:italic'>" + str(cons.get("reasoning", "")) + "</div></div>", unsafe_allow_html=True)
                            st.session_state.trades.append({"time": PKT(), "coin": ls, "market": mt, "side": dec, "entry": cons.get("entry"), "sl": cons.get("sl"), "tp1": cons.get("tp1"), "tp2": cons.get("tp2")})
                            st.session_state.alerts.append({"time": PKT(), "msg": "LLM " + dec + " " + ls + " " + mt + " Conf " + str(cf) + "%"})
                            if voice_on:
                                VOICE("LLM says " + dec + " on " + ls.replace("USDT", "") + " confidence " + str(cf) + " percent")

with T2:
    st.markdown("### Scanner")
    mkt3 = st.radio("Market", ["SPOT", "FUTURES"], horizontal=True, key="mkt3")
    mkt_id3 = "SPOT" if mkt3 == "SPOT" else "SWAP"
    cc1, cc2, cc3 = st.columns([1, 1, 2])
    n = cc1.slider("Coins", 20, 150, 40, 10)
    mstr = cc2.slider("Min Str", 0, 100, 30, 5)
    go = cc3.button("Start Scan", type="primary", key="scan")
    if go:
        al = COINS(mkt_id3)
        if not al:
            st.error("No coins")
        else:
            lst = al[:n]
            prog = st.progress(0)
            res = []
            new_al = []
            for i, c in enumerate(lst):
                prog.progress((i + 1) / len(lst))
                r = SCN(c["s"], mkt_id3)
                if r and r["Str"] >= mstr:
                    res.append(r)
                    if r["Sig"] in ["LONG", "SHORT"] and r["Str"] >= 65:
                        new_al.append({"time": PKT(), "msg": r["Sig"] + " " + r["Sym"] + " " + mkt3 + " Str " + str(r["Str"])})
            prog.empty()
            st.session_state.scan_res = res
            st.session_state.alerts = (st.session_state.alerts + new_al)[-30:]
            st.success("Found " + str(len(res)) + " in " + mkt3)
            if voice_on and len(new_al) > 0:
                VOICE("Found " + str(len(new_al)) + " strong signals in " + mkt3)
    if st.session_state.scan_res:
        dr = pd.DataFrame(st.session_state.scan_res).sort_values("Str", ascending=False)
        lg = dr[dr["Sig"] == "LONG"]
        sh = dr[dr["Sig"] == "SHORT"]
        m1, m2, m3 = st.columns(3)
        m1.metric("LONG", len(lg))
        m2.metric("SHORT", len(sh))
        m3.metric("Vol Spikes", len(dr[dr["VR"] > 1.5]))
        st.markdown("#### LONG")
        for _, r in lg.head(15).iterrows():
            st.markdown("<div class='sig'><b>" + r["Sym"] + "</b> <span class='buy'>LONG</span> Str <b>" + str(r["Str"]) + "</b><br><b>Entry:</b> $" + str(r["E"]) + " <b>SL:</b> $" + str(r["SL"]) + " <b>TP1:</b> $" + str(r["TP1"]) + " <b>TP2:</b> $" + str(r["TP2"]) + "</div>", unsafe_allow_html=True)
        st.markdown("#### SHORT")
        for _, r in sh.head(15).iterrows():
            st.markdown("<div class='sig sigS'><b>" + r["Sym"] + "</b> <span class='sell'>SHORT</span> Str <b>" + str(r["Str"]) + "</b><br><b>Entry:</b> $" + str(r["E"]) + " <b>SL:</b> $" + str(r["SL"]) + " <b>TP1:</b> $" + str(r["TP1"]) + " <b>TP2:</b> $" + str(r["TP2"]) + "</div>", unsafe_allow_html=True)

with T3:
    st.markdown("### Live Trades")
    if st.session_state.trades:
        for t in st.session_state.trades[-15:][::-1]:
            if not t.get("entry"):
                continue
            try:
                cur = TX(t["coin"])
                cpx = cur.get("p", t["entry"])
            except:
                cpx = t["entry"]
            if t["side"] == "BUY":
                pnl = (cpx - t["entry"]) / t["entry"] * 100
            elif t["side"] == "SELL":
                pnl = (t["entry"] - cpx) / t["entry"] * 100
            else:
                pnl = 0
            sc = "#22c55e" if pnl > 0 else "#ef4444" if pnl < 0 else "#f59e0b"
            status = "OPEN"
            if t["side"] == "BUY":
                if cpx >= t["tp1"]:
                    status = "TP1 HIT"
                elif cpx <= t["sl"]:
                    status = "SL HIT"
            elif t["side"] == "SELL":
                if cpx <= t["tp1"]:
                    status = "TP1 HIT"
                elif cpx >= t["sl"]:
                    status = "SL HIT"
            st.markdown("<div class='radar'><b>" + t["coin"] + " " + t.get("market", "") + "</b> <span style='color:" + sc + "'>" + t["side"] + "</span> at " + t["time"] + "<br><b>Entry:</b> $" + str(t["entry"]) + " <b>Live:</b> $" + str(round(cpx, 6)) + " <b>SL:</b> $" + str(t["sl"]) + " <b>TP1:</b> $" + str(t["tp1"]) + " <b>TP2:</b> $" + str(t["tp2"]) + "<br><b>PnL:</b> <span style='color:" + sc + ";font-size:18px;font-weight:900'>" + "{:+.2f}%".format(pnl) + "</span> <b>Status:</b> " + status + "</div>", unsafe_allow_html=True)
    else:
        st.info("No trades. Run Auto or LLM.")

with T4:
    st.markdown("### Market Radar")
    mkt4 = st.radio("Market", ["SPOT", "FUTURES"], horizontal=True, key="mkt4")
    mkt_id4 = "SPOT" if mkt4 == "SPOT" else "SWAP"
    al = COINS(mkt_id4)
    opt = [c["s"] for c in al[:200]] if al else ["BTCUSDT"]
    s = st.selectbox("Coin", opt, index=0, key="radar")
    tx = TX(s, mkt_id4)
    oifr = OI_FR(s)
    bk = BOOK(s, mkt_id4)
    if tx:
        p = tx.get("p", 0)
        ch = tx.get("c", 0)
        cc = "#22c55e" if ch > 0 else "#ef4444"
        st.markdown("<div class='card'><div class='big' style='color:white'>$" + "{:,.4f}".format(p) + "</div><div style='color:" + cc + "'>" + "{:+.2f}%".format(ch) + "</div></div>", unsafe_allow_html=True)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("OI", "${:.2f}M".format(oifr["oi"] / 1e6))
        k2.metric("FR", "{:+.4f}%".format(oifr["fr"]))
        k3.metric("24h H", "${:,.4f}".format(tx.get("h24", 0)))
        k4.metric("24h L", "${:,.4f}".format(tx.get("l24", 0)))
        st.markdown("#### Liquidity Zones")
        for pr_, q in bk["asks"][:5]:
            st.markdown("<div class='zone'><div><b style='color:#ef4444'>$" + "{:,.4f}".format(pr_) + "</b> Sell</div><div style='flex:1;margin:0 12px;background:#ef4444;height:8px;border-radius:4px'></div><div>99</div></div>", unsafe_allow_html=True)
        for pr_, q in bk["bids"][:5]:
            st.markdown("<div class='zone'><div><b style='color:#22c55e'>$" + "{:,.4f}".format(pr_) + "</b> Buy</div><div style='flex:1;margin:0 12px;background:#22c55e;height:8px;border-radius:4px'></div><div>99</div></div>", unsafe_allow_html=True)
        st.markdown("#### Order Book")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**BIDS**")
            for pr_, q in bk["bids"][:8]:
                st.markdown("<div style='color:#22c55e;font-size:12px'>$" + "{:,.4f}".format(pr_) + " - " + "{:.3f}".format(q) + "</div>", unsafe_allow_html=True)
        with col2:
            st.markdown("**ASKS**")
            for pr_, q in bk["asks"][:8]:
                st.markdown("<div style='color:#ef4444;font-size:12px'>$" + "{:,.4f}".format(pr_) + " - " + "{:.3f}".format(q) + "</div>", unsafe_allow_html=True)
        f = FG()
        g = GM()
        m2 = MP()
        s1, s2b, s3, s4 = st.columns(4)
        s1.metric("Fear Greed", str(f["v"]) + " " + f["l"])
        s2b.metric("BTC Dom", "{:.2f}%".format(g["btc"]))
        s3.metric("Block", "{:,}".format(m2["h"]))
        s4.metric("Mempool", "{:,}".format(m2["c"]))

with T5:
    st.markdown("### Chart + Signal Progress")
    mkt5 = st.radio("Market", ["SPOT", "FUTURES"], horizontal=True, key="mkt5")
    mkt_id5 = "SPOT" if mkt5 == "SPOT" else "SWAP"
    al = COINS(mkt_id5)
    opt = [c["s"] for c in al[:300]] if al else ["BTCUSDT"]
    cc1, cc2 = st.columns([2, 1])
    s5 = cc1.selectbox("Coin", opt, index=0, key="c5")
    iv5 = cc2.selectbox("TF", ["15m", "1h", "4h", "1d"], index=1, key="t5")
    df5 = KL(s5, iv5, 300, mkt_id5)
    if df5.empty or len(df5) < 30:
        st.error("Not enough data")
    else:
        df5 = IND(df5)
        sp, rs = ZN(df5)
        sg = SG(df5)
        last = df5.iloc[-1]
        last_price = float(last["c"])
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.62, 0.16, 0.22], subplot_titles=("", "Vol", "RSI"))
        fig.add_trace(go.Candlestick(x=df5["t"].tolist(), open=df5["o"].tolist(), high=df5["h"].tolist(), low=df5["l"].tolist(), close=df5["c"].tolist(), name=s5, increasing_line_color="#22c55e", decreasing_line_color="#ef4444"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df5["t"].tolist(), y=df5["e20"].tolist(), line=dict(color="#22d3ee", width=1.5), name="EMA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df5["t"].tolist(), y=df5["e50"].tolist(), line=dict(color="#fbbf24", width=1.5), name="EMA50"), row=1, col=1)
        for p in rs:
            fig.add_hrect(y0=p * 0.997, y1=p * 1.003, fillcolor="#ef4444", opacity=0.18, line_width=0, row=1, col=1)
        for p in sp:
            fig.add_hrect(y0=p * 0.997, y1=p * 1.003, fillcolor="#22c55e", opacity=0.18, line_width=0, row=1, col=1)
        for x in sg:
            cl2 = "#22c55e" if x["ty"] == "BUY" else "#ef4444"
            yp = x["p"] * 0.995 if x["ty"] == "BUY" else x["p"] * 1.005
            fig.add_trace(go.Scatter(x=[x["t"]], y=[yp], mode="markers+text", marker=dict(symbol="triangle-up" if x["ty"] == "BUY" else "triangle-down", size=15, color=cl2), text=[x["ty"] + " " + x["t"].strftime("%m-%d %H:%M")], textposition="bottom center", textfont=dict(color=cl2, size=9), showlegend=False), row=1, col=1)
        vc = ["#22c55e" if c >= o else "#ef4444" for c, o in zip(df5["c"].tolist(), df5["o"].tolist())]
        fig.add_trace(go.Bar(x=df5["t"].tolist(), y=df5["v"].tolist(), marker_color=vc, name="Vol"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df5["t"].tolist(), y=df5["rsi"].tolist(), line=dict(color="#a78bfa", width=1.5), name="RSI"), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", row=3, col=1)
        fig.update_layout(template="plotly_dark", height=800, paper_bgcolor="#0b0f17", plot_bgcolor="#0b0f17", xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.02), title=mkt5 + " " + s5 + " " + iv5)
        fig.update_xaxes(showgrid=True, gridcolor="#1f2937")
        fig.update_yaxes(showgrid=True, gridcolor="#1f2937")
        st.plotly_chart(fig, use_container_width=True)

        if sg:
            st.markdown("### Signal Progress - From Signal Time To Now")
            for s in sg[-10:][::-1]:
                at = float(df5["atr"].iloc[s["i"]]) if not pd.isna(df5["atr"].iloc[s["i"]]) else s["p"] * 0.01
                tr = TRK(df5, s, at)
                sig_time = s["t"].strftime("%Y-%m-%d %I:%M %p")
                hrs = tr["du"]
                sig_price = s["p"]
                if s["ty"] == "BUY":
                    move = (last_price - sig_price) / sig_price * 100
                else:
                    move = (sig_price - last_price) / sig_price * 100
                move_col = "#22c55e" if move > 0 else "#ef4444" if move < 0 else "#f59e0b"
                sl_hit = tr["sl"]
                tp1_hit = tr["tp1"]
                tp2_hit = tr["tp2"]
                sl_time = tr["sl_t"].strftime("%m-%d %H:%M") if tr["sl_t"] is not None else "-"
                tp1_time = tr["tp1_t"].strftime("%m-%d %H:%M") if tr["tp1_t"] is not None else "-"
                tp2_time = tr["tp2_t"].strftime("%m-%d %H:%M") if tr["tp2_t"] is not None else "-"
                status = "TP2 HIT" if tp2_hit else "TP1 HIT" if tp1_hit else "SL HIT" if sl_hit else "RUNNING"
                status_col = "#22c55e" if tp2_hit or tp1_hit else "#ef4444" if sl_hit else "#f59e0b"
                bar_width = min(abs(move) * 5, 100)
                st.markdown("<div class='card' style='border-left:5px solid " + move_col + "'><b>" + s["ty"] + "</b> @ <b>$" + str(round(sig_price, 6)) + "</b> - Signal Time: <b>" + sig_time + "</b><br><b>Current:</b> $" + str(round(last_price, 6)) + " | <b>Move:</b> <span style='color:" + move_col + ";font-weight:900;font-size:16px'>" + "{:+.2f}%".format(move) + "</span> | <b>Duration:</b> " + "{:.1f}h".format(hrs) + "<br><b>Entry:</b> $" + str(round(sig_price, 6)) + " <b>SL:</b> $" + str(round(tr["slp"], 6)) + " <b>TP1:</b> $" + str(round(tr["tp1p"], 6)) + " <b>TP2:</b> $" + str(round(tr["tp2p"], 6)) + "<br><b>SL Hit At:</b> " + sl_time + " | <b>TP1 Hit At:</b> " + tp1_time + " | <b>TP2 Hit At:</b> " + tp2_time + "<br><b>Max Up:</b> " + "{:+.2f}%".format(tr["mu"]) + " | <b>Max Down:</b> " + "{:+.2f}%".format(tr["md"]) + " | <b>Status:</b> <span style='color:" + status_col + ";font-weight:900'>" + status + "</span><div style='height:8px;background:#1f2937;border-radius:4px;margin-top:8px;overflow:hidden'><div style='height:100%;width:" + str(bar_width) + "%;background:" + move_col + "'></div></div></div>", unsafe_allow_html=True)

st.caption("AI Edge Scanner - " + PKT())
