"""
Orchestrates web scraping, image selection, and local downloads for each order. 
Searches {vendor} {product_code} and scrapes contents of the first link, generates
page data, then a page analysis, then downloads selected images.
"""


from openai import OpenAI
from pathlib import Path
import tool.types as t

from curl_cffi import requests

from tool.webscrape import search_first_link, fetch_product_page_data
from tool.webscrape import build_images_from_page_data

from tool.image_selection import analyze_product_page, get_images_from_analysis

from tool.local_download import download_images

def enrich_order_from_search(
    row: t.Order,
    openai_client: OpenAI | None = None,
    session: requests.Session | None = None,
    image_base_path: Path =Path("product_images"),
    debug: bool = False,
) -> t.EnrichedOrder:
    """
    Given a row, returns enriched row by getting page_analysis and downloading images
    Assumptions:
        - Googling {vendor} {product code} results in the correct first link
        - calls _search_first_link, _fetch_product_page_data, _analyze_product_page

    Failure Modes:
        - Missing vendor or product code in order
        - Unable to determine a top link for f"{vendor} {product_code}

    To Add
        - If page analysis from beautifulsoup'ed pageData is unsatisfactory,
        use Playwright

    """

    openai_client = openai_client or OpenAI()
    session = session or requests.Session()
    
    vendor = row.get("vendor")
    product_code = row.get("product_code")
    warnings = []

    title = f"{vendor} {product_code}".strip()

    if not vendor or not product_code:
        warnings.append("Empty vendor or product code")
        enriched_row: t.EnrichedOrder = {
            **row,
            "title": title,
            "images": [],
            "warnings": warnings,
            "main_url": "",
            "debug": None 
            }
        return enriched_row
   
    query = title
    first_link = search_first_link(query)

    if not first_link:
        warnings.append(f"Could not find a top link for {query}")
        warnings.append("Could not determine product title from the source page; using vendor + product code.")

        enriched_row = {
            **row,
            "title": title,
            "images": [],
            "warnings": warnings,
            "main_url": "",
            "debug": None 
            }
        
        return enriched_row

    main_url = first_link
    # TODO: Add warning for infeasible first_links
    # Will need allow_lists for brands and check that either the vendor name
    # or smth on the allow list is in the url


    page_data = fetch_product_page_data(first_link, session)
    warnings.extend(page_data["warnings"])
    candidate_images = build_images_from_page_data(page_data)

    page_analysis = analyze_product_page(
        page_data,
        candidate_images,
        row,
        openai_client,
        debug
    )

    analysis_title = page_analysis.get("product_title")
    if analysis_title:
        title = analysis_title
    # Else: remain as f"{vendor} {product_code}".strip()

    analysis_error = page_analysis["error"]
    if analysis_error:
        warnings.append(analysis_error)
    # Else: remain as f"{vendor} {product_code}".strip()

    selected_images, analysis_result_error = get_images_from_analysis(page_analysis, candidate_images)
    
    if analysis_result_error:
        warnings.append(analysis_result_error)
       
    downloaded_images, download_errors = download_images(row, selected_images, image_base_path, session)

    if download_errors:
        warnings.extend(download_errors)

    debug_dict : t.OrderDebugDict | None
    if debug:
        debug_dict = {
            "page_data" : page_data,
            "page_analysis" : page_analysis
        }
    else:
        debug_dict = None
    
    enriched_row = {
            **row,
            "title": title,
            "images": downloaded_images,
            "warnings": warnings,
            "main_url": main_url,
            "debug": debug_dict 
        }
    return enriched_row

def add_images_to_table(
    table: t.OrderTable, openai_client: OpenAI | None = None,
    image_base_path: Path = Path("product_images"),
    debug: bool = False) -> t.EnrichedOrderTable:

    openai_client = openai_client or OpenAI()
    session = requests.Session()
    orders = table["orders"]
    enriched = []
    for row in orders:
        enriched_row = enrich_order_from_search(
            row,
            openai_client=openai_client,
            session=session,
            image_base_path=image_base_path,
            debug=debug
        )
        enriched.append(enriched_row)
    return {"orders": enriched}