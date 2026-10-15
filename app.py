with T5:
    st.markdown("### Chart - With Signal History + Progress")
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
        last_time = last["t"]
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.62, 0.16, 0.22], subplot_titles=("", "Vol", "RSI"))
        fig.add_trace(go.Candlestick(
            x=df5["t"].tolist(),
            open=df5["o"].tolist(),
            high=df5["h"].tolist(),
            low=df5["l"].tolist(),
            close=df5["c"].tolist(),
            name=s5,
            increasing_line_color="#22c55e",
            decreasing_line_color="#ef4444"
        ), row=1, col=1)
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
                st.markdown(
                    "<div class='card' style='border-left:5px solid " + move_col + "'>" +
                    "<b>" + s["ty"] + "</b> @ <b>$" + str(round(sig_price, 6)) + "</b> - Signal Time: <b>" + sig_time + "</b><br>" +
                    "<b>Current:</b> $" + str(round(last_price, 6)) + " | <b>Move:</b> <span style='color:" + move_col + ";font-weight:900;font-size:16px'>" + "{:+.2f}%".format(move) + "</span> | <b>Duration:</b> " + "{:.1f}h".format(hrs) + "<br>" +
                    "<b>Entry:</b> $" + str(round(sig_price, 6)) + " <b>SL:</b> $" + str(round(tr["slp"], 6)) + " <b>TP1:</b> $" + str(round(tr["tp1p"], 6)) + " <b>TP2:</b> $" + str(round(tr["tp2p"], 6)) + "<br>" +
                    "<b>SL Hit At:</b> " + sl_time + " | <b>TP1 Hit At:</b> " + tp1_time + " | <b>TP2 Hit At:</b> " + tp2_time + "<br>" +
                    "<b>Max Up:</b> " + "{:+.2f}%".format(tr["mu"]) + " | <b>Max Down:</b> " + "{:+.2f}%".format(tr["md"]) + " | <b>Status:</b> <span style='color:" + status_col + ";font-weight:900'>" + status + "</span>" +
                    "<div style='height:8px;background:#1f2937;border-radius:4px;margin-top:8px;overflow:hidden'><div style='height:100%;width:" + str(bar_width) + "%;background:" + move_col + "'></div></div>" +
                    "</div>",
                    unsafe_allow_html=True
                )

st.caption("AI Edge Scanner - " + PKT())
