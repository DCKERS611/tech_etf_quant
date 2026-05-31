"""Simple broker simulator with ETF trading constraints."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import Settings, load_settings
from .constants import LOT_SIZE, MIN_CASH_RESERVE, TRADE_LOG_FIELDS
from .portfolio import Portfolio
from .utils import LOG_DIR, append_csv_row, round_price


@dataclass
class Trade:
    date: str
    time: str
    symbol: str
    name: str
    side: str
    shares: int
    price: float
    amount: float
    commission: float
    slippage: float
    position_type: str
    reason: str
    signal_type: str
    cash_after: float
    equity_after: float
    realized_pnl: float = 0.0
    realized_pnl_ratio: float = 0.0


def calculate_buy_shares(
    requested_amount: float,
    price: float,
    cash: float,
    min_cash_reserve: float = MIN_CASH_RESERVE,
    lot_size: int = LOT_SIZE,
    max_position_amount: float = 6400.0,
    current_position_value: float = 0.0,
    commission_rate: float = 0.00001,
) -> int:
    available_cash = max(cash - min_cash_reserve, 0.0)
    position_room = max(max_position_amount - current_position_value, 0.0)
    target_amount = min(float(requested_amount), available_cash, position_room)
    if target_amount <= 0 or price <= 0:
        return 0
    unit_cost = price * (1 + commission_rate)
    shares = int((target_amount / unit_cost) // lot_size * lot_size)
    return max(shares, 0)


def record_trade(trade: Trade) -> None:
    append_csv_row(LOG_DIR / "trade_log.csv", TRADE_LOG_FIELDS, asdict(trade))


def execute_buy(
    portfolio: Portfolio,
    symbol: str,
    name: str,
    market_price: float,
    requested_amount: float,
    trade_date: str,
    trade_time: str = "09:30",
    position_type: str = "TEST",
    reason: str = "",
    signal_type: str = "BUY_TEST",
    settings: Settings | None = None,
    write_log: bool = False,
) -> Trade | None:
    settings = settings or load_settings()
    commission_rate = float(settings.get("trading.commission_rate", 0.00001))
    slippage_rate = float(settings.get("trading.slippage_rate", 0.0003))
    lot_size = int(settings.get("trading.lot_size", LOT_SIZE))
    min_cash = float(settings.get("account.min_cash_reserve", MIN_CASH_RESERVE))
    initial_cash = float(settings.get("account.initial_cash", 8000))
    max_position_amount = float(settings.get("account.max_position_ratio", 0.8)) * initial_cash
    exec_price = round_price(float(market_price) * (1 + slippage_rate), settings.get("trading.price_tick", 0.001))
    shares = calculate_buy_shares(
        requested_amount,
        exec_price,
        portfolio.cash,
        min_cash,
        lot_size,
        max_position_amount,
        portfolio.position_value,
        commission_rate,
    )
    if shares < lot_size:
        return None
    amount = shares * exec_price
    commission = amount * commission_rate
    portfolio.buy(symbol, name, shares, exec_price, commission, position_type, trade_date)
    trade = Trade(
        date=trade_date,
        time=trade_time,
        symbol=symbol,
        name=name,
        side="BUY",
        shares=shares,
        price=exec_price,
        amount=amount,
        commission=commission,
        slippage=abs(exec_price - market_price) * shares,
        position_type=position_type,
        reason=reason,
        signal_type=signal_type,
        cash_after=portfolio.cash,
        equity_after=portfolio.equity,
    )
    if write_log:
        record_trade(trade)
    return trade


def execute_sell(
    portfolio: Portfolio,
    symbol: str,
    market_price: float,
    trade_date: str,
    trade_time: str = "09:30",
    shares: int | None = None,
    reason: str = "",
    signal_type: str = "SELL",
    settings: Settings | None = None,
    write_log: bool = False,
) -> Trade | None:
    settings = settings or load_settings()
    if symbol not in portfolio.positions:
        return None
    pos = portfolio.positions[symbol]
    sell_shares = pos.shares if shares is None else min(int(shares), pos.shares)
    if sell_shares <= 0:
        return None
    slippage_rate = float(settings.get("trading.slippage_rate", 0.0003))
    commission_rate = float(settings.get("trading.commission_rate", 0.00001))
    exec_price = round_price(float(market_price) * (1 - slippage_rate), settings.get("trading.price_tick", 0.001))
    amount = sell_shares * exec_price
    commission = amount * commission_rate
    pnl, pnl_ratio = portfolio.sell(symbol, sell_shares, exec_price, commission)
    trade = Trade(
        date=trade_date,
        time=trade_time,
        symbol=symbol,
        name=pos.name,
        side="SELL",
        shares=sell_shares,
        price=exec_price,
        amount=amount,
        commission=commission,
        slippage=abs(exec_price - market_price) * sell_shares,
        position_type=pos.position_type,
        reason=reason,
        signal_type=signal_type,
        cash_after=portfolio.cash,
        equity_after=portfolio.equity,
        realized_pnl=pnl,
        realized_pnl_ratio=pnl_ratio,
    )
    if write_log:
        record_trade(trade)
    return trade
