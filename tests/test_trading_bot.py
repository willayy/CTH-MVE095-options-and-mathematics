import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ib_async import Option

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.trading_bot import (
    TradingBot,
    parse_arguments,
)


def test_trading_bot_holds_position_until_maturity_when_price_in_bounds() -> None:
    bot = TradingBot(
        "SPX",
        "CBOE",
        "USD",
        "127.0.0.1",
        7497,
        10,
        10000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    bot.client.get_nearest_expiration.return_value = "20261119"
    bot.client.get_current_price.return_value = 5000.0

    call_contract = Option("SPX", "20261119", 5000.0, "C", "CBOE", currency="USD")
    put_contract = Option("SPX", "20261119", 5000.0, "P", "CBOE", currency="USD")
    bot.client.create_straddle.return_value = (call_contract, put_contract, 2)

    with (
        patch.object(bot, "is_maturity_within_check_window", return_value=True),
        patch(
            "src.trading_bot.bayesian_inference", return_value=(4900.0, 5100.0)
        ) as mock_bayesian_inference,
    ):
        bot.open_new_position()

        mock_bayesian_inference.assert_called_once_with("SPX", 5000.0, 0.95, 0.995)
        assert bot.active_position is not None
        assert bot.active_position.symbol == "SPX"
        assert bot.active_position.lower_price == 4900.0
        assert bot.active_position.upper_price == 5100.0
        assert bot.active_position.order_quantity == 2
        assert bot.client.create_straddle.call_count == 1

        bot.client.get_current_price.return_value = 5020.0
        bot.check_active_position()

        assert bot.active_position is not None
        assert bot.client.neutralize_straddle.call_count == 0


def test_trading_bot_neutralizes_and_reopens_position_when_price_breaks_interval() -> (
    None
):
    bot = TradingBot(
        "SPX",
        "CBOE",
        "USD",
        "127.0.0.1",
        7497,
        10,
        10000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    bot.client.get_nearest_expiration.return_value = "20261119"
    bot.client.get_current_price.return_value = 5000.0

    first_call_contract = Option("SPX", "20261119", 5000.0, "C", "CBOE", currency="USD")
    first_put_contract = Option("SPX", "20261119", 5000.0, "P", "CBOE", currency="USD")
    second_call_contract = Option(
        "SPX", "20261119", 5150.0, "C", "CBOE", currency="USD"
    )
    second_put_contract = Option("SPX", "20261119", 5150.0, "P", "CBOE", currency="USD")
    bot.client.create_straddle.side_effect = [
        (first_call_contract, first_put_contract, 2),
        (second_call_contract, second_put_contract, 2),
    ]

    with (
        patch.object(bot, "is_maturity_within_check_window", return_value=True),
        patch(
            "src.trading_bot.bayesian_inference",
            side_effect=[(4900.0, 5100.0), (5050.0, 5250.0)],
        ) as mock_bayesian_inference,
    ):
        bot.open_new_position()
        mock_bayesian_inference.assert_called_with("SPX", 5000.0, 0.95, 0.995)
        assert bot.active_position is not None
        assert bot.active_position.call_contract == first_call_contract

        bot.client.get_current_price.return_value = 5120.0
        bot.check_active_position()

        assert bot.active_position is None
        bot.client.neutralize_straddle.assert_called_once_with(
            first_call_contract, first_put_contract, 2
        )

        bot.client.get_current_price.return_value = 5150.0
        bot.open_new_position()

        assert bot.active_position is not None
        assert bot.active_position.call_contract == second_call_contract
        assert bot.active_position.lower_price == 5050.0
        assert bot.active_position.upper_price == 5250.0
        assert bot.client.create_straddle.call_count == 2


def test_trading_bot_run_loop_with_three_second_sleep_and_lifecycle() -> None:
    bot = TradingBot(
        "SPX",
        "CBOE",
        "USD",
        "127.0.0.1",
        7497,
        10,
        10000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    bot.client.get_nearest_expiration.return_value = "20261119"

    first_call_contract = Option("SPX", "20261119", 5000.0, "C", "CBOE", currency="USD")
    first_put_contract = Option("SPX", "20261119", 5000.0, "P", "CBOE", currency="USD")
    reopened_call_contract = Option(
        "SPX", "20261119", 5200.0, "C", "CBOE", currency="USD"
    )
    reopened_put_contract = Option(
        "SPX", "20261119", 5200.0, "P", "CBOE", currency="USD"
    )

    bot.client.create_straddle.side_effect = [
        (first_call_contract, first_put_contract, 2),
        (reopened_call_contract, reopened_put_contract, 2),
    ]

    # Iteration 1 open: 5000.0; Iteration 2 check: 5150.0; Iteration 2 open: 5200.0
    bot.client.get_current_price.side_effect = [5000.0, 5150.0, 5200.0]

    iteration_counter = {"count": 0}

    class TerminateLoopException(Exception):
        pass

    def mock_sleep_handler(seconds: float) -> None:
        assert seconds == 3.0
        iteration_counter["count"] += 1
        if iteration_counter["count"] >= 3:
            raise TerminateLoopException()

    bot.client.sleep.side_effect = mock_sleep_handler

    with (
        patch.object(bot, "is_maturity_within_check_window", return_value=True),
        patch(
            "src.trading_bot.bayesian_inference",
            side_effect=[(4900.0, 5100.0), (5100.0, 5300.0)],
        ),
        pytest.raises(TerminateLoopException),
    ):
        bot.run()

    bot.client.check_connection.assert_called_once()
    assert iteration_counter["count"] == 3
    assert bot.client.sleep.call_count == 3
    bot.client.neutralize_straddle.assert_called_once_with(
        first_call_contract, first_put_contract, 2
    )
    assert bot.client.create_straddle.call_count == 2


def test_trading_bot_is_maturity_within_check_window() -> None:
    bot = TradingBot(
        "SPX",
        "CBOE",
        "USD",
        "127.0.0.1",
        7497,
        10,
        10000.0,
        0.95,
        0.995,
        3.0,
    )
    mocked_now = datetime(2026, 11, 19, 16, 0, 0)

    with patch("src.trading_bot.datetime") as mock_datetime:
        mock_datetime.now.return_value = mocked_now
        mock_datetime.strptime = datetime.strptime

        assert bot.is_maturity_within_check_window("20261120") is True

        mock_datetime.now.return_value = datetime(2026, 11, 19, 15, 59, 58)
        assert bot.is_maturity_within_check_window("20261120") is True

        mock_datetime.now.return_value = datetime(2026, 11, 19, 15, 59, 50)
        assert bot.is_maturity_within_check_window("20261120") is False


def test_parse_arguments_parses_single_asset_target() -> None:
    arguments = [
        "SPX",
        "CBOE",
        "USD",
        "--host",
        "127.0.0.1",
        "--port",
        "7497",
        "--client-id",
        "10",
        "--fixed-capital-amount",
        "10000.0",
        "--credibility-percentage",
        "0.95",
        "--decay-factor",
        "0.995",
        "--check-interval-seconds",
        "3.0",
    ]
    parsed = parse_arguments(arguments)
    assert parsed.symbol == "SPX"
    assert parsed.exchange == "CBOE"
    assert parsed.currency == "USD"
    assert parsed.host == "127.0.0.1"
    assert parsed.port == 7497
    assert parsed.client_id == 10
    assert parsed.fixed_capital_amount == 10000.0
    assert parsed.credibility_percentage == 0.95
    assert parsed.decay_factor == 0.995
    assert parsed.check_interval_seconds == 3.0


def test_parse_arguments_raises_error_when_flag_arguments_missing() -> None:
    arguments = [
        "SPX",
        "CBOE",
        "USD",
        "--port",
        "7497",
        "--client-id",
        "10",
        "--fixed-capital-amount",
        "10000.0",
        "--credibility-percentage",
        "0.95",
        "--decay-factor",
        "0.995",
        "--check-interval-seconds",
        "3.0",
    ]
    with pytest.raises(SystemExit):
        parse_arguments(arguments)


def test_parse_arguments_raises_error_when_positional_arguments_missing() -> None:
    arguments = [
        "SPX",
        "CBOE",
        "--host",
        "127.0.0.1",
        "--port",
        "7497",
        "--client-id",
        "10",
        "--fixed-capital-amount",
        "10000.0",
        "--credibility-percentage",
        "0.95",
        "--decay-factor",
        "0.995",
        "--check-interval-seconds",
        "3.0",
    ]
    with pytest.raises(SystemExit):
        parse_arguments(arguments)
