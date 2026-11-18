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

from src.bayesian_inference import bayesian_inference, critical_price_interval
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
        target_specifications: list[tuple[str, str, str, float]],
        host_address: str,
        port_number: int,
        client_identifier: int,
        fixed_capital_amount_dollars: float,
        credibility_interval_percentage: float,
        decay_factor: float,
        check_interval_seconds: float,
    ) -> None:
        if not target_specifications:
            raise ValueError(
                "target_specifications must contain at least one contract specification."
            )
        self.target_specifications = target_specifications
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
        self.active_positions: list[Position] = []

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

    def check_active_positions(self) -> None:
        remaining_positions: list[Position] = []
        for position in self.active_positions:
            current_price = self.client.get_current_price(
                position.symbol, position.exchange, position.currency
            )
            if (
                current_price < position.lower_price
                or current_price > position.upper_price
            ):
                self.client.neutralize_straddle(
                    position.call_contract,
                    position.put_contract,
                    position.order_quantity,
                )
            else:
                remaining_positions.append(position)
        self.active_positions = remaining_positions

    def open_new_positions(self) -> None:
        active_symbols = {position.symbol for position in self.active_positions}
        for symbol, exchange, currency, user_price in self.target_specifications:
            if symbol in active_symbols:
                continue

            nearest_expiration = self.client.get_nearest_expiration(
                symbol, exchange, currency
            )
            if self.is_maturity_within_check_window(nearest_expiration):
                self.client.download_data(symbol, exchange, currency)
                precision_posterior = bayesian_inference(symbol, self.decay_factor)
                lower_price, upper_price = critical_price_interval(
                    user_price,
                    0.0,
                    precision_posterior,
                    self.credibility_interval_percentage,
                )
                call_contract, put_contract, order_quantity = (
                    self.client.create_straddle(
                        symbol,
                        exchange,
                        currency,
                        nearest_expiration,
                        self.fixed_capital_amount_dollars,
                    )
                )
                self.active_positions.append(
                    Position(
                        symbol,
                        exchange,
                        currency,
                        lower_price,
                        upper_price,
                        call_contract,
                        put_contract,
                        order_quantity,
                    )
                )

    def run(self) -> None:
        self.client.check_connection()
        while True:
            self.client.sleep(self.check_interval_seconds)
            self.check_active_positions()
            self.open_new_positions()


def parse_target_specifications(
    raw_targets: list[str],
) -> list[tuple[str, str, str, float]]:
    target_specifications: list[tuple[str, str, str, float]] = []
    if raw_targets:
        if len(raw_targets) % 4 != 0:
            raise ValueError(
                "Target specifications must be provided in quadruplets of SYMBOL EXCHANGE CURRENCY PRICE."
            )
        for index in range(0, len(raw_targets), 4):
            target_specifications.append(
                (
                    raw_targets[index].upper(),
                    raw_targets[index + 1].upper(),
                    raw_targets[index + 2].upper(),
                    float(raw_targets[index + 3]),
                )
            )
    else:
        environment_targets = os.environ.get("TARGET_SPECIFICATIONS")
        if environment_targets:
            for entry in environment_targets.split(","):
                parts = entry.strip().split(":")
                if len(parts) == 4:
                    target_specifications.append(
                        (
                            parts[0].upper(),
                            parts[1].upper(),
                            parts[2].upper(),
                            float(parts[3]),
                        )
                    )
    if not target_specifications:
        raise ValueError(
            "No target specifications provided. Pass contract specifications as command line arguments or via TARGET_SPECIFICATIONS environment variable."
        )
    return target_specifications


def parse_arguments(command_line_arguments: list[str]) -> argparse.Namespace:
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
    targets_environment_value = os.environ.get("TARGET_SPECIFICATIONS")

    argument_parser = argparse.ArgumentParser(
        description="Automated short straddle options trading bot."
    )
    argument_parser.add_argument(
        "targets",
        nargs="*" if targets_environment_value else "+",
        help="Target contract specifications as quadruplets: SYMBOL EXCHANGE CURRENCY PRICE ...",
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
    parsed_arguments.targets = parse_target_specifications(parsed_arguments.targets)
    return parsed_arguments


def main() -> None:
    parsed_arguments = parse_arguments(sys.argv[1:])

    bot = TradingBot(
        parsed_arguments.targets,
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
