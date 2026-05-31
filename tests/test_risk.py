from tech_etf_quant.portfolio import Portfolio, Position
from tech_etf_quant.risk import (
    chase_limit_blocks_main,
    check_position_stop_loss,
    consecutive_loss_permission,
    evaluate_account_risk,
    evaluate_trade_permission,
)


def test_account_hard_defense_at_8_percent_loss():
    assert evaluate_account_risk(7360) == "HARD_DEFENSE"


def test_position_stop_loss_for_test_and_main():
    test_pos = Position("512480", "半导体ETF", 100, 1.0, 0.95, "TEST")
    main_pos = Position("159995", "芯片ETF", 100, 1.0, 0.94, "MAIN")
    assert check_position_stop_loss(test_pos, 0.95)
    assert check_position_stop_loss(main_pos, 0.94)


def test_consecutive_losses_limit_permission():
    allowed, only_test, _ = consecutive_loss_permission(2)
    assert allowed and only_test
    allowed, only_test, _ = consecutive_loss_permission(3)
    assert not allowed and only_test


def test_chase_limit_blocks_main():
    blocked, _ = chase_limit_blocks_main(0.061)
    assert blocked
    blocked, _ = chase_limit_blocks_main(0.041, watch_time="10:30")
    assert blocked


def test_trade_permission_after_losses_is_only_test():
    portfolio = Portfolio()
    portfolio.consecutive_losses = 2
    decision = evaluate_trade_permission(portfolio)
    assert decision.only_test
    assert not decision.allow_main
