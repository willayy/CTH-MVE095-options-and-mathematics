import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bayesian_inference import bayesian_inference
from src.ib_client import InteractiveBrokersClient

DEFAULT_TARGET_SPECIFICATIONS = [
    ("SPX", "CBOE", "USD"),
    ("DJ600", "EUREX", "EUR"),
]


def main(
    target_specifications: list[tuple[str, str, str]],
    host_address: str,
    port_number: int,
    client_identifier: int,
    fixed_capital_amount_dollars: float,
    credibility_interval_percentage: float,
    decay_factor: float,
    check_interval_seconds: float,
    maximum_checks: int,
) -> None:
    client = InteractiveBrokersClient(host_address, port_number, client_identifier)
    client.check_connection()

    active_positions: list[dict] = []

    for symbol, exchange, currency in target_specifications:
        client.download_data(symbol, exchange, currency)
        lower_price, upper_price = bayesian_inference(
            symbol, credibility_interval_percentage, decay_factor
        )

        call_contract, put_contract, order_quantity = client.create_straddle(
            symbol, exchange, currency, fixed_capital_amount_dollars
        )

        active_positions.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "currency": currency,
                "lower_price": lower_price,
                "upper_price": upper_price,
                "call_contract": call_contract,
                "put_contract": put_contract,
                "order_quantity": order_quantity,
                "is_active": True,
            }
        )

    check_index = 0

    while (
        any(position["is_active"] for position in active_positions)
        and check_index < maximum_checks
    ):
        client.sleep(check_interval_seconds)

        for position in active_positions:
            if not position["is_active"]:
                continue

            current_price = client.get_current_price(
                position["symbol"], position["exchange"], position["currency"]
            )

            if (
                current_price < position["lower_price"]
                or current_price > position["upper_price"]
            ):
                client.neutralize_straddle(
                    position["call_contract"],
                    position["put_contract"],
                    position["order_quantity"],
                )
                position["is_active"] = False

        check_index += 1

    client.disconnect()


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

    targets = DEFAULT_TARGET_SPECIFICATIONS
    if len(sys.argv) >= 4 and not sys.argv[1].startswith("-"):
        targets = [(sys.argv[1].upper(), sys.argv[2].upper(), sys.argv[3].upper())]
        if len(sys.argv) > 4:
            credibility_percentage_value = float(sys.argv[4])
        if len(sys.argv) > 5:
            fixed_capital_amount_value = float(sys.argv[5])

    main(
        targets,
        host_address_value,
        port_number_value,
        client_identifier_value,
        fixed_capital_amount_value,
        credibility_percentage_value,
        0.995,
        5.0,
        100,
    )
