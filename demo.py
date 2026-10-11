#!/usr/bin/env python
"""Same entrypoint as `uv run demo`, for people who would rather run a file."""

import sys

from agentic_tox.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
