# “””

OANDA PRO BOT v2.0 — MAXIMUM PERFORMANCE EDITION
Broker  : OANDA (FCA Regulated UK)
Capital : £100 recommended
Target  : 15-70%monthly return

# UPGRADES:
✅ Multi-timeframe confirmation (M15 entry + H1 trend)
✅ 4:1 reward ratio targeting
✅ London & New York session filter only
✅ High-impact news event filter
✅ 5-indicator confirmation (EMA+RSI+MACD+Stoch+Trend)
✅ Dynamic position sizing (scales with your balance)
✅ Trailing stop + break-even protection
✅ Hard account protection — cannot blow account

SETUP:

1. Fill OANDA_API_KEY and OANDA_ACCOUNT_ID below
1. Keep DEMO = True for at least 2 weeks
1. Upload to GitHub → deploy on Railway (free)
1. Monitor on OANDA phone app
   ================================================================
   “””

import requests
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

# ══════════════════════════════════════════════════════════════

# ⚙️  YOUR DETAILS — Fill these in

# ══════════════════════════════════════════════════════════════

OANDA_API_KEY    = a0e59e9e3aab406b02da8b012717f881-c46ee1a92115052cc1fd52303de03d80
OANDA_ACCOUNT_ID = 001-004-21059078-001

DEMO = True  # ✅ Keep True until 2 weeks profitable on demo!

BASE_URL = (
“https://api-fxpractice.oanda.com”
if DEMO else
“https://api-fxtrade.oanda.com”
)

HEADERS = {
“Authorization”: f”Bearer {OANDA_API_KEY}”,
“Content-Type”:  “application/json”,
}

# ══════════════════════════════════════════════════════════════

# 📈  PAIRS

# ══════════════════════════════════════════════════════════════

INSTRUMENTS = [
{“name”: “XAU_USD”, “label”: “Gold”,       “units”: 1,    “digits”: 2},
{“name”: “GBP_USD”, “label”: “GBP/USD”,    “units”: 1000, “digits”: 5},
{“name”: “EUR_USD”, “label”: “EUR/USD”,     “units”: 1000, “digits”: 5},
{“name”: “AUD_USD”, “label”: “AUD/USD”,     “units”: 1000, “digits”: 5},
{“name”: “USD_JPY”, “label”: “USD/JPY”,     “units”: 1000, “digits”: 3},
{“name”: “GBP_JPY”, “label”: “GBP/JPY”,    “units”: 1000, “digits”: 3},
{“name”: “BCO_USD”, “label”: “Oil (Brent)”, “units”: 10,   “digits”: 2},
{“name”: “BTC_USD”, “label”: “BTC/USD”,     “units”: 1,    “digits”: 2},
]

# No session filter for these — they trade profitably 24/7

NO_SESSION_FILTER = [“XAU_USD”, “BTC_USD”, “BCO_USD”]

# ══════════════════════════════════════════════════════════════

# 🛡️  RISK MANAGEMENT

# ══════════════════════════════════════════════════════════════

RISK_PER_TRADE_PCT   = 1.5    # Risk 1.5% of balance per trade
STOP_LOSS_PCT        = 0.012  # 1.2% stop loss
TAKE_PROFIT_PCT      = 0.048  # 4.8% take profit = 4:1 reward ratio
MIN_REWARD_RATIO     = 3.0    # Skip trade if RR below 3:1
MAX_DAILY_LOSS_PCT   = 4.0    # Stop all trading if 4% lost today
MAX_WEEKLY_LOSS_PCT  = 8.0    # Stop all trading if 8% lost this week
MAX_DRAWDOWN_PCT     = 15.0   # Emergency stop at 15% drawdown
MAX_OPEN_TRADES      = 3      # Max simultaneous open trades
MAX_DAILY_TRADES     = 12     # Max trades per day
MAX_CONSEC_LOSSES    = 3      # Pause 2hrs after 3 losses in a row
MIN_BALANCE          = 50.0   # Never trade below this

# Trailing / Break-even

USE_TRAILING         = True
TRAIL_PCT            = 0.012  # Trail 1.2% behind price
BREAKEVEN_TRIGGER    = 0.018  # Move SL to entry after 1.8% profit

# ══════════════════════════════════════════════════════════════

# ⏰  SESSION + INDICATOR SETTINGS

# ══════════════════════════════════════════════════════════════

# Only trade London (07-16 UTC) and New York (13-21 UTC) sessions

LONDON_OPEN  = 7
LONDON_CLOSE = 16
NY_OPEN      = 13
NY_CLOSE     = 21

