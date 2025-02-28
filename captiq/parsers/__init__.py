from typing import Type

from captiq.logging import logger
from captiq.parsers.types import Parser
from captiq.parsers.t212 import Trading212Parser

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