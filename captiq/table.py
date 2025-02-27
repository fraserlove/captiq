import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import KW_ONLY, dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from functools import cache
from typing import Any, Mapping, Set

import prettytable
from moneyed import Currency, Money

from captiq.const import BASE_CURRENCY
from captiq.utils import boldify

# ANSI colors
RED = '\033[91m'
BLUE = '\033[92m'
RESET = '\033[0m'

class OutputFormat(str, Enum):
    TEXT = 'text'
    CSV = 'csv'
    JSON = 'json'
    HTML = 'html'


class Format(Enum):
    DATE = 1
    DECIMAL = 2
    QUANTITY = 3
    MONEY = 4


def string_format() -> Callable[[str, Any], str]:
    def _string_format(_field, val) -> str:
        if isinstance(val, str):
            return val
        return '-'
    return _string_format


def date_format(format: str) -> Callable[[str, Any], str]:
    def _date_format(_field, val) -> str:
        if isinstance(val, date):
            return val.strftime(format)
        return val
    return _date_format


def decimal_format(precision: int = 2) -> Callable[[str, Any], str]:
    def _decimal_format(_field, val) -> str:
        if isinstance(val, Decimal):
            return f'{val:.{precision}f}'
        elif isinstance(val, str):
            return val
        return '-'
    return _decimal_format


def money_format(show_currency: bool) -> Callable[[str, Any], str]:
    def _money_format(_field, val) -> str:
        if isinstance(val, Money):
            precision = currency_precision(val.currency)
            amount = val.amount
            colour = RED if amount < 0 else BLUE
            formatted_amount = f'{amount:.{precision}f}'
            if show_currency:
                return f'{colour}{formatted_amount} {val.currency}{RESET}' if colour else f'{formatted_amount} {val.currency}'
            return f'{colour}{formatted_amount}{RESET}' if colour else formatted_amount
        elif isinstance(val, str):
            return val
        return '-'
    return _money_format


@cache
def currency_precision(currency: Currency) -> int:
    return int(math.log10(currency.sub_unit))


@dataclass
class Field:
    name: str
    format: Format | None = None
    _: KW_ONLY
    visible: bool = True
    show_sum: bool = False