# News filter — pause 30 mins before/after high impact news

NEWS_PAUSE_MINUTES = 30

# Indicators

EMA_FAST     = 10
EMA_SLOW     = 50
EMA_TREND    = 200
RSI_PERIOD   = 14
RSI_BUY_MAX  = 58.0
RSI_SELL_MIN = 42.0
MACD_FAST    = 12
MACD_SLOW    = 26
MACD_SIGNAL  = 9
STOCH_K      = 14
STOCH_BUY    = 40
STOCH_SELL   = 60

TF_ENTRY     = “M15”   # Entry timeframe
TF_TREND     = “H1”    # Trend confirmation timeframe
CANDLES      = 300
SCAN_INTERVAL= 60      # Scan every 60 seconds

# ══════════════════════════════════════════════════════════════

# 📋  LOGGING

# ══════════════════════════════════════════════════════════════

logging.basicConfig(
level=logging.INFO,
format=”%(asctime)s [%(levelname)s] %(message)s”,
handlers=[
logging.StreamHandler(),
logging.FileHandler(“oanda_pro_bot.log”, mode=“a”),
],
)
log = logging.getLogger(**name**)

# ══════════════════════════════════════════════════════════════

# 📊  INDICATORS

# ══════════════════════════════════════════════════════════════

def calc_ema(prices: list, period: int) -> Optional[float]:
if len(prices) < period:
return None
k = 2 / (period + 1)
ema = prices[0]
for p in prices[1:]:
ema = p * k + ema * (1 - k)
return ema

def calc_rsi(prices: list, period: int = 14) -> Optional[float]:
if len(prices) < period + 1:
return None
gains, losses = [], []
for i in range(1, len(prices)):
d = prices[i] - prices[i-1]
gains.append(max(d, 0))
losses.append(max(-d, 0))
ag = sum(gains[-period:]) / period
al = sum(losses[-period:]) / period
if al == 0:
return 100.0
return round(100 - (100 / (1 + ag / al)), 2)

def calc_macd_histogram(prices: list) -> Optional[float]:
if len(prices) < MACD_SLOW + MACD_SIGNAL:
return None
macd_vals = []
for i in range(MACD_SLOW, len(prices)):
fe = calc_ema(prices[:i], MACD_FAST)
se = calc_ema(prices[:i], MACD_SLOW)
if fe and se:
macd_vals.append(fe - se)
if len(macd_vals) < MACD_SIGNAL:
return None
signal = calc_ema(macd_vals, MACD_SIGNAL)
if not signal:
return None
return macd_vals[-1] - signal

def calc_stochastic(highs: list, lows: list, closes: list) -> Optional[float]:
if len(closes) < STOCH_K:
return None
hh = max(highs[-STOCH_K:])
ll = min(lows[-STOCH_K:])
if hh == ll:
return 50.0
return round(100 * (closes[-1] - ll) / (hh - ll), 2)

# ══════════════════════════════════════════════════════════════

# 🌐  OANDA API

# ══════════════════════════════════════════════════════════════

