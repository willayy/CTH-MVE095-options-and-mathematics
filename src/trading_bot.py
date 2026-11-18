import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
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
    start_time: str
    maturity: str


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
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Neutralizing straddle on {self.symbol}: price {current_price:.2f} exited critical interval [{self.active_position.lower_price:.2f}, {self.active_position.upper_price:.2f}].",
                flush=True,
            )
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
            entry_time_string = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            maturity_string = f"{nearest_expiration} 16:00"
            print(
                f"[{entry_time_string}] Opened straddle on {self.symbol} (expiration: {nearest_expiration}, lower: {lower_price:.2f}, upper: {upper_price:.2f}, quantity: {order_quantity}).",
                flush=True,
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
                entry_time_string,
                maturity_string,
            )

    def log_interval_status(self) -> None:
        current_time_string = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_price = self.client.get_current_price(
            self.symbol, self.exchange, self.currency
        )
        if self.active_position is not None:
            position_pnl = self.client.get_position_pnl(
                self.active_position.call_contract,
                self.active_position.put_contract,
            )
            pnl_sign = "+" if position_pnl >= 0 else ""
            print(
                f"[{current_time_string}] [{self.symbol} PING] "
                f"Position Open | "
                f"Spot: {current_price:.2f} {self.currency} | "
                f"P/L: {pnl_sign}{position_pnl:.2f} {self.currency} | "
                f"Start: {self.active_position.start_time} | "
                f"Maturity: {self.active_position.maturity} | "
                f"Critical: [{self.active_position.lower_price:.2f}, {self.active_position.upper_price:.2f}]",
                flush=True,
            )
        else:
            nearest_expiration = self.client.get_nearest_expiration(
                self.symbol, self.exchange, self.currency
            )
            expiration_datetime = datetime.strptime(
                nearest_expiration, "%Y%m%d"
            ).replace(hour=16, minute=0, second=0)
            target_entry_datetime = expiration_datetime - timedelta(hours=24)
            now = datetime.now()
            if (expiration_datetime - now).total_seconds() < (
                24.0 * 3600.0 - self.check_interval_seconds
            ):
                next_entry_datetime = target_entry_datetime + timedelta(days=1)
            else:
                next_entry_datetime = target_entry_datetime
            hours_until_entry = max(
                0.0, (next_entry_datetime - now).total_seconds() / 3600.0
            )
            next_entry_string = next_entry_datetime.strftime("%Y-%m-%d 16:00")
            print(
                f"[{current_time_string}] [{self.symbol} PING] "
                f"No position open | "
                f"Spot: {current_price:.2f} {self.currency} | "
                f"Next Entry: {next_entry_string} (in {hours_until_entry:.1f}h)",
                flush=True,
            )

    def run(self) -> None:
        self.client.check_connection()
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Connected to Interactive Brokers Gateway. Monitoring {self.symbol} ({self.exchange}) every {self.check_interval_seconds}s...",
            flush=True,
        )
        while True:
            self.client.sleep(self.check_interval_seconds)
            self.check_active_position()
            self.open_new_position()
            self.log_interval_status()


def parse_arguments(command_line_arguments: list[str]) -> argparse.Namespace:
    argument_parser = argparse.ArgumentParser(
        description="Automated short straddle options trading bot for a single asset."
    )
    argument_parser.add_argument(
        "symbol",
        type=str,
        help="Target contract symbol (e.g. SPX).",
    )
    argument_parser.add_argument(
        "exchange",
        type=str,
        help="Target contract exchange (e.g. CBOE).",
    )
    argument_parser.add_argument(
        "currency",
        type=str,
        help="Target contract currency (e.g. USD).",
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
