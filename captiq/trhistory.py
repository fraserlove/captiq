from collections.abc import Callable, Mapping, Iterable, Sequence, ValuesView
from typing import NamedTuple

from captiq.exceptions import AmbiguousTickerError
from captiq.table import Field, Format, Table
from captiq.transaction import Acquisition, Disposal, Dividend, Interest, Order, Transaction, Transfer
from captiq.types import ISIN, Ticker

def unique_and_sorted(transactions: Sequence[Transaction] | None) -> Sequence[Transaction]:
    """Remove duplicated transactions and sort them by timestamp."""
    return sorted(set(transactions or []), key=lambda tr: tr.timestamp)

def multifilter(filters: Sequence[Callable] | None, iterable: Iterable) -> Iterable:
    return iterable if not filters else filter(lambda x: all(f(x) for f in filters), iterable)

class Security(NamedTuple):
    isin: ISIN
    name: str = ''

class Transactions:
    def __init__(
        self,
        *,
        orders: Sequence[Order] | None = None,
        dividends: Sequence[Dividend] | None = None,
        transfers: Sequence[Transfer] | None = None,
        interest: Sequence[Interest] | None = None,
    ) -> None:
        self._orders = unique_and_sorted(orders)
        self._dividends = unique_and_sorted(dividends)
        self._transfers = unique_and_sorted(transfers)
        self._interest = unique_and_sorted(interest)
        self._securities: Mapping[ISIN, Security] = {}

    @property
    def orders(self) -> Sequence[Order]:
        return self._orders

    @property
    def dividends(self) -> Sequence[Dividend]:
        return self._dividends

    @property
    def transfers(self) -> Sequence[Transfer]:
        return self._transfers

    @property
    def interest(self) -> Sequence[Interest]:
        return self._interest

    @property
    def securities(self) -> ValuesView[Security]:
        return self._securities_map().values()

    def get_security_name(self, isin: ISIN) -> str | None:
        security = self._securities_map().get(isin)
        return security.name if security else None

    def get_ticker_isin(self, ticker: Ticker) -> ISIN | None:
        isins = set(o.isin for o in self._orders if o.ticker == ticker)

        match len(isins):
            case 0:
                return None
            case 1:
                return next(iter(isins))
            case _:
                raise AmbiguousTickerError(ticker)

    def get_orders_table(self, filters: Sequence[Callable] | None = None, acquisitions_only: bool = False, disposals_only: bool = False) -> Table:
        table = Table([
            Field('Date', Format.DATE),
            Field('Security Name'),
            Field('ISIN'),
            Field('Ticker'),
            Field('Quantity', Format.QUANTITY),
            Field('Price', Format.MONEY),
            Field('Cost', Format.MONEY, show_sum=True, visible=not disposals_only),
            Field('Proceeds', Format.MONEY, show_sum=True, visible=not acquisitions_only),
            Field('Fees', Format.MONEY, show_sum=True),
        ])

        transactions = list(multifilter(filters, self._orders))
        last_idx = len(transactions) - 1

        for idx, tr in enumerate(transactions):
            cost = tr.total if isinstance(tr, Acquisition) else None
            proceeds = tr.total if isinstance(tr, Disposal) else None
            if acquisitions_only and isinstance(tr, Disposal):
                continue
            if disposals_only and isinstance(tr, Acquisition):
                continue
            table.add_row([tr.date, tr.name, tr.isin, tr.ticker, tr.quantity, tr.price, cost, proceeds, tr.fees.total])
            
            if idx < last_idx and tr.tax_year() != transactions[idx + 1].tax_year():
                table.add_row([''] * len(table.field_names))

        return table

    def get_dividends_table(self, filters: Sequence[Callable] | None = None) -> Table:
        table = Table([
            Field('Date', Format.DATE),
            Field('Security Name'),
            Field('ISIN'),
            Field('Ticker'),
            Field('Net Amount', Format.MONEY, show_sum=True),
            Field('Widthheld Amount', Format.MONEY, show_sum=True),
        ])

        transactions = list(multifilter(filters, self._dividends))
        last_idx = len(transactions) - 1

        for idx, tr in enumerate(transactions):
            table.add_row([tr.date, tr.name, tr.isin, tr.ticker, tr.total, tr.withheld])
            
            if idx < last_idx and tr.tax_year() != transactions[idx + 1].tax_year():
                table.add_row([''] * len(table.field_names))

        return table

    def get_transfers_table(self, filters: Sequence[Callable] | None = None, deposits_only: bool = False, withdrawals_only: bool = False) -> Table:
        table = Table([
            Field('Date', Format.DATE),
            Field('Deposit', Format.MONEY, show_sum=True, visible=not withdrawals_only),
            Field('Withdrawal', Format.MONEY, show_sum=True, visible=not deposits_only),
        ])

        transactions = list(multifilter(filters, self._transfers))
        last_idx = len(transactions) - 1

        for idx, tr in enumerate(transactions):
            if tr.total.amount > 0:
                deposited, widthdrew = tr.total, None
                if deposits_only or not withdrawals_only:
                    table.add_row([tr.date, deposited, widthdrew])
            else:
                deposited, widthdrew = None, abs(tr.total)
                if withdrawals_only or not deposits_only:
                    table.add_row([tr.date, deposited, widthdrew])
            
            if idx < last_idx and tr.tax_year() != transactions[idx + 1].tax_year():
                table.add_row([''] * len(table.field_names))

        return table

    def get_interest_table(self, filters: Sequence[Callable] | None = None) -> Table:
        table = Table([
            Field('Date', Format.DATE),
            Field('Amount', Format.MONEY, show_sum=True),
        ])

        transactions = list(multifilter(filters, self._interest))
        last_idx = len(transactions) - 1

        for idx, tr in enumerate(transactions):
            table.add_row([tr.date, tr.total])
            
            if idx < last_idx and tr.tax_year() != transactions[idx + 1].tax_year():
                table.add_row([''] * len(table.field_names))

        return table

    def _securities_map(self) -> Mapping[ISIN, Security]:
        if not self._securities:
            self._securities = {
                o.isin: Security(o.isin, o.name)
                for o in sorted(self._orders, key=lambda o: o.name)
            }
        return self._securities
