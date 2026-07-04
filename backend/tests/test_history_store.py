from datetime import date
from decimal import Decimal

from app.services.history_store import (
    parse_tpex_history,
    parse_twse_history,
    read_snapshot,
    sha256_file,
    write_snapshot,
)
from app.services.market_data import MarketRow


def test_parse_twse_history_filters_non_common_securities() -> None:
    payload = {
        "stat": "OK",
        "date": "20260703",
        "tables": [
            {
                "fields": [
                    "證券代號",
                    "證券名稱",
                    "成交股數",
                    "成交金額",
                    "開盤價",
                    "最高價",
                    "最低價",
                    "收盤價",
                ],
                "data": [
                    ["2330", "台積電", "1,000", "1,010,000", "1000", "1020", "995", "1010"],
                    ["0050", "元大台灣50", "2,000", "400,000", "200", "201", "199", "200"],
                ],
            }
        ],
    }
    rows = parse_twse_history(payload, date(2026, 7, 3))
    assert [row.symbol for row in rows] == ["2330"]
    assert rows[0].volume == 1000


def test_parse_tpex_history_filters_warrants() -> None:
    payload = {
        "stat": "ok",
        "date": "20260703",
        "tables": [
            {
                "fields": [
                    "代號",
                    "名稱",
                    "收盤",
                    "開盤",
                    "最高",
                    "最低",
                    "成交股數",
                    "成交金額(元)",
                ],
                "data": [
                    ["6488", "環球晶", "450", "445", "455", "440", "10,000", "4,500,000"],
                    ["700195", "權證", "1", "1", "1", "1", "10,000", "10,000"],
                ],
            }
        ],
    }
    rows = parse_tpex_history(payload, date(2026, 7, 3))
    assert [row.symbol for row in rows] == ["6488"]


def test_snapshot_roundtrip_is_deterministic(tmp_path) -> None:
    row = MarketRow(
        symbol="2330",
        name="台積電",
        market="TWSE",
        trade_date=date(2026, 7, 3),
        open=Decimal("1000"),
        high=Decimal("1020"),
        low=Decimal("995"),
        close=Decimal("1010"),
        volume=1000,
        turnover=Decimal("1010000"),
        source="TEST",
    )
    path = write_snapshot(
        tmp_path,
        row.trade_date,
        [row],
        ingested_at="2026-07-03T12:00:00+00:00",
    )
    first_hash = sha256_file(path)
    payload, rows = read_snapshot(path)
    write_snapshot(
        tmp_path,
        row.trade_date,
        [row],
        ingested_at="2026-07-03T12:00:00+00:00",
    )
    assert sha256_file(path) == first_hash
    assert payload["counts"]["total"] == 1
    assert rows == [row]

