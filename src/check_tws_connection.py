"""Use this to check connection with TWS"""

from ib_async import IB, Stock


def main() -> None:
    ib = IB()
    ib.connect("127.0.0.1", 7497, clientId=1)

    spy = Stock("SPY", "SMART", "USD")
    ib.qualifyContracts(spy)

    bar = ib.reqHistoricalData(spy, "", "5 D", "1 day", "TRADES", True)[-1]
    print(f"SPY: ${bar.close:.2f} ({bar.date})")

    ib.disconnect()


if __name__ == "__main__":
    main()
