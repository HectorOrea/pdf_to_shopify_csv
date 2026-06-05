"""Turns an enriched table 'robust' (ensures non-null fields) then organizes
the import-ready csv. Each product has a 'first row' containing product info,
all rows contain image info"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
import tool.types as t
import logging

logger = logging.getLogger(__name__)

SHOPIFY_COLUMNS = [
    "Title",
    "URL handle",
    "Vendor",
    "Inventory quantity",
    "Product image URL",
    "Image position",
    "Image alt text",
    ]

COLUMNS_TO_SOON_ADD = [
    "Description",
    "Product category",
    "Type",
    "SKU",
    "SEO Title",
    "SEO Description",
    "Google Shopping / Google Product Category",
    "Google Shopping / Gender",
    "Google Shopping / Age Group",
    "Variants (Option value, linkedto, etc)"]


@dataclass
class ShopifyExportConfig:
    currently_unused_field_placeholder: str = ""

# Removes non a-z, 0-9 characters and replaces with dashes, 
# collapses runs of multiple dashes, and trims dashes from ends
def handle_from_title(value: str) -> str:
    """ Turns a string into a valid url"""
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-") or "untitled-product"

def _base_first_row(order: t.RobustOrder) -> t.ShopifyFirstRow:
    title = order["title"]
    handle = handle_from_title(title)
    vendor = order["vendor"]
    quantity = order["quantity"] or 0

    row = {column: "" for column in SHOPIFY_COLUMNS}
    row.update(
        {
            "Title": title,
            "URL handle": handle,
            "Vendor": vendor,
            "Inventory quantity": str(quantity),
        }
    )
    return row

def _base_not_first_row(order: t.RobustOrder) -> t.ShopifyNotFirstRow:
    row = {column: "" for column in SHOPIFY_COLUMNS}
    return row

"""Creates all rows for a given order. Conceptualized as first row and not first rows"""
def shopify_rows_from_order(
    order: t.RobustOrder,
) -> Tuple[t.ShopifyFirstRow, List[t.ShopifyNotFirstRow]]:
    
    first_row = _base_first_row(order)

    if len(order["images"]) >= 1:
        first_image = order["images"][0]
        first_row["Product image URL"] = first_image["public_url"]
        first_row["Image position"] = "1"
        first_row["Image alt text"] = first_image["alt_text"] or ""

    not_first_rows = []

    handle = first_row["URL handle"]
    for index, image in enumerate(order["images"][1:], start=2):
        row = _base_not_first_row(order)
        row.update({
            "URL handle": handle, 
            "Product image URL": image["public_url"],
            "Image position": str(index), 
            "Image alt text": image["alt_text"] or "",
        })
        not_first_rows.append(row)

    return first_row, not_first_rows

"""Generates rows given an enriched table"""
def shopify_rows_from_robust_table(
    enriched_table: t.RobustOrderTable,
) -> List[t.ShopifyCSVRow]:
    
    orders = enriched_table["orders"]

    rows : List[t.ShopifyCSVRow] = []
    for order in orders:
        first_row, image_rows = shopify_rows_from_order(order)
        rows.append(first_row)
        rows.extend(image_rows)
    return rows

def make_robust_image(image : t.WeakImage) -> t.RobustImage | None:
    
    local_path = image["local_path"]
    public_url = image["public_url"]
    of_a_model = image["of_a_model"]
    cropped = image["cropped"]

    if local_path is None:
        return None
    if public_url is None:
        return None
    if of_a_model is None:
        return None
    if cropped is None:
        return None
    
    # Fill manually all the fields that might be None in WeakImage for mypy
    robust_img : t.RobustImage = {**image,
                                  "local_path" : local_path,
                                  "public_url" : public_url,
                                  "of_a_model" : of_a_model,
                                  "cropped" : cropped
                                  }
    return robust_img

def make_robust_order(order : t.EnrichedOrder) -> t.RobustOrder:
    robust_images : List[t.RobustImage] = []
    for img in order["images"]:
        robust_image = make_robust_image(img)
        if robust_image is None:
            idx = img["candidate_index"]
            order["warnings"].append(f"Image w idx {idx} is not robust, removed before csv")
        else:
            robust_images.append(robust_image)
    robust_order : t.RobustOrder = {**order,
                    "images" : robust_images}
    return robust_order

def make_robust_table(table : t.EnrichedOrderTable) -> t.RobustOrderTable:
    """
    To Add
        - Make this report back when an order is completely empty after making robust
    """
    robust_orders : List[t.RobustOrder] = []
    for o in table["orders"]:
        better_order = make_robust_order(o)
        if len(better_order["images"]) == 0:
            continue
        robust_orders.append(better_order)
    better_table : t.RobustOrderTable = {"orders" : robust_orders}
    return better_table



""" Calls for all rows then writes them into my output file"""
def write_shopify_csv(
    non_robust_table: t.EnrichedOrderTable,
    output_path: str | Path,
) -> Path:

    enriched_table = make_robust_table(non_robust_table)
    logger.info("finished making table robust")
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    rows = shopify_rows_from_robust_table(enriched_table)

    with output_file.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=SHOPIFY_COLUMNS) # writes headers
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    logger.info("finished writing csv")

    return output_file