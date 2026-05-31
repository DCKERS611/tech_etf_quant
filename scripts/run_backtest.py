from datetime import date

from tech_etf_quant.cli import main

if __name__ == "__main__":
    main(["backtest", "--start", "2021-01-01", "--end", date.today().isoformat()])
