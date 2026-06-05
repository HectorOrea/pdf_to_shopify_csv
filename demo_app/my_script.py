from pathlib import Path

from tool.pipeline import run_pipeline


def process_pdf_to_csv(input_path: Path, output_path: Path) -> Path:
    """
    Run the real Moda PDF-to-Shopify-CSV pipeline for the demo app.
    """
    return run_pipeline(input_path, output_path)
