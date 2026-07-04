from app.services.market_data import _roc_date, is_common_stock, parse_history_csv


def test_roc_date_conversion() -> None:
    assert _roc_date("1150703").isoformat() == "2026-07-03"


def test_common_stock_filter() -> None:
    assert is_common_stock("2330")
    assert not is_common_stock("0050")
    assert not is_common_stock("00400A")


def test_csv_contract() -> None:
    content = (
        "symbol,name,market,date,open,high,low,close,volume,turnover\n"
        "2330,台積電,TWSE,2026-07-03,1000,1020,995,1015,1000000,1015000000\n"
    )
    rows = parse_history_csv(content)
    assert len(rows) == 1
    assert rows[0].symbol == "2330"
    assert float(rows[0].close) == 1015

