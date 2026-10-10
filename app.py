import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
import numpy as np
import random
from datetime import datetime, timedelta

st.set_page_config(page_title="Open Signals - Edge", layout="wide", page_icon="⚡")

# ----- SAME THEME CSS LIKE SCREENSHOT -----
st.markdown("""
<style>
body,.stApp { background-color:#0e0e0e!important; color:white; }
.card { background:#1e1e1e; border-radius:16px; padding:16px; margin-bottom:12px; border:1px solid #2a2a2a; }
.yellow-btn { background:#facc15; color:black; border-radius:10px; padding:12px; text-align:center; font-weight:bold; width:100%; border:none; cursor:pointer;}
.tab-active { border-bottom:3px solid #facc15; color:#facc15; font-weight:bold; }
.badge-green { background:#0f2d1e; color:#22c55e; padding:4px 10px; border-radius:8px; font-size:12px; }
.badge-red { background:#3a1111; color:#ef4444; padding:4px 8px; border-radius:6px; font-size:12px; font-weight:bold; }
.metric { color:#aaa; font-size:13px; }
.win { color:#facc15; font-weight:bold; }
.radar-box { background: radial-gradient(circle, #2a2a1a 0%, #111 70%); border-radius:20px; padding:20px; border:1px solid #333; }
</style>
""", unsafe_allow_html=True)

# ----- Header like app -----
col1,col2 = st.columns([3,1])
with col1: st.markdown("<h2 style='margin:0'>Open Signals</h2>", unsafe_allow_html=True)
with col2: st.markdown("<div style='border:1px solid #facc15; border-radius:20px; padding:6px 18px; text-align:center; font-weight:bold; color:white;'>Results</div>", unsafe_allow_html=True)

# ----- Tabs -----
tab = st.radio("", ["Forex","Crypto","Stocks"], horizontal=True, label_visibility="collapsed")
st.markdown("---")

# ----- Stats like screenshot -----
if tab=="Forex":
    t7,t14,t30 = 23,45,95
    w7,w14,w30 = 95.65,97.78,98.95
    symbols = ["XAUUSD","EURJPY","XAUUSD"]
elif tab=="Crypto":
    t7,t14,t30 = 32,54,88
    w7,w14,w30 = 100.0,100.0,98.86
    symbols = ["ATOMUSDT","AMPUSDT","SOLUSDT"]
else:
    t7,t14,t30 = 18,38,72
    w7,w14,w30 = 94.2,96.1,97.3
    symbols = ["AAPL","TSLA","NVDA"]

c1,c2 = st.columns(2)
with c1:
    st.markdown(f"<div class='metric'>Trades last 7 days: <b style='color:white'>{t7}</b></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric'>Trades last 14 days: <b style='color:white'>{t14}</b></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric'>Trades last 30 days: <b style='color:white'>{t30}</b></div>", unsafe_allow_html=True)
with c2:
    st.markdown(f"<div class='metric'>Win rate: <span class='win'>{w7}%</span></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric'>Win rate: <span class='win'>{w14}%</span></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric'>Win rate: <span class='win'>{w30}%</span></div>", unsafe_allow_html=True)

st.write("")

# ----- Live Price for Scanner ( $10k logic ) -----
@st.cache_data(ttl=40)
def get_live():
    try:
        url="https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
        d=requests.get(url, timeout=10).json()
        return pd.DataFrame(d)
    except: return pd.DataFrame()

live_df = get_live()

def make_signal(sym):
    entry = round(random.uniform(100, 4000),2)
    is_short = random.choice([True,False])
    sl = round(entry*1.05 if is_short else entry*0.95,2)
    targets = [round(entry*0.98,2), round(entry*0.95,2), round(entry*0.92,2)] if is_short else [round(entry*1.02,2), round(entry*1.05,2), round(entry*1.08,2)]
    vol = random.choice([5.2,12.5,1.2,8.9])
    tx = f"${random.randint(10,150)}k"
    return entry, sl, targets, is_short, vol, tx

# ----- Signal Cards (Premium locked + one open) -----
for i, sym in enumerate(symbols[:2]):
    st.markdown(f"""
    <div class="card">
        <div style="color:#888; font-size:13px">Oct-0{8+i}, {7-i}:25 PM</div>
        <div style="font-size:20px; font-weight:bold; margin:8px 0">{sym}</div>
        <div class="yellow-btn">Tap to join Premium</div>
    </div>
    """, unsafe_allow_html=True)

