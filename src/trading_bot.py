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
        target_specifications: list[tuple[str, str, str]],
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
        for symbol, exchange, currency in self.target_specifications:
            if symbol in active_symbols:
                continue

            nearest_expiration = self.client.get_nearest_expiration(
                symbol, exchange, currency
            )
            if self.is_maturity_within_check_window(nearest_expiration):
                self.client.download_data(symbol, exchange, currency)
                lower_price, upper_price = bayesian_inference(
                    symbol, self.credibility_interval_percentage, self.decay_factor
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


def parse_target_specifications() -> list[tuple[str, str, str]]:
    targets: list[tuple[str, str, str]] = []
    environment_targets = os.environ.get("TARGET_SPECIFICATIONS")
    if environment_targets:
        for entry in environment_targets.split(","):
            parts = entry.strip().split(":")
            if len(parts) == 3:
                targets.append((parts[0].upper(), parts[1].upper(), parts[2].upper()))
    if len(sys.argv) >= 4:
        argument_index = 1
        while argument_index + 2 < len(sys.argv):
            targets.append(
                (
                    sys.argv[argument_index].upper(),
                    sys.argv[argument_index + 1].upper(),
                    sys.argv[argument_index + 2].upper(),
                )
            )
            argument_index += 3
    if not targets:
        raise ValueError(
            "No target specifications provided. Pass contract specifications as command line arguments or via TARGET_SPECIFICATIONS environment variable."
        )
    return targets


if __name__ == "__main__":
    host_address_value = os.environ.get("INTERACTIVE_BROKERS_HOST", "127.0.0.1")
    port_number_value = int(os.environ.get("INTERACTIVE_BROKERS_PORT", "7497"))
    client_identifier_value = int(os.environ.get("INTERACTIVE_BROKERS_CLIENT_ID", "10"))
    fixed_capital_amount_value = float(
        os.environ.get("FIXED_CAPITAL_AMOUNT_DOLLARS", "10000.0")
    )
    credibility_percentage_value = float(
        os.environ.get("CREDIBILITY_INTERVAL_PERCENTAGE", "0.95")
    )

    targets = parse_target_specifications()

    bot = TradingBot(
        targets,
        host_address_value,
        port_number_value,
        client_identifier_value,
        fixed_capital_amount_value,
        credibility_percentage_value,
        0.995,
        5.0,
    )
    bot.run()
