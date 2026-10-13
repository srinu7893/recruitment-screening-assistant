import argparse
import json
from pathlib import Path

from .core import evaluate


def main():
    parser = argparse.ArgumentParser(description="Validate structured screening evidence and route for review")
    parser.add_argument("input", type=Path, help="JSON assessment envelope")
    args = parser.parse_args()
    try:
        result = evaluate(json.loads(args.input.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f"Assessment failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
