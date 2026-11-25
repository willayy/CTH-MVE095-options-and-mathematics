import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.trading_bot import Instrument, TradingBot


def parse_instrument(instrument_string: str) -> Instrument:
    parts = instrument_string.strip().split(":")
    if len(parts) != 3:
        raise ValueError(
            f"Instrument must be in SYMBOL:EXCHANGE:CURRENCY format, got: '{instrument_string}'."
        )
    symbol, exchange, currency = parts
    return Instrument(symbol.upper(), exchange.upper(), currency.upper())


def parse_arguments(command_line_arguments: list[str]) -> argparse.Namespace:
    argument_parser = argparse.ArgumentParser(
        description="Automated short straddle options trading bot across multiple assets."
    )
    argument_parser.add_argument(
        "instruments",
        nargs="+",
        type=str,
        help="Target instruments in SYMBOL:EXCHANGE:CURRENCY format (e.g. SPX:CBOE:USD).",
    )
    argument_parser.add_argument(
        "--host",
        type=str,
        required=True,
        help="Interactive Brokers Gateway or TWS host address.",
    )
    argument_parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="Interactive Brokers Gateway or TWS port number.",
    )
    argument_parser.add_argument(
        "--client-id",
        type=int,
        required=True,
        help="Interactive Brokers client identifier.",
    )
    argument_parser.add_argument(
        "--fixed-capital-amount",
        type=float,
        required=True,
        help="Fixed capital allocation amount in dollars.",
    )
    argument_parser.add_argument(
        "--credibility-percentage",
        type=float,
        required=True,
        help="Credibility interval percentage for Bayesian inference.",
    )
    argument_parser.add_argument(
        "--decay-factor",
        type=float,
        required=True,
        help="Exponential sample weight decay factor.",
    )
    argument_parser.add_argument(
        "--check-interval-seconds",
        type=float,
        required=True,
        help="Interval in seconds between active position checks.",
    )
    return argument_parser.parse_args(command_line_arguments)


def main() -> None:
    parsed_arguments = parse_arguments(sys.argv[1:])
    instruments = [
        parse_instrument(instrument_string)
        for instrument_string in parsed_arguments.instruments
    ]

    bot = TradingBot(
        instruments,
        parsed_arguments.host,
        parsed_arguments.port,
        parsed_arguments.client_id,
        parsed_arguments.fixed_capital_amount,
        parsed_arguments.credibility_percentage,
        parsed_arguments.decay_factor,
        parsed_arguments.check_interval_seconds,
    )
    bot.run()


if __name__ == "__main__":
    main()