# Opened card with Target 1 hit
entry, sl, targets, is_short, vol, tx = make_signal(symbols[2] if len(symbols)>2 else "XAUUSD")
st.markdown(f"""
<div class="card">
    <div style="display:flex; justify-content:space-between">
        <span style="color:#888; font-size:13px">Opened: Oct-08, 11:49 AM <span style="background:#222; padding:2px 6px; border-radius:6px; margin-left:6px">~1d</span></span>
        <span class="badge-green">Target 1 ✓</span>
    </div>
    <div style="margin-top:10px">
        <span class="{'badge-red' if is_short else 'badge-green'}">{'SHORT' if is_short else 'LONG'}</span>
        <span style="font-weight:bold; font-size:18px; margin-left:8px">{symbols[2] if len(symbols)>2 else 'XAUUSD'}</span>
    </div>
    <div style="margin-top:12px; display:flex; justify-content:space-between"><span>Entry price</span><b>{entry}</b></div>
    <div style="display:flex; justify-content:space-between"><span>Stop Loss 209 pips</span><b>{sl}</b></div>
    <div style="display:flex; justify-content:space-between"><span>Volume</span><b>${vol}M High Vol ✓ Tx {tx} ✓</b></div>
    <div style="margin-top:10px; background:#222; padding:10px; border-radius:10px; display:flex; justify-content:space-between">
        <span>Targets</span><span>▼</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ----- $10k Volume Scanner Table -----
st.markdown("### 🐳 $10k+ Whale Scanner Radar")
if not live_df.empty:
    live_df['tx_size'] = live_df['total_volume']/1000
    filtered = live_df[live_df['total_volume']>=10000].head(25)
    filtered = filtered[['symbol','current_price','total_volume','price_change_percentage_24h']]
    filtered.columns = ['Coin','Price','Vol 24h $','24h% Pump/Dump']
    filtered['Signal'] = filtered['24h% Pump/Dump'].apply(lambda x: "🚀 Volume UP" if x>3 else "🔻 Volume DOWN" if x<-3 else "⚠️ Whale $10k+")
    filtered['Avg Tx'] = filtered['Vol 24h $'].apply(lambda x: f"${x/1000:.0f}k")
    st.dataframe(filtered, use_container_width=True, height=350)

# ----- Ai Edge Radar (8 Facets) -----
st.markdown("## Ai Edge")
st.markdown("<p style='color:#facc15; letter-spacing:3px; font-size:12px'>— EIGHT FACETS · ONE VERDICT</p>", unsafe_allow_html=True)
st.markdown("<h3>Every chart, studied from<br>eight angles.</h3>", unsafe_allow_html=True)

# Radar Chart for Edge
import plotly.graph_objects as go
categories = ['TREND','MOMENTUM','REGIME','RISK','VOLUME','SENTIMENT','FLOW','MACRO']
values = [random.randint(60,95) for _ in categories]

fig = go.Figure()
fig.add_trace(go.Scatterpolar(r=values+ [values[0]], theta=categories+ [categories[0]], fill='toself', fillcolor='rgba(250,204,21,0.2)', line=dict(color='#facc15')))
fig.update_layout(polar=dict(radialaxis=dict(visible=False, range=[0,100]), angularaxis=dict(color="white")), showlegend=False, paper_bgcolor="#1a1a1a", plot_bgcolor="#1a1a1a", height=380, margin=dict(l=20,r=20,t=20,b=20))
st.plotly_chart(fig, use_container_width=True)

st.markdown("""
<div class="card">
● Trend, momentum, regime, risk, volume, sentiment, flow and macro are each weighed independently — no single-indicator bias.
</div>
""", unsafe_allow_html=True)

st.markdown("<div class='yellow-btn' style='font-size:16px'>Unlock Ai Edge →</div>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#666; font-size:11px; margin-top:6px'>For analysis only · not financial advice</p>", unsafe_allow_html=True)

# Bottom Nav fake
st.markdown("---")
st.markdown("<div style='text-align:center; color:#888'>Home | Markets | <span style='color:#facc15'>Signals</span> | Edge | Learn | Profile</div>", unsafe_allow_html=True)
