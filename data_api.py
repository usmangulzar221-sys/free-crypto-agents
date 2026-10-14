import requests, pandas as pd
from datetime import datetime, timedelta
import streamlit as st

OK = "https://www.okx.com/api/v5"
TFM = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}

def PKT():
    return (datetime.utcnow() + timedelta(hours=5)).strftime("%I:%M:%S %p")

def PKT24():
    return (datetime.utcnow() + timedelta(hours=5)).strftime("%H:%M:%S")

def IID(s, m):
    if m == "SPOT":
        return s[:-4] + "-USDT" if s.endswith("USDT") else s
    return s[:-4] + "-USDT-SWAP" if s.endswith("USDT") else s

@st.cache_data(ttl=3600)
def COINS(market="SPOT"):
    try:
        it = "SPOT" if market == "SPOT" else "SWAP"
        r = requests.get(OK + "/market/tickers", params={"instType": it}, timeout=12).json()
        if r.get("code") != "0":
            return []
        o = []
        for d in r["data"]:
            i = d.get("instId", "")
            if market == "SPOT":
                if not i.endswith("-USDT") or "USDC" in i or "DAI" in i:
                    continue
                s = i.replace("-", "")
            else:
                if not i.endswith("-USDT-SWAP"):
                    continue
                s = i.replace("-USDT-SWAP", "USDT")
            try:
                v = float(d.get("volCcy24h", 0))
            except:
                v = 0
            if v < 50000:
                continue
            o.append({"s": s, "iid": i, "v": v})
        o.sort(key=lambda x: x["v"], reverse=True)
        return o[:500]
    except:
        return []

@st.cache_data(ttl=20)
def KL(s, i="1h", n=300, m="SPOT"):
    try:
        r = requests.get(OK + "/market/candles", params={"instId": IID(s, m), "bar": TFM.get(i, "1H"), "limit": min(n, 300)}, timeout=10).json()
        if r.get("code") != "0" or not r.get("data"):
            return pd.DataFrame()
        d = r["data"]
        df = pd.DataFrame(d, columns=["t", "o", "h", "l", "c", "v", "vq", "vc", "x"])
        for c in ["o", "h", "l", "c", "v"]:
            df[c] = df[c].astype(float)
        df["t"] = pd.to_datetime(df["t"].astype(float), unit="ms")
        return df[["t", "o", "h", "l", "c", "v"]].sort_values("t").reset_index(drop=True)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=10)
def TX(s, m="SPOT"):
    try:
        r = requests.get(OK + "/market/ticker", params={"instId": IID(s, m)}, timeout=8).json()
        if r.get("code") != "0" or not r.get("data"):
            return {}
        d = r["data"][0]
        la = float(d["last"])
        op = float(d["open24h"])
        cg = (la - op) / op * 100 if op else 0
        try:
            vl = float(d.get("volCcy24h", 0))
        except:
            vl = 0
        return {"p": la, "c": cg, "v": vl, "h24": float(d.get("high24h", la)), "l24": float(d.get("low24h", la))}
    except:
        return {}

@st.cache_data(ttl=60)
def OI_FR(s):
    try:
        iid = IID(s, "FUTURES")
        r1 = requests.get(OK + "/public/open-interest", params={"instType": "SWAP", "instId": iid}, timeout=6).json()
        r2 = requests.get(OK + "/public/funding-rate", params={"instId": iid}, timeout=6).json()
        oi = 0
        fr = 0
        if r1.get("code") == "0" and r1.get("data"):
            try:
                oi = float(r1["data"][0].get("oiCcy", 0))
            except:
                oi = 0
        if r2.get("code") == "0" and r2.get("data"):
            try:
                fr = float(r2["data"][0].get("fundingRate", 0)) * 100
            except:
                fr = 0
        return {"oi": oi, "fr": fr}
    except:
        return {"oi": 0, "fr": 0}

@st.cache_data(ttl=15)
def BOOK(s, m="SPOT"):
    try:
        r = requests.get(OK + "/market/books", params={"instId": IID(s, m), "sz": 20}, timeout=8).json()
        if r.get("code") != "0" or not r.get("data"):
            return {"bids": [], "asks": []}
        d = r["data"][0]
        return {"bids": [(float(x[0]), float(x[1])) for x in d.get("bids", [])], "asks": [(float(x[0]), float(x[1])) for x in d.get("asks", [])]}
    except:
        return {"bids": [], "asks": []}

@st.cache_data(ttl=300)
def FG():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6).json()
        d = r["data"][0]
        return {"v": int(d["value"]), "l": d["value_classification"]}
    except:
        return {"v": 50, "l": "Neutral"}

@st.cache_data(ttl=300)
def GM():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=8).json()
        d = r["data"]
        return {"btc": round(d["market_cap_percentage"].get("btc", 0), 2), "eth": round(d["market_cap_percentage"].get("eth", 0), 2), "mc": d["total_market_cap"]["usd"], "tv": d["total_volume"]["usd"], "mcc": round(d.get("market_cap_change_percentage_24h_usd", 0), 2)}
    except:
        return {"btc": 0, "eth": 0, "mc": 0, "tv": 0, "mcc": 0}

@st.cache_data(ttl=60)
def MP():
    try:
        r1 = requests.get("https://mempool.space/api/mempool", timeout=6).json()
        r2 = requests.get("https://mempool.space/api/v1/fees/recommended", timeout=6).json()
        r3 = requests.get("https://mempool.space/api/blocks/tip/height", timeout=6).text
        return {"h": int(r3), "c": r1.get("count", 0), "ff": r2.get("fastestFee", 0), "f30": r2.get("halfHourFee", 0), "f1h": r2.get("hourFee", 0)}
    except:
        return {"h": 0, "c": 0, "ff": 0, "f30": 0, "f1h": 0}
