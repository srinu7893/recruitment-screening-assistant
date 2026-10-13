"""Backup and integrity checks without logging profile contents."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3


def backup(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        raise ValueError("Source database does not exist")
    if destination.exists():
        raise ValueError("Backup destination must be new")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.touch(mode=0o600)
    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(destination)) as target:
                original.backup(target)
                result = target.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise ValueError("Backup integrity check failed")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def main():
    parser = argparse.ArgumentParser(description="Create a verified SQLite backup")
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()
    try:
        backup(args.source, args.destination)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(2, f"Backup failed: {exc}\n")
    print("Backup created and integrity verified.")


if __name__ == "__main__":
    main()
