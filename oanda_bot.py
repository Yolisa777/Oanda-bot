import requests
import time
import logging
from datetime import datetime, timezone, timedelta

OANDA_API_KEY = ‘a0e59e9e3aab406b02da8b012717f881-c46ee1a92115052cc1fd52303de03d80’
OANDA_ACCOUNT_ID = ‘001-004-21059078-001’
DEMO = False

BASE_URL = ‘https://api-fxpractice.oanda.com’ if DEMO else ‘https://api-fxtrade.oanda.com’
HEADERS = {‘Authorization’: ’Bearer ’ + OANDA_API_KEY, ‘Content-Type’: ‘application/json’}

INSTRUMENTS = [
{‘name’: ‘XAU_USD’, ‘label’: ‘Gold’,      ‘units’: 1,   ‘digits’: 2},
{‘name’: ‘GBP_USD’, ‘label’: ‘GBP/USD’,   ‘units’: 100, ‘digits’: 5},
{‘name’: ‘EUR_USD’, ‘label’: ‘EUR/USD’,    ‘units’: 100, ‘digits’: 5},
{‘name’: ‘AUD_USD’, ‘label’: ‘AUD/USD’,    ‘units’: 100, ‘digits’: 5},
{‘name’: ‘USD_JPY’, ‘label’: ‘USD/JPY’,    ‘units’: 100, ‘digits’: 3},
{‘name’: ‘GBP_JPY’, ‘label’: ‘GBP/JPY’,   ‘units’: 100, ‘digits’: 3},
{‘name’: ‘BCO_USD’, ‘label’: ‘Oil’,        ‘units’: 5,   ‘digits’: 2},
{‘name’: ‘BTC_USD’, ‘label’: ‘BTC/USD’,    ‘units’: 1,   ‘digits’: 2},
]

NO_SESSION_FILTER = [‘XAU_USD’, ‘BTC_USD’, ‘BCO_USD’]

RISK_PER_TRADE_PCT  = 2.0
STOP_LOSS_PCT       = 0.010
TAKE_PROFIT_PCT     = 0.040
MIN_REWARD_RATIO    = 3.0
MAX_DAILY_LOSS_PCT  = 6.0
MAX_WEEKLY_LOSS_PCT = 12.0
MAX_DRAWDOWN_PCT    = 20.0
MAX_OPEN_TRADES     = 3
MAX_DAILY_TRADES    = 10
MAX_CONSEC_LOSSES   = 3
MIN_BALANCE         = 20.0
USE_TRAILING        = True
TRAIL_PCT           = 0.010
BREAKEVEN_TRIGGER   = 0.015
LONDON_OPEN         = 7
LONDON_CLOSE        = 16
NY_OPEN             = 13
NY_CLOSE            = 21
NEWS_PAUSE          = 30
EMA_FAST            = 8
EMA_SLOW            = 21
EMA_TREND           = 200
RSI_PERIOD          = 14
RSI_BUY_MAX         = 62.0
RSI_SELL_MIN        = 38.0
MACD_FAST           = 12
MACD_SLOW           = 26
MACD_SIGNAL         = 9
STOCH_K             = 14
STOCH_BUY           = 45
STOCH_SELL          = 55
TF_ENTRY            = ‘M15’
TF_TREND            = ‘H1’
CANDLES             = 300
SCAN_INTERVAL       = 60

logging.basicConfig(
level=logging.INFO,
format=’%(asctime)s [%(levelname)s] %(message)s’,
handlers=[logging.StreamHandler(), logging.FileHandler(‘oanda_bot.log’, mode=‘a’)],
)
log = logging.getLogger(**name**)

def calc_ema(prices, period):
if len(prices) < period:
return None
k = 2 / (period + 1)
ema = prices[0]
for p in prices[1:]:
ema = p * k + ema * (1 - k)
return ema

def calc_rsi(prices, period=14):
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

def calc_macd_histogram(prices):
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
return macd_vals[-1] - signal if signal else None

def calc_stochastic(highs, lows, closes):
if len(closes) < STOCH_K:
return None
hh = max(highs[-STOCH_K:])
ll = min(lows[-STOCH_K:])
if hh == ll:
return 50.0
return round(100 * (closes[-1] - ll) / (hh - ll), 2)

