from datetime import date

from tech_etf_quant.cli import main

if __name__ == "__main__":
    main(["report", "--date", date.today().isoformat()])
