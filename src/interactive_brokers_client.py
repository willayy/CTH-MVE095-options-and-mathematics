import math
import sys
from pathlib import Path

from ib_async import IB, Index, MarketOrder, Option, util

DATA_DIRECTORY = Path(__file__).resolve().parent.parent / "data"


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
    destination_file = DATA_DIRECTORY / f"{symbol.lower()}_daily.csv"
    destination_file.parent.mkdir(parents=True, exist_ok=True)
    interactive_brokers = IB()
    check_connection(interactive_brokers, host, port, client_id)

    contract = Index(symbol, exchange, currency)
    interactive_brokers.qualifyContracts(contract)
    historical_bars = interactive_brokers.reqHistoricalData(
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
    interactive_brokers.disconnect()
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
