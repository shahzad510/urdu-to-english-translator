"""Allow ``python -m urdu_translator`` to open the desktop application."""

from urdu_translator.app import main

if __name__ == "__main__":
    raise SystemExit(main())
