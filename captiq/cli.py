from collections.abc import Callable, Sequence
from typing import Annotated, Optional
from pathlib import Path
import click, typer

from captiq.config import config
from captiq.exceptions import CaptiqError
from captiq.providers import SecurityData, FXData
from captiq.logging import configure_logger
from captiq.tax import TaxCalculator
from captiq.transaction import Transaction
from captiq.trhistory import Transactions
from captiq.types import Ticker, Year
from captiq.logging import logger, set_log_level
from captiq.year import TaxYear
from captiq import __version__, __package__
from captiq.parsers import parse_files


class OrderedCommands(typer.core.TyperGroup):
    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(self.commands.keys())


class MutuallyExclusiveError(click.exceptions.UsageError):
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

TaxYearOpt = Annotated[int, typer.Option(
    min=2008, max=TaxYear.current(),
    metavar='TAX-YEAR', help='Filter by tax year.',
    show_default=True,
)]

TickerOpt = Annotated[Optional[str], typer.Option(
    metavar='TICKER', help='Filter by ticker.',
    show_default=False,
)]


def abort(message: str) -> None:
    logger.critical(message)
    raise typer.Exit(code=1)


def parse(input_paths: list[Path]) -> tuple[Transactions, TaxCalculator]:
    try:
        transactions = parse_files(input_paths)
        tax_calculator = TaxCalculator(transactions, SecurityData(transactions, config.cache), FXData())
        return transactions, tax_calculator
    except CaptiqError as e:
        abort(str(e))


def create_filters(tax_year: int | None = None, ticker: str | None = None) -> Sequence[Callable[[Transaction], bool]]:
    return [
        lambda tr: tr.tax_year() == Year(tax_year) if tax_year else True,
        lambda tr: tr.ticker == ticker if ticker else True,
    ]


def output_table(table, table_type: str, tax_year: int, json_export: bool = False, csv_export: bool = False) -> None:
    if json_export and csv_export:
        raise MutuallyExclusiveError('--json', '--csv')
    
    if json_export:
        json_file = Path(f"{table_type}_{tax_year}.json")
        json_file.write_text(table.get_json_string(header=True), encoding='utf-8')
        logger.info(f'Table exported to {json_file}')
    elif csv_export:
        csv_file = Path(f"{table_type}_{tax_year}.csv")
        csv_file.write_text(table.get_csv_string(header=True), encoding='utf-8')
        logger.info(f'Table exported to {csv_file}')
    else:
        print(table.to_string())


def version_callback(value: bool) -> None:
    if value:
        print(f'{__package__} {__version__}')
        raise typer.Exit()


@app.callback()
def main_callback(
    strict: Annotated[bool, typer.Option(help='Abort if data integrity issues are found.')] = config.strict,
    cache: Annotated[Path, typer.Option(dir_okay=False, help='Cache file to store securities data.')] = config.cache,
    include_fx_fees: Annotated[bool, typer.Option(help='Include FX fees as an allowable cost.')] = config.include_fx_fees,
    verbose: Annotated[bool, typer.Option('--verbose', help='Enable additional logging.')] = False,
    quiet: Annotated[bool, typer.Option('--quiet', help='Disable all non-critical logging.')] = False,
    version: Annotated[bool, typer.Option('--version', callback=version_callback, help='Show version information.')] = False,
) -> None:
    if verbose and quiet:
        raise MutuallyExclusiveError('--verbose', '--quiet')

    config.strict = strict
    config.cache = cache
    config.include_fx_fees = include_fx_fees
    set_log_level(verbose, quiet)

    configure_logger()


@app.command('orders')
def orders_command(
    files: FilesArg,
    tax_year: TaxYearOpt = TaxYear.current(),
    ticker: TickerOpt = None,
    acquisitions_only: Annotated[bool, typer.Option('--acquisitions', help='Show only acquisitions.')] = False,
    disposals_only: Annotated[bool, typer.Option('--disposals', help='Show only disposals.')] = False,
    json_export: Annotated[bool, typer.Option('--json', help='Export table to automatically named JSON file.')] = False,
    csv_export: Annotated[bool, typer.Option('--csv', help='Export table to automatically named CSV file.')] = False
) -> None:
    '''
    Show share buy/sell orders.
    '''
    if acquisitions_only and disposals_only:
        raise MutuallyExclusiveError('--acquisitions', '--disposals')

    tr_hist, _ = parse(files)
    filters = create_filters(tax_year=tax_year, ticker=ticker)
    
    if table := tr_hist.get_orders_table(filters, acquisitions_only, disposals_only):
        output_table(table, 'orders', tax_year, json_export, csv_export)
    else:
        logger.info(f'No orders found')


