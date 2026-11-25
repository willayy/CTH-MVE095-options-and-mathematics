import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from ib_async import Option

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.main import parse_instrument
from src.trading_bot import (
    Instrument,
    Position,
    TradingBot,
)


def test_parse_instrument() -> None:
    instrument = parse_instrument("spx:cboe:usd")
    assert instrument.symbol == "SPX"
    assert instrument.exchange == "CBOE"
    assert instrument.currency == "USD"


def test_trading_bot_opens_position_when_it_should() -> None:
    instruments = [Instrument("SPX", "CBOE", "USD")]
    bot = TradingBot(
        instruments,
        "127.0.0.1",
        7497,
        10,
        100000.0,
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
        bot.maybe_open_new_positions()

        bot.client.download_data.assert_called_once_with("SPX", "CBOE", "USD")
        mock_bayesian_inference.assert_called_once_with("SPX", 5000.0, 0.95, 0.995)
        bot.client.create_straddle.assert_called_once_with(
            "SPX", "CBOE", "USD", "20261119", 100000.0
        )
        assert "SPX" in bot.active_positions
        active_position = bot.active_positions["SPX"]
        assert active_position.symbol == "SPX"
        assert active_position.exchange == "CBOE"
        assert active_position.currency == "USD"
        assert active_position.lower_price == 4900.0
        assert active_position.upper_price == 5100.0
        assert active_position.call_contract == call_contract
        assert active_position.put_contract == put_contract
        assert active_position.order_quantity == 2
        assert active_position.maturity == "20261119 16:00"
        assert active_position.start_time is not None
        assert active_position.status == "OPEN"
        assert active_position.loss == 0.0


def test_trading_bot_neutralizes_when_it_should() -> None:
    instruments = [Instrument("SPX", "CBOE", "USD")]
    bot = TradingBot(
        instruments,
        "127.0.0.1",
        7497,
        10,
        100000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    call_contract = Option("SPX", "20261119", 5000.0, "C", "CBOE", currency="USD")
    put_contract = Option("SPX", "20261119", 5000.0, "P", "CBOE", currency="USD")
    bot.active_positions["SPX"] = Position(
        "SPX",
        "CBOE",
        "USD",
        4900.0,
        5100.0,
        call_contract,
        put_contract,
        2,
        "2026-11-18 16:00:00",
        "20261119 16:00",
        "OPEN",
        0.0,
    )

    bot.client.get_current_price.return_value = 5150.0
    bot.client.get_position_profit_and_loss.return_value = -250.0
    bot.check_active_positions()

    bot.client.neutralize_straddle.assert_called_once_with(
        call_contract, put_contract, 2
    )
    assert bot.active_positions["SPX"].status == "NEUTRALIZED"
    assert bot.active_positions["SPX"].loss == -250.0


def test_trading_bot_opens_position_again() -> None:
    instruments = [Instrument("SPX", "CBOE", "USD")]
    bot = TradingBot(
        instruments,
        "127.0.0.1",
        7497,
        10,
        100000.0,
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
    bot.active_positions["SPX"] = Position(
        "SPX",
        "CBOE",
        "USD",
        4900.0,
        5100.0,
        call_contract,
        put_contract,
        2,
        "2026-11-18 16:00:00",
        "20261119 16:00",
        "NEUTRALIZED",
        -200.0,
    )

    with (
        patch.object(bot, "is_maturity_within_check_window", return_value=True),
        patch(
            "src.trading_bot.bayesian_inference", return_value=(5050.0, 5250.0)
        ) as mock_bayesian_inference,
    ):
        bot.maybe_open_new_positions()

        mock_bayesian_inference.assert_called_once_with("SPX", 5150.0, 0.95, 0.995)
        bot.client.create_straddle.assert_called_once_with(
            "SPX", "CBOE", "USD", "20261119", 100000.0
        )
        assert bot.active_positions["SPX"].lower_price == 5050.0
        assert bot.active_positions["SPX"].upper_price == 5250.0
        assert bot.active_positions["SPX"].call_contract == call_contract
        assert bot.active_positions["SPX"].put_contract == put_contract
        assert bot.active_positions["SPX"].order_quantity == 2
        assert bot.active_positions["SPX"].maturity == "20261119 16:00"
        assert bot.active_positions["SPX"].start_time is not None
        assert bot.active_positions["SPX"].status == "OPEN"
        assert bot.active_positions["SPX"].loss == 0.0


def test_trading_bot_keeps_position_until_maturity() -> None:
    instruments = [Instrument("SPX", "CBOE", "USD")]
    bot = TradingBot(
        instruments,
        "127.0.0.1",
        7497,
        10,
        100000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    call_contract = Option("SPX", "20261119", 5000.0, "C", "CBOE", currency="USD")
    put_contract = Option("SPX", "20261119", 5000.0, "P", "CBOE", currency="USD")
    bot.active_positions["SPX"] = Position(
        "SPX",
        "CBOE",
        "USD",
        4900.0,
        5100.0,
        call_contract,
        put_contract,
        2,
        "2026-11-18 16:00:00",
        "20261119 16:00",
        "OPEN",
        0.0,
    )

    bot.client.get_current_price.return_value = 5020.0
    bot.check_active_positions()

    assert bot.active_positions["SPX"].status == "OPEN"
    assert bot.client.neutralize_straddle.call_count == 0


def test_trading_bot_syncs_position_from_broker() -> None:
    instruments = [
        Instrument("SPX", "CBOE", "USD"),
        Instrument("ESTX50", "EUREX", "EUR"),
    ]
    bot = TradingBot(
        instruments,
        "127.0.0.1",
        7497,
        10,
        100000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    call_contract = Option("SPX", "20261119", 5000.0, "C", "CBOE", currency="USD")
    call_contract.lastTradeDateOrContractMonth = "20261119"
    put_contract = Option("SPX", "20261119", 5000.0, "P", "CBOE", currency="USD")
    bot.client.fetch_straddle_from_portfolio.side_effect = lambda symbol: (
        (call_contract, put_contract, 3) if symbol == "SPX" else None
    )
    bot.client.get_current_price.return_value = 5000.0

    with patch("src.trading_bot.bayesian_inference", return_value=(4920.0, 5080.0)):
        bot.sync_positions_from_broker()

    bot.client.download_data.assert_called_once_with("SPX", "CBOE", "USD")
    assert "SPX" in bot.active_positions
    assert bot.active_positions["SPX"].status == "OPEN"
    assert bot.active_positions["SPX"].order_quantity == 3
    assert bot.active_positions["SPX"].lower_price == 4920.0
    assert bot.active_positions["SPX"].upper_price == 5080.0
    assert "ESTX50" not in bot.active_positions


def test_log_status_prints_profit_and_loss_and_count(capsys) -> None:
    instruments = [Instrument("SPX", "CBOE", "USD")]
    bot = TradingBot(
        instruments,
        "127.0.0.1",
        7497,
        10,
        100000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    call_contract = Option("SPX", "20261119", 5000.0, "C", "CBOE", currency="USD")
    put_contract = Option("SPX", "20261119", 5000.0, "P", "CBOE", currency="USD")
    bot.active_positions["SPX"] = Position(
        "SPX",
        "CBOE",
        "USD",
        4900.0,
        5100.0,
        call_contract,
        put_contract,
        2,
        "2026-11-18 16:00:00",
        "20261119 16:00",
        "OPEN",
        0.0,
    )
    bot.client.get_position_profit_and_loss.return_value = 150.25
    bot.client.get_total_account_value.return_value = 997702.64

    bot.log_status()
    captured = capsys.readouterr()
    assert (
        captured.out.strip()
        == "Current Positions P/L: +150.25 | Total Account Value: 997702.64 | Open Positions: 1"
    )
