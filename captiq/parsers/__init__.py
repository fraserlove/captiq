from typing import Type

from .types import Parser
from .t212 import Trading212Parser
from captiq.logging import logger
from captiq.exceptions import CaptiqError
from captiq.trhistory import Transactions

def find_parser(csv_file: str) -> Parser | None:
    '''
    Find the first parser that can parse the given CSV file.
    '''
    parsers: list[Type[Parser]] = [
        Trading212Parser,
    ]

    for parser_class in parsers:
        parser = parser_class(csv_file)
        if parser.can_parse():
            logger.debug(f'Found parser: {parser_class.__name__}')
            return parser

    return None

def parse_files(input_paths: list[str]) -> Transactions:
    """
    Parse CSV files from the given paths and return transactions.
    """
    orders, dividends, transfers, interest = [], [], [], []

    for path in input_paths:
        if path.is_dir():
            csv_files = sorted(path.glob('**/*.csv'))
            if not csv_files:
                logger.debug(f'No CSV files found under {path}/')
                continue
            logger.debug(f'Found {len(csv_files)} CSV files under {path}/')
        else:
            csv_files = [path]
            
        for csv_file in csv_files:
            logger.debug(f'Parsing input file: {csv_file}')
            if parser := find_parser(csv_file):
                try:
                    result = parser.parse()
                except CaptiqError as e:
                    raise CaptiqError(str(e))
                logger.info(
                    f'{csv_file.name.split(".")[0]} → {len(result.orders)} orders · {len(result.dividends)} dividends · '
                    f'{len(result.transfers)} transfers · {len(result.interest)} interest'
                )

                orders.extend(result.orders)
                dividends.extend(result.dividends)
                transfers.extend(result.transfers)
                interest.extend(result.interest)
            else:
                raise CaptiqError(f'Unable to find a parser for {csv_file}')

    return Transactions(orders=orders, dividends=dividends, transfers=transfers, interest=interest)
