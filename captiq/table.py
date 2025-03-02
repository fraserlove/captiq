import math
import prettytable
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Set
from moneyed import Currency, Money

from captiq import BASE_CURRENCY
from captiq.logging import BOLD, RESET, BLUE, RED

class Format(Enum):
    DATE = 1
    DECIMAL = 2
    QUANTITY = 3
    MONEY = 4

@dataclass
class Field:
    name: str
    format: Format | None = None
    visible: bool = True
    show_sum: bool = False

def get_precision(currency: Currency) -> int:
    ''' Return the number of decimal places for a currency. '''
    return int(math.log10(currency.sub_unit))

def boldify(text: str) -> str:
    ''' Format text with bold. '''
    return f'{BOLD}{text}{RESET}'

def colourify(money: Money, show_currency: bool = True) -> str:
    ''' Format Money with colour (red for negative, blue for positive). '''
    precision = get_precision(money.currency)
    amount = f'{money.amount:.{precision}f}'
    colour = RED if money.amount < 0 else BLUE
    currency = f' {money.currency}' if show_currency else ''
    return f'{colour}{amount}{currency}{RESET}'

def string_format() -> Callable[[str, Any], str]:
    def _string_format(_field, val: str) -> str:
        return val if val else ''
    return _string_format

def date_format(format: str) -> Callable[[str, Any], str]:
    def _date_format(_field, val: date) -> str:
        return val.strftime(format) if val else ''
    return _date_format

def decimal_format(precision: int) -> Callable[[str, Any], str]:
    def _decimal_format(_field, val: Decimal) -> str:
        return f'{val:.{precision}f}' if val else ''
    return _decimal_format

def money_format(show_currency: bool) -> Callable[[str, Any], str]:
    def _money_format(_field, val: Money | list[Money]) -> str:
        if isinstance(val, list):
            return '\n'.join(colourify(money, show_currency) for money in val)
        return colourify(val, show_currency) if isinstance(val, Money) else val if isinstance(val, str) else ''
    return _money_format

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
        import csv, io

        options = self._get_options(kwargs)
        csv_options = {key: value for key, value in kwargs.items() if key not in options}
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
        json_options.update({key: value for key, value in kwargs.items() if key not in options})
        objects: list[Any] = []

        field_names = self._get_expanded_field_names()

        if options.get('header'):
            objects.append(field_names)

        for row in self._get_expanded_rows(options):
            objects.append(dict(zip(field_names, row, strict=False)))

        return json.dumps(objects, **json_options)

    def to_string(self) -> str:
        self._set_fields_names(bold_text=True)
        self._set_fields_format()

        if self.rows and any(field.show_sum for field in self.__fields):
            self._add_total_row()

        fields = [field.name for field in self.__fields if field.visible]
        table_str = self.get_formatted_string(fields=fields)
        
        return f'\n{table_str}\n'

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
        self.add_row([self._sum_field(field) if field.show_sum else None for field in self.__fields])

    def _sum_field(self, field: Field) -> str:
        i = self._field_index(field.name)

        if field.format == Format.MONEY and self._is_multicurrency(field.name):
            totals = defaultdict(Decimal)
            for row in self.rows:
                if row[i]:
                    totals[row[i].currency] += row[i].amount
            
            return money_format(show_currency=True)('', [Money(total, currency) for currency, total in totals.items()])

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
                    expanded_row.extend([field, None])
            else:
                expanded_row.append(field)

        return expanded_row