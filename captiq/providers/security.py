from decimal import Decimal
from pathlib import Path
from typing import Protocol

import yfinance as yf
import yaml
from moneyed import Money

from captiq.providers.exceptions import DataProviderError
from captiq.providers.types import SecurityInfo, Split
from captiq.trhistory import TransactionHistory
from captiq.types import ISIN
from captiq.logging import logger

class SecurityProvider(Protocol):
    def fetch_info(self, isin: ISIN) -> SecurityInfo:
        pass

    def fetch_price(self, isin: ISIN) -> Money:
        pass

class YahooSecurityProvider(SecurityProvider):
    def fetch_info(self, isin: ISIN) -> SecurityInfo:
        try:
            yf_data = yf.Ticker(isin)
            name = yf_data.info['shortName']
        except Exception as ex:
            logger.debug(f'Exception from yfinance: {repr(ex)}')
            raise DataProviderError(f'Failed to fetch information for {isin}')

        splits = [Split(pd_date.to_pydatetime(), Decimal(ratio)) for pd_date, ratio in yf_data.splits.items()]
        return SecurityInfo(name, splits)

    def fetch_price(self, isin: ISIN) -> Money:
        try:
            yf_data = yf.Ticker(isin)
            price = Decimal(yf_data.info['currentPrice'])
            currency = yf_data.info['currency']
        except Exception as e:
            logger.debug(f'Exception from yfinance: {repr(e)}')
            raise DataProviderError(f'Failed to fetch last price for {isin}')

        if currency == 'GBp':
            currency = 'GBP'
            price *= Decimal('0.01')
        return Money(price, currency)

class SecurityData:
    def __init__(self, tr_hist: TransactionHistory, cache_file: Path, security_provider: SecurityProvider | None = None) -> None:
        self._security_provider = security_provider or YahooSecurityProvider()
        self._tr_hist = tr_hist
        self._cache_file = cache_file
        self._security_info: dict[ISIN, SecurityInfo] = {}
        self._security_price: dict[ISIN, Money] = {}
        
        self._initialise()

    def get_security_info(self, isin: ISIN) -> SecurityInfo:
        return self._security_info[isin]

    def get_security_price(self, isin) -> Money | None:
        if price := self._security_price.get(isin):
            return price

        if self._security_provider:
            try:
                price = self._security_provider.fetch_price(isin)
                logger.debug(f'Using {round(price.amount, 2)} {price.currency.code} share price for {isin}')
                self._security_price[isin] = price
            except DataProviderError as ex:
                logger.warning(str(ex))

        return price

    def _initialise(self) -> None:
        self._load_cache()

        orders = self._tr_hist.orders
        update_cache = False

        for isin, name in self._tr_hist.securities:
            if (security_info := self._security_info.get(isin)):
                last_order = next(o for o in reversed(orders) if o.isin == isin)

                if security_info.last_updated > last_order.timestamp:
                    logger.debug(f'Securities cache for {name} ({isin}) is up-to-date')
                    continue

            self._security_info[isin] = SecurityInfo(name, [])
            update_cache = True

            if self._security_provider:
                logger.info(f'Fetching information for {isin} - {name}')
                try:
                    self._security_info[isin] = self._security_provider.fetch_info(isin)
                except DataProviderError as ex:
                    logger.warning(str(ex))

        if update_cache:
            self._update_cache()

    def _load_cache(self) -> None:
        if self._cache_file.exists():
            logger.debug(f'Loading securities cache from {self._cache_file}')

            with self._cache_file.open('r') as file:
                if data := yaml.load(file, Loader=yaml.FullLoader):
                    self._security_info = data['securities']

    def _update_cache(self) -> None:
        logger.debug(f'{"Updating" if self._cache_file.exists() else "Creating"} securities cache on {self._cache_file}')
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        securities_info = dict(sorted(self._security_info.items()))
        data = {'securities': securities_info}

        with self._cache_file.open('w') as file:
            yaml.dump(data, file, sort_keys=False) 