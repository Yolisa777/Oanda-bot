import os
import requests
import time
import logging
from datetime import datetime, timezone, timedelta

OANDA_API_KEY = os.environ.get(“OANDA_API_KEY”, “”)
OANDA_ACCOUNT_ID = os.environ.get(“OANDA_ACCOUNT_ID”, “”)
BASE_URL = “https://api-fxtrade.oanda.com”
HEADERS = {“Authorization”: “Bearer “ + OANDA_API_KEY, “Content-Type”: “application/json”}

INSTRUMENTS = [
{“name”: “XAU_USD”, “label”: “Gold”,    “units”: 1,   “digits”: 2},
{“name”: “GBP_USD”, “label”: “GBPUSD”,  “units”: 100, “digits”: 5},
{“name”: “EUR_USD”, “label”: “EURUSD”,  “units”: 100, “digits”: 5},
{“name”: “AUD_USD”, “label”: “AUDUSD”,  “units”: 100, “digits”: 5},
{“name”: “USD_JPY”, “label”: “USDJPY”,  “units”: 100, “digits”: 3},
{“name”: “GBP_JPY”, “label”: “GBPJPY”,  “units”: 100, “digits”: 3},
{“name”: “BCO_USD”, “label”: “Oil”,     “units”: 5,   “digits”: 2},
{“name”: “BTC_USD”, “label”: “BTCUSD”,  “units”: 1,   “digits”: 2},
]

NO_SESSION = [“XAU_USD”, “BTC_USD”, “BCO_USD”]
RISK_PCT = 2.0
SL_PCT = 0.010
TP_PCT = 0.040
MIN_RR = 3.0
MAX_DAY_LOSS = 6.0
MAX_WEEK_LOSS = 12.0
MAX_DD = 20.0
MAX_OPEN = 3
MAX_TRADES = 10
MAX_LOSSES = 3
MIN_BAL = 20.0
TRAIL = True
TRAIL_PCT = 0.010
BE_TRIGGER = 0.015
LON_O = 7
LON_C = 16
NY_O = 13
NY_C = 21
NEWS_MIN = 30
EMA_F = 8
EMA_S = 21
EMA_T = 200
RSI_P = 14
RSI_BUY = 62.0
RSI_SELL = 38.0
MACD_F = 12
MACD_S = 26
MACD_SIG = 9
STOCH_K = 14
STOCH_B = 45
STOCH_S = 55
TF_E = “M15”
TF_T = “H1”
BARS = 300
SLEEP = 60

logging.basicConfig(level=logging.INFO, format=”%(asctime)s %(message)s”, handlers=[logging.StreamHandler()])
log = logging.getLogger(**name**)

def ema(prices, period):
if len(prices) < period:
return None
k = 2.0 / (period + 1)
v = prices[0]
for p in prices[1:]:
v = p * k + v * (1 - k)
return v

def rsi(prices, period=14):
if len(prices) < period + 1:
return None
g, lo = [], []
for i in range(1, len(prices)):
d = prices[i] - prices[i - 1]
g.append(max(d, 0))
lo.append(max(-d, 0))
ag = sum(g[-period:]) / period
al = sum(lo[-period:]) / period
if al == 0:
return 100.0
return round(100 - (100 / (1 + ag / al)), 2)

def macd(prices):
if len(prices) < MACD_S + MACD_SIG:
return None
vals = []
for i in range(MACD_S, len(prices)):
fe = ema(prices[:i], MACD_F)
se = ema(prices[:i], MACD_S)
if fe and se:
vals.append(fe - se)
if len(vals) < MACD_SIG:
return None
sig = ema(vals, MACD_SIG)
return vals[-1] - sig if sig else None

def stoch(highs, lows, closes):
if len(closes) < STOCH_K:
return None
hh = max(highs[-STOCH_K:])
ll = min(lows[-STOCH_K:])
if hh == ll:
return 50.0
return round(100 * (closes[-1] - ll) / (hh - ll), 2)

def get_balance():
try:
r = requests.get(BASE_URL + “/v3/accounts/” + OANDA_ACCOUNT_ID + “/summary”, headers=HEADERS, timeout=10)
return float(r.json()[“account”][“balance”])
except Exception as e:
log.error(“Balance: “ + str(e))
return 0.0

def get_candles(instrument, gran, count=BARS):
try:
r = requests.get(
BASE_URL + “/v3/instruments/” + instrument + “/candles”,
headers=HEADERS,
params={“count”: count, “granularity”: gran, “price”: “M”},
timeout=10,
)
data = [c for c in r.json().get(“candles”, []) if c.get(“complete”)]
return {
“c”: [float(x[“mid”][“c”]) for x in data],
“h”: [float(x[“mid”][“h”]) for x in data],
“l”: [float(x[“mid”][“l”]) for x in data],
}
except Exception as e:
log.error(“Candles “ + instrument + “: “ + str(e))
return None

