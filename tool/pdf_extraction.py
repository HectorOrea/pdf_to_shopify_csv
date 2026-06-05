"""
Extracts pdf data and formats it in OrderTable schema
"""


import pdfplumber
from pathlib import Path
import tool.types as t
from openai import OpenAI
import logging
import json

logger = logging.getLogger(__name__)

def process_pdf(pdf_path: Path) -> t.OrderTable:
    """
    Assumptions:
        - PDF's biggest table contains vendors, product_codes, and quantities
        - PDF is extractable with pdf plumber (might not be the case for simpler "scans")
        - openAI can turn the raw table data into JSON
    Failure modes:
        - PDF not scraped

    Things to consider / add
    - What if the pdf is multiple pages?
    - What is the table isn't explicit?

    """

    print(f"Processing: {pdf_path}")
    with pdfplumber.open(pdf_path) as pdf:
        p0 = pdf.pages[0]
        raw_table = p0.extract_table()
    target_schema = {
        "type": "object",
        "properties": {
            "orders": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "vendor": {"type": "string"},
                        "product_code": {"type": "string"},
                        "quantity": {"type": "integer"}
                    },
                    "required": ["vendor", "product_code", "quantity"]
                }
            }
        },
        "required": ["orders"],

        "example_output": [
        {
            "vendor": "Zara",
            "product_code": "ZR-44321",
            "quantity": 12
        } ],

        "normalization_rules": [
            "Do not modify product_code at all, leave it as is",
            "Convert quantity to integer",
            "Remove units like 'pcs' or 'units'",
            "Do not invent missing values",
            "If quantity is missing, set it to null"
            ]
    }

    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # or "gpt-4o" if you want higher quality
        messages=[
            {
                "role": "system",
                "content": "You are a data normalization engine. Return only valid JSON."
            },
            {
                "role": "user",
                "content": f"""
                    Here is raw table data: {raw_table}
                    Normalize it to this schema: {target_schema}
                    Return only JSON.
                    """
            }
        ],
        response_format={"type": "json_object"},
        temperature=0
    )

    structured_content = response.choices[0].message.content

    if not structured_content:
        logger.error("AI returned empty response")
        raise
    
    try:
        normalized_table = json.loads(structured_content) # turn string representing JSON object into python dict
    except json.JSONDecodeError:
        logger.error("AI returned invalid JSON: %s", structured_content)
        raise

    return normalized_table