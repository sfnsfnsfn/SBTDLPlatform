#!/usr/bin/env python3
"""CLI wrapper for ProjectDbBootstrap -- migrate legacy project data to SQLite.

Usage::

    python scripts/migrate_project_db.py <project_path> --dry-run
    python scripts/migrate_project_db.py <project_path> --rebuild-index
    python scripts/migrate_project_db.py <project_path> --check
    python scripts/migrate_project_db.py <project_path> --checkpoint

Commands
--------
--dry-run        Scan the project directory and print what would be done
                 without creating or modifying the SQLite index.
--rebuild-index  Full bootstrap: scan the project and populate/update the
                 SQLite index (project.sqlite).
--check          Compare the existing SQLite index against the filesystem
                 and report any mismatches.
--checkpoint     Run a WAL checkpoint on the project SQLite index.
--verbose, -v    Increase logging verbosity (debug level).

Exit codes
----------
0   Success
1   Error (invalid path, missing index, etc.)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap path resolution
#
# The new platform modules (project_db.py, project_db_bootstrap.py,
# sqlite_repositories/) live in the main repo but may not be visible from
# a git worktree.  We compute the main repo path and add it to sys.path so
# imports resolve correctly whether the script is run from the main repo
# or from a worktree.
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve()
_REPO_ROOT = str(_HERE.parents[1])  # scripts/.. = repo root

if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from anylabeling.platform.infrastructure.project_db import ProjectDb
from anylabeling.platform.infrastructure.project_db_bootstrap import (
    ProjectDbBootstrap,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate legacy project data to SQLite index.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s /path/to/project --dry-run\n"
            "  %(prog)s /path/to/project --rebuild-index\n"
            "  %(prog)s /path/to/project --check\n"
            "  %(prog)s /path/to/project --checkpoint\n"
        ),
    )
    parser.add_argument(
        "project_path",
        help="Path to the project directory (must exist)",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan without writing to DB; print what would be done",
    )
    group.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Full bootstrap: scan and populate the SQLite index",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help=(
            "Compare index against filesystem; report mismatches "
            "(requires existing index)"
        ),
    )
    group.add_argument(
        "--checkpoint",
        action="store_true",
        help="Run a WAL checkpoint on the project SQLite index",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Increase logging verbosity (debug level)",
    )

    return parser


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def _run_dry_run(project_path: Path) -> int:
    """Scan the project using an in-memory database and print counts."""
    db = ProjectDb(":memory:")
    db.open()

    bootstrap = ProjectDbBootstrap(db, project_path)
    report = bootstrap.run()

    db.close()

    print(f"DRY RUN for: {project_path}")
    print(f"  Assets:         {report.assets_processed}")
    print(f"  Annotations:    {report.annotations_processed}")
    print(f"  Dataset builds: {report.dataset_builds_processed}")
    print(f"  Runs:           {report.runs_processed}")
    print(f"  Models:         {report.models_processed}")
    if report.errors:
        print(f"  Errors:         {len(report.errors)}")
        for err in report.errors:
            print(f"    - {err}")

    db_path = project_path / "project.sqlite"
    if db_path.exists():
        _logger.warning(
            "A project.sqlite already exists at %s -- "
            "dry-run did not modify it.",
            db_path,
        )

    print("  (no changes written to disk)")
    return 0


def _run_rebuild_index(project_path: Path) -> int:
    """Full bootstrap: scan and write to the SQLite index."""
    db_path = project_path / "project.sqlite"
    db = ProjectDb(db_path)
    db.open()

    bootstrap = ProjectDbBootstrap(db, project_path)
    report = bootstrap.run()

    db.close()

    print(f"Rebuilt index for: {project_path}")
    print(f"  Assets:         {report.assets_processed}")
    print(f"  Annotations:    {report.annotations_processed}")
    print(f"  Dataset builds: {report.dataset_builds_processed}")
    print(f"  Runs:           {report.runs_processed}")
    print(f"  Models:         {report.models_processed}")
    if report.errors:
        print(f"  Errors:         {len(report.errors)}")
        for err in report.errors:
            print(f"    - {err}")

    return 0


def _run_check(project_path: Path) -> int:
    """Compare DB index against the filesystem."""
    db_path = project_path / "project.sqlite"
    if not db_path.exists():
        print(
            f"Error: No SQLite index found at {db_path}. "
            "Run --rebuild-index first.",
            file=sys.stderr,
        )
        return 1

    db = ProjectDb(db_path)
    db.open()

    # Gather DB asset paths
    rows = db.query_all("SELECT rel_path FROM assets")
    db_assets: set[str] = {row["rel_path"] for row in rows}

    # Walk filesystem assets/
    assets_dir = project_path / "assets"
    fs_assets: set[str] = set()
    if assets_dir.is_dir():
        for p in assets_dir.rglob("*"):
            if p.is_file():
                fs_assets.add(p.relative_to(assets_dir).as_posix())

    db.close()

    only_in_db = db_assets - fs_assets
    only_in_fs = fs_assets - db_assets

    print(f"Consistency check for: {project_path}")
    print(f"  DB assets:            {len(db_assets)}")
    print(f"  Filesystem assets:    {len(fs_assets)}")

    if only_in_db:
        print(f"  In DB but not on disk:  {len(only_in_db)}")
        for path in sorted(only_in_db):
            print(f"    - {path}")

    if only_in_fs:
        print(f"  On disk but not in DB:  {len(only_in_fs)}")
        for path in sorted(only_in_fs):
            print(f"    - {path}")

    if not only_in_db and not only_in_fs:
        print("  Index is consistent with filesystem.")

    return 0


def _run_checkpoint(project_path: Path) -> int:
    """Run a WAL checkpoint (truncate) on the SQLite index."""
    db_path = project_path / "project.sqlite"
    if not db_path.exists():
        print(
            f"Error: No SQLite index found at {db_path}. "
            "Run --rebuild-index first.",
            file=sys.stderr,
        )
        return 1

    db = ProjectDb(db_path)
    db.open()
    db.checkpoint(truncate=True)
    db.close()

    print(f"WAL checkpoint completed for: {project_path}")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate command handler.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    project_path = Path(args.project_path)
    if not project_path.is_dir():
        print(
            f"Error: '{args.project_path}' is not a valid directory.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        return _run_dry_run(project_path)
    elif args.rebuild_index:
        return _run_rebuild_index(project_path)
    elif args.check:
        return _run_check(project_path)
    elif args.checkpoint:
        return _run_checkpoint(project_path)

    # No command specified -- show help
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
