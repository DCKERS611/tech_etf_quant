"""Portfolio and position state."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Position:
    symbol: str
    name: str
    shares: int
    avg_cost: float
    last_price: float
    position_type: str = "TEST"
    open_date: str = ""

    @property
    def market_value(self) -> float:
        return float(self.shares * self.last_price)

    @property
    def unrealized_pnl(self) -> float:
        return float((self.last_price - self.avg_cost) * self.shares)

    @property
    def unrealized_pnl_ratio(self) -> float:
        if self.avg_cost <= 0:
            return 0.0
        return float(self.last_price / self.avg_cost - 1)


@dataclass
class Portfolio:
    cash: float = 8000.0
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    max_equity: float = 8000.0
    trade_count: int = 0
    consecutive_losses: int = 0
    risk_state: str = "NORMAL"

    @property
    def position_value(self) -> float:
        return float(sum(position.market_value for position in self.positions.values()))

    @property
    def equity(self) -> float:
        return float(self.cash + self.position_value)

    @property
    def drawdown(self) -> float:
        if self.max_equity <= 0:
            return 0.0
        return float(self.equity / self.max_equity - 1)

    def update_market_prices(self, prices: dict[str, float]) -> None:
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].last_price = float(price)
        self.max_equity = max(self.max_equity, self.equity)

    def buy(
        self,
        symbol: str,
        name: str,
        shares: int,
        price: float,
        commission: float,
        position_type: str,
        trade_date: str,
    ) -> None:
        if shares <= 0:
            return
        cost = shares * price + commission
        if cost > self.cash + 1e-8:
            raise ValueError("insufficient cash")
        if symbol in self.positions:
            pos = self.positions[symbol]
            total_shares = pos.shares + shares
            pos.avg_cost = (pos.avg_cost * pos.shares + price * shares) / total_shares
            pos.shares = total_shares
            pos.last_price = price
            if position_type in {"MAIN", "STRONG"}:
                pos.position_type = position_type
        else:
            self.positions[symbol] = Position(symbol, name, shares, price, price, position_type, trade_date)
        self.cash -= cost
        self.trade_count += 1
        self.max_equity = max(self.max_equity, self.equity)

    def sell(self, symbol: str, shares: int, price: float, commission: float) -> tuple[float, float]:
        if symbol not in self.positions:
            return 0.0, 0.0
        pos = self.positions[symbol]
        shares = min(int(shares), pos.shares)
        if shares <= 0:
            return 0.0, 0.0
        proceeds = shares * price - commission
        pnl = (price - pos.avg_cost) * shares - commission
        pnl_ratio = price / pos.avg_cost - 1 if pos.avg_cost > 0 else 0.0
        pos.shares -= shares
        pos.last_price = price
        self.cash += proceeds
        self.realized_pnl += pnl
        self.trade_count += 1
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        if pos.shares <= 0:
            del self.positions[symbol]
        self.max_equity = max(self.max_equity, self.equity)
        return float(pnl), float(pnl_ratio)

    def can_sell(self, symbol: str, trade_date: str) -> bool:
        pos = self.positions.get(symbol)
        if pos is None:
            return False
        return bool(pos.open_date) and str(trade_date) > str(pos.open_date)

    def snapshot(self) -> dict:
        return {
            "cash": self.cash,
            "equity": self.equity,
            "position_value": self.position_value,
            "realized_pnl": self.realized_pnl,
            "max_equity": self.max_equity,
            "drawdown": self.drawdown,
            "trade_count": self.trade_count,
            "consecutive_losses": self.consecutive_losses,
            "risk_state": self.risk_state,
            "positions": {
                symbol: {
                    "name": pos.name,
                    "shares": pos.shares,
                    "avg_cost": pos.avg_cost,
                    "last_price": pos.last_price,
                    "market_value": pos.market_value,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "unrealized_pnl_ratio": pos.unrealized_pnl_ratio,
                    "position_type": pos.position_type,
                    "open_date": pos.open_date,
                }
                for symbol, pos in self.positions.items()
            },
        }
