"""
Generates the product analysis and turns the analysis into
image objects. Analysis involves first getting a page summary then passing it
to OpenAI to select the 'best' images. 

Also includes util functions to convert analysis into Image Objects
"""

from typing import List
import tool.types as t

import json

from openai import OpenAI

from tool.webscrape import get_page_summary


def analyze_product_page(
    page_data: t.ProductPageData,
    candidate_images: List[t.CandidateImage],
    order: t.Order,
    openai_client: OpenAI,
    debug: bool = False
    ) -> t.ProductPageAnalysis:
    """
    Note this is AI facing and does nothing except call to generate a summary, take the analysis, turn it into
    a good JSON (if possible) and report that back. Must be validated and 
    built into image objects in enrich_order
    Assumptions:
        - The correct image can be deduced from the url alone

    Failure Mode:
        - The urls alone aren't enough to decide which is the product image
        - openai fails to respond
        - openai returns an invalid json
        - 

    To Add
        - Confidence scores
    """
    
    page_summary = get_page_summary(page_data, candidate_images)
    vendor = order["vendor"]
    product_code = order["product_code"]
    prompt = (
        f"Vendor: {vendor}\n"
        f"Product code: {product_code}\n"
        "You are reviewing a product page summary.\n"
        "Return ONLY a JSON object with no markdown, code fences, or explanation.\n"
        "Format: "
        "{\"product_title\": \"best page title or empty string\", "
        "\"image_indices\": [list of candidate image indices (as ints) that are photos of the product]}.\n"
        "The candidate images are passed through as their index, their url,"
        "and their alt text (if applicable). Only choose indices from the set provided."
        "Prefer full product photos over logos, icons, or unrelated graphics"
        "Return an empty list if none look like product images"
        "If you cannot confidently identify the product title, return an empty string for product_title.\n"
        f"Page summary:\n{page_summary}"
    )
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You identify retail product titles and matching product photos from webpage content."
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    content = response.choices[0].message.content
    if not content:
        idx = list(range(len(page_data["image_urls"])))
        analysis : t.ProductPageAnalysis = {
            "product_title" : None,
            "candidate_images" : candidate_images,
            "selected_image_indices": idx,
            "error" : "OpenAI returned empty analysis.",
            "summary" : page_summary if debug else None,
            "raw_AI_output" : content if debug else None
        }
        return analysis
    
    try:
        parsed = json.loads(content) 
    except json.JSONDecodeError:
        idx = list(range(len(page_data["image_urls"])))
        analysis = {
            "product_title" : None,
            "candidate_images" : candidate_images,
            "selected_image_indices": idx,
            "error" : "Could not parse OpenAI product-page analysis.",
            "summary" : page_summary if debug else None,
            "raw_AI_output" : content if debug else None
        }
        return analysis
    
    pt = parsed.get("product_title")
    idx = parsed.get("image_indices")

    error_parts = []

    #TODO: Handle error when 
    if pt is None:
        error_parts.append("Analysis did not result in a product_title")
    if idx is None:
        error_parts.append("Analysis did not result in indices")
    error = " and ".join(error_parts) or None

    analysis = {
            "product_title" : pt,
            "candidate_images" : candidate_images,
            "selected_image_indices": idx,
            "error" : error,
            "summary" : page_summary if debug else None,
            "raw_AI_output" : content if debug else None
        }

    return analysis

def _image_from_candidate_image(candidate : t.CandidateImage) -> t.WeakImage:
    img : t.WeakImage = { **candidate,
           "local_path" : None,
           "public_url" : None,
           "confidence" : 0,
           "of_a_model" : False,
           "cropped" : False,
           "errors" : []
    }
    return img

def get_images_from_analysis(
        page_analysis: t.ProductPageAnalysis, 
        candidate_images: List[t.CandidateImage],
        ) -> tuple[List[t.WeakImage], str | None]:
    "Assumes the indices of the input CandidateImage list is equivalent to"
    "those returned by the AI"
    selected_indices = page_analysis["selected_image_indices"]
    selected_images = []
    error = None

    if not selected_indices:
        n = min(10, len(candidate_images))
        error = f"OpenAI decided no candidate images were valid, returning first {n} instead"
        images = [_image_from_candidate_image(candidate) for candidate in candidate_images[:n]]
        return images, error

    for i in selected_indices:
        if i < 0 or i >= len(candidate_images):
            error = "at least 1 impossible index returned by AI"
            continue
        img = _image_from_candidate_image(candidate_images[i])
        selected_images.append(img)

    return selected_images, error