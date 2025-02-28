from collections import defaultdict, namedtuple
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import TypeAlias

from moneyed import Money

from captiq.config import config
from captiq.const import BASE_CURRENCY
from captiq.exceptions import AmbiguousTickerError, IncompleteRecordsError, CaptiqError
from captiq.providers.security import SecurityData
from captiq.providers.fx import FXData
from captiq.table import Field, Format, Table
from captiq.tax import CapitalGain, Section104
from captiq.transaction import Acquisition, Disposal, Order
from captiq.trhistory import TransactionHistory
from captiq.types import ISIN, Ticker, Year
from captiq.logging import logger, raise_or_warn

GroupKey = namedtuple('GroupKey', ['isin', 'date', 'type'])
GroupDict: TypeAlias = Mapping[GroupKey, Sequence[Order]]

def same_day_match(ord1: Acquisition, ord2: Disposal) -> bool:
    return ord1.isin == ord2.isin and ord1.date == ord2.date

def thirty_days_match(ord1: Acquisition, ord2: Disposal) -> bool:
    return ord1.isin == ord2.isin and ord2.date < ord1.date <= ord2.date + timedelta(days=30)

class TaxCalculator:
    def __init__(self, tr_hist: TransactionHistory, security_data: SecurityData, fx_data: FXData) -> None:
        self._tr_hist = tr_hist
        self._security_data = security_data
        self._fx_data = fx_data
        self._acquisitions: dict[ISIN, list[Acquisition]] = defaultdict(list)
        self._disposals: dict[ISIN, list[Disposal]] = defaultdict(list)
        self._holdings: dict[ISIN, Section104] = {}
        self._capital_gains: dict[Year, list[CapitalGain]] = defaultdict(list)

    def capital_gains(self, tax_year: Year | None = None) -> Sequence[CapitalGain]:
        self._calculate_capital_gains()
        if tax_year:
            return self._capital_gains.get(tax_year, [])
        return [cg for cg_group in self._capital_gains.values() for cg in cg_group]

    def holding(self, isin: ISIN) -> Section104 | None:
        self._calculate_capital_gains()
        return self._holdings.get(isin)

    def get_capital_gains_table(self, tax_year: Year, ticker_filter: Ticker | None, gains_only: bool, losses_only: bool) -> Table:
        assert not (gains_only and losses_only)
        self._calculate_capital_gains()

        table = Table([
            Field('Disposal Date', Format.DATE),
            Field('Identification'),
            Field('Security Name'),
            Field('ISIN'),
            Field('Quantity', Format.QUANTITY),
            Field(f'Cost', Format.MONEY, show_sum=True),
            Field(f'Proceeds', Format.MONEY, show_sum=True),
            Field(f'Gain/loss', Format.MONEY, show_sum=True),
        ])

        for cg in self.capital_gains(tax_year):
            if ticker_filter and cg.disposal.ticker != ticker_filter:
                continue
            if gains_only and cg.gain < BASE_CURRENCY.zero:
                continue
            if losses_only and cg.gain > BASE_CURRENCY.zero:
                continue

            table.add_row([
                cg.disposal.date,
                cg.identification,
                cg.disposal.name,
                cg.disposal.isin,
                cg.quantity,
                cg.cost,
                cg.disposal.gross_proceeds,
                cg.gain,
            ])

        return table

    def get_holdings_table(self, ticker_filter: Ticker | None = None, show_gain: bool = False) -> Table:
        self._calculate_capital_gains()

        table = Table([
            Field('Security Name'),
            Field('ISIN'), 
            Field('Quantity', Format.QUANTITY),
            Field(f'Cost', Format.MONEY, show_sum=True),
            Field(f'Unrealised Proceeds', Format.MONEY, visible=show_gain, show_sum=True),
            Field(f'Unrealised Gain/Loss', Format.MONEY, visible=show_gain, show_sum=True),
            Field('Weight (%)', Format.DECIMAL, visible=show_gain and ticker_filter is None),
        ])

        holdings = []
        if not ticker_filter:
            holdings = sorted(self._holdings.items(), key=lambda x: x[1].cost, reverse=True)
        else:
            try:
                isin = self._tr_hist.get_ticker_isin(ticker_filter)
                if isin in self._holdings:
                    holdings = [(isin, self._holdings[isin])]
            except AmbiguousTickerError as e:
                logger.warning(e)

        market_values = ({isin: value for isin, holding in holdings 
                        if (value := self._get_holding_value(isin, holding))}
                        if show_gain else {})

        portfolio_value = sum(market_values.values())

        for isin, holding in holdings:
            gain: Money | None = None
            weight: Decimal | None = None

            if holding_value := market_values.get(isin):
                gain = holding_value - holding.cost
                weight = holding_value / portfolio_value * 100

            table.add_row([
                self._tr_hist.get_security_name(isin),
                isin,
                holding.quantity,
                holding.cost,
                holding_value or None,
                gain or None,
                weight or None,
            ])

        return table

    def disposal_years(self) -> Sequence[Year]:
        self._calculate_capital_gains()
        return list(self._capital_gains.keys())

    def _calculate_capital_gains(self) -> None:
        if self._capital_gains or self._holdings:
            return

        logger.debug('Calculating capital gains')
        self._validate_orders()

        # Normalise order quantities for any share splits/consolidations
        orders = self._normalise_orders(self._tr_hist.orders)
        if not config.include_fx_fees:
            orders = self._exclude_unallowable_costs(orders)

        # Aggregate orders that have the same isin, date and type.
        same_day = self._group_same_day(orders)

        for isin, name in self._tr_hist.securities:
            logger.debug(f'Calculating capital gains for {name} ({isin})')

            # Merge same-day orders by type into acquisitions/disposals
            self._merge_same_day(isin, same_day)

            # Match same-day disposals
            self._match_shares(isin, same_day_match)

            # Match bed & b. disposals
            self._match_shares(isin, thirty_days_match)

            # Match Section 104 disposals
            self._process_section104_disposals(isin)

        # Sort capital gains by disposal date for reporting
        for year, events in self._capital_gains.items():
            self._capital_gains[year] = sorted(events, key=lambda te: (te.disposal.timestamp, te.disposal.isin))

    def _validate_orders(self) -> None:
        for order in self._tr_hist.orders:
            if (order.total.currency != BASE_CURRENCY or order.fees.total.currency != BASE_CURRENCY):
                raise CaptiqError(f'Orders with a non-GBP total are not supported: {order}')

    def _normalise_orders(self, orders: Sequence[Order]) -> Sequence[Order]:
        return [o.adjust_quantity(self._security_data.get_security_info(o.isin).splits) for o in orders]

    def _exclude_unallowable_costs(self, orders: Sequence[Order]) -> Sequence[Order]:
        new_orders = []
        for order in orders:
            if not order.fees.forex:
                new_orders.append(order)
                continue

            total = (order.total - order.fees.forex if isinstance(order, Acquisition) else order.total + order.fees.forex)
            
            new_orders.append(replace(
                order,
                total=total,
                fees=replace(order.fees, forex=None),
                notes=f'FX fees removed from order {order.number}'
            ))
        return new_orders

    def _group_same_day(self, orders: Sequence[Order]) -> GroupDict:
        same_day = defaultdict(list)
        for o in orders:
            key = GroupKey(o.isin, o.date, type(o))
            same_day[key].append(o)
        return same_day

    def _merge_same_day(self, isin: ISIN, same_day: GroupDict) -> None:
        security_orders = (orders for key, orders in same_day.items() if key.isin == isin)
        for orders in security_orders:
            order = Order.merge(*orders) if len(orders) > 1 else orders[0]
            if isinstance(order, Acquisition):
                self._acquisitions[isin].append(order)
            elif isinstance(order, Disposal):
                self._disposals[isin].append(order)

            if len(orders) > 1:
                logger.debug(f'New \'same-day\' merged order: {order}')

    def _match_shares(self, isin: ISIN, match_fn: Callable[[Acquisition, Disposal], bool]) -> None:
        acquisits = self._acquisitions[isin]
        disposals = self._disposals[isin]
        matched: set[Order] = set()

        acq_idx = disp_idx = 0
        while disp_idx < len(disposals):
            if acq_idx == len(acquisits):
                acq_idx = 0
                disp_idx += 1
                continue

            acq = acquisits[acq_idx]
            disp = disposals[disp_idx]

            if not match_fn(acq, disp) or acq in matched:
                acq_idx += 1
                continue

            matched.update([acq, disp])

            if acq.quantity > disp.quantity:
                acq, acquisits[acq_idx] = acq.split(disp.quantity)
                acq_idx = 0
                disp_idx += 1
            elif disp.quantity > acq.quantity:
                disp, disposals[disp_idx] = disp.split(acq.quantity)
                acq_idx += 1
            else:
                acq_idx = 0
                disp_idx += 1

            self._capital_gains[disp.tax_year()].append(CapitalGain(disp, acq.total + disp.fees.total, acq.date))

        self._acquisitions[isin] = [o for o in acquisits if o not in matched]
        self._disposals[isin] = [o for o in disposals if o not in matched]

    def _process_section104_disposals(self, isin: ISIN) -> None:
        security_orders = sorted(
            [*self._acquisitions[isin], *self._disposals[isin]],
            key=lambda order: order.date
        )

        for order in security_orders:
            holding = self._holdings.get(isin)

            if isinstance(order, Acquisition):
                if holding:
                    holding.increase(order.date, order.quantity, order.total)
                else:
                    self._holdings[isin] = Section104(order.date, order.quantity, order.total)

            elif isinstance(order, Disposal):
                if not holding:
                    raise_or_warn(IncompleteRecordsError(isin, self._tr_hist.get_security_name(isin) or '?'))
                    logger.warning(f'Not calculating holding for {isin}')
                    break

                allowable_cost = holding.cost * order.quantity / holding.quantity
                holding.decrease(order.date, order.quantity, allowable_cost)

                if holding.quantity < 0.0:
                    raise_or_warn(IncompleteRecordsError(isin, self._tr_hist.get_security_name(isin) or '?'))
                    logger.warning(f'Not calculating holding for {isin}')
                    del self._holdings[isin]
                    break

                if holding.quantity == Decimal('0.0'):
                    del self._holdings[isin]

                self._capital_gains[order.tax_year()].append(CapitalGain(order, allowable_cost + order.fees.total))

    def _get_holding_value(self, isin: ISIN, holding: Section104) -> Money | None:
        if price := self._security_data.get_security_price(isin):
            if price_base_currency := self._fx_data.convert_money(price, BASE_CURRENCY):
                return holding.quantity * price_base_currency
        return None
