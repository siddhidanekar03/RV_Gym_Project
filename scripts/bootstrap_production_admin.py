#!/usr/bin/env python3
"""
Wrapper script for production administrator bootstrap.
Supports interactive password prompt to avoid storing passwords in shell history.
Usage:
    python scripts/bootstrap_production_admin.py --email admin@rvfitness.in --name "System Administrator"
"""
import getpass
import os
import sys

workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from backend.app.core.config import settings
from backend.app.cli.bootstrap_admin import main

FORBIDDEN_KEYWORDS = ["staging", "test", "smoke", "dev", "mock", "sandbox"]


def verify_production_bootstrap_environment() -> None:
    """Ensure bootstrap wrapper cannot execute against staging, development, or test databases."""
    env = (os.environ.get("ENVIRONMENT") or settings.ENVIRONMENT or "").strip().lower()
    if env != "production":
        raise ValueError(
            f"SAFETY VIOLATION: bootstrap_production_admin.py requires ENVIRONMENT='production'. "
            f"Detected environment '{env or '<unset>'}'. Accidental execution against non-production environments is forbidden. "
            "For non-production administrative setup, use backend/app/cli/bootstrap_admin.py directly."
        )

    db_url = (os.environ.get("DATABASE_URL") or settings.DATABASE_URL or "").lower()
    for kw in FORBIDDEN_KEYWORDS:
        if kw in db_url:
            raise ValueError(
                f"SAFETY VIOLATION: Target database URL contains non-production keyword '{kw}'. "
                "Refusing to execute production admin bootstrap on a non-production database."
            )


if __name__ == "__main__":
    try:
        verify_production_bootstrap_environment()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # If password is not provided as a CLI argument, securely prompt for it
    has_password_arg = any(arg == "--password" or arg.startswith("--password=") for arg in sys.argv)
    if not has_password_arg:
        try:
            pw = getpass.getpass("Enter Administrator Password (min 8 chars): ")
            pw_confirm = getpass.getpass("Confirm Administrator Password: ")
            if pw != pw_confirm:
                print("ERROR: Passwords do not match. Bootstrap aborted.", file=sys.stderr)
                sys.exit(1)
            sys.argv.extend(["--password", pw])
        except (KeyboardInterrupt, EOFError):
            print("\nBootstrap cancelled by user.", file=sys.stderr)
            sys.exit(1)

    sys.exit(main())