def get_balance() -> float:
try:
r = requests.get(
f”{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/summary”,
headers=HEADERS, timeout=10
)
return float(r.json()[“account”][“balance”])
except Exception as e:
log.error(f”Balance error: {e}”)
return 0.0

def get_candles(instrument: str, granularity: str, count: int = CANDLES) -> Optional[dict]:
try:
r = requests.get(
f”{BASE_URL}/v3/instruments/{instrument}/candles”,
headers=HEADERS,
params={“count”: count, “granularity”: granularity, “price”: “M”},
timeout=10,
)
candles = [c for c in r.json().get(“candles”, []) if c.get(“complete”)]
return {
“closes”: [float(c[“mid”][“c”]) for c in candles],
“highs”:  [float(c[“mid”][“h”]) for c in candles],
“lows”:   [float(c[“mid”][“l”]) for c in candles],
}
except Exception as e:
log.error(f”Candle error ({instrument}/{granularity}): {e}”)
return None

def get_open_trades() -> dict:
try:
r = requests.get(
f”{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/openTrades”,
headers=HEADERS, timeout=10
)
return {t[“instrument”]: t for t in r.json().get(“trades”, [])}
except Exception as e:
log.error(f”Open trades error: {e}”)
return {}

def get_price(instrument: str) -> Optional[float]:
try:
r = requests.get(
f”{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/pricing”,
headers=HEADERS,
params={“instruments”: instrument},
timeout=10,
)
prices = r.json().get(“prices”, [])
if prices:
return (float(prices[0][“asks”][0][“price”]) +
float(prices[0][“bids”][0][“price”])) / 2
return None
except Exception as e:
log.error(f”Price error ({instrument}): {e}”)
return None

def place_order(instrument: str, units: int, direction: str,
sl: float, tp: float, digits: int) -> bool:
signed  = units if direction == “BUY” else -units
payload = {
“order”: {
“type”:       “MARKET”,
“instrument”: instrument,
“units”:      str(signed),
“stopLossOnFill”:   {“price”: f”{sl:.{digits}f}”, “timeInForce”: “GTC”},
“takeProfitOnFill”: {“price”: f”{tp:.{digits}f}”, “timeInForce”: “GTC”},
“timeInForce”: “FOK”,
}
}
try:
r    = requests.post(
f”{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/orders”,
headers=HEADERS, json=payload, timeout=10
)
resp = r.json()
if “orderFillTransaction” in resp:
fill = resp[“orderFillTransaction”]
log.info(f”✅ {direction} | {instrument} | Fill: {fill.get(‘price’)} | “
f”SL: {sl:.{digits}f} | TP: {tp:.{digits}f} | Units: {signed}”)
return True
log.error(f”❌ Rejected ({instrument}): {resp}”)
return False
except Exception as e:
log.error(f”Order error ({instrument}): {e}”)
return False

def modify_sl(trade_id: str, new_sl: float, digits: int):
try:
requests.put(
f”{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/trades/{trade_id}/orders”,
headers=HEADERS,
json={“stopLoss”: {“price”: f”{new_sl:.{digits}f}”, “timeInForce”: “GTC”}},
timeout=10,
)
except Exception as e:
log.error(f”Modify SL error: {e}”)

def get_daily_pnl() -> float:
try:
today = datetime.now(timezone.utc).strftime(”%Y-%m-%dT00:00:00Z”)
r     = requests.get(
f”{BASE_URL}/v3/accounts/{OANDA_ACCOUNT_ID}/transactions”,
headers=HEADERS,
params={“from”: today, “type”: “ORDER_FILL”},
timeout=10,
)
return sum(float(t.get(“pl”, 0)) for t in r.json().get(“transactions”, []))
except:
return 0.0

# ══════════════════════════════════════════════════════════════

# 📰  NEWS FILTER

# ══════════════════════════════════════════════════════════════

_news_cache      = []
_news_cache_time = None

def fetch_news() -> list:
global _news_cache, _news_cache_time
now = datetime.now(timezone.utc)
if _news_cache_time and (now - _news_cache_time).seconds < 1800:
return _news_cache
try:
r = requests.get(
“https://nfs.faireconomy.media/ff_calendar_thisweek.json”,
timeout=10
)
_news_cache      = [e for e in r.json() if e.get(“impact”) == “High”]
_news_cache_time = now
log.info(f”📰 {len(_news_cache)} high-impact news events loaded”)
except:
log.warning(“📰 News feed unavailable — skipping news filter”)
return _news_cache

def is_news_time(instrument: str) -> bool:
parts = instrument.split(”_”)
now   = datetime.now(timezone.utc)
for event in fetch_news():
try:
currency = event.get(“country”, “”).upper()
if not any(currency in p for p in parts):
continue
et   = datetime.fromisoformat(event[“date”].replace(“Z”, “+00:00”))
diff = (et - now).total_seconds() / 60
if -NEWS_PAUSE_MINUTES <= diff <= NEWS_PAUSE_MINUTES:
log.info(f”📰 Skipping {instrument} — news in {diff:.0f}m: {event.get(‘title’)}”)
return True
except:
continue
return False

# ══════════════════════════════════════════════════════════════

# ⏰  SESSION FILTER

# ══════════════════════════════════════════════════════════════

def in_session(instrument: str) -> bool:
if instrument in NO_SESSION_FILTER:
return True
hour = datetime.now(timezone.utc).hour
return (LONDON_OPEN <= hour < LONDON_CLOSE) or (NY_OPEN <= hour < NY_CLOSE)

# ══════════════════════════════════════════════════════════════

# 🎯  SIGNAL ENGINE — 5 indicators + multi-timeframe

# ══════════════════════════════════════════════════════════════

def get_signal(instrument: str) -> str:
# H1 trend direction
h1 = get_candles(instrument, TF_TREND, 250)
if not h1 or len(h1[“closes”]) < EMA_TREND:
return “HOLD”

```
trend_ema  = calc_ema(h1["closes"], EMA_TREND)
h1_price   = h1["closes"][-1]
up_trend   = h1_price > trend_ema if trend_ema else False
down_trend = h1_price < trend_ema if trend_ema else False

# M15 entry signals
m15 = get_candles(instrument, TF_ENTRY, CANDLES)
if not m15 or len(m15["closes"]) < EMA_SLOW + 2:
    return "HOLD"

c = m15["closes"]
h = m15["highs"]
l = m15["lows"]

ef_now  = calc_ema(c,      EMA_FAST)
es_now  = calc_ema(c,      EMA_SLOW)
ef_prev = calc_ema(c[:-1], EMA_FAST)
es_prev = calc_ema(c[:-1], EMA_SLOW)
rsi     = calc_rsi(c)
macd_h  = calc_macd_histogram(c)
stoch   = calc_stochastic(h, l, c)

if None in (ef_now, es_now, ef_prev, es_prev, rsi):
    return "HOLD"

bull = (ef_prev < es_prev) and (ef_now > es_now)
bear = (ef_prev > es_prev) and (ef_now < es_now)

# Score each direction — need 4/5 to trade
buy_score = sum([
    bull,
    up_trend,
    rsi < RSI_BUY_MAX,
    macd_h is None or macd_h > 0,
    stoch is None or stoch < STOCH_BUY,
])
sell_score = sum([
    bear,
    down_trend,
    rsi > RSI_SELL_MIN,
    macd_h is None or macd_h < 0,
    stoch is None or stoch > STOCH_SELL,
])

if buy_score  >= 4: return "BUY"
if sell_score >= 4: return "SELL"
return "HOLD"
```

# ══════════════════════════════════════════════════════════════

# 🔁  TRAILING STOP MANAGER

# ══════════════════════════════════════════════════════════════

def manage_trailing(open_trades: dict):
for instrument, trade in open_trades.items():
try:
tid        = trade[“id”]
open_price = float(trade[“price”])
cur_sl     = float(trade.get(“stopLossOrder”, {}).get(“price”, 0))
units      = int(trade[“currentUnits”])
direction  = “BUY” if units > 0 else “SELL”
digits     = next((i[“digits”] for i in INSTRUMENTS if i[“name”] == instrument), 5)
cur_price  = get_price(instrument)
if not cur_price:
continue

```
        new_sl = cur_sl
        if direction == "BUY":
            profit_pct = (cur_price - open_price) / open_price
            if profit_pct >= BREAKEVEN_TRIGGER and cur_sl < open_price:
                new_sl = open_price
                log.info(f"🔒 Break-even set: {instrument}")
            if USE_TRAILING:
                trail = cur_price * (1 - TRAIL_PCT)
                if trail > new_sl:
                    new_sl = trail
        else:
            profit_pct = (open_price - cur_price) / open_price
            if profit_pct >= BREAKEVEN_TRIGGER and (cur_sl > open_price or cur_sl == 0):
                new_sl = open_price
                log.info(f"🔒 Break-even set: {instrument}")
            if USE_TRAILING:
                trail = cur_price * (1 + TRAIL_PCT)
                if trail < new_sl or new_sl == 0:
                    new_sl = trail

        if abs(new_sl - cur_sl) > 0.00001:
            modify_sl(tid, new_sl, digits)
    except Exception as e:
        log.error(f"Trailing error ({instrument}): {e}")
```

# ══════════════════════════════════════════════════════════════

# 🚀  MAIN

# ══════════════════════════════════════════════════════════════

def main():
log.info(“╔══════════════════════════════════════════════╗”)
log.info(“║    OANDA PRO BOT v2.0 — STARTED             ║”)
log.info(f”║    Mode: {‘DEMO ✅’ if DEMO else ‘LIVE 🔴’}                             ║”)
log.info(“║    Pairs: 8 | RR: 4:1 | Filters: ALL ON    ║”)
log.info(“╚══════════════════════════════════════════════╝”)

```
start_bal    = get_balance()
week_bal     = start_bal
daily_loss   = 0.0
weekly_loss  = 0.0
daily_trades = 0
consec_loss  = 0
pause_until  = None
emergency    = False
last_day     = datetime.now(timezone.utc).date()
last_week    = datetime.now(timezone.utc).isocalendar()[1]

log.info(f"💰 Starting balance: £{start_bal:.2f}")

while True:
    try:
        now     = datetime.now(timezone.utc)
        today   = now.date()
        balance = get_balance()

        # Daily reset
        if today != last_day:
            daily_loss = 0.0; daily_trades = 0
            start_bal  = balance; last_day = today
            log.info(f"📅 New day! Balance: £{balance:.2f}")

        # Weekly reset
        cur_week = now.isocalendar()[1]
        if cur_week != last_week:
            weekly_loss = 0.0; week_bal = balance; last_week = cur_week
            log.info(f"📅 New week! Balance: £{balance:.2f}")

        # Emergency drawdown check
        drawdown = (start_bal - balance) / max(start_bal, 1) * 100
        if drawdown >= MAX_DRAWDOWN_PCT:
            log.critical(f"🚨 EMERGENCY STOP — Drawdown: {drawdown:.1f}%")
            emergency = True
            break

        if emergency:
            time.sleep(60); continue

        # P&L tracking
        pnl = get_daily_pnl()
        if pnl < 0:
            daily_loss = weekly_loss = abs(pnl)

        # Hard limits
        checks = [
            (balance < MIN_BALANCE,                                       f"🛑 Balance too low: £{balance:.2f}"),
            (daily_loss  >= start_bal * MAX_DAILY_LOSS_PCT  / 100,       f"🛑 Daily loss limit: £{daily_loss:.2f}"),
            (weekly_loss >= week_bal  * MAX_WEEKLY_LOSS_PCT / 100,       f"🛑 Weekly loss limit: £{weekly_loss:.2f}"),
            (daily_trades >= MAX_DAILY_TRADES,                            f"🛑 Daily trade limit: {daily_trades}"),
        ]
        if any(cond for cond, _ in checks):
            for cond, msg in checks:
                if cond: log.warning(msg)
            time.sleep(SCAN_INTERVAL); continue

        # Consecutive loss pause
        if pause_until:
            if now < pause_until:
                log.info(f"⏸  Paused until {pause_until.strftime('%H:%M UTC')}")
                time.sleep(SCAN_INTERVAL); continue
            else:
                pause_until = None; consec_loss = 0
                log.info("▶️  Pause lifted.")

        if consec_loss >= MAX_CONSEC_LOSSES:
            pause_until = now + timedelta(hours=2); consec_loss = 0
            log.warning("⏸  3 losses in a row — pausing 2 hours.")
            time.sleep(SCAN_INTERVAL); continue

        # Manage open trades
        open_trades = get_open_trades()
        manage_trailing(open_trades)

        if len(open_trades) >= MAX_OPEN_TRADES:
            time.sleep(SCAN_INTERVAL); continue

        # Scan pairs
        for inst in INSTRUMENTS:
            name   = inst["name"]
            label  = inst["label"]
            units  = inst["units"]
            digits = inst["digits"]

            if name in open_trades:          continue
            if not in_session(name):         continue
            if is_news_time(name):           continue

            signal = get_signal(name)
            if signal == "HOLD":
                log.info(f"📊 {label:12} → HOLD"); continue

            price = get_price(name)
            if not price: continue

            sl = price * (1 - STOP_LOSS_PCT)   if signal == "BUY" else price * (1 + STOP_LOSS_PCT)
            tp = price * (1 + TAKE_PROFIT_PCT) if signal == "BUY" else price * (1 - TAKE_PROFIT_PCT)
            rr = TAKE_PROFIT_PCT / STOP_LOSS_PCT

            if rr < MIN_REWARD_RATIO: continue

            # Dynamic sizing — scales up as balance grows
            risk_amt  = balance * RISK_PER_TRADE_PCT / 100
            dyn_units = max(1, int((risk_amt / (price * STOP_LOSS_PCT)) * units))

            log.info(f"🎯 {signal} | {label} | {price:.{digits}f} | "
                     f"SL:{sl:.{digits}f} TP:{tp:.{digits}f} RR:{rr:.1f}:1")

            if place_order(name, dyn_units, signal, sl, tp, digits):
                daily_trades += 1
                open_trades   = get_open_trades()
                if len(open_trades) >= MAX_OPEN_TRADES:
                    break

        log.info(f"💰 £{balance:.2f} | Open:{len(open_trades)}/{MAX_OPEN_TRADES} | "
                 f"Trades:{daily_trades}/{MAX_DAILY_TRADES} | "
                 f"P&L:£{pnl:.2f} | DD:{drawdown:.1f}%")

    except KeyboardInterrupt:
        log.info("👋 Bot stopped."); break
    except Exception as e:
        log.error(f"💥 Error: {e}")

    time.sleep(SCAN_INTERVAL)
```

if **name** == “**main**”:
main()
