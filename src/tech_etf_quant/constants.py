"""Project constants and CSV schemas."""

from __future__ import annotations

INITIAL_CASH = 8000.00
MAX_ACCOUNT_LOSS_RATIO = 0.08
MAX_ACCOUNT_LOSS_AMOUNT = 640.00
ACCOUNT_HARD_STOP_EQUITY = 7360.00

COMMISSION_RATE = 0.00001
SLIPPAGE_RATE = 0.0003
LOT_SIZE = 100
PRICE_TICK = 0.001

TEST_POSITION_AMOUNT = 1000.00
LIGHT_POSITION_AMOUNT = 2000.00
STANDARD_POSITION_MIN = 3000.00
STANDARD_POSITION_MAX = 5000.00
MAX_POSITION_RATIO = 0.80
MAX_POSITION_AMOUNT = 6400.00
MIN_CASH_RESERVE = 1000.00

TEST_STOP_LOSS_RATIO = 0.05
MAIN_STOP_LOSS_RATIO = 0.06
ACCOUNT_MAX_LOSS_RATIO = 0.08
CHASE_LIMIT_NORMAL = 0.04
CHASE_LIMIT_HARD = 0.06
HIGH_OPEN_LIMIT = 0.02
CONSECUTIVE_LOSS_LIMIT_1 = 2
CONSECUTIVE_LOSS_LIMIT_2 = 3
MAIN_TRADE_COOLDOWN_DAYS = 10

ETF_GROUP_NAMES = {
    "semiconductor": "半导体组",
    "cpo_pcb": "CPO/PCB组",
    "electronics_mlcc": "电子/MLCC组",
    "rare_earth": "稀土材料组",
    "benchmark": "基准指数",
}

TRADE_LOG_FIELDS = [
    "date",
    "time",
    "symbol",
    "name",
    "side",
    "shares",
    "price",
    "amount",
    "commission",
    "slippage",
    "position_type",
    "reason",
    "signal_type",
    "cash_after",
    "equity_after",
    "realized_pnl",
    "realized_pnl_ratio",
]

WATCH_LOG_FIELDS = [
    "date",
    "time",
    "symbol",
    "price",
    "pct_change",
    "amount",
    "status",
    "watch_decision",
    "note",
]

RISK_LOG_FIELDS = [
    "date",
    "risk_type",
    "level",
    "symbol",
    "message",
    "action_required",
]

ERROR_LOG_FIELDS = ["date", "module", "symbol", "error_type", "message"]

STANDARD_COLUMNS = [
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "amplitude",
    "pct_change",
    "change",
    "turnover",
]

SIGNALS = {
    "BUY_TEST",
    "BUY_LIGHT",
    "BUY_STANDARD",
    "BUY_STRONG",
    "HOLD",
    "SELL",
    "REDUCE",
}
