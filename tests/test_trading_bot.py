import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from ib_async import Option

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.trading_bot import (
    Position,
    TradingBot,
)


def test_trading_bot_opens_position_when_it_should() -> None:
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

        bot.client.download_data.assert_called_once_with("SPX", "CBOE", "USD")
        mock_bayesian_inference.assert_called_once_with("SPX", 5000.0, 0.95, 0.995)
        bot.client.create_straddle.assert_called_once_with(
            "SPX", "CBOE", "USD", "20261119", 10000.0
        )
        assert bot.active_position is not None
        assert bot.active_position.symbol == "SPX"
        assert bot.active_position.exchange == "CBOE"
        assert bot.active_position.currency == "USD"
        assert bot.active_position.lower_price == 4900.0
        assert bot.active_position.upper_price == 5100.0
        assert bot.active_position.call_contract == call_contract
        assert bot.active_position.put_contract == put_contract
        assert bot.active_position.order_quantity == 2


def test_trading_bot_neutralizes_when_it_should() -> None:
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
    call_contract = Option("SPX", "20261119", 5000.0, "C", "CBOE", currency="USD")
    put_contract = Option("SPX", "20261119", 5000.0, "P", "CBOE", currency="USD")
    bot.active_position = Position(
        "SPX",
        "CBOE",
        "USD",
        4900.0,
        5100.0,
        call_contract,
        put_contract,
        2,
    )

    bot.client.get_current_price.return_value = 5150.0
    bot.check_active_position()

    bot.client.neutralize_straddle.assert_called_once_with(
        call_contract, put_contract, 2
    )
    assert bot.active_position is None


def test_trading_bot_opens_position_again() -> None:
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
    bot.client.get_current_price.return_value = 5150.0
    call_contract = Option("SPX", "20261119", 5150.0, "C", "CBOE", currency="USD")
    put_contract = Option("SPX", "20261119", 5150.0, "P", "CBOE", currency="USD")
    bot.client.create_straddle.return_value = (call_contract, put_contract, 2)

    assert bot.active_position is None

    with (
        patch.object(bot, "is_maturity_within_check_window", return_value=True),
        patch(
            "src.trading_bot.bayesian_inference", return_value=(5050.0, 5250.0)
        ) as mock_bayesian_inference,
    ):
        bot.open_new_position()

        mock_bayesian_inference.assert_called_once_with("SPX", 5150.0, 0.95, 0.995)
        bot.client.create_straddle.assert_called_once_with(
            "SPX", "CBOE", "USD", "20261119", 10000.0
        )
        assert bot.active_position is not None
        assert bot.active_position.lower_price == 5050.0
        assert bot.active_position.upper_price == 5250.0
        assert bot.active_position.call_contract == call_contract
        assert bot.active_position.put_contract == put_contract
        assert bot.active_position.order_quantity == 2


def test_trading_bot_keeps_position_until_maturity() -> None:
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
    call_contract = Option("SPX", "20261119", 5000.0, "C", "CBOE", currency="USD")
    put_contract = Option("SPX", "20261119", 5000.0, "P", "CBOE", currency="USD")
    bot.active_position = Position(
        "SPX",
        "CBOE",
        "USD",
        4900.0,
        5100.0,
        call_contract,
        put_contract,
        2,
    )

    bot.client.get_current_price.return_value = 5020.0
    bot.check_active_position()

    assert bot.active_position is not None
    assert bot.client.neutralize_straddle.call_count == 0
