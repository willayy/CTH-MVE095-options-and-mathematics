import math
from datetime import datetime
from pathlib import Path
from typing import cast

import ib_async.wrapper
from ib_async import IB, Index, MarketOrder, Option, util

if hasattr(ib_async.wrapper, "warningCodes"):
    ib_async.wrapper.warningCodes = ib_async.wrapper.warningCodes | {10349}

DATA_DIRECTORY = Path(__file__).resolve().parent.parent / "data"


class InteractiveBrokersClient:
    def __init__(
        self,
        host: str,
        port: int,
        client_identifier: int,
    ) -> None:
        self.host = host
        self.port = port
        self.client_identifier = client_identifier
        self.interactive_brokers = IB()

    def check_connection(self) -> None:
        self.interactive_brokers.connect(
            self.host, self.port, clientId=self.client_identifier
        )
        if not self.interactive_brokers.isConnected():
            raise ConnectionError("Failed to connect to Interactive Brokers.")
        self.interactive_brokers.reqMarketDataType(3)

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
        self.interactive_brokers.sleep(1.0)
        for price in (market_data.marketPrice(), market_data.close, market_data.last):
            if not math.isnan(price) and price > 0.0:
                return float(price)
        return float("nan")

    def get_nearest_expiration(
        self,
        symbol: str,
        exchange: str,
        currency: str,
    ) -> str:
        underlying_contract = Index(symbol, exchange, currency)
        self.interactive_brokers.qualifyContracts(underlying_contract)
        chains = self.interactive_brokers.reqSecDefOptParams(
            underlying_contract.symbol,
            "",
            underlying_contract.secType,
            underlying_contract.conId,
        )
        now = datetime.now()
        all_expirations = [
            expiration for chain in chains for expiration in chain.expirations
        ]
        future_expirations = [
            expiration
            for expiration in all_expirations
            if datetime.strptime(expiration, "%Y%m%d").replace(
                hour=16, minute=0, second=0
            )
            > now
        ]
        return min(future_expirations) if future_expirations else min(all_expirations)

    def create_straddle(
        self,
        symbol: str,
        exchange: str,
        currency: str,
        expiration_date_string: str,
        fixed_capital_amount_dollars: float,
    ) -> tuple[Option, Option, int]:
        underlying_contract = Index(symbol, exchange, currency)
        self.interactive_brokers.qualifyContracts(underlying_contract)
        chains = self.interactive_brokers.reqSecDefOptParams(
            underlying_contract.symbol,
            "",
            underlying_contract.secType,
            underlying_contract.conId,
        )
        matching_chains = [
            chain for chain in chains if expiration_date_string in chain.expirations
        ]
        selected_chain = next(
            (
                chain
                for chain in matching_chains
                if chain.exchange == underlying_contract.exchange
            ),
            matching_chains[0] if matching_chains else chains[0],
        )

        current_price = self.get_current_price(symbol, exchange, currency)

        closest_strike = min(
            selected_chain.strikes,
            key=lambda strike_price: abs(strike_price - current_price),
        )

        call_contract = Option(
            underlying_contract.symbol,
            expiration_date_string,
            closest_strike,
            "C",
            underlying_contract.exchange,
            currency=underlying_contract.currency,
            tradingClass=selected_chain.tradingClass,
        )
        put_contract = Option(
            underlying_contract.symbol,
            expiration_date_string,
            closest_strike,
            "P",
            underlying_contract.exchange,
            currency=underlying_contract.currency,
            tradingClass=selected_chain.tradingClass,
        )
        self.interactive_brokers.qualifyContracts(call_contract, put_contract)

        multiplier = float(getattr(call_contract, "multiplier", 100.0) or 100.0)
        notional_value = closest_strike * multiplier
        if notional_value <= 0.0:
            raise ValueError(
                f"Contract notional value must be positive, got {notional_value}."
            )
        order_quantity = max(1, int(fixed_capital_amount_dollars / notional_value))

        self.interactive_brokers.placeOrder(
            call_contract, MarketOrder("SELL", order_quantity, tif="DAY")
        )
        self.interactive_brokers.placeOrder(
            put_contract, MarketOrder("SELL", order_quantity, tif="DAY")
        )
        return call_contract, put_contract, order_quantity

    def neutralize_straddle(
        self,
        call_contract: Option,
        put_contract: Option,
        order_quantity: int,
    ) -> None:
        self.interactive_brokers.placeOrder(
            call_contract, MarketOrder("BUY", order_quantity, tif="DAY")
        )
        self.interactive_brokers.placeOrder(
            put_contract, MarketOrder("BUY", order_quantity, tif="DAY")
        )

    def has_open_position(
        self,
        symbol: str,
        expiration_date_string: str,
    ) -> bool:
        return any(
            getattr(item.contract, "symbol", "") == symbol
            and getattr(item.contract, "lastTradeDateOrContractMonth", "")
            == expiration_date_string
            and item.position < 0
            for item in self.interactive_brokers.portfolio()
        )

    def find_portfolio_option(
        self,
        symbol: str,
        expiration_date_string: str,
        option_right: str,
    ) -> Option | None:
        return next(
            (
                cast(Option, item.contract)
                for item in self.interactive_brokers.portfolio()
                if getattr(item.contract, "symbol", "") == symbol
                and getattr(item.contract, "lastTradeDateOrContractMonth", "")
                == expiration_date_string
                and item.position < 0
                and getattr(item.contract, "right", "") == option_right
            ),
            None,
        )

    def fetch_open_straddle(
        self,
        symbol: str,
        expiration_date_string: str,
    ) -> tuple[Option, Option, int] | None:
        call_contract = self.find_portfolio_option(symbol, expiration_date_string, "C")
        put_contract = self.find_portfolio_option(symbol, expiration_date_string, "P")
        if call_contract is None or put_contract is None:
            return None
        order_quantity = next(
            (
                int(abs(item.position))
                for item in self.interactive_brokers.portfolio()
                if item.contract.conId == call_contract.conId
            ),
            0,
        )
        return call_contract, put_contract, order_quantity

    def get_total_unrealized_profit_and_loss(self) -> float:
        return sum(
            float(item.unrealizedPNL) for item in self.interactive_brokers.portfolio()
        )

    def get_open_straddles_count(self) -> int:
        return sum(
            1
            for item in self.interactive_brokers.portfolio()
            if item.position < 0 and getattr(item.contract, "right", "") == "C"
        )

    def get_total_account_value(self) -> float:
        return next(
            (
                float(account_value.value)
                for account_value in self.interactive_brokers.accountValues()
                if account_value.tag == "NetLiquidation"
            ),
            0.0,
        )
