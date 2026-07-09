"""Deprecated ``hippo`` console-script alias (ADR-0004).

The ``hippo`` command is now ``mosaic``. This wrapper prints a one-line
deprecation notice to **stderr** (stdout stays script-safe) and delegates
to the real Typer app.
"""

import sys


def legacy_main() -> None:
    """Entry point for the legacy ``hippo`` console script."""
    print(
        "warning: the 'hippo' command has been renamed to 'mosaic' "
        "(ADR-0004); this alias will be removed in a future release.",
        file=sys.stderr,
    )
    from mosaic.cli.main import app

    app()
