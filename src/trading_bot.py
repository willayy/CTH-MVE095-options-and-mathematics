import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ib_async import Option

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bayesian_inference import bayesian_inference
from src.ib_client import InteractiveBrokersClient


@dataclass
class Position:
    symbol: str
    exchange: str
    currency: str
    lower_price: float
    upper_price: float
    call_contract: Option
    put_contract: Option
    order_quantity: int


class TradingBot:
    def __init__(
        self,
        symbol: str,
        exchange: str,
        currency: str,
        host_address: str,
        port_number: int,
        client_identifier: int,
        fixed_capital_amount_dollars: float,
        credibility_interval_percentage: float,
        decay_factor: float,
        check_interval_seconds: float,
    ) -> None:
        self.symbol = symbol.upper()
        self.exchange = exchange.upper()
        self.currency = currency.upper()
        self.host_address = host_address
        self.port_number = port_number
        self.client_identifier = client_identifier
        self.fixed_capital_amount_dollars = fixed_capital_amount_dollars
        self.credibility_interval_percentage = credibility_interval_percentage
        self.decay_factor = decay_factor
        self.check_interval_seconds = check_interval_seconds
        self.client = InteractiveBrokersClient(
            host_address, port_number, client_identifier
        )
        self.active_position: Position | None = None

    def is_maturity_within_check_window(
        self,
        expiration_date_string: str,
    ) -> bool:
        expiration_datetime = datetime.strptime(
            expiration_date_string, "%Y%m%d"
        ).replace(hour=16, minute=0, second=0)
        seconds_until_expiration = (
            expiration_datetime - datetime.now()
        ).total_seconds()
        target_seconds = 24.0 * 3600.0
        return (
            abs(seconds_until_expiration - target_seconds)
            <= self.check_interval_seconds
        )

    def check_active_position(self) -> None:
        if self.active_position is None:
            return

        current_price = self.client.get_current_price(
            self.symbol, self.exchange, self.currency
        )
        if (
            current_price < self.active_position.lower_price
            or current_price > self.active_position.upper_price
        ):
            self.client.neutralize_straddle(
                self.active_position.call_contract,
                self.active_position.put_contract,
                self.active_position.order_quantity,
            )
            self.active_position = None

    def open_new_position(self) -> None:
        if self.active_position is not None:
            return

        nearest_expiration = self.client.get_nearest_expiration(
            self.symbol, self.exchange, self.currency
        )
        if self.is_maturity_within_check_window(nearest_expiration):
            self.client.download_data(self.symbol, self.exchange, self.currency)
            current_price = self.client.get_current_price(
                self.symbol, self.exchange, self.currency
            )
            lower_price, upper_price = bayesian_inference(
                self.symbol,
                current_price,
                self.credibility_interval_percentage,
                self.decay_factor,
            )
            call_contract, put_contract, order_quantity = self.client.create_straddle(
                self.symbol,
                self.exchange,
                self.currency,
                nearest_expiration,
                self.fixed_capital_amount_dollars,
            )
            self.active_position = Position(
                self.symbol,
                self.exchange,
                self.currency,
                lower_price,
                upper_price,
                call_contract,
                put_contract,
                order_quantity,
            )

    def run(self) -> None:
        self.client.check_connection()
        while True:
            self.client.sleep(self.check_interval_seconds)
            self.check_active_position()
            self.open_new_position()


def parse_arguments(command_line_arguments: list[str]) -> argparse.Namespace:
    symbol_environment_value = os.environ.get("TARGET_SYMBOL")
    exchange_environment_value = os.environ.get("TARGET_EXCHANGE")
    currency_environment_value = os.environ.get("TARGET_CURRENCY")
    host_environment_value = os.environ.get("INTERACTIVE_BROKERS_HOST")
    port_environment_value = os.environ.get("INTERACTIVE_BROKERS_PORT")
    client_identifier_environment_value = os.environ.get(
        "INTERACTIVE_BROKERS_CLIENT_ID"
    )
    fixed_capital_amount_environment_value = os.environ.get(
        "FIXED_CAPITAL_AMOUNT_DOLLARS"
    )
    credibility_percentage_environment_value = os.environ.get(
        "CREDIBILITY_INTERVAL_PERCENTAGE"
    )
    decay_factor_environment_value = os.environ.get("DECAY_FACTOR")
    check_interval_environment_value = os.environ.get("CHECK_INTERVAL_SECONDS")

    argument_parser = argparse.ArgumentParser(
        description="Automated short straddle options trading bot for a single asset."
    )
    argument_parser.add_argument(
        "symbol",
        nargs="?" if symbol_environment_value else None,
        default=symbol_environment_value,
        help="Target contract symbol (e.g. SPX).",
    )
    argument_parser.add_argument(
        "exchange",
        nargs="?" if exchange_environment_value else None,
        default=exchange_environment_value,
        help="Target contract exchange (e.g. CBOE).",
    )
    argument_parser.add_argument(
        "currency",
        nargs="?" if currency_environment_value else None,
        default=currency_environment_value,
        help="Target contract currency (e.g. USD).",
    )
    argument_parser.add_argument(
        "--host",
        default=host_environment_value,
        required=host_environment_value is None,
        help="Interactive Brokers Gateway or TWS host address.",
    )
    argument_parser.add_argument(
        "--port",
        type=int,
        default=(
            int(port_environment_value) if port_environment_value is not None else None
        ),
        required=port_environment_value is None,
        help="Interactive Brokers Gateway or TWS port number.",
    )
    argument_parser.add_argument(
        "--client-id",
        type=int,
        default=(
            int(client_identifier_environment_value)
            if client_identifier_environment_value is not None
            else None
        ),
        required=client_identifier_environment_value is None,
        help="Interactive Brokers client identifier.",
    )
    argument_parser.add_argument(
        "--fixed-capital-amount",
        type=float,
        default=(
            float(fixed_capital_amount_environment_value)
            if fixed_capital_amount_environment_value is not None
            else None
        ),
        required=fixed_capital_amount_environment_value is None,
        help="Fixed capital allocation amount in dollars.",
    )
    argument_parser.add_argument(
        "--credibility-percentage",
        type=float,
        default=(
            float(credibility_percentage_environment_value)
            if credibility_percentage_environment_value is not None
            else None
        ),
        required=credibility_percentage_environment_value is None,
        help="Credibility interval percentage for Bayesian inference.",
    )
    argument_parser.add_argument(
        "--decay-factor",
        type=float,
        default=(
            float(decay_factor_environment_value)
            if decay_factor_environment_value is not None
            else None
        ),
        required=decay_factor_environment_value is None,
        help="Exponential sample weight decay factor.",
    )
    argument_parser.add_argument(
        "--check-interval-seconds",
        type=float,
        default=(
            float(check_interval_environment_value)
            if check_interval_environment_value is not None
            else None
        ),
        required=check_interval_environment_value is None,
        help="Interval in seconds between active position checks.",
    )
    parsed_arguments = argument_parser.parse_args(command_line_arguments)
    parsed_arguments.symbol = parsed_arguments.symbol.upper()
    parsed_arguments.exchange = parsed_arguments.exchange.upper()
    parsed_arguments.currency = parsed_arguments.currency.upper()
    return parsed_arguments


def main() -> None:
    parsed_arguments = parse_arguments(sys.argv[1:])

    bot = TradingBot(
        parsed_arguments.symbol,
        parsed_arguments.exchange,
        parsed_arguments.currency,
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