def get_open_trades():
try:
r = requests.get(BASE_URL + “/v3/accounts/” + OANDA_ACCOUNT_ID + “/openTrades”, headers=HEADERS, timeout=10)
return {t[“instrument”]: t for t in r.json().get(“trades”, [])}
except Exception as e:
log.error(“Trades: “ + str(e))
return {}

def get_price(instrument):
try:
r = requests.get(
BASE_URL + “/v3/accounts/” + OANDA_ACCOUNT_ID + “/pricing”,
headers=HEADERS,
params={“instruments”: instrument},
timeout=10,
)
px = r.json().get(“prices”, [])
if px:
return (float(px[0][“asks”][0][“price”]) + float(px[0][“bids”][0][“price”])) / 2
return None
except Exception as e:
log.error(“Price “ + instrument + “: “ + str(e))
return None

def place_order(instrument, units, direction, sl, tp, digits):
signed = units if direction == “BUY” else -units
fmt = “{:.” + str(digits) + “f}”
payload = {
“order”: {
“type”: “MARKET”,
“instrument”: instrument,
“units”: str(signed),
“stopLossOnFill”: {“price”: fmt.format(sl), “timeInForce”: “GTC”},
“takeProfitOnFill”: {“price”: fmt.format(tp), “timeInForce”: “GTC”},
“timeInForce”: “FOK”,
}
}
try:
r = requests.post(BASE_URL + “/v3/accounts/” + OANDA_ACCOUNT_ID + “/orders”, headers=HEADERS, json=payload, timeout=10)
resp = r.json()
if “orderFillTransaction” in resp:
log.info(“FILLED “ + direction + “ “ + instrument + “ @ “ + str(resp[“orderFillTransaction”].get(“price”)))
return True
log.error(“Rejected “ + instrument + “: “ + str(resp))
return False
except Exception as e:
log.error(“Order “ + instrument + “: “ + str(e))
return False

def update_sl(trade_id, new_sl, digits):
try:
fmt = “{:.” + str(digits) + “f}”
requests.put(
BASE_URL + “/v3/accounts/” + OANDA_ACCOUNT_ID + “/trades/” + trade_id + “/orders”,
headers=HEADERS,
json={“stopLoss”: {“price”: fmt.format(new_sl), “timeInForce”: “GTC”}},
timeout=10,
)
except Exception as e:
log.error(“SL: “ + str(e))

def get_pnl():
try:
today = datetime.now(timezone.utc).strftime(”%Y-%m-%dT00:00:00Z”)
r = requests.get(
BASE_URL + “/v3/accounts/” + OANDA_ACCOUNT_ID + “/transactions”,
headers=HEADERS,
params={“from”: today, “type”: “ORDER_FILL”},
timeout=10,
)
return sum(float(t.get(“pl”, 0)) for t in r.json().get(“transactions”, []))
except:
return 0.0

_nc = []
_nt = None

