import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bayesian_inference import bayesian_inference
from src.ib_client import InteractiveBrokersClient


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
    client = InteractiveBrokersClient(host, port, client_id)
    client.check_connection()

    client.download_data(symbol, exchange, currency)
    lower_price, upper_price = bayesian_inference(
        symbol, coverage_probability, decay_factor
    )

    call_contract, put_contract = client.create_straddle(
        symbol, exchange, currency, order_quantity
    )

    check_index = 0
    position_active = True

    while position_active and check_index < maximum_checks:
        client.sleep(check_interval_seconds)
        current_price = client.get_current_price(symbol, exchange, currency)

        if condition(current_price, lower_price, upper_price):
            client.neutralize_straddle(
                call_contract,
                put_contract,
                order_quantity,
            )
            position_active = False

        check_index += 1

    client.disconnect()


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
