import argparse
import asyncio
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pixivpy_async as pa


README_ROW_RE = re.compile(
    r"^\|\s*\[(?P<filename>[^\]]+)\]\([^)]*\)\s*\|.*?\|\s*\[(?P<label>[^\]]+)\]\((?P<source>https://www\.pixiv\.net/artworks/(?P<pid>\d+))\)\s*\|",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PixivEntry:
    filename: str
    pid: int


def build_parser() -> argparse.ArgumentParser:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Update wallpaper mtimes from Pixiv publication dates.",
    )
    parser.add_argument(
        "--readme",
        type=Path,
        default=script_dir.parent / "README.md",
        help="Path to the wallpaper README table.",
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=script_dir / "refresh_token.txt",
        help="Path to the Pixiv refresh token file.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=8.0,
        help="Seconds to wait between Pixiv requests.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned updates without changing file mtimes.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N Pixiv rows from the README.",
    )
    parser.add_argument(
        "--pid",
        type=int,
        action="append",
        default=None,
        help="Only process specific Pixiv artwork ID(s). Can be passed multiple times.",
    )
    parser.add_argument(
        "--filename",
        action="append",
        default=None,
        help="Only process specific filename(s). Can be passed multiple times.",
    )
    return parser


def parse_readme(readme_path: Path) -> list[PixivEntry]:
    entries: list[PixivEntry] = []

    with readme_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            match = README_ROW_RE.match(line.strip())
            if not match:
                continue
            entries.append(
                PixivEntry(
                    filename=match.group("filename"),
                    pid=int(match.group("pid")),
                )
            )

    return entries


def load_refresh_token(token_file: Path) -> str:
    return token_file.read_text(encoding="utf-8").strip()


async def fetch_create_dates(
    entries: list[PixivEntry],
    refresh_token: str,
    delay_seconds: float,
) -> dict[int, datetime]:
    pid_to_date: dict[int, datetime] = {}
    unique_pids = sorted({entry.pid for entry in entries})

    async with pa.PixivClient() as client:
        api = pa.AppPixivAPI(client=client)
        await api.login(refresh_token=refresh_token)

        for index, pid in enumerate(unique_pids, start=1):
            response = await api.illust_detail(pid)
            create_date = datetime.fromisoformat(response.illust.create_date)
            pid_to_date[pid] = create_date
            print(
                f"[{index}/{len(unique_pids)}] pid={pid} published={create_date.isoformat()}"
            )

            if index != len(unique_pids):
                await asyncio.sleep(delay_seconds)

    return pid_to_date


def apply_mtime_updates(
    entries: list[PixivEntry],
    pid_to_date: dict[int, datetime],
    base_dir: Path,
    dry_run: bool,
) -> tuple[int, int]:
    updated = 0
    missing = 0
    filenames_by_pid: dict[int, list[str]] = defaultdict(list)
    for entry in entries:
        filenames_by_pid[entry.pid].append(entry.filename)

    for pid, filenames in filenames_by_pid.items():
        timestamp = pid_to_date[pid].timestamp()
        iso_date = pid_to_date[pid].isoformat()
        for filename in filenames:
            image_path = base_dir / filename
            if not image_path.exists():
                missing += 1
                print(f"missing: {image_path}")
                continue

            if dry_run:
                print(f"dry-run: {image_path} -> {iso_date}")
            else:
                os.utime(image_path, (timestamp, timestamp))
                print(f"updated: {image_path} -> {iso_date}")
            updated += 1

    return updated, missing


async def async_main(args: argparse.Namespace) -> int:
    readme_path = args.readme.resolve()
    token_file = args.token_file.resolve()
    base_dir = readme_path.parent

    entries = parse_readme(readme_path)
    if not entries:
        print(f"no Pixiv entries found in {readme_path}")
        return 1

    if args.pid:
        pid_filter = set(args.pid)
        entries = [entry for entry in entries if entry.pid in pid_filter]

    if args.filename:
        filename_filter = {name.strip() for name in args.filename if name.strip()}
        entries = [entry for entry in entries if entry.filename in filename_filter]

    if args.limit is not None:
        entries = entries[: args.limit]

    if not entries:
        print("no rows matched the provided filters")
        return 1

    refresh_token = load_refresh_token(token_file)
    pid_to_date = await fetch_create_dates(
        entries=entries,
        refresh_token=refresh_token,
        delay_seconds=args.delay_seconds,
    )
    updated, missing = apply_mtime_updates(
        entries=entries,
        pid_to_date=pid_to_date,
        base_dir=base_dir,
        dry_run=args.dry_run,
    )

    print(
        f"done: {updated} files processed, {len(pid_to_date)} Pixiv requests, {missing} missing files"
    )
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