def get_news():
global _nc, _nt
now = datetime.now(timezone.utc)
if _nt and (now - _nt).seconds < 1800:
return _nc
try:
r = requests.get(“https://nfs.faireconomy.media/ff_calendar_thisweek.json”, timeout=10)
_nc = [e for e in r.json() if e.get(“impact”) == “High”]
_nt = now
except:
pass
return _nc

def news_block(instrument):
parts = instrument.split(”_”)
now = datetime.now(timezone.utc)
for event in get_news():
try:
cur = event.get(“country”, “”).upper()
if not any(cur in p for p in parts):
continue
et = datetime.fromisoformat(event[“date”].replace(“Z”, “+00:00”))
diff = (et - now).total_seconds() / 60
if -NEWS_MIN <= diff <= NEWS_MIN:
return True
except:
continue
return False

def in_session(instrument):
if instrument in NO_SESSION:
return True
h = datetime.now(timezone.utc).hour
return (LON_O <= h < LON_C) or (NY_O <= h < NY_C)

def get_signal(instrument):
h1 = get_candles(instrument, TF_T, 250)
if not h1 or len(h1[“c”]) < EMA_T:
return “HOLD”
te = ema(h1[“c”], EMA_T)
up = h1[“c”][-1] > te if te else False
dn = h1[“c”][-1] < te if te else False
m15 = get_candles(instrument, TF_E, BARS)
if not m15 or len(m15[“c”]) < EMA_S + 2:
return “HOLD”
c = m15[“c”]
h = m15[“h”]
l = m15[“l”]
ef0 = ema(c, EMA_F)
es0 = ema(c, EMA_S)
ef1 = ema(c[:-1], EMA_F)
es1 = ema(c[:-1], EMA_S)
rv = rsi(c)
mh = macd(c)
sv = stoch(h, l, c)
if None in (ef0, es0, ef1, es1, rv):
return “HOLD”
bull = (ef1 < es1) and (ef0 > es0)
bear = (ef1 > es1) and (ef0 < es0)
bs = sum([bull, up, rv < RSI_BUY, mh is None or mh > 0, sv is None or sv < STOCH_B])
ss = sum([bear, dn, rv > RSI_SELL, mh is None or mh < 0, sv is None or sv > STOCH_S])
if bs >= 4:
return “BUY”
if ss >= 4:
return “SELL”
return “HOLD”

def manage_trailing(trades):
for instrument, trade in trades.items():
try:
tid = trade[“id”]
op = float(trade[“price”])
csl = float(trade.get(“stopLossOrder”, {}).get(“price”, 0))
units = int(trade[“currentUnits”])
direction = “BUY” if units > 0 else “SELL”
digits = next((i[“digits”] for i in INSTRUMENTS if i[“name”] == instrument), 5)
cp = get_price(instrument)
if not cp:
continue
nsl = csl
if direction == “BUY”:
pp = (cp - op) / op
if pp >= BE_TRIGGER and csl < op:
nsl = op
if TRAIL:
t = cp * (1 - TRAIL_PCT)
if t > nsl:
nsl = t
else:
pp = (op - cp) / op
if pp >= BE_TRIGGER and (csl > op or csl == 0):
nsl = op
if TRAIL:
t = cp * (1 + TRAIL_PCT)
if t < nsl or nsl == 0:
nsl = t
if abs(nsl - csl) > 0.00001:
update_sl(tid, nsl, digits)
except Exception as e:
log.error(“Trail “ + instrument + “: “ + str(e))

def main():
log.info(“OANDA BOT STARTED - LIVE”)
log.info(“ACCOUNT: “ + str(OANDA_ACCOUNT_ID))
sb = get_balance()
wb = sb
dl = 0.0
wl = 0.0
dt = 0
cl = 0
pu = None
em = False
ld = datetime.now(timezone.utc).date()
lw = datetime.now(timezone.utc).isocalendar()[1]
log.info(“Balance: “ + str(round(sb, 2)))

```
while True:
    try:
        now = datetime.now(timezone.utc)
        today = now.date()
        bal = get_balance()

        if today != ld:
            dl = 0.0
            dt = 0
            sb = bal
            ld = today
            log.info("New day! Bal: " + str(round(bal, 2)))

        cw = now.isocalendar()[1]
        if cw != lw:
            wl = 0.0
            wb = bal
            lw = cw

        dd = (sb - bal) / max(sb, 1) * 100
        if dd >= MAX_DD:
            log.critical("EMERGENCY STOP DD: " + str(round(dd, 1)) + "%")
            em = True
            break

        if em:
            time.sleep(60)
            continue

        pnl = get_pnl()
        if pnl < 0:
            dl = wl = abs(pnl)

        if bal < MIN_BAL:
            log.warning("Low bal: " + str(round(bal, 2)))
            time.sleep(SLEEP)
            continue

        if dl >= sb * MAX_DAY_LOSS / 100:
            log.warning("Day loss limit")
            time.sleep(SLEEP)
            continue

        if wl >= wb * MAX_WEEK_LOSS / 100:
            log.warning("Week loss limit")
            time.sleep(SLEEP)
            continue

        if dt >= MAX_TRADES:
            log.warning("Trade limit")
            time.sleep(SLEEP)
            continue

        if pu:
            if now < pu:
                time.sleep(SLEEP)
                continue
            else:
                pu = None
                cl = 0
                log.info("Pause lifted")

        if cl >= MAX_LOSSES:
            pu = now + timedelta(hours=2)
            cl = 0
            log.warning("Pausing 2hrs")
            time.sleep(SLEEP)
            continue

        ot = get_open_trades()
        manage_trailing(ot)

        if len(ot) >= MAX_OPEN:
            time.sleep(SLEEP)
            continue

        for inst in INSTRUMENTS:
            nm = inst["name"]
            lb = inst["label"]
            un = inst["units"]
            dg = inst["digits"]

            if nm in ot:
                continue
            if not in_session(nm):
                continue
            if news_block(nm):
                continue

            sig = get_signal(nm)
            if sig == "HOLD":
                log.info(lb + " HOLD")
                continue

            px = get_price(nm)
            if not px:
                continue

            if sig == "BUY":
                sl = px * (1 - SL_PCT)
                tp = px * (1 + TP_PCT)
            else:
                sl = px * (1 + SL_PCT)
                tp = px * (1 - TP_PCT)

            rr = TP_PCT / SL_PCT
            if rr < MIN_RR:
                continue

            log.info(sig + " " + lb + " @ " + str(round(px, dg)))

            if place_order(nm, un, sig, sl, tp, dg):
                dt += 1
                cl = 0
                ot = get_open_trades()
                if len(ot) >= MAX_OPEN:
                    break

        log.info("Bal:" + str(round(bal, 2)) + " Open:" + str(len(ot)) + " Trades:" + str(dt) + " PnL:" + str(round(pnl, 2)) + " DD:" + str(round(dd, 1)) + "%")

    except KeyboardInterrupt:
        log.info("Stopped")
        break
    except Exception as e:
        log.error("Err: " + str(e))

    time.sleep(SLEEP)
```

if **name** == “**main**”:
main()
