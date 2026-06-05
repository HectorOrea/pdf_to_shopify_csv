"""
Downloads images to local directory
"""

from urllib.parse import urlsplit, urlunsplit, urlparse
import re
from typing import List, Tuple
from pathlib import Path
from curl_cffi.requests.exceptions import RequestException
import tool.types as t
from curl_cffi import requests

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "referer": "https://www.adidas.com/us/y-3-aop-knit-crew/JX7332.html",
    "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "macOS",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
}



def _fallback_image_url_without_query(image_url: str) -> str | None:
    """
    Some commerce CDNs append resizing directives in the query string, e.g.
    '?sw=588&sh=782'. Those usually work, but when they do not, the base asset
    without the transformation query is often still a valid image.

    We use this as a retry target only after the original URL fails, so we keep
    the primary fetch behavior faithful to what the site provided.
    """
    parts = urlsplit(image_url)
    if not parts.query:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))


def _to_safe_segment(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value)[:48]


def download_images(
        row: t.Order, 
        selected_images: List[t.WeakImage], 
        base_dir: Path, 
        session: requests.Session) -> Tuple[List[t.WeakImage], List[str]]:
    """
    downloads and adds local_paths for all images, returns images it was successful for
    """

    vendor = row["vendor"]
    product_code = row["product_code"]
    safe_vendor = _to_safe_segment(vendor or "vendor")
    safe_code = _to_safe_segment(product_code or "pc")

    downloaded_images = []
    errors = []
    none_downloaded = True
    for (i, img) in enumerate(selected_images):
        url = img["src_url"]
        response = None
        final_exc = None

        # Try the exact scraped URL first. If that fails and the URL carries a
        # transformation query (common on image CDNs), retry the base asset
        # without the query string before giving up.
        candidate_urls = [url]
        #TODO: See how necessary this fallback image thing is
        fallback_url = _fallback_image_url_without_query(url)
        if fallback_url and fallback_url != url:
            candidate_urls.append(fallback_url)

        for candidate_url in candidate_urls:
            try:
                response = session.get(candidate_url, headers=HEADERS, timeout=20, stream=True)
                response.raise_for_status()
                if candidate_url != url:
                    img["src_url"] = candidate_url
                break
            except RequestException as exc:
                final_exc = exc
                response = None

        if response is None:
            candidate_index = img["candidate_index"]
            errors.append(f"Failed to download candidate {candidate_index} from {url}: {final_exc}")
            img["local_path"] = None
            continue
        
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix or ".jpg"
        filename = f"{safe_vendor}_{safe_code}_{i}{suffix}"
        dest_dir = base_dir / safe_vendor / safe_code
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename
        with dest_path.open("wb") as out_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    out_file.write(chunk)
        none_downloaded = False
        img["local_path"] = dest_path
        downloaded_images.append(img)

    if none_downloaded:
        errors.append("No images were downloaded for this product.")

    return downloaded_images, errors