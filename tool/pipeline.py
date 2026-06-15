""" Orchestrates the pdf-to-csv pipeline. Extracts orders from the input pdf,
enriches these with scraped images of the products, uploads them to shopify,
and generates the csv which updates the product catalogue when imported to Shopify """


from pathlib import Path

from tool.debug_view import create_visual_aid

from tool.pdf_extraction import process_pdf

from tool.enrichment import add_images_to_table

from tool.shopify_formatting import write_shopify_csv
from tool.shopify_upload_files import upload_enriched_table_images_to_shopify

import logging

logger = logging.getLogger(__name__)

def run_pipeline(pdf_path: Path, output_path: Path | str = "bulk-add.csv") -> Path:
    if not pdf_path.exists():
        raise FileNotFoundError(f"File '{pdf_path}' not found.")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"'{pdf_path}' is not a PDF.")

    # Turn pdf into simple JSON (vendors, product codes, quantity).
    initial_table = process_pdf(pdf_path)

    enriched_table = add_images_to_table(initial_table)
    logger.info("finished adding images to table")
    
    create_visual_aid(enriched_table)
    logger.info("finished creating visual debugging aid")
    uploaded_table = upload_enriched_table_images_to_shopify(enriched_table)
    logger.info("finished uploading all files")
    output_file = write_shopify_csv(uploaded_table, output_path)
    logger.info("finished writing output file")
    return output_file
