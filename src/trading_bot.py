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
    status: str
    loss: float


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
        self.active_positions: dict[str, Position] = {}

    def is_maturity_within_check_window(
        self,
        expiration_date: str,
    ) -> bool:
        expiration_time = datetime.strptime(expiration_date, "%Y%m%d").replace(
            hour=16, minute=0, second=0
        )
        seconds_until_expiration = (expiration_time - datetime.now()).total_seconds()
        return abs(seconds_until_expiration - 24.0 * 3600.0) <= 300.0

    def _create_position(
        self,
        instrument: Instrument,
        lower_price: float,
        upper_price: float,
        call_contract: Option,
        put_contract: Option,
        order_quantity: int,
        expiration_date: str,
    ) -> Position:
        return Position(
            instrument.symbol,
            instrument.exchange,
            instrument.currency,
            lower_price,
            upper_price,
            call_contract,
            put_contract,
            order_quantity,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            f"{expiration_date} 16:00",
            "OPEN",
            0.0,
        )

    def load_open_position_from_broker(
        self,
        instrument: Instrument,
        straddle_components: tuple[Option, Option, int],
    ) -> None:
        call_contract, put_contract, order_quantity = straddle_components
        active_position = self.active_positions.get(instrument.symbol)
        if active_position is not None and active_position.status == "OPEN":
            return
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
        expiration_date = getattr(call_contract, "lastTradeDateOrContractMonth", "")
        self.active_positions[instrument.symbol] = self._create_position(
            instrument,
            lower_price,
            upper_price,
            call_contract,
            put_contract,
            order_quantity,
            expiration_date,
        )

    def sync_positions_from_broker(self) -> None:
        for instrument in self.instruments:
            straddle_components = self.client.fetch_straddle_from_portfolio(
                instrument.symbol
            )
            if straddle_components is not None:
                self.load_open_position_from_broker(instrument, straddle_components)
            else:
                active_position = self.active_positions.get(instrument.symbol)
                if active_position is not None and active_position.status == "OPEN":
                    active_position.status = "NEUTRALIZED"

    def check_active_positions(self) -> None:
        for instrument in self.instruments:
            active_position = self.active_positions.get(instrument.symbol)
            if active_position is None or active_position.status != "OPEN":
                continue

            current_price = self.client.get_current_price(
                instrument.symbol, instrument.exchange, instrument.currency
            )
            if (
                current_price < active_position.lower_price
                or current_price > active_position.upper_price
            ):
                active_position.loss = self.client.get_position_profit_and_loss(
                    active_position.call_contract,
                    active_position.put_contract,
                )
                self.client.neutralize_straddle(
                    active_position.call_contract,
                    active_position.put_contract,
                    active_position.order_quantity,
                )
                active_position.status = "NEUTRALIZED"

    def maybe_open_new_positions(self) -> None:
        for instrument in self.instruments:
            active_position = self.active_positions.get(instrument.symbol)
            if active_position is not None and active_position.status == "OPEN":
                continue

            nearest_expiration = self.client.get_nearest_expiration(
                instrument.symbol, instrument.exchange, instrument.currency
            )
            if self.is_maturity_within_check_window(nearest_expiration):
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
                call_contract, put_contract, order_quantity = (
                    self.client.create_straddle(
                        instrument.symbol,
                        instrument.exchange,
                        instrument.currency,
                        nearest_expiration,
                        self.fixed_capital_amount_dollars,
                    )
                )
                self.active_positions[instrument.symbol] = self._create_position(
                    instrument,
                    lower_price,
                    upper_price,
                    call_contract,
                    put_contract,
                    order_quantity,
                    nearest_expiration,
                )

    def log_status(self) -> None:
        total_profit_and_loss = sum(
            self.client.get_position_profit_and_loss(
                position.call_contract, position.put_contract
            )
            if position.status == "OPEN"
            else position.loss
            for position in self.active_positions.values()
            if position.status in {"OPEN", "NEUTRALIZED"}
        )
        total_account_value = self.client.get_total_account_value()
        open_positions_count = sum(
            1
            for position in self.active_positions.values()
            if position.status == "OPEN"
        )
        profit_and_loss_sign = "+" if total_profit_and_loss >= 0.0 else ""
        print(
            f"Current Positions P/L: {profit_and_loss_sign}{total_profit_and_loss:.2f} | "
            f"Total Account Value: {total_account_value:.2f} | "
            f"Open Positions: {open_positions_count}",
            flush=True,
        )

    def run(self) -> None:
        self.client.check_connection()
        self.sync_positions_from_broker()
        self.log_status()
        while True:
            self.client.sleep(self.check_interval_seconds)
            self.sync_positions_from_broker()
            self.check_active_positions()
            self.maybe_open_new_positions()
            self.log_status()
