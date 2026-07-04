import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.config import get_settings
from app.models import Instrument
from app.services.backtest import backtest
from app.services.demo_data import seed_demo
from app.services.market_data import (
    OfficialSnapshotClient,
    import_history_csv,
    upsert_market_rows,
)
from app.services.history_store import (
    backfill_history,
    prune_history,
    write_state_manifest,
)
from app.services.scanner import _load_bars, run_scan
from app.services.static_export import export_static_data

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_STATE_PATH = PROJECT_ROOT / "data" / "state" / "manifest.json"
DEFAULT_STATIC_OUTPUT = PROJECT_ROOT / "frontend" / "public" / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description="Taiwan stock scanner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db")
    subparsers.add_parser("seed-demo")
    subparsers.add_parser("fetch-latest")
    subparsers.add_parser("scan")
    csv_parser = subparsers.add_parser("import-csv")
    csv_parser.add_argument("path", type=Path)
    backtest_parser = subparsers.add_parser("backtest")
    backtest_parser.add_argument("symbol")
    history_parser = subparsers.add_parser("backfill-history")
    history_parser.add_argument("--start", type=date.fromisoformat)
    history_parser.add_argument("--end", type=date.fromisoformat)
    history_parser.add_argument("--days", type=int, default=183)
    history_parser.add_argument("--delay", type=float, default=0.15)
    update_parser = subparsers.add_parser("update-latest")
    update_parser.add_argument("--lookback", type=int, default=10)
    update_parser.add_argument("--delay", type=float, default=0.15)
    export_parser = subparsers.add_parser("export-static")
    export_parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    export_parser.add_argument("--output", type=Path, default=DEFAULT_STATIC_OUTPUT)
    args = parser.parse_args()

    if args.command in {"backfill-history", "update-latest"}:
        taipei_today = datetime.now(ZoneInfo(get_settings().timezone)).date()
        end = (
            args.end
            if args.command == "backfill-history" and args.end
            else taipei_today
        )
        if args.command == "backfill-history":
            start = args.start or end - timedelta(days=args.days)
        else:
            start = end - timedelta(days=args.lookback)
        result = backfill_history(
            DEFAULT_RAW_DIR,
            start,
            end,
            delay_seconds=args.delay,
        )
        cutoff = end - timedelta(days=183)
        result["pruned"] = prune_history(DEFAULT_RAW_DIR, cutoff)
        manifest = write_state_manifest(DEFAULT_RAW_DIR, DEFAULT_STATE_PATH)
        print(json.dumps({**result, **manifest}, ensure_ascii=False, indent=2))
        return
    if args.command == "export-static":
        manifest = export_static_data(args.raw_dir, args.output)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return
    init_db()
    if args.command == "init-db":
        print("Database initialized")
        return
    with SessionLocal() as session:
        if args.command == "seed-demo":
            imported = seed_demo(session)
            generated = run_scan(session)
            print(f"Imported {imported} rows; generated {generated} signals")
        elif args.command == "fetch-latest":
            rows = OfficialSnapshotClient().fetch_all()
            print(f"Imported {upsert_market_rows(session, rows)} official rows")
        elif args.command == "scan":
            print(f"Generated {run_scan(session)} signals")
        elif args.command == "import-csv":
            print(f"Imported {import_history_csv(session, args.path)} CSV rows")
        elif args.command == "backtest":
            instrument = session.scalar(
                select(Instrument).where(Instrument.symbol == args.symbol)
            )
            if instrument is None:
                raise SystemExit(f"Unknown symbol: {args.symbol}")
            report = backtest(_load_bars(session, instrument.id))
            print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
