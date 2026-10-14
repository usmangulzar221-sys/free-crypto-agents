import os, json
import streamlit as st

try:
    from groq import Groq
    GA = True
except:
    GA = False

def gkey():
    try:
        return st.secrets["GROQ_API_KEY"]
    except:
        return os.environ.get("GROQ_API_KEY", "")

GK = gkey()
cl = None
MD = None
if GA and GK:
    try:
        cl = Groq(api_key=GK)
        MD = "openai/gpt-oss-120b"
    except:
        cl = None

def L(sp, up, mt=400):
    if cl is None:
        return None, "No key"
    try:
        r = cl.chat.completions.create(model=MD, messages=[{"role": "system", "content": sp}, {"role": "user", "content": up}], temperature=0.3, max_tokens=mt)
        return r.choices[0].message.content, None
    except Exception as e:
        return None, str(e)[:150]

def PJ(r):
    if not r:
        return None
    try:
        t = r.strip()
        if "```" in t:
            p = t.split("```")
            if len(p) >= 2:
                t = p[1].replace("json", "").strip()
        return json.loads(t)
    except:
        return {"verdict": r[:25], "score": 0, "reason": r[:70]}

AGS = [
    ("Trend", "You are trend analyst. Reply JSON only with keys verdict (BULLISH or BEARISH or SIDEWAYS), score (-3 to 3), reason (one line)."),
    ("Momentum", "You are momentum analyst. Reply JSON only with keys verdict (STRONG or WEAK or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Volume", "You are volume analyst. Reply JSON only with keys verdict (HIGH or NORMAL or LOW), score (-3 to 3), reason (one line)."),
    ("Risk", "You are risk manager. Reply JSON only with keys verdict (LOW or MEDIUM or HIGH), score (-3 to 3), sl_price (number), reason (one line)."),
    ("SR", "You are S/R analyst. Reply JSON only with keys verdict (NEAR_SUPPORT or NEAR_RESISTANCE or MID), score (-3 to 3), reason (one line)."),
    ("Sentiment", "You analyze sentiment. Reply JSON only with keys verdict (GREEDY or FEARFUL or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Indicator", "You analyze indicators. Reply JSON only with keys verdict (BULLISH or BEARISH or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Volatility", "You analyze volatility. Reply JSON only with keys verdict (HIGH or NORMAL or LOW), score (-3 to 3), reason (one line)."),
    ("Flow", "You analyze money flow. Reply JSON only with keys verdict (INFLOW or OUTFLOW or NEUTRAL), score (-3 to 3), reason (one line)."),
    ("Regime", "You identify regime. Reply JSON only with keys verdict (TRENDING or RANGING or VOLATILE), score (-3 to 3), reason (one line)."),
    ("CVD", "You analyze CVD. Reply JSON only with keys verdict (BUY_DOM or SELL_DOM), score (-3 to 3), reason (one line)."),
]

def R1(snap_text):
    res = []
    for nm, sy in AGS:
        rr, ee = L(sy, snap_text, 150)
        if ee:
            res.append({"n": nm, "v": "ERR", "s": 0, "r": ee[:40], "sl": None})
            continue
        d = PJ(rr)
        if d is None:
            res.append({"n": nm, "v": "?", "s": 0, "r": (rr or "")[:40], "sl": None})
        else:
            res.append({"n": nm, "v": d.get("verdict", "?"), "s": int(d.get("score", 0)), "r": d.get("reason", ""), "sl": d.get("sl_price")})
    return res

def R2(snap_text, r1):
    sm = "Round 1:\n"
    for a in r1:
        sm += a["n"] + ": " + str(a["v"]) + " (" + str(a["s"]) + ")\n"
    sy = "You are senior strategist. Read all opinions. Reply JSON only with keys verdict (BULLISH or BEARISH or NEUTRAL), score (-3 to 3), reason (one line)."
    rr, ee = L(sy, snap_text + "\n\n" + sm, 200)
    if ee:
        return {"n": "Senior", "v": "?", "s": 0, "r": ee[:50]}
    d = PJ(rr)
    if d is None:
        return {"n": "Senior", "v": "?", "s": 0, "r": (rr or "")[:50]}
    return {"n": "Senior", "v": d.get("verdict", "?"), "s": int(d.get("score", 0)), "r": d.get("reason", "")}

def R3(snap_text, r1, r2):
    sm = "Round 1:\n"
    for a in r1:
        sm += a["n"] + ": " + str(a["v"]) + " (" + str(a["s"]) + ")\n"
    sm += "\nSenior: " + str(r2["v"]) + " (" + str(r2["s"]) + ")"
    sy = "You are Chief. Reply JSON only with keys decision (BUY or SELL or HOLD), market_type (SPOT or FUTURES), confidence (0-100), entry, sl, tp1, tp2, tp3, reasoning (2 lines)."
    rr, ee = L(sy, snap_text + "\n\n" + sm + "\n\nFinal decision.", 400)
    if ee:
        return None, ee
    d = PJ(rr)
    if d is None:
        return None, "Parse: " + (rr or "")[:100]
    return d, None
