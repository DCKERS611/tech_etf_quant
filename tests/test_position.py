from tech_etf_quant.broker_sim import calculate_buy_shares, execute_buy
from tech_etf_quant.portfolio import Portfolio


def test_buy_shares_are_lot_sized():
    shares = calculate_buy_shares(1000, 1.0, 8000)
    assert shares % 100 == 0
    assert shares >= 100


def test_cash_shortage_rejects_trade():
    shares = calculate_buy_shares(1000, 10.0, 1000)
    assert shares == 0


def test_buy_keeps_cash_reserve():
    portfolio = Portfolio(cash=8000, max_equity=8000)
    trade = execute_buy(portfolio, "512480", "半导体ETF", 1.0, 7000, "2024-01-02")
    assert trade is not None
    assert portfolio.cash >= 1000 - 1


def test_max_position_amount_is_capped():
    shares = calculate_buy_shares(8000, 1.0, 10_000, min_cash_reserve=1000, max_position_amount=6400)
    assert shares * 1.0 <= 6400
