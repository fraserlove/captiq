import csv
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Final

from dateutil.parser import parse as parse_timestamp
from moneyed import Money

from captiq.exceptions import CalculatedAmountError, FeesError, OrderDateError, TransactionTypeError
from captiq.fees import Fees
from captiq.parsers.types import ParsingResult
from captiq.year import MIN_TIMESTAMP
from captiq.transaction import Acquisition, Disposal, Dividend, Interest, Order, Transfer
from captiq.types import ISIN, Ticker
from captiq.logging import logger, raise_or_warn

def read_decimal(val: str, default: Decimal = Decimal('0.0')) -> Decimal:
    return Decimal(val) if val.strip() else default

def read_money(row: Mapping[str, str], field: str) -> Money | None:
    if amount := row.get(field, '').strip():
        return Money(amount=amount, currency=row[f'Currency ({field})'])
    return None

class Trading212Parser:

    REQUIRED_FIELDS: Final = (
        'Action',
        'Time',
        'ISIN',
        'Ticker',
        'Name',
        'No. of shares',
        'Price / share',
        'Currency (Price / share)',
        'Exchange rate',
        'Total',
        'Currency (Total)',
    )

    DIVIDEND_FIELDS: Final = (
        'Withholding tax',
        'Currency (Withholding tax)',
    )

    FEE_FIELDS: Final = (
        'Charge amount',
        'Currency (Charge amount)',
        'Finra fee',
        'Currency (Finra fee)',
        'Stamp duty reserve tax',
        'Currency (Stamp duty reserve tax)',
        'Transaction fee',
        'Currency (Transaction fee)',
        'French transaction tax',
        'Currency (French transaction tax)',
        'Currency conversion fee',
        'Currency (Currency conversion fee)',
    )

    IGNORED_FIELDS: Final = (
        'ID',
        'Notes',
        'Result',
        'Currency (Result)',
        'Deposit fee',
        'Currency (Deposit fee)',
        'Merchant name',
        'Merchant category',
        'Currency conversion from amount',
        'Currency (Currency conversion from amount)',
        'Currency conversion to amount',
        'Currency (Currency conversion to amount)',
    )

    FIELDS: Final = (*REQUIRED_FIELDS, *DIVIDEND_FIELDS, *FEE_FIELDS, *IGNORED_FIELDS)

    ORDER_FUNCTIONS: Final = {
        'Market buy': '_parse_order',
        'Limit buy': '_parse_order', 
        'Stop buy': '_parse_order',
        'Market sell': '_parse_order',
        'Limit sell': '_parse_order',
        'Stop sell': '_parse_order',
    }

    DIVIDEND_FUNCTIONS: Final = {
        'Dividend (Ordinary)': '_parse_dividend',
        'Dividend (Dividend)': '_parse_dividend',
        'Dividend (Dividends paid by us corporations)': '_parse_dividend',
        'Dividend (Dividends paid by foreign corporations)': '_parse_dividend',
        'Dividend (Return of capital non us)': None,
    }

    TRANSFER_FUNCTIONS: Final = {
        'Deposit': '_parse_transfer',
        'Withdrawal': '_parse_transfer',
    }

    INTEREST_FUNCTIONS: Final = {
        'Interest on cash': '_parse_interest',
        'Lending interest': '_parse_interest',
    }

    IGNORED_FUNCTIONS: Final = {
        'Result adjustment': None,
        'Dividend adjustment': None,
        'Card debit': None,
        'Spending cashback': None,
        'Currency conversion': None,
        'New card cost': None,
    }

    PARSE_FUNCTIONS: Final = {**ORDER_FUNCTIONS, **DIVIDEND_FUNCTIONS, **TRANSFER_FUNCTIONS, **INTEREST_FUNCTIONS, **IGNORED_FUNCTIONS}

    def __init__(self, csv_file: Path) -> None:
        self._csv_file = csv_file
        self._orders: list[Order] = []
        self._dividends: list[Dividend] = []
        self._transfers: list[Transfer] = []
        self._interest: list[Interest] = []

    def can_parse(self) -> bool:
        with self._csv_file.open(encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames or []

        # Check all default fields are present
        for field in self.REQUIRED_FIELDS:
            if field not in fieldnames:
                logger.error(f'Required field \'{field}\' not present in {self._csv_file}')
                return False

        # Check for unknown fields
        for field in fieldnames:
            if field not in self.FIELDS:
                logger.warning(f'Unknown field \'{field}\' in {self._csv_file}')

        return True

    def parse(self) -> ParsingResult:
        with self._csv_file.open(encoding='utf-8') as file:
            for row in csv.DictReader(file):
                tr_type = row['Action']
                tr_id = row['ID']

                if tr_type not in self.PARSE_FUNCTIONS:
                    raise_or_warn(TransactionTypeError(self._csv_file, row, tr_type))
                    continue

                if not (fn_name := self.PARSE_FUNCTIONS.get(tr_type)):
                    continue

                timestamp = parse_timestamp(row['Time'])
                if not timestamp.tzinfo:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)

                    if total := read_money(row, 'Total'):
                        fn = getattr(self, fn_name)
                        fn(row, tr_type, timestamp, tr_id, total)

        return ParsingResult(self._orders, self._dividends, self._transfers, self._interest)

    def _parse_order(self, row: Mapping[str, str], tr_type: str, timestamp: datetime, tr_id: str, total: Money) -> None:
        isin = ISIN(row['ISIN'])
        ticker = Ticker(row['Ticker'])
        name = row['Name'] 
        quantity = Decimal(row['No. of shares'])
        price_share = Decimal(row['Price / share'])
        forex_rate = read_decimal(row['Exchange rate'], default=Decimal('1.0'))

        # Possible fees
        charge = read_money(row, 'Charge amount')
        stamp_duty = read_money(row, 'Stamp duty reserve tax')
        forex_fee = read_money(row, 'Currency conversion fee')
        sec_fee = read_money(row, 'Transaction fee')
        finra_fee = read_money(row, 'Finra fee')
        french_tax = read_money(row, 'French transaction tax')

        if timestamp < MIN_TIMESTAMP:
            raise OrderDateError(self._csv_file, row)

        # Ensure only one type of exchange fee is present
        fees = {
            'Stamp duty reserve tax': stamp_duty,
            'Finra fee': finra_fee,
            'Transaction fee': sec_fee,
            'French transaction tax': french_tax
        }
        present_fees = [(name, fee) for name, fee in fees.items() if fee]
        if len(present_fees) > 1:
            raise FeesError(self._csv_file, row, present_fees[0][0], present_fees[1][0])

        fees = Fees(charge=charge, stamp_duty=stamp_duty, forex=forex_fee, finra=finra_fee, sec=sec_fee, french=french_tax, currency=total.currency)

        is_buy = tr_type in ('Market buy', 'Limit buy', 'Stop buy')
        order_class = Acquisition if is_buy else Disposal
        fees_total = fees.total if is_buy else -fees.total

        tx_amount = Money(price_share * quantity / forex_rate, total.currency)
        tx_total = (tx_amount + fees_total).round(2)

        # Validate the calculated total against the total column
        if abs(tx_total - total).amount > Decimal('0.01'):
            raise_or_warn(CalculatedAmountError(self._csv_file, row, total.amount, tx_total.amount))

        self._orders.append(order_class(timestamp, isin=isin, ticker=ticker, name=name, total=total, quantity=quantity, fees=fees, tr_id=tr_id))

        logger.debug(f'Parsed row {str(row)} as {self._orders[-1]}\n')

    def _parse_dividend(self, row: Mapping[str, str], tr_type: str, timestamp: datetime, tr_id: str, total: Money) -> None:
        isin = ISIN(row['ISIN'])
        ticker = Ticker(row['Ticker'])
        name = row['Name']
        withheld = read_money(row, 'Withholding tax')

        self._dividends.append(Dividend(timestamp, isin=isin, ticker=ticker, name=name, total=total, withheld=withheld, tr_id=tr_id))

        logger.debug(f'Parsed row {str(row)} as {self._dividends[-1]}\n')

    def _parse_transfer(self, row: Mapping[str, str], tr_type: str, timestamp: datetime, tr_id: str, total: Money) -> None:
        if tr_type == 'Withdrawal':
            total = -abs(total)

        self._transfers.append(Transfer(timestamp, tr_id=tr_id, total=total))

        logger.debug(f'Parsed row {str(row)} as {self._transfers[-1]}\n')

    def _parse_interest(self, row: Mapping[str, str], tr_type: str, timestamp: datetime, tr_id: str, total: Money) -> None:
        self._interest.append(Interest(timestamp, tr_id=tr_id, total=total))

        logger.debug(f'Parsed row {str(row)} as {self._interest[-1]}\n')
