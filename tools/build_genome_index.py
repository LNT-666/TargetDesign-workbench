#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command-line entry point for building the local genome index."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from search.genome_index import main  # noqa: E402


if __name__ == "__main__":
    main()