def get_balance():
try:
r = requests.get(BASE_URL + ‘/v3/accounts/’ + OANDA_ACCOUNT_ID + ‘/summary’, headers=HEADERS, timeout=10)
return float(r.json()[‘account’][‘balance’])
except Exception as e:
log.error(’Balance error: ’ + str(e))
return 0.0

def get_candles(instrument, granularity, count=CANDLES):
try:
r = requests.get(
BASE_URL + ‘/v3/instruments/’ + instrument + ‘/candles’,
headers=HEADERS,
params={‘count’: count, ‘granularity’: granularity, ‘price’: ‘M’},
timeout=10,
)
candles = [c for c in r.json().get(‘candles’, []) if c.get(‘complete’)]
return {
‘closes’: [float(c[‘mid’][‘c’]) for c in candles],
‘highs’:  [float(c[‘mid’][‘h’]) for c in candles],
‘lows’:   [float(c[‘mid’][‘l’]) for c in candles],
}
except Exception as e:
log.error(’Candle error ’ + instrument + ’: ’ + str(e))
return None

def get_open_trades():
try:
r = requests.get(BASE_URL + ‘/v3/accounts/’ + OANDA_ACCOUNT_ID + ‘/openTrades’, headers=HEADERS, timeout=10)
return {t[‘instrument’]: t for t in r.json().get(‘trades’, [])}
except Exception as e:
log.error(’Open trades error: ’ + str(e))
return {}

def get_price(instrument):
try:
r = requests.get(
BASE_URL + ‘/v3/accounts/’ + OANDA_ACCOUNT_ID + ‘/pricing’,
headers=HEADERS,
params={‘instruments’: instrument},
timeout=10,
)
prices = r.json().get(‘prices’, [])
if prices:
return (float(prices[0][‘asks’][0][‘price’]) + float(prices[0][‘bids’][0][‘price’])) / 2
return None
except Exception as e:
log.error(’Price error ’ + instrument + ’: ’ + str(e))
return None

def place_order(instrument, units, direction, sl, tp, digits):
signed = units if direction == ‘BUY’ else -units
fmt = ‘{:.’ + str(digits) + ‘f}’
payload = {
‘order’: {
‘type’:       ‘MARKET’,
‘instrument’: instrument,
‘units’:      str(signed),
‘stopLossOnFill’:   {‘price’: fmt.format(sl),  ‘timeInForce’: ‘GTC’},
‘takeProfitOnFill’: {‘price’: fmt.format(tp),  ‘timeInForce’: ‘GTC’},
‘timeInForce’: ‘FOK’,
}
}
try:
r    = requests.post(BASE_URL + ‘/v3/accounts/’ + OANDA_ACCOUNT_ID + ‘/orders’, headers=HEADERS, json=payload, timeout=10)
resp = r.json()
if ‘orderFillTransaction’ in resp:
fill = resp[‘orderFillTransaction’]
log.info(’FILLED ’ + direction + ’ ’ + instrument + ’ @ ’ + str(fill.get(‘price’)))
return True
log.error(’Rejected ’ + instrument + ’: ’ + str(resp))
return False
except Exception as e:
log.error(’Order error ’ + instrument + ’: ’ + str(e))
return False

def modify_sl(trade_id, new_sl, digits):
try:
fmt = ‘{:.’ + str(digits) + ‘f}’
requests.put(
BASE_URL + ‘/v3/accounts/’ + OANDA_ACCOUNT_ID + ‘/trades/’ + trade_id + ‘/orders’,
headers=HEADERS,
json={‘stopLoss’: {‘price’: fmt.format(new_sl), ‘timeInForce’: ‘GTC’}},
timeout=10,
)
except Exception as e:
log.error(’Modify SL error: ’ + str(e))

def get_daily_pnl():
try:
today = datetime.now(timezone.utc).strftime(’%Y-%m-%dT00:00:00Z’)
r = requests.get(
BASE_URL + ‘/v3/accounts/’ + OANDA_ACCOUNT_ID + ‘/transactions’,
headers=HEADERS,
params={‘from’: today, ‘type’: ‘ORDER_FILL’},
timeout=10,
)
return sum(float(t.get(‘pl’, 0)) for t in r.json().get(‘transactions’, []))
except:
return 0.0

_news_cache      = []
_news_cache_time = None

