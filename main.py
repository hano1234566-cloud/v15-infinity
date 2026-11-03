import ccxt
import time
import json
import os
from datetime import datetime

COINS_60 = [
 "NEAR/USDT:USDT","ARB/USDT:USDT","W/USDT:USDT","ENA/USDT:USDT",
 "TIA/USDT:USDT","WIF/USDT:USDT","1000PEPE/USDT:USDT","1000BONK/USDT:USDT",
 # ... باقي 60 عملة نفسها
]

CONTRACT_SIZE = 1
FEE_RATE = 0.0004
STATE_FILE = "state.json"
LOSS_FIXED = -0.20

STATE = {}
# نفس LEVELS لكن بفرق كبير + صافي
LEVELS_MAP = {
    0.30: 0.10,
    0.80: 0.50,
    1.20: 0.80,
    2.00: 1.40
}

def load_state():
    global STATE
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE,'r') as f:
            STATE = json.load(f)

def save_state():
    with open(STATE_FILE,'w') as f:
        json.dump(STATE,f)

def calculate_net_profit(gross):
    # صافي بعد الرسوم 0.04
    return gross - 0.04

def get_next_stop(net):
    stop = LOSS_FIXED
    for profit in sorted(LEVELS_MAP.keys()):
        if net >= profit:
            stop = LEVELS_MAP[profit]
    return stop

# ... نفس دوال exchange, place_stop_loss, check_positions
# مع شرط: if new_stop > old_stop فقط يرفع - ممنوع ينزل

print("OKX BOT V30028 RUNNING - SAME UI")