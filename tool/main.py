"""
Parses args and starts pipeline
"""

import argparse
import logging
from dotenv import load_dotenv
from pathlib import Path
import sys

from tool.pipeline import run_pipeline

load_dotenv()

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")

def main():

    parser = argparse.ArgumentParser(
        description="Do something with a PDF file"
    )
    parser.add_argument(
        "pdf",
        type=Path,
        help="Path to the PDF file"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("bulk-add.csv"),
        help="Path to write the Shopify CSV file"
    )

    args = parser.parse_args()

    try:
        run_pipeline(args.pdf, args.output)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()