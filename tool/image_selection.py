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

MAX_NUM_SELECTED_IMAGES = 10
DEFAULT_INVALID_CONFIDENCE = 3.0
DEFAULT_FALLBACK_CONFIDENCE = 0.0


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
        "\"image_data\": ["
        "{\"candidate_index\": candidate image index as an int, "
        "\"confidence\": confidence from 0 to 10 as a number}"
        "]}.\n"
        "The candidate images are passed through as their index, their url, "
        "and their alt text (if applicable). Only choose indices from the set provided. "
        "Prefer full product photos over logos, icons, or unrelated graphics. "
        "Return an empty image_data list if none look like product images. "
        "Confidence should be 10 only when you are certain the image shows the exact product, "
        "and 0 when you are certain it does not. "
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
        image_data = _fallback_image_data(candidate_images)
        idx = [image["candidate_index"] for image in image_data]
        analysis : t.ProductPageAnalysis = {
            "product_title" : None,
            "candidate_images" : candidate_images,
            "selected_image_indices": idx,
            "selected_image_data": image_data,
            "error" : "OpenAI returned empty analysis.",
            "summary" : page_summary if debug else None,
            "raw_AI_output" : content if debug else None
        }
        return analysis
    
    try:
        parsed = json.loads(content) 
    except json.JSONDecodeError:
        image_data = _fallback_image_data(candidate_images)
        idx = [image["candidate_index"] for image in image_data]
        analysis = {
            "product_title" : None,
            "candidate_images" : candidate_images,
            "selected_image_indices": idx,
            "selected_image_data": image_data,
            "error" : "Could not parse OpenAI product-page analysis.",
            "summary" : page_summary if debug else None,
            "raw_AI_output" : content if debug else None
        }
        return analysis
    
    pt = parsed.get("product_title")
    image_data = parsed.get("image_data")

    error_parts = []

    if pt is None:
        error_parts.append("Analysis did not result in a product_title")
    if image_data is None:
        legacy_indices = parsed.get("image_indices")
        if legacy_indices is not None:
            image_data = [
                {
                    "candidate_index": candidate_index,
                    "confidence": DEFAULT_INVALID_CONFIDENCE,
                }
                for candidate_index in legacy_indices
            ]
            error_parts.append(
                "Analysis returned legacy image_indices without confidence; using default confidence"
            )
        else:
            image_data = []
            error_parts.append("Analysis did not result in image_data")
    error = " and ".join(error_parts) or None
    idx = [
        selection.get("candidate_index")
        for selection in image_data
        if isinstance(selection, dict)
    ]

    analysis = {
            "product_title" : pt,
            "candidate_images" : candidate_images,
            "selected_image_indices": idx,
            "selected_image_data": image_data,
            "error" : error,
            "summary" : page_summary if debug else None,
            "raw_AI_output" : content if debug else None
        }

    return analysis


def _fallback_image_data(candidate_images: List[t.CandidateImage]) -> List[t.SelectedImageData]:
    return [
        {
            "candidate_index": candidate["candidate_index"],
            "confidence": DEFAULT_FALLBACK_CONFIDENCE,
        }
        for candidate in candidate_images[:MAX_NUM_SELECTED_IMAGES]
    ]

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
    selected_image_data = page_analysis.get("selected_image_data")
    if selected_image_data is None:
        selected_indices = page_analysis["selected_image_indices"] or []
        selected_image_data = [
            {
                "candidate_index": candidate_index,
                "confidence": DEFAULT_INVALID_CONFIDENCE,
            }
            for candidate_index in selected_indices
        ]
    selected_images = []
    errors: list[str] = []

    if not selected_image_data:
        n = min(MAX_NUM_SELECTED_IMAGES, len(candidate_images))
        error = f"OpenAI decided no candidate images were valid, returning first {n} instead"
        images = [_image_from_candidate_image(candidate) for candidate in candidate_images[:n]]
        for image in images:
            image["confidence"] = DEFAULT_FALLBACK_CONFIDENCE
        return images, error

    selected_by_index: dict[int, tuple[float, list[str]]] = {}
    for selection in selected_image_data:
        if not isinstance(selection, dict):
            errors.append("OpenAI returned at least 1 image_data item that was not an object")
            continue

        raw_index = selection.get("candidate_index")
        if isinstance(raw_index, bool): # Since python interprets bool as a subset of int
            errors.append("OpenAI returned at least 1 image_data item without a valid candidate_index")
            continue
        try:
            i = int(raw_index)
        except (TypeError, ValueError):
            errors.append("OpenAI returned at least 1 image_data item without a valid candidate_index")
            continue

        if i < 0 or i >= len(candidate_images):
            errors.append("OpenAI returned at least 1 impossible candidate_index")
            continue

        image_errors = []
        raw_confidence = selection.get("confidence")
        if isinstance(raw_confidence, bool):
            confidence = DEFAULT_INVALID_CONFIDENCE
            image_errors.append(
                f"OpenAI returned invalid confidence {raw_confidence!r}; defaulted to {DEFAULT_INVALID_CONFIDENCE}"
            )
        else:
            try:
                confidence = float(raw_confidence)
            except (TypeError, ValueError):
                confidence = DEFAULT_INVALID_CONFIDENCE
                image_errors.append(
                    f"OpenAI returned invalid confidence {raw_confidence!r}; defaulted to {DEFAULT_INVALID_CONFIDENCE}"
                )
        if confidence < 0 or confidence > 10:
            image_errors.append(
                f"OpenAI returned confidence {confidence} outside 0-10; defaulted to {DEFAULT_INVALID_CONFIDENCE}"
            )
            confidence = DEFAULT_INVALID_CONFIDENCE

        # Handles duplicate indices
        existing = selected_by_index.get(i)
        if existing is None or confidence > existing[0]:
            selected_by_index[i] = (confidence, image_errors)

    ranked_images = sorted(
        selected_by_index.items(),
        key=lambda item: (-item[1][0], item[0]),
    )

    for i, (confidence, image_errors) in ranked_images[:MAX_NUM_SELECTED_IMAGES]:
        img = _image_from_candidate_image(candidate_images[i])
        img["confidence"] = confidence
        img["errors"].extend(image_errors)
        selected_images.append(img)

    if not selected_images:
        n = min(MAX_NUM_SELECTED_IMAGES, len(candidate_images))
        errors.append(f"No valid candidate image indices returned by AI, returning first {n} instead")
        selected_images = [
            _image_from_candidate_image(candidate)
            for candidate in candidate_images[:n]
        ]
        for image in selected_images:
            image["confidence"] = DEFAULT_FALLBACK_CONFIDENCE

    error = " and ".join(errors) or None
    return selected_images, error
