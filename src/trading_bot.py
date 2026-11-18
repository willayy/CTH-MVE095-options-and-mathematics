import math
import sys
from pathlib import Path

from ib_async import IB, Index

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bayesian_inference import bayesian_inference
from src.ib_client import (
    check_connection,
    create_straddle,
    download_data,
    neutralize_straddle,
)


def condition(
    current_price: float,
    lower_price: float,
    upper_price: float,
) -> bool:
    return current_price < lower_price or current_price > upper_price


def main(
    symbol: str,
    exchange: str,
    currency: str,
    host: str,
    port: int,
    client_id: int,
    coverage_probability: float,
    decay_factor: float,
    order_quantity: int,
    check_interval_seconds: float,
    maximum_checks: int,
) -> None:
    interactive_brokers = IB()
    check_connection(interactive_brokers, host, port, client_id)

    download_data(symbol, exchange, currency, host, port, client_id)
    
    lower_price, upper_price = bayesian_inference(
        symbol, coverage_probability, decay_factor
    )

    underlying_contract = Index(symbol, exchange, currency)
    
    interactive_brokers.qualifyContracts(underlying_contract)

    call_contract, put_contract = create_straddle(
        interactive_brokers, underlying_contract, order_quantity
    )

    market_data = interactive_brokers.reqMktData(underlying_contract, "", False, False)
    
    check_index = 0
    
    position_active = True

    while position_active and check_index < maximum_checks:
        
        interactive_brokers.sleep(check_interval_seconds)
        
        current_price = market_data.marketPrice()
        
        if math.isnan(current_price) or current_price <= 0.0:
            current_price = market_data.close

        if condition(current_price, lower_price, upper_price):
            
            neutralize_straddle(
                interactive_brokers,
                call_contract,
                put_contract,
                order_quantity,
            )
            
            position_active = False

        check_index += 1

    interactive_brokers.disconnect()


if __name__ == "__main__":
    main(
        sys.argv[1].upper(),
        sys.argv[2].upper(),
        sys.argv[3].upper(),
        "127.0.0.1",
        7497,
        10,
        0.95,
        0.995,
        1,
        5.0,
        100,
    )
