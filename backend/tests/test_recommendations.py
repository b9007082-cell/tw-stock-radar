from app.services.recommendations import build_recommendations


def _signal(
    symbol: str,
    strategy: str,
    *,
    level: str = "CONFIRMED",
    close: float = 100.0,
    stop: float = 95.0,
    peak: float = 110.0,
    ma5: float = 99.0,
    slope: float = 0.03,
    volume_ratio: float = 1.5,
    trigger: float = 99.0,
    extra_metrics: dict | None = None,
) -> dict:
    return {
        "id": int(symbol),
        "symbol": symbol,
        "name": f"股票{symbol}",
        "market": "TWSE",
        "signal_date": "2026-07-07",
        "strategy": strategy,
        "strategy_version": "test",
        "level": level,
        "score": 90,
        "close": close,
        "entry_price": close if level == "CONFIRMED" else None,
        "entry_zone_low": None,
        "entry_zone_high": None,
        "trigger_price": trigger,
        "stop_price": stop,
        "risk_percent": None,
        "timing_status": "READY",
        "timing_note": "",
        "overheated": False,
        "executable": False,
        "validation_status": "RESEARCH",
        "reasons": [],
        "metrics": {
            "latest_peak": peak,
            "latest_trough": stop,
            "ma5": ma5,
            "ma20_slope_5d": slope,
            "volume_ratio": volume_ratio,
            **(extra_metrics or {}),
        },
    }


def test_excludes_structure_risk_above_eight_percent() -> None:
    signal = _signal(
        "1001",
        "CONSOLIDATION_BREAKOUT",
        close=100,
        stop=91.9,
    )
    result = build_recommendations([signal])
    assert result["consolidation_breakout"] == []


def test_pullback_requires_at_least_one_point_five_r() -> None:
    rejected = _signal(
        "1001",
        "PULLBACK_RESUME",
        close=100,
        stop=95,
        peak=107.49,
    )
    accepted = _signal(
        "1002",
        "PULLBACK_RESUME",
        close=100,
        stop=95,
        peak=107.5,
    )
    result = build_recommendations([rejected, accepted])
    assert [item["symbol"] for item in result["pullback_resume"]] == ["1002"]
    assert result["pullback_resume"][0]["reward_risk_ratio"] == 1.5


def test_confirmed_always_ranks_before_trial() -> None:
    confirmed = _signal(
        "1002",
        "CONSOLIDATION_BREAKOUT",
        level="CONFIRMED",
        volume_ratio=0.6,
    )
    trial = _signal(
        "1001",
        "CONSOLIDATION_BREAKOUT",
        level="TRIAL",
        volume_ratio=3.0,
        close=98.5,
        trigger=99,
    )
    result = build_recommendations([trial, confirmed])
    assert [item["symbol"] for item in result["consolidation_breakout"]] == [
        "1002",
        "1001",
    ]


def test_strategy_weights_rank_stronger_inputs_higher() -> None:
    pullback_low = _signal(
        "1001", "PULLBACK_RESUME", peak=108, slope=0.01
    )
    pullback_high = _signal(
        "1002", "PULLBACK_RESUME", peak=115, slope=0.03
    )
    breakout_low = _signal(
        "2001", "CONSOLIDATION_BREAKOUT", volume_ratio=0.7
    )
    breakout_high = _signal(
        "2002", "CONSOLIDATION_BREAKOUT", volume_ratio=2.0
    )
    result = build_recommendations(
        [pullback_low, pullback_high, breakout_low, breakout_high]
    )
    assert result["pullback_resume"][0]["symbol"] == "1002"
    assert result["consolidation_breakout"][0]["symbol"] == "2002"


def test_limits_each_strategy_to_ten_and_breaks_ties_by_symbol() -> None:
    signals = [
        _signal(
            str(symbol),
            "CONSOLIDATION_BREAKOUT",
        )
        for symbol in range(1012, 1000, -1)
    ]
    result = build_recommendations(signals)
    items = result["consolidation_breakout"]
    assert len(items) == 10
    assert [item["symbol"] for item in items] == [
        str(symbol) for symbol in range(1001, 1011)
    ]


def test_bottom_reversal_ranks_by_deeper_drop_and_volume() -> None:
    mild = _signal(
        "3001",
        "BOTTOM_REVERSAL",
        level="WATCH",
        close=100,
        stop=94,
        extra_metrics={
            "drawdown_percent": 16.0,
            "stop_volume_ratio": 2.1,
            "previous_stop_low": 94,
            "latest_volume_lots": 2500,
            "stop_volume_lots": 2400,
            "confirmed_buy": False,
        },
    )
    strong = _signal(
        "3002",
        "BOTTOM_REVERSAL",
        level="CONFIRMED",
        close=100,
        stop=96,
        extra_metrics={
            "drawdown_percent": 25.0,
            "stop_volume_ratio": 3.2,
            "previous_stop_low": 96,
            "latest_volume_lots": 3000,
            "stop_volume_lots": 2900,
            "confirmed_buy": True,
        },
    )
    result = build_recommendations([mild, strong])
    items = result["bottom_reversal"]
    assert [item["symbol"] for item in items] == ["3002", "3001"]
    assert "突破止跌K高點" in items[0]["ranking_reasons"]
    assert items[0]["structure_risk_percent"] == 4.0


def test_unknown_fields_do_not_change_snapshot_ranking() -> None:
    signal = _signal("1001", "CONSOLIDATION_BREAKOUT")
    baseline = build_recommendations([signal])["consolidation_breakout"][0]
    changed = build_recommendations(
        [{**signal, "future_close": 9999}]
    )["consolidation_breakout"][0]
    assert baseline["rank"] == changed["rank"]
    assert baseline["recommendation_score"] == changed["recommendation_score"]


def test_ranking_reasons_include_volume_contraction_metrics() -> None:
    pullback = _signal(
        "1001",
        "PULLBACK_RESUME",
        extra_metrics={
            "pullback_volume_ratio": 0.72,
            "rebound_volume_ratio": 1.18,
        },
    )
    breakout = _signal(
        "2001",
        "CONSOLIDATION_BREAKOUT",
        extra_metrics={"consolidation_volume_ratio": 0.68},
    )
    result = build_recommendations([pullback, breakout])
    assert "回檔量縮 0.72倍" in result["pullback_resume"][0]["ranking_reasons"]
    assert "轉強量 1.18倍" in result["pullback_resume"][0]["ranking_reasons"]
    assert (
        "整理量縮 0.68倍"
        in result["consolidation_breakout"][0]["ranking_reasons"]
    )
