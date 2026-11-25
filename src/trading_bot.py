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
class Instrument:
    symbol: str
    exchange: str
    currency: str


@dataclass
class ActiveBoundary:
    lower_price: float
    upper_price: float
    call_contract: Option
    put_contract: Option
    order_quantity: int
    expiration_date: str


class TradingBot:
    def __init__(
        self,
        instruments: list[Instrument],
        host_address: str,
        port_number: int,
        client_identifier: int,
        fixed_capital_amount_dollars: float,
        credibility_interval_percentage: float,
        decay_factor: float,
        check_interval_seconds: float,
    ) -> None:
        self.instruments = instruments
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
        self.active_boundaries: dict[str, ActiveBoundary] = {}
        self.opened_expirations: set[tuple[str, str]] = set()

    def is_within_expiration_window(
        self,
        expiration_date: str,
        minimum_window_seconds: float,
        maximum_window_seconds: float,
    ) -> bool:
        expiration_time = datetime.strptime(expiration_date, "%Y%m%d").replace(
            hour=16, minute=0, second=0
        )
        seconds_until_expiration = (expiration_time - datetime.now()).total_seconds()
        return (
            minimum_window_seconds <= seconds_until_expiration <= maximum_window_seconds
        )

    def check_active_boundaries(self) -> None:
        for instrument in self.instruments:
            boundary = self.active_boundaries.get(instrument.symbol)
            if boundary is None:
                continue

            expiration_time = datetime.strptime(
                boundary.expiration_date, "%Y%m%d"
            ).replace(hour=16, minute=0, second=0)
            if datetime.now() >= expiration_time:
                del self.active_boundaries[instrument.symbol]
                continue

            current_price = self.client.get_current_price(
                instrument.symbol, instrument.exchange, instrument.currency
            )
            if (
                current_price < boundary.lower_price
                or current_price > boundary.upper_price
            ):
                self.client.neutralize_straddle(
                    boundary.call_contract,
                    boundary.put_contract,
                    boundary.order_quantity,
                )
                del self.active_boundaries[instrument.symbol]

    def should_open_position(
        self,
        instrument: Instrument,
        nearest_expiration: str,
    ) -> bool:
        expiration_key = (instrument.symbol, nearest_expiration)
        return (
            not self.client.has_open_position(instrument.symbol, nearest_expiration)
            and expiration_key not in self.opened_expirations
            and self.is_within_expiration_window(
                nearest_expiration, 23.5 * 3600.0, 24.0 * 3600.0
            )
        )

    def open_straddle(
        self,
        instrument: Instrument,
        nearest_expiration: str,
    ) -> None:
        self.client.download_data(
            instrument.symbol, instrument.exchange, instrument.currency
        )
        current_price = self.client.get_current_price(
            instrument.symbol, instrument.exchange, instrument.currency
        )
        lower_price, upper_price = bayesian_inference(
            instrument.symbol,
            current_price,
            self.credibility_interval_percentage,
            self.decay_factor,
        )
        call_contract, put_contract, order_quantity = self.client.create_straddle(
            instrument.symbol,
            instrument.exchange,
            instrument.currency,
            nearest_expiration,
            self.fixed_capital_amount_dollars,
        )
        self.opened_expirations.add((instrument.symbol, nearest_expiration))
        self.active_boundaries[instrument.symbol] = ActiveBoundary(
            lower_price,
            upper_price,
            call_contract,
            put_contract,
            order_quantity,
            nearest_expiration,
        )

    def recover_boundary(
        self,
        instrument: Instrument,
        nearest_expiration: str,
    ) -> None:
        open_straddle = self.client.fetch_open_straddle(
            instrument.symbol, nearest_expiration
        )
        if open_straddle is None:
            return
        call_contract, put_contract, order_quantity = open_straddle
        self.client.download_data(
            instrument.symbol, instrument.exchange, instrument.currency
        )
        current_price = self.client.get_current_price(
            instrument.symbol, instrument.exchange, instrument.currency
        )
        lower_price, upper_price = bayesian_inference(
            instrument.symbol,
            current_price,
            self.credibility_interval_percentage,
            self.decay_factor,
        )
        self.active_boundaries[instrument.symbol] = ActiveBoundary(
            lower_price,
            upper_price,
            call_contract,
            put_contract,
            order_quantity,
            nearest_expiration,
        )

    def trade(self) -> None:
        for instrument in self.instruments:
            nearest_expiration = self.client.get_nearest_expiration(
                instrument.symbol, instrument.exchange, instrument.currency
            )
            if self.should_open_position(instrument, nearest_expiration):
                self.open_straddle(instrument, nearest_expiration)
            elif (
                instrument.symbol not in self.active_boundaries
                and self.client.has_open_position(instrument.symbol, nearest_expiration)
            ):
                self.opened_expirations.add((instrument.symbol, nearest_expiration))
                self.recover_boundary(instrument, nearest_expiration)

    def log_status(self) -> None:
        total_profit_and_loss = self.client.get_total_unrealized_profit_and_loss()
        total_account_value = self.client.get_total_account_value()
        open_positions_count = self.client.get_open_straddles_count()
        profit_and_loss_sign = "+" if total_profit_and_loss >= 0.0 else ""
        print(
            f"Current Positions P/L: {profit_and_loss_sign}{total_profit_and_loss:.2f} | "
            f"Total Account Value: {total_account_value:.2f} | "
            f"Open Positions: {open_positions_count}",
            flush=True,
        )

    def run(self) -> None:
        self.client.check_connection()
        while True:
            self.check_active_boundaries()
            self.trade()
            self.log_status()
            self.client.sleep(self.check_interval_seconds)
