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
        self.positions: dict[str, Position] = {}

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

    def recover_position(
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
        self.positions[instrument.symbol] = Position(
            lower_price,
            upper_price,
            call_contract,
            put_contract,
            order_quantity,
            nearest_expiration,
        )

    def check_opening_conditions(self, instrument: Instrument) -> bool:
        nearest_expiration = self.client.get_nearest_expiration(
            instrument.symbol, instrument.exchange, instrument.currency
        )
        return self.is_within_expiration_window(
            instrument, nearest_expiration, 23.5 * 3600.0, 24.0 * 3600.0
        ) and not self.client.has_open_position(instrument.symbol, nearest_expiration)

    def open_position(self, instrument: Instrument) -> None:
        nearest_expiration = self.client.get_nearest_expiration(
            instrument.symbol, instrument.exchange, instrument.currency
        )
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
            lower_price,
            upper_price,
        )
        self.positions[instrument.symbol] = Position(
            lower_price,
            upper_price,
            call_contract,
            put_contract,
            order_quantity,
            nearest_expiration,
        )

    def check_closing_conditions(self, instrument: Instrument) -> bool:
        if instrument.symbol not in self.positions:
            nearest_expiration = self.client.get_nearest_expiration(
                instrument.symbol, instrument.exchange, instrument.currency
            )
            if self.client.has_open_position(instrument.symbol, nearest_expiration):
                self.recover_position(instrument, nearest_expiration)
            else:
                return False

        position = self.positions.get(instrument.symbol)
        if position is None:
            return False

        if self.client.is_contract_expired(position.call_contract):
            del self.positions[instrument.symbol]
            return False

        current_price = self.client.get_current_price(
            instrument.symbol, instrument.exchange, instrument.currency
        )
        return (
            current_price < position.lower_price or current_price > position.upper_price
        )

    def close_position(self, instrument: Instrument) -> None:
        position = self.positions.get(instrument.symbol)
        if position is None:
            return

        if self.client.has_open_position(instrument.symbol, position.expiration_date):
            self.client.neutralize_straddle(
                position.call_contract,
                position.put_contract,
                position.order_quantity,
            )
        del self.positions[instrument.symbol]

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
            for instrument in self.instruments:
                if self.check_opening_conditions(instrument):
                    self.open_position(instrument)
                if self.check_closing_conditions(instrument):
                    self.close_position(instrument)

            self.log_status()
            self.client.sleep(self.check_interval_seconds)
