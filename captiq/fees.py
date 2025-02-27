from dataclasses import dataclass
from decimal import Decimal

from moneyed import Currency, Money

from captiq.const import BASE_CURRENCY

def add(a: Money | None, b: Money | None) -> Money | None:
    return (a + b) if a and b else (a or b)

def sub(a: Money | None, b: Money | None) -> Money | None:
    return (a - b) if a and b else (a or (-b if b else None))

def mul(m: Money | None, v: Decimal) -> Money | None:
    return m * v if m else None

def div(m: Money | None, v: Decimal) -> Money | None:
    return m / v if m else None


@dataclass(frozen=True)
class Fees:
    '''Holds fees incurred on a share acquisition/disposal order'''

    # Commission/dealing charge fee
    charge: Money | None = None

    # Stamp Duty or Stamp Duty Reserve Tax fee
    stamp_duty: Money | None = None

    # Currency conversion fee
    forex: Money | None = None

    # Financial Industry Regulatory Authority fee
    finra: Money | None = None

    # Securities and Exchange Commission fee
    sec: Money | None = None

    # French Financial Transaction Tax
    french: Money | None = None

    currency: Currency = BASE_CURRENCY

    @property
    def total(self) -> Money:
        fees = [fee for fee in [self.charge, self.stamp_duty, self.forex, self.finra, self.sec, self.french] if fee]
        return sum(fees, start=self.currency.zero)

    def __add__(self: 'Fees', other: 'Fees') -> 'Fees':
        return Fees(
            charge=add(self.charge, other.charge),
            stamp_duty=add(self.stamp_duty, other.stamp_duty),
            forex=add(self.forex, other.forex),
            finra=add(self.finra, other.finra),
            sec=add(self.sec, other.sec),
            french=add(self.french, other.french),
            currency=self.currency,
        )

    def __sub__(self: 'Fees', other: 'Fees') -> 'Fees':
        return Fees(
            charge=sub(self.charge, other.charge),
            stamp_duty=sub(self.stamp_duty, other.stamp_duty),
            forex=sub(self.forex, other.forex),
            finra=sub(self.finra, other.finra),
            sec=sub(self.sec, other.sec),
            french=sub(self.french, other.french),
            currency=self.currency,
        )

    def __mul__(self: 'Fees', val: Decimal) -> 'Fees':
        return Fees(
            charge=mul(self.charge, val),
            stamp_duty=mul(self.stamp_duty, val),
            forex=mul(self.forex, val),
            finra=mul(self.finra, val),
            sec=mul(self.sec, val),
            french=mul(self.french, val),
            currency=self.currency,
        )

    def __truediv__(self: 'Fees', val: Decimal) -> 'Fees':
        return Fees(
            charge=div(self.charge, val),
            stamp_duty=div(self.stamp_duty, val),
            forex=div(self.forex, val),
            finra=div(self.finra, val),
            sec=div(self.sec, val),
            french=div(self.french, val),
            currency=self.currency,
        )
