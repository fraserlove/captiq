from dataclasses import dataclass
from decimal import Decimal
from moneyed import Money
from datetime import date

from captiq.transaction import Disposal

@dataclass
class CapitalGain:
    disposal: Disposal
    cost: Money
    acquisition_date: date | None = None

    @property
    def gain(self) -> Money:
        return self.disposal.gross_proceeds - self.cost

    @property
    def quantity(self) -> Decimal:
        return self.disposal.original_quantity or self.disposal.quantity

    @property
    def identification(self) -> str:
        match self.acquisition_date:
            case None:
                return 'Section 104'
            case self.disposal.date:
                return 'Same day'
            case _:
                return f'Bed & B. ({self.acquisition_date})'

    def __str__(self) -> str:
        return (f'{self.disposal.date} {self.disposal.isin:<4} '
                f'quantity: {self.quantity}, cost: {self.cost}, '
                f'proceeds: {self.disposal.gross_proceeds}, '
                f'gain: {self.gain}, identification: {self.identification}')

@dataclass
class Section104:
    quantity: Decimal
    cost: Money

    def __init__(self, _date: date, quantity: Decimal, cost: Money):
        self.quantity = quantity
        self.cost = cost

    def increase(self, _date: date, quantity: Decimal, cost: Money) -> None:
        self.quantity += quantity
        self.cost += cost

    def decrease(self, _date: date, quantity: Decimal, cost: Money) -> None:
        self.quantity -= quantity
        self.cost -= cost