class Table(prettytable.PrettyTable):
    def __init__(self, fields: Sequence[Field], **kwargs) -> None:
        super().__init__([field.name for field in fields], **kwargs)

        # Table styling
        self.hrules = prettytable.ALL
        self.vrules = prettytable.FRAME
        self.padding_width = 1
        self.set_style(prettytable.SINGLE_BORDER)

        self.__fields = fields

    def __bool__(self) -> bool:
        return len(self.rows) > 0

    def get_csv_string(self, **kwargs) -> str:
        import csv
        import io

        options = self._get_options(kwargs)
        csv_options = {
            key: value for key, value in kwargs.items() if key not in options
        }
        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer, **csv_options)

        if options.get('header'):
            csv_writer.writerow(self._get_expanded_field_names())

        for row in self._get_expanded_rows(options):
            csv_writer.writerow(row)

        return csv_buffer.getvalue()

    def get_json_string(self, **kwargs) -> str:
        import json

        options = self._get_options(kwargs)
        json_options: Any = {'indent': 4, 'separators': (',', ': '), 'sort_keys': True}
        json_options.update(
            {key: value for key, value in kwargs.items() if key not in options}
        )
        objects: list[Any] = []

        field_names = self._get_expanded_field_names()

        if options.get('header'):
            objects.append(field_names)

        for row in self._get_expanded_rows(options):
            objects.append(dict(zip(field_names, row, strict=False)))

        return json.dumps(objects, **json_options)

    def to_string(self, format: OutputFormat = OutputFormat.TEXT, leading_nl: bool = True) -> str:
        if format in (OutputFormat.TEXT, OutputFormat.HTML):
            self._set_fields_names(bold_text=format == OutputFormat.TEXT)

        self._set_fields_format()

        if (
            self.rows
            and any(field.show_sum for field in self.__fields)
            and format in (OutputFormat.TEXT, OutputFormat.HTML)
        ):
            self._add_total_row()

        start_nl = '\n' if leading_nl else ''
        end_nl = '\n' if format == OutputFormat.TEXT else ''

        fields = [field.name for field in self.__fields if field.visible]

        kwargs: dict[str, Any] = {'fields': fields}
        if format == OutputFormat.JSON:
            kwargs['default'] = str

        table_str = self.get_formatted_string(format, **kwargs)

        if format == OutputFormat.CSV:
            table_str = table_str.rstrip()

        return f'{start_nl}{table_str}{end_nl}'

    def _set_fields_names(self, bold_text: bool) -> None:
        for field in self.__fields:
            if field.format == Format.MONEY:
                currencies = self._get_currencies(field.name)
                if len(currencies) == 0:
                    field.name += f' ({BASE_CURRENCY})'
                elif len(currencies) == 1:
                    currency = next(iter(currencies))
                    field.name += f' ({currency.code})'

            if bold_text:
                field.name = boldify(field.name)

        self.field_names = [field.name for field in self.__fields]

    def _set_fields_format(self) -> None:
        for field in self.__fields:
            match field.format:
                case Format.DATE:
                    self.custom_format[field.name] = date_format('%d/%m/%Y')
                    self.align[field.name] = 'l'
                case Format.DECIMAL:
                    self.custom_format[field.name] = decimal_format(2)
                    self.align[field.name] = 'r'
                case Format.QUANTITY:
                    self.custom_format[field.name] = decimal_format(8)
                    self.align[field.name] = 'r'
                case Format.MONEY:
                    self.custom_format[field.name] = money_format(show_currency=self._is_multicurrency(field.name))
                    self.align[field.name] = 'r'
                case _:
                    self.custom_format[field.name] = string_format()
                    self.align[field.name] = 'l'

    def _add_total_row(self) -> None:
        self.add_row([self._sum_field(field) if field.show_sum else '' for field in self.__fields])

    def _sum_field(self, field: Field) -> str:
        i = self._field_index(field.name)

        if field.format == Format.MONEY and self._is_multicurrency(field.name):
            totals: dict[Currency, Decimal] = defaultdict(Decimal)
            for row in self.rows:
                if row[i]:
                    precision = currency_precision(row[i].currency)
                    totals[row[i].currency] += round(row[i].amount, precision)

            formatter = money_format(show_currency=True)
            return '\n'.join(formatter('', Money(total, cur)) for cur, total in totals.items())

        total = sum(row[i].amount if isinstance(row[i], Money) else row[i] for row in self.rows if row[i])

        match field.format:
            case Format.MONEY:
                return money_format(show_currency=False)('', Money(total, BASE_CURRENCY))
            case Format.DECIMAL | Format.QUANTITY:
                return decimal_format()('', total)
            case _:
                return str(total)

    def _field_index(self, field_name: str) -> int:
        return next(i for i, field in enumerate(self.__fields) if field.name == field_name)

    def _get_currencies(self, field_name: str) -> Set[Currency]:
        i = self._field_index(field_name)
        return set(row[i].currency for row in self.rows if row[i] and isinstance(row[i], Money))

    def _is_multicurrency(self, field_name: str) -> bool:
        return len(self._get_currencies(field_name)) > 1

    def _get_expanded_field_names(self) -> Sequence[str]:
        field_names = []

        for field in self.__fields:
            field_names.append(field.name)
            if field.format == Format.MONEY:
                field_names.append(f'{field.name} (Currency)')

        return field_names

    def _get_expanded_rows(self, options: Mapping) -> Sequence[Sequence[Any]]:
        return [self._get_expanded_row(row) for row in self._get_rows(options)]

    def _get_expanded_row(self, row: Sequence[Any]) -> Sequence[Any]:
        expanded_row: list[Any] = []

        for i, field in enumerate(row):
            if self.__fields[i].format == Format.MONEY:
                if isinstance(field, Money):
                    expanded_row.extend([field.amount, field.currency])
                else:
                    expanded_row.extend(['-', None])
            else:
                expanded_row.append(field)

        return expanded_row