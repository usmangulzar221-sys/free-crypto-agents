import pandas as pd, numpy as np

def IND(df):
    df = df.copy()
    df["e20"] = df["c"].ewm(span=20, adjust=False).mean()
    df["e50"] = df["c"].ewm(span=50, adjust=False).mean()
    df["e200"] = df["c"].ewm(span=200, adjust=False).mean()
    d = df["c"].diff()
    g = d.clip(lower=0).rolling(14).mean()
    l = (-d.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - 100 / (1 + g / l.replace(0, np.nan))
    tr = pd.concat([df["h"] - df["l"], (df["h"] - df["c"].shift()).abs(), (df["l"] - df["c"].shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["va"] = df["v"].rolling(20).mean()
    df["vr"] = df["v"] / df["va"]
    e1 = df["c"].ewm(span=12, adjust=False).mean()
    e2 = df["c"].ewm(span=26, adjust=False).mean()
    df["macd"] = e1 - e2
    df["msig"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["mhist"] = df["macd"] - df["msig"]
    df["bbm"] = df["c"].rolling(20).mean()
    sd = df["c"].rolling(20).std()
    df["bbu"] = df["bbm"] + 2 * sd
    df["bbl"] = df["bbm"] - 2 * sd
    rm = df["rsi"].rolling(14).min()
    rx = df["rsi"].rolling(14).max()
    df["sk"] = ((df["rsi"] - rm) / (rx - rm).replace(0, np.nan) * 100).rolling(3).mean()
    pdm = df["h"].diff().clip(lower=0)
    mdm = (-df["l"].diff()).clip(lower=0)
    at14 = tr.rolling(14).mean()
    df["pdi"] = 100 * (pdm.rolling(14).mean() / at14.replace(0, np.nan))
    df["mdi"] = 100 * (mdm.rolling(14).mean() / at14.replace(0, np.nan))
    dx = 100 * (df["pdi"] - df["mdi"]).abs() / (df["pdi"] + df["mdi"]).replace(0, np.nan)
    df["adx"] = dx.rolling(14).mean()
    tp = (df["h"] + df["l"] + df["c"]) / 3
    df["vwap"] = (tp * df["v"]).rolling(20).sum() / df["v"].rolling(20).sum().replace(0, np.nan)
    hh = df["h"].rolling(14).max()
    ll = df["l"].rolling(14).min()
    df["wr"] = -100 * (hh - df["c"]) / (hh - ll).replace(0, np.nan)
    up = df["c"].diff().clip(lower=0) * df["v"]
    dn = (-df["c"].diff()).clip(lower=0) * df["v"]
    df["cvd"] = (up - dn).cumsum()
    return df

def ZN(df, lb=5):
    H = df["h"].values
    L = df["l"].values
    rs = []
    sp = []
    for i in range(lb, len(df) - lb):
        if H[i] == max(H[i - lb:i + lb + 1]):
            rs.append(H[i])
        if L[i] == min(L[i - lb:i + lb + 1]):
            sp.append(L[i])
    return sp[-3:], rs[-3:]

def SG(df):
    out = []
    for i in range(1, len(df)):
        pf = df["e20"].iloc[i - 1]
        ps = df["e50"].iloc[i - 1]
        cf = df["e20"].iloc[i]
        cs = df["e50"].iloc[i]
        r = df["rsi"].iloc[i]
        if pd.isna(pf) or pd.isna(r):
            continue
        if pf <= ps and cf > cs and r < 70:
            out.append({"i": i, "t": df["t"].iloc[i], "p": float(df["c"].iloc[i]), "ty": "BUY", "r": float(r)})
        elif pf >= ps and cf < cs and r > 30:
            out.append({"i": i, "t": df["t"].iloc[i], "p": float(df["c"].iloc[i]), "ty": "SELL", "r": float(r)})
    return out

def TRK(df, s, atr):
    i = s["i"]
    e = s["p"]
    f = df.iloc[i + 1:]
    r = {"mu": 0, "md": 0, "du": 0, "tp1": False, "tp2": False, "sl": False, "fh": None, "cur": e, "slp": 0, "tp1p": 0, "tp2p": 0, "sl_t": None, "tp1_t": None, "tp2_t": None, "first_t": None}
    if f.empty:
        return r
    tp1p = e + 1.5 * atr if s["ty"] == "BUY" else e - 1.5 * atr
    tp2p = e + 3 * atr if s["ty"] == "BUY" else e - 3 * atr
    slp = e - 2 * atr if s["ty"] == "BUY" else e + 2 * atr
    t1 = t2 = sh = False
    fh = None
    sl_t = tp1_t = tp2_t = first_t = None
    for _, row in f.iterrows():
        if s["ty"] == "BUY":
            if row["h"] >= tp1p and not t1:
                t1 = True
                tp1_t = row["t"]
                if fh is None:
                    fh = "TP1"
                    first_t = row["t"]
            if row["h"] >= tp2p and not t2:
                t2 = True
                tp2_t = row["t"]
            if row["l"] <= slp and not sh:
                sh = True
                sl_t = row["t"]
                if fh is None:
                    fh = "SL"
                    first_t = row["t"]
        else:
            if row["l"] <= tp1p and not t1:
                t1 = True
                tp1_t = row["t"]
                if fh is None:
                    fh = "TP1"
                    first_t = row["t"]
            if row["l"] <= tp2p and not t2:
                t2 = True
                tp2_t = row["t"]
            if row["h"] >= slp and not sh:
                sh = True
                sl_t = row["t"]
                if fh is None:
                    fh = "SL"
                    first_t = row["t"]
    mu = (float(f["h"].max()) - e) / e * 100
    md = (float(f["l"].min()) - e) / e * 100
    du = (df["t"].iloc[-1] - df["t"].iloc[i]).total_seconds() / 3600
    return {"mu": mu, "md": md, "du": du, "tp1": t1, "tp2": t2, "sl": sh, "fh": fh, "cur": float(df["c"].iloc[-1]), "slp": slp, "tp1p": tp1p, "tp2p": tp2p, "sl_t": sl_t, "tp1_t": tp1_t, "tp2_t": tp2_t, "first_t": first_t}

def SCN(s, m="SPOT"):
    from data_api import KL, TX
    try:
        df = KL(s, "1h", 200, m)
        if df.empty or len(df) < 100:
            return None
        df = IND(df)
        la = df.iloc[-1]
        p = float(la["c"])
        r = float(la["rsi"]) if not pd.isna(la["rsi"]) else 50
        v = float(la["vr"]) if not pd.isna(la["vr"]) else 0
        a = float(la["atr"]) if not pd.isna(la["atr"]) else p * 0.01
        e20 = float(la["e20"])
        e50 = float(la["e50"])
        tr = "BULL" if e20 > e50 else "BEAR"
        t = TX(s, m)
        cg = t.get("c", 0) if t else 0
        vl = t.get("v", 0) if t else 0
        if tr == "BULL" and 40 < r < 65:
            sg = "LONG"
        elif tr == "BEAR" and 35 < r < 60:
            sg = "SHORT"
        else:
            sg = "WAIT"
        if sg == "LONG":
            e = p
            sl = p - 2 * a
            tp1 = p + 1.5 * a
            tp2 = p + 3 * a
        elif sg == "SHORT":
            e = p
            sl = p + 2 * a
            tp1 = p - 1.5 * a
            tp2 = p - 3 * a
        else:
            e = sl = tp1 = tp2 = p
        st2 = 0
        if tr == "BULL" and sg == "LONG":
            st2 += 30
        if tr == "BEAR" and sg == "SHORT":
            st2 += 30
        if 45 < r < 60:
            st2 += 15
        if v > 1.5:
            st2 += 20
        elif v > 1.2:
            st2 += 10
        st2 += min(int(abs(cg)), 20)
        st2 = min(st2, 100)
        return {"Sym": s, "Px": round(p, 6), "Cg": round(cg, 2), "Tr": tr, "RSI": round(r, 1), "VR": round(v, 2), "Sig": sg, "Str": st2, "E": round(e, 6), "SL": round(sl, 6), "TP1": round(tp1, 6), "TP2": round(tp2, 6)}
    except:
        return None
