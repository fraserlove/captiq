import logging
import operator
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import click
import typer

from captiq.config import config
from captiq.exceptions import CaptiqError
from captiq.providers import SecurityData, FXData

from captiq.logging import configure_logger
from captiq.parsers import find_parser
from captiq.table import OutputFormat
from captiq.taxcalc import TaxCalculator
from captiq.transaction import Acquisition, Disposal, Transaction
from captiq.trhistory import TrHistory
from captiq.types import Ticker, Year
from captiq.utils import boldify, tax_year_full_date, tax_year_short_date
from captiq.logging import logger

__version__ = '1.0.0'
__package__ = 'captiq'


class OrderedCommands(typer.core.TyperGroup):
    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(self.commands.keys())


class MutuallyExclusiveOption(click.exceptions.UsageError):
    def __init__(self, opt1: str, opt2: str) -> None:
        super().__init__(f'Option {opt1} cannot be used together with option {opt2}')


app = typer.Typer(
    cls=OrderedCommands,
    context_settings={'help_option_names': ['-h', '--help']},
    no_args_is_help=True,
    pretty_exceptions_enable=True,
)

FilesArg = Annotated[list[Path], typer.Argument(
    exists=True, dir_okay=True, readable=True,
    help='CSV files and/or directories containing CSV files to process.',
    show_default=False,
)]

TaxYearOpt = Annotated[Optional[int], typer.Option(
    min=2008, max=datetime.now().year,
    metavar='TAX-YEAR', help='Filter by tax year.',
    show_default=False,
)]

TickerOpt = Annotated[Optional[str], typer.Option(
    metavar='TICKER', help='Filter by ticker.',
    show_default=False,
)]

OutputFormatOpt = Annotated[OutputFormat, typer.Option(
    '--output', '-o', help='Output format.'
)]


def abort(message: str) -> None:
    logger.critical(message)
    raise typer.Exit(code=1)


def parse(input_paths: list[Path]) -> tuple[TrHistory, TaxCalculator]:
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
                    abort(str(e))
                logger.info(
                    f'{csv_file.name.split(".")[0]} → {len(result.orders)} orders · {len(result.dividends)} dividends · '
                    f'{len(result.transfers)} transfers · {len(result.interest)} interest'
                )

                orders.extend(result.orders)
                dividends.extend(result.dividends)
                transfers.extend(result.transfers)
                interest.extend(result.interest)
            else:
                abort(f'Unable to find a parser for {csv_file}')

    tr_hist = TrHistory(orders=orders, dividends=dividends, transfers=transfers, interest=interest)
    tax_calculator = TaxCalculator(tr_hist, SecurityData(tr_hist, config.cache_file), FXData())
    return tr_hist, tax_calculator


def create_filters(
    tax_year: int | None = None,
    ticker: str | None = None,
    tr_type: type[Transaction] | None = None,
    total_op: Callable | None = None,
) -> Sequence[Callable[[Transaction], bool]]:
    filters = []

    if tax_year:
        filters.append(lambda tr: tr.tax_year() == Year(tax_year))

    if ticker:
        filters.append(lambda tr: tr.ticker == ticker)

    if tr_type:
        filters.append(lambda tr: isinstance(tr, tr_type))

    if total_op:
        filters.append(lambda tr: total_op(tr.total.amount, 0.0))

    return filters


def version_callback(value: bool) -> None:
    if value:
        print(f'{__package__} {__version__}')
        raise typer.Exit()


@app.callback()
def main_callback(
    strict: Annotated[bool, typer.Option(help='Abort if data integrity issues are found.')] = config.strict,
    cache_file: Annotated[Path, typer.Option(dir_okay=False, help='Cache file to store additional data about securities.')] = config.cache_file,
    include_fx_fees: Annotated[bool, typer.Option(help='Include foreign exchange fees as an allowable cost.')] = config.include_fx_fees,
    verbose: Annotated[bool, typer.Option('--verbose', help='Enable additional logging.')] = False,
    quiet: Annotated[bool, typer.Option('--quiet', help='Disable all non-critical logging.')] = False,
    version: Annotated[Optional[bool], typer.Option('--version', callback=version_callback, help='Show version information and exit.')] = None,
) -> None:
    if verbose and quiet:
        raise MutuallyExclusiveOption('--verbose', '--quiet')

    config.strict = strict
    config.cache_file = cache_file
    config.include_fx_fees = include_fx_fees
    config.log_level = logging.DEBUG if verbose else logging.CRITICAL if quiet else config.log_level

    configure_logger()


