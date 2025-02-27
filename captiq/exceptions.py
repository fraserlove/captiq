from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from captiq.types import ISIN, Ticker

class CaptiqError(Exception):
    pass

class ParseError(CaptiqError):
    def __init__(self, file: Path, row: Mapping[str, str], message: str) -> None:
        super().__init__(f'{file}: {message} on row {row}')

class TransactionTypeError(ParseError):
    def __init__(self, file: Path, row: Mapping[str, str], tr_type: str) -> None:
        super().__init__(file, row, f'Invalid type of transaction \'({tr_type})\'')

class CalculatedAmountError(ParseError):
    def __init__(self, file: Path, row: Mapping[str, str], csv_amount: Decimal, cal_amount: Decimal) -> None:
        super().__init__(file, row, f'Calculated amount ({cal_amount}) is different than the expected value ({csv_amount})')

class FeesError(ParseError):
    def __init__(self, file: Path, row: Mapping[str, str], fee_a: str, fee_b: str) -> None:
        super().__init__(file, row, f'Incompatible fees have a non-zero amount: \'{fee_a}\' and \'{fee_b}\'')

class OrderDateError(ParseError):
    def __init__(self, file: Path, row: Mapping[str, str]) -> None:
        super().__init__(file, row, 'Orders executed before 6 April of 2008 are not supported')

class IncompleteRecordsError(CaptiqError):
    def __init__(self, isin: ISIN, name: str) -> None:
        super().__init__(f'Records appear to be incomplete for {name} ({isin}): share quantity cannot be negative')

class AmbiguousTickerError(CaptiqError):
    def __init__(self, ticker: Ticker) -> None:
        super().__init__(f'Ticker {ticker} is ambiguous (used on different securities)')
