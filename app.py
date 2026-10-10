import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime

st.set_page_config(page_title="Mega Scanner - All Features", layout="wide", page_icon="⚡")
st.markdown("""
<style>
.stApp{background:#080808!important}
.card{background:#1a1a1a; border:1px solid #2a2a2a; border-radius:16px; padding:14px; color:white; margin-bottom:12px}
.yellow-btn{background:#facc15; color:black; border-radius:10px; padding:10px; font-weight:900; text-align:center}
.badge-g{background:#0f2d1e; color:#22c55e; padding:4px 10px; border-radius:8px; font-size:11px; font-weight:bold}
.badge-r{background:#3a1111; color:#ef4444; padding:4px 8px; border-radius:6px; font-size:11px; font-weight:bold}
.metric{color:#999; font-size:12px}
.win{color:#facc15; font-weight:bold}
</style>
""", unsafe_allow_html=True)

# SUPER TREND (10,3)
def supertrend(df, p=10, m=3):
    hl2=(df['High']+df['Low'])/2
    atr=(df['High']-df['Low']).rolling(p).mean()
    up=hl2+m*atr
    dn=hl2-m*atr
    trend=[1]*len(df); stl=[0]*len(df)
    for i in range(1,len(df)):
        if df['Close'].iloc[i]>up.iloc[i-1]: trend[i]=1
        elif df['Close'].iloc[i]<dn.iloc[i-1]: trend[i]=-1
        else: trend[i]=trend[i-1]
        stl[i]=dn.iloc[i] if trend[i]==1 else up.iloc[i]
    df['ST']=stl; df['ST_DIR']=trend; return df

@st.cache_data(ttl=60)
def get_data(tic, per="30d", inter="4h"):
    df=yf.download(tic, period=per, interval=inter, progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns=df.columns.get_level_values(0)
    if df.empty: return df
    df=supertrend(df)
    delta=df['Close'].diff()
    gain=delta.clip(lower=0).rolling(14).mean()
    loss=-delta.clip(upper=0).rolling(14).mean()
    df['RSI']=100-(100/(1+gain/(loss.replace(0,0.001))))
    df['VolAvg']=df['Volume'].rolling(20).mean()
    return df

@st.cache_data(ttl=60)
def get_coins():
    try:
        url="https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1&price_change_percentage=24h"
        return pd.DataFrame(requests.get(url, timeout=15).json())
    except: return pd.DataFrame()

def eight_factors(df):
    if df.empty: return [50]*8, "WAIT"
    last=df.iloc[-1]
    trend=85 if last['ST_DIR']==1 else 25
    mom=int(np.clip(last['RSI'],0,100)) if not np.isnan(last['RSI']) else 50
    ma50=df['Close'].rolling(50).mean().iloc[-1] if len(df)>50 else df['Close'].mean()
    regime=80 if last['Close']>ma50 else 35
    atr=(df['High']-df['Low']).rolling(10).mean().iloc[-1]
    risk=int(np.clip(100-(atr/last['Close']*500),0,100))
    vol=90 if last['Volume']>last['VolAvg']*1.5 else 60 if last['Volume']>last['VolAvg'] else 30
    chg=df['Close'].pct_change(5).iloc[-1]*100
    sentiment=int(np.clip(50+chg*5,0,100))
    flow=75 if last['Volume']>df['Volume'].mean() else 45
    macro=70 if df['Close'].iloc[-5:].mean()<last['Close'] else 40
    verdict="LONG" if np.mean([trend,mom,regime,sentiment])>60 else "SHORT"
    return [trend,mom,regime,risk,vol,sentiment,int(flow),macro], verdict

# HEADER - SAME AS YOUR SCREENSHOT
c1,c2=st.columns([3,1])
with c1: st.markdown("<h2 style='color:white; margin:0'>Open Signals - ALL FEATURES</h2><p style='color:#888; font-size:12px'>Yesterday 9:13 PM - Tradingpapa.com crypto - Live</p>", unsafe_allow_html=True)
with c2: st.markdown("<div style='border:1.5px solid #facc15; border-radius:20px; padding:6px 18px; text-align:center; font-weight:bold; color:white;'>Results - No Premium</div>", unsafe_allow_html=True)

tabs=st.tabs(["📈 BTC Detail Chart (Support/Resist + ST + RSI + Vol)", "🐳 $10k Whale Scanner Radar", "⚡ All Signals - 8 Factors Open", "📊 Ai Edge Radar"])

# TAB 1 - DETAILED CHART LIKE SCREENSHOT
with tabs[0]:
    df=get_data("BTC-USD")
    coins_df=get_coins()
    if not df.empty:
        last=float(df['Close'].iloc[-1])
        factors, verdict=eight_factors(df)
        fig=make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.6,0.15,0.25])
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="BTCUSD 4h Coinbase"), row=1,col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['ST'], line=dict(color="#facc15", width=2.5), name="SuperTrend 10,3"), row=1,col=1)
        fig.add_hrect(y0=87000,y1=876
