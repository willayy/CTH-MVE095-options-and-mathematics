import sys
from dataclasses import dataclass
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
class Position:
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
        self.positions: dict[tuple[str, str], Position] = {}

    def is_within_expiration_window(
        self,
        instrument: Instrument,
        expiration_date: str,
        minimum_window_seconds: float,
        maximum_window_seconds: float,
    ) -> bool:
        seconds_until_expiration = self.client.get_seconds_until_expiration(
            instrument.symbol,
            instrument.exchange,
            instrument.currency,
            expiration_date,
        )
        return (
            minimum_window_seconds <= seconds_until_expiration <= maximum_window_seconds
        )

    def compute_price_bounds(self, instrument: Instrument) -> tuple[float, float]:
        self.client.download_data(
            instrument.symbol, instrument.exchange, instrument.currency
        )
        current_price = self.client.get_current_price(
            instrument.symbol, instrument.exchange, instrument.currency
        )
        return bayesian_inference(
            instrument.symbol,
            current_price,
            self.credibility_interval_percentage,
            self.decay_factor,
        )

    def recover_position(
        self,
        instrument: Instrument,
        expiration_date: str,
    ) -> None:
        open_straddle = self.client.fetch_open_straddle(
            instrument.symbol, expiration_date
        )
        if open_straddle is None:
            return
        call_contract, put_contract, order_quantity = open_straddle
        lower_price, upper_price = self.compute_price_bounds(instrument)
        position_key = (instrument.symbol, expiration_date)
        self.positions[position_key] = Position(
            lower_price,
            upper_price,
            call_contract,
            put_contract,
            order_quantity,
            expiration_date,
        )

    def can_open_expiration(
        self,
        instrument: Instrument,
        expiration_date: str,
    ) -> bool:
        position_key = (instrument.symbol, expiration_date)
        if position_key in self.positions:
            return False
        within_window = self.is_within_expiration_window(
            instrument, expiration_date, 23.5 * 3600.0, 24.5 * 3600.0
        )
        if not within_window:
            return False
        return not self.client.has_open_position(instrument.symbol, expiration_date)

    def find_openable_expirations(self, instrument: Instrument) -> list[str]:
        upcoming_expirations = self.client.get_upcoming_expirations(
            instrument.symbol, instrument.exchange, instrument.currency
        )
        return [
            expiration_date
            for expiration_date in upcoming_expirations
            if self.can_open_expiration(instrument, expiration_date)
        ]

    def open_position(self, instrument: Instrument, expiration_date: str) -> None:
        lower_price, upper_price = self.compute_price_bounds(instrument)
        call_contract, put_contract, order_quantity = self.client.create_straddle(
            instrument.symbol,
            instrument.exchange,
            instrument.currency,
            expiration_date,
            self.fixed_capital_amount_dollars,
            lower_price,
            upper_price,
        )
        position_key = (instrument.symbol, expiration_date)
        self.positions[position_key] = Position(
            lower_price,
            upper_price,
            call_contract,
            put_contract,
            order_quantity,
            expiration_date,
        )

    def recover_positions(self, instrument: Instrument) -> None:
        upcoming_expirations = self.client.get_upcoming_expirations(
            instrument.symbol, instrument.exchange, instrument.currency
        )
        for expiration_date in upcoming_expirations:
            self.recover_untracked_expiration(instrument, expiration_date)

    def recover_untracked_expiration(
        self,
        instrument: Instrument,
        expiration_date: str,
    ) -> None:
        position_key = (instrument.symbol, expiration_date)
        if position_key in self.positions:
            return
        if self.client.has_open_position(instrument.symbol, expiration_date):
            self.recover_position(instrument, expiration_date)

    def is_position_closable(
        self,
        instrument: Instrument,
        expiration_date: str,
        position: Position,
    ) -> bool:
        if self.client.is_contract_expired(position.call_contract):
            del self.positions[(instrument.symbol, expiration_date)]
            return False
        current_price = self.client.get_current_price(
            instrument.symbol, instrument.exchange, instrument.currency
        )
        return (
            current_price < position.lower_price or current_price > position.upper_price
        )

    def find_closable_expirations(self, instrument: Instrument) -> list[str]:
        tracked_entries = [
            (expiration_date, position)
            for (symbol, expiration_date), position in list(self.positions.items())
            if symbol == instrument.symbol
        ]
        return [
            expiration_date
            for expiration_date, position in tracked_entries
            if self.is_position_closable(instrument, expiration_date, position)
        ]

    def close_position(self, instrument: Instrument, expiration_date: str) -> None:
        position_key = (instrument.symbol, expiration_date)
        position = self.positions.get(position_key)
        if position is None:
            return

        if self.client.has_open_position(instrument.symbol, position.expiration_date):
            self.client.neutralize_straddle(
                position.call_contract,
                position.put_contract,
                position.order_quantity,
            )
        del self.positions[position_key]

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

    def process_instrument(self, instrument: Instrument) -> None:
        for expiration_date in self.find_openable_expirations(instrument):
            self.open_position(instrument, expiration_date)
        self.recover_positions(instrument)
        for expiration_date in self.find_closable_expirations(instrument):
            self.close_position(instrument, expiration_date)

    def run_iteration(self) -> None:
        for instrument in self.instruments:
            self.process_instrument(instrument)
        self.log_status()
        self.client.sleep(self.check_interval_seconds)

    def run(self) -> None:
        self.client.check_connection()
        while True:
            self.run_iteration()
