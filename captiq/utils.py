import datetime
from collections.abc import Callable, Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Final

from moneyed import GBP, Money

from captiq.config import config
from captiq.types import Year
from captiq.logging import logger

TAX_YEAR_START: Final = (4, 6) # (month, day)


def tax_year_period(tax_year: Year) -> tuple[datetime.date, datetime.date]:
    start = datetime.date(tax_year, *TAX_YEAR_START)
    end = datetime.date(tax_year + 1, *TAX_YEAR_START) - datetime.timedelta(days=1)
    return start, end


def date_to_tax_year(date: datetime.date) -> Year:
    year = date.year
    return Year(year if date >= datetime.date(year, *TAX_YEAR_START) else year - 1)


def tax_year_short_date(tax_year: Year) -> str:
    return f'{tax_year}/{(tax_year + 1) % 100}'


def tax_year_full_date(tax_year: Year) -> str:
    return f'6th April {tax_year} to 5th April {tax_year + 1}'


def multifilter(filters: Sequence[Callable] | None, iterable: Iterable) -> Iterable:
    return iterable if not filters else filter(lambda x: all(f(x) for f in filters), iterable)


def raise_or_warn(e: Exception) -> None:
    if config.strict:
        raise e
    logger.warning(e)


def read_decimal(val: str, default: Decimal = Decimal('0.0')) -> Decimal:
    return Decimal(val) if val.strip() else default


def read_sterling(amount: str | None) -> Money | None:
    return Money(amount, GBP) if amount and amount.strip() else None


def dict2str(d: Mapping[str, str]) -> str:
    return str({k: v for k, v in d.items() if v.strip()})


def boldify(text: str) -> str:
    return f'\033[1m{text}\033[0m'