@app.command('dividends')
def dividends_command(
    files: FilesArg,
    tax_year: TaxYearOpt = TaxYear.current(),
    ticker: TickerOpt = None,
    json_export: Annotated[bool, typer.Option('--json', help='Export table to automatically named JSON file.')] = False,
    csv_export: Annotated[bool, typer.Option('--csv', help='Export table to automatically named CSV file.')] = False
) -> None:
    '''
    Show share dividends paid out.
    '''
    tr_hist, _ = parse(files)
    filters = create_filters(tax_year=tax_year, ticker=ticker)

    if table := tr_hist.get_dividends_table(filters):
        output_table(table, 'dividends', tax_year, json_export, csv_export)
    else:
        logger.info(f'No dividends found')


@app.command('transfers')
def transfers_command(
    files: FilesArg,
    tax_year: TaxYearOpt = TaxYear.current(),
    deposits_only: Annotated[bool, typer.Option('--deposits', help='Show only deposits.')] = False,
    withdrawals_only: Annotated[bool, typer.Option('--withdrawals', help='Show only withdrawals.')] = False,
    json_export: Annotated[bool, typer.Option('--json', help='Export table to automatically named JSON file.')] = False,
    csv_export: Annotated[bool, typer.Option('--csv', help='Export table to automatically named CSV file.')] = False
) -> None:
    '''
    Show cash deposits and cash withdrawals.
    '''
    if deposits_only and withdrawals_only:
        raise MutuallyExclusiveError('--deposits', '--withdrawals')

    tr_hist, _ = parse(files)
    filters = create_filters(tax_year=tax_year)
    
    if table := tr_hist.get_transfers_table(filters, deposits_only, withdrawals_only):
        output_table(table, 'transfers', tax_year, json_export, csv_export)
    else:
        logger.info(f'No transfers found')


@app.command('interest')
def interest_command(
    files: FilesArg,
    tax_year: TaxYearOpt = TaxYear.current(),
    json_export: Annotated[bool, typer.Option('--json', help='Export table to automatically named JSON file.')] = False,
    csv_export: Annotated[bool, typer.Option('--csv', help='Export table to automatically named CSV file.')] = False
) -> None:
    '''
    Show interest earned on cash.
    '''
    tr_hist, _ = parse(files)
    filters = create_filters(tax_year=tax_year)

    if table := tr_hist.get_interest_table(filters):
        output_table(table, 'interest', tax_year, json_export, csv_export)
    else:
        logger.info(f'No interest found')


@app.command('capital-gains')
def capital_gains_command(
    files: FilesArg,
    tax_year: TaxYearOpt = TaxYear.current(),
    ticker: TickerOpt = None,
    gains_only: Annotated[bool, typer.Option('--gains', help='Show only capital gains.')] = False,
    losses_only: Annotated[bool, typer.Option('--losses', help='Show only capital losses.')] = False,
    json_export: Annotated[bool, typer.Option('--json', help='Export table to automatically named JSON file.')] = False,
    csv_export: Annotated[bool, typer.Option('--csv', help='Export table to automatically named CSV file.')] = False
) -> None:
    '''
    Show capital gains report.
    '''
    if gains_only and losses_only:
        raise MutuallyExclusiveError('--gains', '--losses')

    _, tax_calculator = parse(files)
    tax_year = Year(tax_year)
    ticker = Ticker(ticker)

    if table := tax_calculator.get_capital_gains_table(tax_year, ticker, gains_only, losses_only):
        output_table(table, 'capital_gains', tax_year, json_export, csv_export)
    else:
        logger.info(f'No capital gains found')


@app.command('holdings')
def holdings_command(
    files: FilesArg,
    ticker: TickerOpt = None,
    show_unrealised: Annotated[bool, typer.Option('--unrealised', help='Show unrealised gains/losses.')] = False,
    json_export: Annotated[bool, typer.Option('--json', help='Export table to automatically named JSON file.')] = False,
    csv_export: Annotated[bool, typer.Option('--csv', help='Export table to automatically named CSV file.')] = False
) -> None:
    '''
    Show current holdings.
    '''
    _, tax_calculator = parse(files)
    ticker = Ticker(ticker)

    if table := tax_calculator.get_holdings_table(ticker, show_unrealised):
        output_table(table, 'holdings', TaxYear.current(), json_export, csv_export)
    else:
        logger.info(f'No holdings found')
