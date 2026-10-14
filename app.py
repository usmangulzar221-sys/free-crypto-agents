import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Scanner", layout="wide")
st.title("Crypto Scanner - Live")

try:
    from groq import Groq
    GK = st.secrets.get("GROQ_API_KEY", "")
    cl = Groq(api_key=GK) if GK else None
    MD = "openai/gpt-oss-120b"
except:
    cl = None
    MD = None

def kl(s, i="1H", n=200):
    try:
        r = requests.get("https://www.okx.com/api/v5/market/candles", params={"instId": s, "bar": i, "limit": n}, timeout=10).json()
        if r.get("code") != "0":
            return pd.DataFrame()
        d = r["data"]
        df = pd.DataFrame(d, columns=["t","o","h","l","c","v","vq","vc","x"])
        for c in ["o","h","l","c","v"]:
            df[c] = df[c].astype(float)
        df["t"] = pd.to_datetime(df["t"].astype(float), unit="ms")
        return df[["t","o","h","l","c","v"]].sort_values("t").reset_index(drop=True)
    except:
        return pd.DataFrame()

def px(s):
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker", params={"instId": s}, timeout=5).json()
        return float(r["data"][0]["last"])
    except:
        return 0

if not cl:
    k = st.sidebar.text_input("Groq key", type="password")
    if k:
        try:
            cl = Groq(api_key=k)
            st.sidebar.success("OK")
        except:
            st.sidebar.error("Bad key")

st.sidebar.markdown("Model: " + str(MD or "-"))

c1, c2, c3 = st.columns(3)
c1.metric("BTC", "${:,.2f}".format(px("BTC-USDT")))
c2.metric("ETH", "${:,.2f}".format(px("ETH-USDT")))
c3.metric("SOL", "${:,.2f}".format(px("SOL-USDT")))

s = st.selectbox("Coin", ["BTC-USDT","ETH-USDT","SOL-USDT","BNB-USDT","XRP-USDT","ADA-USDT"])
df = kl(s, "1H", 300)

if not df.empty:
    df["e20"] = df["c"].ewm(span=20).mean()
    df["e50"] = df["c"].ewm(span=50).mean()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df["t"], open=df["o"], high=df["h"], low=df["l"], close=df["c"], name=s))
    fig.add_trace(go.Scatter(x=df["t"], y=df["e20"], line=dict(color="cyan"), name="EMA20"))
    fig.add_trace(go.Scatter(x=df["t"], y=df["e50"], line=dict(color="yellow"), name="EMA50"))
    fig.update_layout(template="plotly_dark", height=550, xaxis_rangeslider_visible=False, title=s)
    st.plotly_chart(fig, use_container_width=True)
    la = df.iloc[-1]
    st.write("Price: $" + str(la["c"]) + " | EMA20: " + str(round(la["e20"], 4)) + " | EMA50: " + str(round(la["e50"], 4)))

if st.button("Run LLM Analysis"):
    if not cl:
        st.error("Groq key missing")
    else:
        with st.spinner("Analyzing..."):
            try:
                r = cl.chat.completions.create(model=MD, messages=[{"role":"user","content":"Analyze " + s + " on 1H. Give BUY, SELL, or HOLD with reason in 3 lines."}], max_tokens=300)
                st.success("LLM says:")
                st.write(r.choices[0].message.content)
            except Exception as e:
                st.error(str(e))

st.caption("Live OKX Data - " + datetime.now().strftime("%H:%M:%S"))
