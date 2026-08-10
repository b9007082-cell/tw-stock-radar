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


def test_pullback_excludes_structure_risk_above_eight_percent() -> None:
    signal = _signal(
        "1001",
        "PULLBACK_RESUME",
        close=100,
        stop=91.9,
        peak=120,
    )
    result = build_recommendations([signal])
    assert result["pullback_resume"] == []


def test_bottom_launch_allows_wider_base_risk() -> None:
    signal = _signal(
        "2001",
        "CONSOLIDATION_BREAKOUT",
        close=100,
        stop=75,
        extra_metrics={
            "distance_from_low_percent": 15,
            "base_range_percent": 12,
            "base_volume_ratio": 0.72,
        },
    )
    result = build_recommendations([signal])
    assert result["consolidation_breakout"][0]["symbol"] == "2001"
    assert result["consolidation_breakout"][0]["structure_risk_percent"] == 25.0


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


def test_disposition_reversal_has_independent_ranking_bucket() -> None:
    mild = _signal(
        "3501",
        "DISPOSITION_REVERSAL",
        level="WATCH",
        close=100,
        stop=92,
        extra_metrics={
            "drawdown_percent": 28.0,
            "disposition_similarity_score": 48.0,
            "stop_volume_ratio": 2.2,
            "previous_stop_low": 92,
            "limit_like_drop_days": 2,
            "deviation_rate_percent": -16.0,
            "latest_volume_lots": 2500,
            "confirmed_buy": False,
            "inferred_disposition_status": "急跌止跌觀察",
        },
    )
    strong = _signal(
        "3502",
        "DISPOSITION_REVERSAL",
        level="CONFIRMED",
        close=122,
        stop=111,
        extra_metrics={
            "drawdown_percent": 44.0,
            "disposition_similarity_score": 82.0,
            "stop_volume_ratio": 5.8,
            "previous_stop_low": 111,
            "limit_like_drop_days": 4,
            "deviation_rate_percent": -28.0,
            "latest_volume_lots": 3600,
            "confirmed_buy": True,
            "inferred_disposition_status": "疑似處置急跌後止跌",
        },
    )
    result = build_recommendations([mild, strong])
    items = result["disposition_reversal"]
    assert [item["symbol"] for item in items] == ["3502", "3501"]
    assert "相似度 82分" in items[0]["ranking_reasons"]
    assert items[0]["structure_risk_percent"] == 9.02


def test_lorentzian_ml_has_independent_ranking_bucket() -> None:
    mild = _signal(
        "4001",
        "LORENTZIAN_ML",
        level="WATCH",
        close=100,
        stop=94,
        extra_metrics={
            "ml_prediction": 2,
            "ml_confidence": 0.25,
            "kernel_slope_percent": 0.1,
            "relative_strength_percentile": 0.55,
            "structure_risk_percent": 6.0,
            "latest_volume_lots": 2500,
        },
    )
    strong = _signal(
        "4002",
        "LORENTZIAN_ML",
        level="CONFIRMED",
        close=100,
        stop=95,
        extra_metrics={
            "ml_prediction": 6,
            "ml_confidence": 0.75,
            "ml_neighbors": 8,
            "kernel_slope_percent": 1.1,
            "relative_strength_percentile": 0.82,
            "structure_risk_percent": 5.0,
            "latest_volume_lots": 3600,
        },
    )
    result = build_recommendations([mild, strong])
    items = result["lorentzian_ml"]
    assert [item["symbol"] for item in items] == ["4002", "4001"]
    assert "ML投票 +6/8" in items[0]["ranking_reasons"]
    assert items[0]["structure_risk_percent"] == 5.0


