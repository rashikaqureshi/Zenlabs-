
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from service.config import settings
from service.cursor import load_cursor, save_cursor
from service.normalizer import call_metric_to_row, normalize
from service.poller import fetch_calls_since
from service.writer import insert_calls

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def load_fixtures(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def init_schema(sql_path: Path) -> None:
    # NOTE: splits DDL on ';'. Fine for 001_init.sql (no ';' inside statements);
    # fragile if a statement ever contains a semicolon in a string/comment.
    from service.clickhouse_client import get_client

    client = get_client()
    ddl = sql_path.read_text()
    for statement in ddl.split(";"):
        stmt = statement.strip()
        if stmt:
            client.command(stmt)
    log.info("Applied schema from %s", sql_path)


def ingest_once(cursor: datetime | None = None) -> datetime:
    tenant_id = settings.tenant_id
    if cursor is None:
        cursor = load_cursor(tenant_id)

    metrics = fetch_calls_since(cursor)
    if not metrics:
        log.info("No new calls since %s", cursor.isoformat())
        return cursor

    rows = [call_metric_to_row(m) for m in metrics]
    n = insert_calls(rows)

    new_cursor = max(m.started_at for m in metrics)
    if new_cursor.tzinfo is None:
        new_cursor = new_cursor.replace(tzinfo=timezone.utc)

    save_cursor(tenant_id, new_cursor)
    log.info("Ingested %s rows; cursor -> %s", n, new_cursor.isoformat())
    return new_cursor


def ingest_fixtures(path: Path) -> int:
    raw = load_fixtures(path)
    rows = [normalize(r) for r in raw]
    return insert_calls(rows)


def run_watch() -> None:
    interval = settings.poll_interval_seconds
    log.info("Watch mode: polling every %ss", interval)
    while True:
        try:
            ingest_once()
        except Exception:
            log.exception("Ingest cycle failed")
        time.sleep(interval)


def run_backfill(since: datetime) -> None:
    log.info("Backfill from %s", since.isoformat())
    cursor = since
    while True:
        metrics = fetch_calls_since(cursor)
        if not metrics:
            log.info("Backfill complete at cursor %s", cursor.isoformat())
            break

        rows = [call_metric_to_row(m) for m in metrics]
        insert_calls(rows)

        new_cursor = max(m.started_at for m in metrics)
        if new_cursor.tzinfo is None:
            new_cursor = new_cursor.replace(tzinfo=timezone.utc)
        save_cursor(settings.tenant_id, new_cursor)
        log.info("Backfill batch: %s rows, cursor -> %s", len(rows), new_cursor.isoformat())

        if new_cursor <= cursor:
            break
        cursor = new_cursor


def parse_since(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Invalid date: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hotel voice analytics ingester")
    parser.add_argument(
        "--init-schema",
        action="store_true",
        help="Apply sql/001_init.sql to ClickHouse",
    )
    parser.add_argument(
        "--load-fixtures",
        type=Path,
        metavar="PATH",
        help="Load JSONL fixtures into calls (offline demo)",
    )
    parser.add_argument("--watch", action="store_true", help="Poll zenlabs on an interval")
    parser.add_argument(
        "--backfill",
        type=parse_since,
        metavar="DATE",
        help="Replay poller from DATE (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Single poll cycle (zenlabs -> CH)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    if args.init_schema:
        init_schema(root / "sql" / "001_init.sql")
        return

    if args.load_fixtures:
        n = ingest_fixtures(args.load_fixtures)
        log.info("Loaded %s fixture rows", n)
        return

    if args.backfill:
        run_backfill(args.backfill)
        return

    if args.watch:
        run_watch()
        return

    if args.once:
        ingest_once()
        return

    parser.print_help()


if __name__ == "__main__":
    main()