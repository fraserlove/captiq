import operator

from abc import ABC
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from functools import reduce
from typing import ClassVar, Self

from moneyed import Money

from captiq.fees import Fees
from captiq.providers import Split
from captiq.types import ISIN, Ticker, Year
from captiq.utils import date_to_tax_year

@dataclass(frozen=True)
class Transaction(ABC):
    timestamp: datetime
    total: Money
    tr_id: str | None = None
    notes: str | None = None

    @property
    def date(self) -> date:
        return self.timestamp.date()

    def tax_year(self) -> Year:
        return date_to_tax_year(self.date)


@dataclass(kw_only=True, frozen=True)
class Order(Transaction, ABC):
    number: int = field(default=0, compare=False)
    isin: ISIN
    ticker: Ticker | None = None
    name: str | None = None
    quantity: Decimal
    original_quantity: Decimal | None = None
    fees: Fees = field(default_factory=Fees)

    order_count: ClassVar[int] = 0

    def __post_init__(self) -> None:
        Order.order_count += 1
        object.__setattr__(self, 'number', Order.order_count)

    def split(self: Self, split_quantity: Decimal) -> tuple[Self, Self]:
        assert self.quantity >= split_quantity

        match_total = self.total / self.quantity * split_quantity
        match_quantity = split_quantity
        match_fees = self.fees / self.quantity * split_quantity

        remainder_total = self.total - match_total
        remainder_quantity = self.quantity - match_quantity
        remainder_fees = self.fees - match_fees

        match = replace(
            self,
            total=match_total,
            quantity=match_quantity,
            fees=match_fees,
            notes=f'Splitted from order {self.number}',
        )

        remainder = replace(
            self,
            total=remainder_total,
            quantity=remainder_quantity,
            fees=remainder_fees,
            notes=f'Splitted from order {self.number}',
        )

        return match, remainder

    @staticmethod
    def merge(*orders: 'Order') -> 'Order':
        assert len(orders) > 1

        isin = orders[0].isin
        assert all(order.isin == isin for order in orders)

        timestamp = orders[0].timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        total = reduce(operator.add, (order.total for order in orders))
        quantity = Decimal(sum(order.quantity for order in orders))
        fees = reduce(operator.add, (order.fees for order in orders))
        notes = f'Merged from orders {",".join(str(order.number) for order in orders)}'

        return replace(
            orders[0],
            timestamp=timestamp,
            total=total,
            quantity=quantity,
            fees=fees,
            notes=notes,
        )

    def adjust_quantity(self, splits: Sequence[Split]) -> 'Order':
        split_ratios = [s.ratio for s in splits if self.timestamp < s.date]

        if not split_ratios:
            return self

        quantity = reduce(operator.mul, [self.quantity, *split_ratios])
        notes = f'Adjusted from order {self.number} after applying the following split ratios: {", ".join(map(str, split_ratios))}'

        return replace(
            self,
            isin=self.isin,
            quantity=quantity,
            original_quantity=self.quantity,
            notes=notes,
        )


@dataclass(frozen=True)
class Acquisition(Order):
    @property
    def cost_before_fees(self) -> Money:
        return self.total - self.fees.total

    @property
    def price(self) -> Money:
        return self.cost_before_fees / self.quantity


@dataclass(frozen=True)
class Disposal(Order):
    @property
    def gross_proceeds(self) -> Money:
        return self.total + self.fees.total

    @property
    def price(self) -> Money:
        return self.gross_proceeds / self.quantity


@dataclass(kw_only=True, frozen=True)
class Dividend(Transaction):
    isin: ISIN
    name: str | None = None
    ticker: Ticker | None = None
    withheld: Money


@dataclass(frozen=True)
class Transfer(Transaction):
    pass


@dataclass(frozen=True)
class Interest(Transaction):
    pass