def test_bollinger_squeeze_has_independent_ranking_bucket() -> None:
    weak = _signal(
        "5001",
        "BOLLINGER_SQUEEZE",
        level="CONFIRMED",
        close=103,
        stop=96,
        extra_metrics={
            "bollinger_upper": 102,
            "bollinger_lower": 97,
            "bollinger_width_percent": 6.0,
            "bollinger_width_percentile": 0.12,
            "previous_bollinger_width_percentile": 0.18,
            "bollinger_first_breakout_upper": True,
            "bollinger_breakout_upper": True,
            "main_force_buying": True,
            "close_position_percent": 74,
            "volume_ratio": 1.55,
            "latest_volume_lots": 2400,
        },
    )
    strong = _signal(
        "5002",
        "BOLLINGER_SQUEEZE",
        level="CONFIRMED",
        close=103.5,
        stop=97,
        extra_metrics={
            "bollinger_upper": 102,
            "bollinger_lower": 99,
            "bollinger_width_percent": 3.0,
            "bollinger_width_percentile": 0.05,
            "previous_bollinger_width_percentile": 0.05,
            "bollinger_first_breakout_upper": True,
            "bollinger_breakout_upper": True,
            "main_force_buying": True,
            "close_position_percent": 88,
            "volume_ratio": 2.0,
            "latest_volume_lots": 3200,
        },
    )
    result = build_recommendations([weak, strong])
    items = result["bollinger_squeeze"]
    assert [item["symbol"] for item in items] == ["5002", "5001"]
    assert "布林寬度 3.00%" in items[0]["ranking_reasons"]
    assert "第一根突破上軌" in items[0]["ranking_reasons"]
    assert "主力攻擊量" in items[0]["ranking_reasons"]
    assert items[0]["structure_risk_percent"] == 0.0


def test_intraday_ma60_touch_has_independent_ranking_bucket() -> None:
    far = _signal(
        "6001",
        "INTRADAY_MA60_TOUCH",
        level="WATCH",
        close=100,
        extra_metrics={
            "intraday_abs_distance_to_ma60_percent": 1.4,
            "intraday_distance_to_ma60_percent": -1.4,
            "intraday_ma60": 101.4,
            "intraday_ma60_slope_percent": 0.05,
            "intraday_ma60_turning_up": True,
            "intraday_volume_ratio": 1.0,
            "intraday_volume_breakout": False,
            "reclaimed_intraday_ma60": False,
            "pulled_back_without_breaking_intraday_ma60": False,
            "daily_volume_lots": 2500,
        },
    )
    near = _signal(
        "6002",
        "INTRADAY_MA60_TOUCH",
        level="CONFIRMED",
        close=100,
        extra_metrics={
            "intraday_abs_distance_to_ma60_percent": 0.2,
            "intraday_distance_to_ma60_percent": 0.2,
            "intraday_ma60": 99.8,
            "intraday_ma60_slope_percent": 0.25,
            "intraday_ma60_turning_up": True,
            "intraday_volume_ratio": 1.6,
            "intraday_volume_breakout": True,
            "reclaimed_intraday_ma60": True,
            "pulled_back_without_breaking_intraday_ma60": False,
            "daily_volume_lots": 6200,
        },
    )
    result = build_recommendations([far, near])
    items = result["intraday_ma60_touch"]
    assert [item["symbol"] for item in items] == ["6002", "6001"]
    assert "距60分MA60 +0.20%" in items[0]["ranking_reasons"]
    assert "60MA上彎 +0.25%" in items[0]["ranking_reasons"]
    assert items[0]["structure_risk_percent"] == 0.2


def test_low_price_high_yield_has_independent_ranking_bucket() -> None:
    low_yield = _signal(
        "7001",
        "LOW_PRICE_HIGH_YIELD",
        level="WATCH",
        close=80,
        extra_metrics={
            "dividend_yield": 5.2,
            "drawdown_from_high_percent": 14.0,
            "distance_from_low_percent": 18.0,
            "pb_ratio": 1.4,
            "pe_ratio": 14.0,
            "latest_volume_lots": 2500,
        },
    )
    high_yield = _signal(
        "7002",
        "LOW_PRICE_HIGH_YIELD",
        level="TRIAL",
        close=80,
        extra_metrics={
            "dividend_yield": 7.4,
            "drawdown_from_high_percent": 28.0,
            "distance_from_low_percent": 5.0,
            "pb_ratio": 0.8,
            "pe_ratio": 9.0,
            "latest_volume_lots": 3600,
        },
    )
    result = build_recommendations([low_yield, high_yield])
    items = result["low_price_high_yield"]
    assert [item["symbol"] for item in items] == ["7002", "7001"]
    assert "殖利率 7.40%" in items[0]["ranking_reasons"]
    assert items[0]["structure_risk_percent"] == 5.0


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
