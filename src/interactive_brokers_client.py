import math
import sys
from pathlib import Path

from ib_async import IB, Index, MarketOrder, Option, util

DATA_DIRECTORY = Path(__file__).resolve().parent.parent / "data"


class InteractiveBrokersClient:
    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.interactive_brokers = IB()

    def check_connection(self) -> None:
        self.interactive_brokers.connect(self.host, self.port, clientId=self.client_id)
        if not self.interactive_brokers.isConnected():
            raise ConnectionError("Failed to connect to Interactive Brokers.")

    def disconnect(self) -> None:
        self.interactive_brokers.disconnect()

    def sleep(self, seconds: float) -> None:
        self.interactive_brokers.sleep(seconds)

    def download_data(
        self,
        symbol: str,
        exchange: str,
        currency: str,
    ) -> Path:
        destination_file = DATA_DIRECTORY / f"{symbol.lower()}_daily.csv"
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        contract = Index(symbol, exchange, currency)
        self.interactive_brokers.qualifyContracts(contract)
        historical_bars = self.interactive_brokers.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="10 Y",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        data_frame = util.df(historical_bars)
        data_frame.to_csv(destination_file, index=False)
        return destination_file

    def get_current_price(
        self,
        symbol: str,
        exchange: str,
        currency: str,
    ) -> float:
        contract = Index(symbol, exchange, currency)
        self.interactive_brokers.qualifyContracts(contract)
        market_data = self.interactive_brokers.reqMktData(contract, "", False, False)
        current_price = market_data.marketPrice()
        if math.isnan(current_price) or current_price <= 0.0:
            current_price = market_data.close
        return float(current_price)

    def create_straddle(
        self,
        symbol: str,
        exchange: str,
        currency: str,
        order_quantity: int,
    ) -> tuple[Option, Option]:
        underlying_contract = Index(symbol, exchange, currency)
        self.interactive_brokers.qualifyContracts(underlying_contract)
        chains = self.interactive_brokers.reqSecDefOptParams(
            underlying_contract.symbol,
            "",
            underlying_contract.secType,
            underlying_contract.conId,
        )
        selected_chain = chains[0]
        nearest_expiration = sorted(selected_chain.expirations)[0]

        market_data = self.interactive_brokers.reqMktData(
            underlying_contract, "", False, False
        )
        self.interactive_brokers.sleep(1.0)
        current_price = market_data.marketPrice()
        if math.isnan(current_price) or current_price <= 0.0:
            current_price = market_data.close

        closest_strike = min(
            selected_chain.strikes,
            key=lambda strike_price: abs(strike_price - current_price),
        )

        call_contract = Option(
            underlying_contract.symbol,
            nearest_expiration,
            closest_strike,
            "C",
            selected_chain.exchange,
            currency=underlying_contract.currency,
        )
        put_contract = Option(
            underlying_contract.symbol,
            nearest_expiration,
            closest_strike,
            "P",
            selected_chain.exchange,
            currency=underlying_contract.currency,
        )
        self.interactive_brokers.qualifyContracts(call_contract, put_contract)

        self.interactive_brokers.placeOrder(
            call_contract, MarketOrder("SELL", order_quantity)
        )
        self.interactive_brokers.placeOrder(
            put_contract, MarketOrder("SELL", order_quantity)
        )
        return call_contract, put_contract

    def neutralize_straddle(
        self,
        call_contract: Option,
        put_contract: Option,
        order_quantity: int,
    ) -> None:
        self.interactive_brokers.placeOrder(
            call_contract, MarketOrder("BUY", order_quantity)
        )
        self.interactive_brokers.placeOrder(
            put_contract, MarketOrder("BUY", order_quantity)
        )


IBClient = InteractiveBrokersClient


def check_connection(
    interactive_brokers: IB,
    host: str,
    port: int,
    client_id: int,
) -> None:
    interactive_brokers.connect(host, port, clientId=client_id)
    if not interactive_brokers.isConnected():
        raise ConnectionError("Failed to connect to Interactive Brokers.")


def download_data(
    symbol: str,
    exchange: str,
    currency: str,
    host: str,
    port: int,
    client_id: int,
) -> Path:
    client = InteractiveBrokersClient(host, port, client_id)
    client.check_connection()
    destination_file = client.download_data(symbol, exchange, currency)
    client.disconnect()
    return destination_file


def create_straddle(
    interactive_brokers: IB,
    underlying_contract: Index,
    order_quantity: int,
) -> tuple[Option, Option]:
    chains = interactive_brokers.reqSecDefOptParams(
        underlying_contract.symbol,
        "",
        underlying_contract.secType,
        underlying_contract.conId,
    )
    selected_chain = chains[0]
    nearest_expiration = sorted(selected_chain.expirations)[0]

    market_data = interactive_brokers.reqMktData(underlying_contract, "", False, False)
    interactive_brokers.sleep(1.0)
    current_price = market_data.marketPrice()
    if math.isnan(current_price) or current_price <= 0.0:
        current_price = market_data.close

    closest_strike = min(
        selected_chain.strikes,
        key=lambda strike_price: abs(strike_price - current_price),
    )

    call_contract = Option(
        underlying_contract.symbol,
        nearest_expiration,
        closest_strike,
        "C",
        selected_chain.exchange,
        currency=underlying_contract.currency,
    )
    put_contract = Option(
        underlying_contract.symbol,
        nearest_expiration,
        closest_strike,
        "P",
        selected_chain.exchange,
        currency=underlying_contract.currency,
    )
    interactive_brokers.qualifyContracts(call_contract, put_contract)

    interactive_brokers.placeOrder(call_contract, MarketOrder("SELL", order_quantity))
    interactive_brokers.placeOrder(put_contract, MarketOrder("SELL", order_quantity))
    return call_contract, put_contract


def neutralize_straddle(
    interactive_brokers: IB,
    call_contract: Option,
    put_contract: Option,
    order_quantity: int,
) -> None:
    interactive_brokers.placeOrder(call_contract, MarketOrder("BUY", order_quantity))
    interactive_brokers.placeOrder(put_contract, MarketOrder("BUY", order_quantity))


if __name__ == "__main__":
    download_data(
        sys.argv[1].upper(),
        sys.argv[2].upper(),
        sys.argv[3].upper(),
        "127.0.0.1",
        7497,
        10,
    )