@app.command('orders')
def orders_command(
    files: FilesArg,
    tax_year: TaxYearOpt = None,
    ticker: TickerOpt = None,
    acquisitions_only: Annotated[bool, typer.Option('--acquisitions', help='Show only acquisitions.')] = False,
    disposals_only: Annotated[bool, typer.Option('--disposals', help='Show only disposals.')] = False,
    format: OutputFormatOpt = OutputFormat.TEXT,
) -> None:
    '''
    Show share buy/sell orders.
    '''
    if acquisitions_only and disposals_only:
        raise MutuallyExclusiveOption('--acquisitions', '--disposals')

    tr_hist, _ = parse(files)
    tr_type = Acquisition if acquisitions_only else Disposal if disposals_only else None
    filters = create_filters(tax_year=tax_year, ticker=ticker, tr_type=tr_type)
    
    if table := tr_hist.get_orders_table(filters):
        print(table.to_string(format, leading_nl=config.logging_enabled))


@app.command('dividends')
def dividends_command(
    files: FilesArg,
    tax_year: TaxYearOpt = None,
    ticker: TickerOpt = None,
    format: OutputFormatOpt = OutputFormat.TEXT,
) -> None:
    '''
    Show share dividends paid out.
    '''
    tr_hist, _ = parse(files)
    filters = create_filters(tax_year=tax_year, ticker=ticker)
    if table := tr_hist.get_dividends_table(filters):
        print(table.to_string(format, leading_nl=config.logging_enabled))


@app.command('transfers')
def transfers_command(
    files: FilesArg,
    tax_year: TaxYearOpt = None,
    deposits_only: Annotated[bool, typer.Option('--deposits', help='Show only deposits.')] = False,
    withdrawals_only: Annotated[bool, typer.Option('--withdrawals', help='Show only withdrawals.')] = False,
    format: OutputFormatOpt = OutputFormat.TEXT,
) -> None:
    '''
    Show cash deposits and cash withdrawals.
    '''
    if deposits_only and withdrawals_only:
        raise MutuallyExclusiveOption('--deposits', '--withdrawals')

    tr_hist, _ = parse(files)
    total_op = operator.gt if deposits_only else operator.lt if withdrawals_only else None
    filters = create_filters(tax_year=tax_year, total_op=total_op)
    
    if table := tr_hist.get_transfers_table(filters):
        print(table.to_string(format, leading_nl=config.logging_enabled))


@app.command('interest')
def interest_command(
    files: FilesArg,
    tax_year: TaxYearOpt = None,
    format: OutputFormatOpt = OutputFormat.TEXT,
) -> None:
    '''
    Show interest earned on cash.
    '''
    tr_hist, _ = parse(files)
    filters = create_filters(tax_year=tax_year)
    if table := tr_hist.get_interest_table(filters):
        print(table.to_string(format, leading_nl=config.logging_enabled))


@app.command('capital-gains')
def capital_gains_command(
    files: FilesArg,
    gains_only: Annotated[bool, typer.Option('--gains', help='Show only capital gains.')] = False,
    losses_only: Annotated[bool, typer.Option('--losses', help='Show only capital losses.')] = False,
    tax_year: TaxYearOpt = None,
    ticker: TickerOpt = None,
    format: OutputFormatOpt = OutputFormat.TEXT,
) -> None:
    '''
    Show capital gains report.
    '''
    if gains_only and losses_only:
        raise MutuallyExclusiveOption('--gains', '--losses')

    if format != OutputFormat.TEXT and not tax_year:
        raise click.exceptions.UsageError(f'The {format.value} format requires the option --tax-year to be used')

    _, tax_calculator = parse(files)
    tax_year = Year(tax_year) if tax_year else None
    ticker = Ticker(ticker) if ticker else None

    try:
        tax_years = [tax_year] if tax_year else sorted(tax_calculator.disposal_years())
    except CaptiqError as e:
        abort(str(e))

    for tax_year_idx, tax_year in enumerate(tax_years):
        table = tax_calculator.get_capital_gains_table(tax_year, ticker, gains_only, losses_only)

        if table:
            print(end='\n' if tax_year_idx == 0 and config.logging_enabled else '')

            if format == OutputFormat.TEXT:
                print(f'{boldify(f"Capital Gains Tax Report {tax_year_short_date(tax_year)}")}')
                print(f'{tax_year_full_date(tax_year)}')
                print(table.to_string(format))
            else:
                print(table.to_string(format, leading_nl=False))


@app.command('holdings')
def holdings_command(
    files: FilesArg,
    ticker: TickerOpt = None,
    show_gain: Annotated[bool, typer.Option('--gains', help='Show unrealised gains/losses.')] = False,
    format: OutputFormatOpt = OutputFormat.TEXT,
) -> None:
    '''
    Show current holdings.
    '''
    _, tax_calculator = parse(files)
    ticker = Ticker(ticker) if ticker else None
    if table := tax_calculator.get_holdings_table(ticker, show_gain):
        print(table.to_string(format, leading_nl=config.logging_enabled))

def main() -> None:
    app()