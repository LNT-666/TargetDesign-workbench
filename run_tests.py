#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-command test runner with an optional mandatory BLAST gate."""

import argparse
import os
import shutil
import subprocess
import sys
import unittest


ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "shared"))

BLAST_TOOLS = ("blastn", "makeblastdb")


def check_blast_tools():
    """Return tool versions, or a clear error when the mandatory gate fails."""
    versions = {}
    for command in BLAST_TOOLS:
        path = shutil.which(command)
        if path is None:
            return None, "missing required tool: %s" % command
        try:
            result = subprocess.run(
                [command, "-version"], capture_output=True, text=True)
        except OSError as exc:
            return None, "version/command failure: %s (%s)" % (
                command, exc)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return None, "version/command failure: %s (%s)" % (
                command, detail or "exit %d" % result.returncode)
        text = (result.stdout or result.stderr or "").strip()
        versions[command] = text.splitlines()[0] if text else path
    return versions, ""


def build_suite(only_blast=False):
    loader = unittest.TestLoader()
    if only_blast:
        return loader.loadTestsFromName("tests.test_blast_integration")
    return loader.discover(os.path.join(ROOT, "tests"))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the programfile test suite.")
    parser.add_argument(
        "--require-blast", action="store_true",
        help="Fail before discovery when BLAST+ is missing or unusable; "
             "also reject skipped real-BLAST tests.")
    parser.add_argument(
        "--only-blast", action="store_true",
        help="Run only tests/test_blast_integration.py.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.require_blast:
        versions, reason = check_blast_tools()
        if versions is None:
            print("BLAST required gate failed: %s" % reason)
            return 1
        for command in BLAST_TOOLS:
            print("%s: %s" % (command, versions[command]))

    suite = build_suite(only_blast=args.only_blast)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.require_blast:
        blast_skips = [
            "%s (%s)" % (test, reason)
            for test, reason in result.skipped
            if "test_blast_integration" in test.id()
        ]
        if result.testsRun == 0 or blast_skips:
            print("BLAST required gate failed: real-BLAST tests did not run")
            for skipped in blast_skips:
                print("  skipped: %s" % skipped)
            return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
