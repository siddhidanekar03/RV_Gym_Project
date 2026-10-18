#!/usr/bin/env python3
"""
Wrapper script for pre-migration staging target verification.
Usage:
    python scripts/verify_staging_migration_target.py
"""
import os
import sys

# Ensure root workspace is in sys.path
workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from backend.app.cli.verify_staging_migration_target import main

if __name__ == "__main__":
    main()
