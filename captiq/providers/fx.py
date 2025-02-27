from decimal import Decimal
from typing import Protocol

import yfinance as yf
from moneyed import Currency, Money

from captiq.providers.exceptions import DataProviderError
from captiq.logging import logger

class FXProvider(Protocol):
    def fetch_exchange_rate(self, currency_from: Currency, currency_to: Currency) -> Decimal:
        pass

class YahooFXProvider(FXProvider):
    def fetch_exchange_rate(self, currency_from: Currency, currency_to: Currency) -> Decimal:
        try:
            yf_data = yf.Ticker(f'{currency_from.code}{currency_to.code}=X')
            fx_rate = Decimal(yf_data.info['bid'])
        except Exception as e:
            logger.debug(f'Exception from yfinance: {repr(e)}')
            raise DataProviderError(f'Failed to fetch exchange rate for {currency_from.name} ({currency_from.code}) to {currency_to.name} ({currency_to.code})')

        return fx_rate 

class FXData:
    def __init__(self, fx_provider: FXProvider | None = None) -> None:
        self._fx_provider = fx_provider or YahooFXProvider()
        self._exchange_rates: dict[tuple[Currency, Currency], Decimal] = {}

    def get_fx_rate(self, currency_from: Currency, currency_to: Currency) -> Decimal | None:
        if fx_rate := self._exchange_rates.get((currency_from, currency_to)):
            return fx_rate

        if self._fx_provider:
            try:
                fx_rate = self._fx_provider.fetch_exchange_rate(currency_from, currency_to)
                inv_fx_rate = Decimal('1.0') / fx_rate
                logger.debug(f'FX: {fx_rate:.5f} {currency_from.code}/{currency_to.code} (inv: {inv_fx_rate:.5f})')
                self._exchange_rates[(currency_from), (currency_to)] = fx_rate
                self._exchange_rates[(currency_to), (currency_from)] = inv_fx_rate
            except DataProviderError as ex:
                logger.warning(str(ex))

        return fx_rate

    def convert_money(self, money: Money, currency: Currency) -> Money | None:
        if money.currency == currency:
            return money

        if fx_rate := self.get_fx_rate(money.currency, currency):
            return Money(money.amount * fx_rate, currency)

        return None 