def fetch_news():
global _news_cache, _news_cache_time
now = datetime.now(timezone.utc)
if _news_cache_time and (now - _news_cache_time).seconds < 1800:
return _news_cache
try:
r = requests.get(‘https://nfs.faireconomy.media/ff_calendar_thisweek.json’, timeout=10)
_news_cache      = [e for e in r.json() if e.get(‘impact’) == ‘High’]
_news_cache_time = now
except:
pass
return _news_cache

def is_news_time(instrument):
parts = instrument.split(’_’)
now   = datetime.now(timezone.utc)
for event in fetch_news():
try:
currency = event.get(‘country’, ‘’).upper()
if not any(currency in p for p in parts):
continue
et   = datetime.fromisoformat(event[‘date’].replace(‘Z’, ‘+00:00’))
diff = (et - now).total_seconds() / 60
if -NEWS_PAUSE <= diff <= NEWS_PAUSE:
return True
except:
continue
return False

def in_session(instrument):
if instrument in NO_SESSION_FILTER:
return True
hour = datetime.now(timezone.utc).hour
return (LONDON_OPEN <= hour < LONDON_CLOSE) or (NY_OPEN <= hour < NY_CLOSE)

def get_signal(instrument):
h1 = get_candles(instrument, TF_TREND, 250)
if not h1 or len(h1[‘closes’]) < EMA_TREND:
return ‘HOLD’
trend_ema  = calc_ema(h1[‘closes’], EMA_TREND)
h1_price   = h1[‘closes’][-1]
up_trend   = h1_price > trend_ema if trend_ema else False
down_trend = h1_price < trend_ema if trend_ema else False

```
m15 = get_candles(instrument, TF_ENTRY, CANDLES)
if not m15 or len(m15['closes']) < EMA_SLOW + 2:
    return 'HOLD'

c = m15['closes']
h = m15['highs']
l = m15['lows']

ef_now  = calc_ema(c,      EMA_FAST)
es_now  = calc_ema(c,      EMA_SLOW)
ef_prev = calc_ema(c[:-1], EMA_FAST)
es_prev = calc_ema(c[:-1], EMA_SLOW)
rsi     = calc_rsi(c)
macd_h  = calc_macd_histogram(c)
stoch   = calc_stochastic(h, l, c)

if None in (ef_now, es_now, ef_prev, es_prev, rsi):
    return 'HOLD'

bull = (ef_prev < es_prev) and (ef_now > es_now)
bear = (ef_prev > es_prev) and (ef_now < es_now)

buy_score  = sum([bull,  up_trend,   rsi < RSI_BUY_MAX,  macd_h is None or macd_h > 0, stoch is None or stoch < STOCH_BUY])
sell_score = sum([bear, down_trend,  rsi > RSI_SELL_MIN, macd_h is None or macd_h < 0, stoch is None or stoch > STOCH_SELL])

if buy_score  >= 4: return 'BUY'
if sell_score >= 4: return 'SELL'
return 'HOLD'
```

def manage_trailing(open_trades):
for instrument, trade in open_trades.items():
try:
tid        = trade[‘id’]
open_price = float(trade[‘price’])
cur_sl     = float(trade.get(‘stopLossOrder’, {}).get(‘price’, 0))
units      = int(trade[‘currentUnits’])
direction  = ‘BUY’ if units > 0 else ‘SELL’
digits     = next((i[‘digits’] for i in INSTRUMENTS if i[‘name’] == instrument), 5)
cur_price  = get_price(instrument)
if not cur_price:
continue
new_sl = cur_sl
if direction == ‘BUY’:
profit_pct = (cur_price - open_price) / open_price
if profit_pct >= BREAKEVEN_TRIGGER and cur_sl < open_price:
new_sl = open_price
if USE_TRAILING:
trail = cur_price * (1 - TRAIL_PCT)
if trail > new_sl:
new_sl = trail
else:
profit_pct = (open_price - cur_price) / open_price
if profit_pct >= BREAKEVEN_TRIGGER and (cur_sl > open_price or cur_sl == 0):
new_sl = open_price
if USE_TRAILING:
trail = cur_price * (1 + TRAIL_PCT)
if trail < new_sl or new_sl == 0:
new_sl = trail
if abs(new_sl - cur_sl) > 0.00001:
modify_sl(tid, new_sl, digits)
except Exception as e:
log.error(’Trailing error ’ + instrument + ’: ’ + str(e))

def main():
log.info(‘OANDA PRO BOT v3.0 - £100 LIVE’)
log.info(‘Mode: LIVE - REAL MONEY’)

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

log.info('Starting balance: ' + str(round(start_bal, 2)))

while True:
    try:
        now     = datetime.now(timezone.utc)
        today   = now.date()
        balance = get_balance()

        if today != last_day:
            daily_loss   = 0.0
            daily_trades = 0
            start_bal    = balance
            last_day     = today
            log.info('New day! Balance: ' + str(round(balance, 2)))

        cur_week = now.isocalendar()[1]
        if cur_week != last_week:
            weekly_loss = 0.0
            week_bal    = balance
            last_week   = cur_week

        drawdown = (start_bal - balance) / max(start_bal, 1) * 100
        if drawdown >= MAX_DRAWDOWN_PCT:
            log.critical('EMERGENCY STOP - Drawdown: ' + str(round(drawdown, 1)) + '%')
            emergency = True
            break

        if emergency:
            time.sleep(60)
            continue

        pnl = get_daily_pnl()
        if pnl < 0:
            daily_loss = weekly_loss = abs(pnl)

        if balance < MIN_BALANCE:
            log.warning('Balance too low: ' + str(round(balance, 2)))
            time.sleep(SCAN_INTERVAL)
            continue

        if daily_loss >= start_bal * MAX_DAILY_LOSS_PCT / 100:
            log.warning('Daily loss limit hit')
            time.sleep(SCAN_INTERVAL)
            continue

        if weekly_loss >= week_bal * MAX_WEEKLY_LOSS_PCT / 100:
            log.warning('Weekly loss limit hit')
            time.sleep(SCAN_INTERVAL)
            continue

        if daily_trades >= MAX_DAILY_TRADES:
            log.warning('Daily trade limit hit')
            time.sleep(SCAN_INTERVAL)
            continue

        if pause_until:
            if now < pause_until:
                time.sleep(SCAN_INTERVAL)
                continue
            else:
                pause_until = None
                consec_loss = 0
                log.info('Pause lifted.')

        if consec_loss >= MAX_CONSEC_LOSSES:
            pause_until = now + timedelta(hours=2)
            consec_loss = 0
            log.warning('3 losses in a row - pausing 2 hours')
            time.sleep(SCAN_INTERVAL)
            continue

        open_trades = get_open_trades()
        manage_trailing(open_trades)

        if len(open_trades) >= MAX_OPEN_TRADES:
            time.sleep(SCAN_INTERVAL)
            continue

        for inst in INSTRUMENTS:
            name   = inst['name']
            label  = inst['label']
            units  = inst['units']
            digits = inst['digits']

            if name in open_trades:     continue
            if not in_session(name):    continue
            if is_news_time(name):      continue

            signal = get_signal(name)
            if signal == 'HOLD':
                log.info(label + ' -> HOLD')
                continue

            price = get_price(name)
            if not price:
                continue

            sl = price * (1 - STOP_LOSS_PCT)   if signal == 'BUY' else price * (1 + STOP_LOSS_PCT)
            tp = price * (1 + TAKE_PROFIT_PCT) if signal == 'BUY' else price * (1 - TAKE_PROFIT_PCT)
            rr = TAKE_PROFIT_PCT / STOP_LOSS_PCT

            if rr < MIN_REWARD_RATIO:
                continue

            log.info(signal + ' ' + label + ' @ ' + str(round(price, digits)))

            if place_order(name, units, signal, sl, tp, digits):
                daily_trades += 1
                consec_loss   = 0
                open_trades   = get_open_trades()
                if len(open_trades) >= MAX_OPEN_TRADES:
                    break

        log.info('Balance:' + str(round(balance, 2)) + ' Open:' + str(len(open_trades)) + ' Trades:' + str(daily_trades) + ' PnL:' + str(round(pnl, 2)) + ' DD:' + str(round(drawdown, 1)) + '%')

    except KeyboardInterrupt:
        log.info('Bot stopped.')
        break
    except Exception as e:
        log.error('Error: ' + str(e))

    time.sleep(SCAN_INTERVAL)
```

if **name** == ‘**main**’:
main()
