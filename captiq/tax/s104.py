from dataclasses import dataclass
from decimal import Decimal
from datetime import date
from moneyed import Money

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