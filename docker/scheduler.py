import os
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def execute_session(
    symbol: str,
    exchange: str,
    currency: str,
    host_address: str,
    port_number: int,
    client_identifier: int,
) -> None:
    print(
        f"[{datetime.now().isoformat()}] Launching trading session for {symbol} on {exchange}..."
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.trading_bot",
            symbol,
            exchange,
            currency,
            host_address,
            str(port_number),
            str(client_identifier),
        ],
        cwd=str(PROJECT_ROOT),
        check=True,
    )


def run_scheduler(
    host_address: str,
    port_number: int,
    client_identifier: int,
    poll_interval_seconds: float,
) -> None:
    european_timezone = ZoneInfo("Europe/Berlin")
    united_states_timezone = ZoneInfo("America/New_York")

    last_european_execution_date: date | None = None
    last_united_states_execution_date: date | None = None

    print(
        f"Scheduler started. Monitoring EU market open (09:00 CET) and US market open (09:30 ET)."
    )
    print(
        f"Connecting to Interactive Brokers at {host_address}:{port_number} with client ID {client_identifier}."
    )

    while True:
        current_time_european = datetime.now(european_timezone)
        current_time_united_states = datetime.now(united_states_timezone)

        # European Market (STOXX Europe 600 on EUREX): Monday - Friday at 09:00 CET
        is_european_weekday = current_time_european.weekday() < 5
        is_european_open_window = (
            current_time_european.hour == 9 and 0 <= current_time_european.minute <= 2
        )
        if (
            is_european_weekday
            and is_european_open_window
            and last_european_execution_date != current_time_european.date()
        ):
            last_european_execution_date = current_time_european.date()
            execute_session(
                "DJ600",
                "EUREX",
                "EUR",
                host_address,
                port_number,
                client_identifier,
            )

        # United States Market (S&P 500 on CBOE): Monday - Friday at 09:30 ET
        is_united_states_weekday = current_time_united_states.weekday() < 5
        is_united_states_open_window = (
            current_time_united_states.hour == 9
            and 30 <= current_time_united_states.minute <= 32
        )
        if (
            is_united_states_weekday
            and is_united_states_open_window
            and last_united_states_execution_date != current_time_united_states.date()
        ):
            last_united_states_execution_date = current_time_united_states.date()
            execute_session(
                "SPX",
                "CBOE",
                "USD",
                host_address,
                port_number,
                client_identifier,
            )

        time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    host_value = os.environ.get("INTERACTIVE_BROKERS_HOST", "127.0.0.1")
    port_value = int(os.environ.get("INTERACTIVE_BROKERS_PORT", "7497"))
    client_id_value = int(os.environ.get("INTERACTIVE_BROKERS_CLIENT_ID", "10"))

    if len(sys.argv) > 1 and sys.argv[1] == "--run-now":
        target_market = sys.argv[2].upper()
        if target_market in ("EU", "STOXX600", "DJ600"):
            execute_session(
                "DJ600", "EUREX", "EUR", host_value, port_value, client_id_value
            )
        elif target_market in ("US", "SPX", "SP500"):
            execute_session(
                "SPX", "CBOE", "USD", host_value, port_value, client_id_value
            )
    else:
        run_scheduler(host_value, port_value, client_id_value, 5.0)
