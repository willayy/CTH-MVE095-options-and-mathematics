import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from ib_async import Option

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ib_client import InteractiveBrokersClient
from src.main import parse_instrument
from src.trading_bot import (
    ActiveBoundary,
    Instrument,
    TradingBot,
)


def test_parse_instrument() -> None:
    instrument = parse_instrument("spx:cboe:usd")
    assert instrument.symbol == "SPX"
    assert instrument.exchange == "CBOE"
    assert instrument.currency == "USD"


def test_is_within_expiration_window() -> None:
    instrument = Instrument("SPX", "CBOE", "USD")
    bot = TradingBot(
        [instrument],
        "127.0.0.1",
        7497,
        10,
        100000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    bot.client.get_seconds_until_expiration.return_value = 23.8 * 3600.0
    assert (
        bot.is_within_expiration_window(
            instrument, "20991119", 23.5 * 3600.0, 24.0 * 3600.0
        )
        is True
    )

    bot.client.get_seconds_until_expiration.return_value = 6.0 * 3600.0
    assert (
        bot.is_within_expiration_window(
            instrument, "20991119", 23.5 * 3600.0, 24.0 * 3600.0
        )
        is False
    )


def test_is_contract_expired() -> None:
    client = InteractiveBrokersClient("127.0.0.1", 7497, 1)
    client.interactive_brokers = MagicMock()
    mock_details = MagicMock()
    mock_details.realExpirationDate = "20200101"
    mock_details.lastTradeTime = "16:00:00"
    mock_details.timeZoneId = "UTC"
    client.interactive_brokers.reqContractDetails.return_value = [mock_details]

    option = Option("SPX", "20200101", 5000.0, "C", "CBOE")
    assert client.is_contract_expired(option) is True

    mock_details.realExpirationDate = "20990101"
    assert client.is_contract_expired(option) is False

    mock_details.lastTradeTime = ""
    assert client.is_contract_expired(option) is True


def test_select_boundary_strikes() -> None:
    client = InteractiveBrokersClient("127.0.0.1", 7497, 1)
    strikes = [4800.0, 4850.0, 4900.0, 4950.0, 5000.0, 5050.0, 5100.0, 5150.0, 5200.0]
    call_strike, put_strike = client.select_boundary_strikes(strikes, 4920.0, 5080.0)
    assert put_strike == 4900.0
    assert call_strike == 5100.0


def test_select_boundary_strikes_on_exact_boundary() -> None:
    client = InteractiveBrokersClient("127.0.0.1", 7497, 1)
    strikes = [4800.0, 4900.0, 5000.0, 5100.0, 5200.0]
    call_strike, put_strike = client.select_boundary_strikes(strikes, 4900.0, 5100.0)
    assert put_strike == 4900.0
    assert call_strike == 5100.0


def test_select_boundary_strikes_fallback_when_outside_available_strikes() -> None:
    client = InteractiveBrokersClient("127.0.0.1", 7497, 1)
    strikes = [4900.0, 5000.0, 5100.0]
    call_strike, put_strike = client.select_boundary_strikes(strikes, 4700.0, 5300.0)
    assert put_strike == 4900.0
    assert call_strike == 5100.0


def test_check_opening_conditions_and_open_position() -> None:
    instrument = Instrument("SPX", "CBOE", "USD")
    bot = TradingBot(
        [instrument],
        "127.0.0.1",
        7497,
        10,
        100000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    bot.client.get_nearest_expiration.return_value = "20991119"
    bot.client.has_open_position.return_value = False
    bot.client.get_current_price.return_value = 5000.0
    call_contract = Option("SPX", "20991119", 5100.0, "C", "CBOE", currency="USD")
    put_contract = Option("SPX", "20991119", 4900.0, "P", "CBOE", currency="USD")
    bot.client.create_straddle.return_value = (call_contract, put_contract, 2)

    with (
        patch.object(bot, "is_within_expiration_window", return_value=True),
        patch(
            "src.trading_bot.bayesian_inference", return_value=(4900.0, 5100.0)
        ) as mock_bayesian_inference,
    ):
        assert bot.check_opening_conditions(instrument) is True
        bot.open_position(instrument)

        bot.client.download_data.assert_called_once_with("SPX", "CBOE", "USD")
        mock_bayesian_inference.assert_called_once_with("SPX", 5000.0, 0.95, 0.995)
        bot.client.create_straddle.assert_called_once_with(
            "SPX", "CBOE", "USD", "20991119", 100000.0, 4900.0, 5100.0
        )
        assert "SPX" in bot.active_boundaries
        boundary = bot.active_boundaries["SPX"]
        assert boundary.lower_price == 4900.0
        assert boundary.upper_price == 5100.0
        assert boundary.call_contract == call_contract
        assert boundary.put_contract == put_contract
        assert boundary.order_quantity == 2
        assert boundary.expiration_date == "20991119"


def test_check_opening_conditions_returns_false_when_position_already_open() -> None:
    instrument = Instrument("SPX", "CBOE", "USD")
    bot = TradingBot(
        [instrument],
        "127.0.0.1",
        7497,
        10,
        100000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    bot.client.get_nearest_expiration.return_value = "20991119"
    bot.client.has_open_position.return_value = True

    with patch.object(bot, "is_within_expiration_window", return_value=True):
        assert bot.check_opening_conditions(instrument) is False


def test_check_closing_conditions_and_close_position_neutralizes_when_bounds_breached() -> (
    None
):
    instrument = Instrument("SPX", "CBOE", "USD")
    bot = TradingBot(
        [instrument],
        "127.0.0.1",
        7497,
        10,
        100000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    call_contract = Option("SPX", "20991119", 5000.0, "C", "CBOE", currency="USD")
    put_contract = Option("SPX", "20991119", 5000.0, "P", "CBOE", currency="USD")
    bot.active_boundaries["SPX"] = ActiveBoundary(
        4900.0, 5100.0, call_contract, put_contract, 2, "20991119"
    )
    bot.client.is_contract_expired.return_value = False
    bot.client.get_current_price.return_value = 5150.0
    bot.client.has_open_position.return_value = True

    assert bot.check_closing_conditions(instrument) is True
    bot.close_position(instrument)

    bot.client.neutralize_straddle.assert_called_once_with(
        call_contract, put_contract, 2
    )
    assert "SPX" not in bot.active_boundaries


def test_check_closing_conditions_disregards_expired_contract() -> None:
    instrument = Instrument("SPX", "CBOE", "USD")
    bot = TradingBot(
        [instrument],
        "127.0.0.1",
        7497,
        10,
        100000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    call_contract = Option("SPX", "20200101", 3000.0, "C", "CBOE", currency="USD")
    put_contract = Option("SPX", "20200101", 3000.0, "P", "CBOE", currency="USD")
    bot.active_boundaries["SPX"] = ActiveBoundary(
        2900.0, 3100.0, call_contract, put_contract, 2, "20200101"
    )
    bot.client.is_contract_expired.return_value = True

    assert bot.check_closing_conditions(instrument) is False
    assert "SPX" not in bot.active_boundaries
    assert bot.client.neutralize_straddle.call_count == 0


def test_check_closing_conditions_recovers_boundary_on_restart() -> None:
    instrument = Instrument("SPX", "CBOE", "USD")
    bot = TradingBot(
        [instrument],
        "127.0.0.1",
        7497,
        10,
        100000.0,
        0.95,
        0.995,
        3.0,
    )
    bot.client = MagicMock()
    bot.client.get_nearest_expiration.return_value = "20991119"
    bot.client.has_open_position.return_value = True
    call_contract = Option("SPX", "20991119", 5000.0, "C", "CBOE", currency="USD")
    put_contract = Option("SPX", "20991119", 5000.0, "P", "CBOE", currency="USD")
    bot.client.fetch_open_straddle.return_value = (call_contract, put_contract, 2)
    bot.client.is_contract_expired.return_value = False
    bot.client.get_current_price.return_value = 5000.0

    with patch("src.trading_bot.bayesian_inference", return_value=(4920.0, 5080.0)):
        assert bot.check_closing_conditions(instrument) is False

    bot.client.download_data.assert_called_once_with("SPX", "CBOE", "USD")
    assert "SPX" in bot.active_boundaries
    assert bot.active_boundaries["SPX"].lower_price == 4920.0
    assert bot.active_boundaries["SPX"].upper_price == 5080.0


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
    bot.client.get_total_unrealized_profit_and_loss.return_value = 150.25
    bot.client.get_total_account_value.return_value = 997702.64
    bot.client.get_open_straddles_count.return_value = 1

    bot.log_status()
    captured = capsys.readouterr()
    assert (
        captured.out.strip()
        == "Current Positions P/L: +150.25 | Total Account Value: 997702.64 | Open Positions: 1"
    )
