# Captiq

Captiq analyses account activity on share investment platforms to calculate UK Capital Gains Tax in accordance with HMRC share identification rules and provides information for the Capital Gains SA108 form in a Self Assessment tax return. Additionally, it provides options to view the allocation weight and unrealised gain/loss for open positions, share acquisitions and disposals, dividends paid out, interest on cash earned, and cash deposits or withdrawals. Captiq is based on [Investir](https://github.com/tacgomes/investir) by [Tiago Gomes](https://github.com/tacgomes).

## Installation and Usage

Before installing Captiq, consider using a virtual environment for the installation to avoid conflicts with other Python packages.

```bash
python -m venv .venv
source .venv/bin/activate
```

Clone the repository and install the `captiq` package:

```bash
git clone https://github.com/fraserlove/captiq.git
cd captiq
pip install .
```

Verify that `captiq` was installed successfully via `captiq --version`.

Shell completion is available for your shell and can be viewed with `captiq --show-completion` or installed with `captiq --install-completion`.

### Usage

Captiq processes data from CSV files exported from your investment platform. Currently, only _Trading 212_ is supported. You can provide individual CSV files or directories containing multiple CSV files. Captiq commands take the following form:

```
captiq [OPTIONS]... COMMAND [ARGS]... [FILES]...
```

- `OPTIONS` specify global options available for all commands, such as `--strict` to abort if data integrity issues are found, or `--verbose` to enable additional logging.
- `COMMAND` specifies the command to execute, such as `orders` to view share acquisitions and disposals.
- `ARGS` are command-specific options, such as `--acquisitions` to show only acquisitions.
- `FILES` are the CSV files or directories containing CSV files to process.

Use `captiq --help` or `captiq -h` to view available options and commands, or alternatively, `captiq COMMAND --help` or `captiq COMMAND -h` for command-specific information.

The `capital-gains` command generates a capital gains report. Other commands are available to view share `holdings`, market `orders` (acquisitions and disposals), `dividends` paid out, `transfers` (cash deposits or withdrawals), and `interest` earned.

If no `--tax-year` argument is provided, the current tax year is used.

## Example

Suppose you have a CSV file `T212.csv` containing your Trading 212 account activity. A capital gains report can be generated as follows:
```console
$ captiq capital-gains --tax-year 2020 T212.csv
INFO | T212 → 460 orders · 16 dividends · 52 transfers · 32 interest

┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Disposal Date   Identification          Security Name                   ISIN              Quantity   Cost (GBP)   Proceeds (GBP)   Gain/loss (GBP) │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 09/11/2024      Same day                National Grid                   GB00BDR05C01    1.00000000         9.61             9.55             -0.06 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 09/11/2024      Same day                Advanced Micro Devices          US0079031078    0.00690100         0.43             0.45              0.02 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 09/11/2024      Same day                Amazon                          US0231351067    0.00010987         0.26             0.27              0.01 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 09/11/2024      Same day                Alphabet (Class A)              US02079K3059    0.00360257         4.90             4.90              0.00 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 09/11/2024      Same day                Sony                            US8356993076    0.07305000         4.92             4.89             -0.03 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 16/11/2024      Same day                Oxford Instruments              GB0006650450    0.06111945         1.25             1.20             -0.05 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 16/11/2024      Section 104             Oxford Instruments              GB0006650450    0.94362308        20.01            18.45             -1.56 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 16/11/2024      Same day                Alphabet (Class A)              US02079K3059    0.00135927         1.84             1.84              0.00 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 16/11/2024      Same day                Micron Technology               US5951121038    0.05498100         2.50             2.52              0.02 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 16/11/2024      Bed & B. (2020-11-23)   Micron Technology               US5951121038    0.02622700         1.25             1.20             -0.04 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 16/11/2024      Same day                Sony                            US8356993076    0.01483900         1.02             1.02             -0.00 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 16/11/2024      Same day                IBM                             US4592001014    0.00515750         0.46             0.46             -0.00 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 01/03/2025      Section 104             Hive Digital Technologies Ltd   CA4339211035   60.00000000       237.72           182.02            -55.70 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                          286.17           228.77            -57.40 │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Additional Information

Share sub-divisions and consolidations are supported and detected automatically via the [Yahoo Finance API](https://pypi.org/project/yfinance/), however spin-off events (de-mergers) are not currently supported.

No special handling of accumulation shares in investment funds (where dividends or interest are automatically reinvested) is currently supported. This may result in different tax implications than what is reported.

Multi-currency accounts in Trading 212 are partially supported. It is possible to view orders, dividends, interest and transfers whose total is not in pound sterling, but it is not possible to calculate capital gains tax at the moment.

## Disclaimer

The information provided by Captiq might be inaccurate or simply not correct for your specific circumstances. Use the software at your own risk and always seek advice from a professional accountant before submitting your Self-Assessment tax return.

## License

Captiq is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.