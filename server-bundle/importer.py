#!/usr/bin/env python3
"""Thin CLI entry point for the VirtueMart product importer.

    python importer.py products.csv --dry-run     # plan only, zero writes
    python importer.py products.csv --import      # writes (asks confirmation)
    python importer.py products.csv --validate-only
"""
import sys

from vmimporter.cli import main

if __name__ == "__main__":
    sys.exit(main())
