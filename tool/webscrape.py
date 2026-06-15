"""
Functions for webscraping. Include setting up proxies, initial serach engine 
scraping, product page scraping (with and without headless browsers), and 
generating the page summary from the raw html. 
"""

import os
import logging

import tool.types as t
from typing import List

import serpapi
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException
from bs4 import BeautifulSoup, Tag

from html import unescape
from urllib.parse import urljoin, quote, urlsplit, urlunsplit

from playwright.sync_api import sync_playwright

import re
import os

logger = logging.getLogger(__name__)


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

def get_proxy() -> str | None:
    proxy_domain = os.environ.get("PROXY_DOMAIN")
    proxy_auth = os.environ.get("PROXY_AUTH")
    if not proxy_domain or not proxy_auth:
        return None
    return f"http://{proxy_auth}@{proxy_domain}"


def _normalize_image_url(raw_url: str, page_url: str) -> str | None:
    """
    Convert a scraped image reference into a stable absolute URL.

    Why this exists:
        - Some stores return relative image paths, so we need urljoin(page_url, src).
        - Some scraped attributes contain HTML-escaped characters like '&amp;'.
        - Our previous implementation called quote() on the entire URL, which
          encoded '?' and '&' into '%3F' and '%26'. That turned a valid URL like
          'image.jpg?sw=588&sh=782' into a completely different path that 404s.
        - We only want to percent-encode the path portion when needed, while
          preserving the query string as an actual query string.

    Implementation notes:
        - unescape() converts HTML entities back to normal URL characters.
        - We preserve existing '%' in the path to avoid double-encoding already
          valid sequences like '%28' and '%29'
        - Query parameters are preserved verbatim because image CDNs often use
          them for sizing/cropping directives.
    """
    cleaned_url = unescape(raw_url).strip()
    if not cleaned_url or cleaned_url.startswith("data:"):
        return None

    absolute_url = urljoin(page_url, cleaned_url)
    parts = urlsplit(absolute_url)

    normalized_path = quote(parts.path, safe="/%:@()+,;=-._~")
    return urlunsplit(
        (parts.scheme, parts.netloc, normalized_path, parts.query, parts.fragment)
    )

def search_first_link(query: str) -> str | None:
    """
    Input:
        - query : str (what get's googled)
    
    Output:
        - Optional[str] (link of first google search result)
    
    Failure Modes:
        - No SERPAPI key

    """
    api_key = os.environ.get("SERPAPI_KEY") or os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        logger.warning("SERPAPI_KEY is not configured; cannot lookup %s", query)
        return None
    client = serpapi.Client(api_key=api_key)
    try:
        response = client.search(
            q=query,
            engine="google",
            hl="en",
            gl="us",
        )
    except Exception as exc:
        logger.warning("SerpAPI search failed for %s: %s", query, exc)
        return None
    organic = response.get("organic_results") or []
    for entry in organic:
        href = entry.get("link") or entry.get("redirect_link")
        if href:
            return href
    return None

def _use_playwright_to_fetch_page_data(url: str, limit: int) -> t.ProductPageData:
    """
    To Add
    - Add more robust error handling
    - Better logic for when I use playwright 
    """

    urls : List[str] = []
    alts : List[str | None] = []
    with sync_playwright() as p:
        PROXY = get_proxy()
        browser = p.chromium.launch(proxy={"server": PROXY})
        page = browser.new_page()
        try:
            page.goto(url)
            page.wait_for_load_state("load")
            page.wait_for_timeout(5000)
            page.screenshot(path="pptest.png", full_page=True)
        except Exception as exc:
            data: t.ProductPageData = {
            "main_url": url,
            "html": "",
            "image_urls": [],
            "alt_texts": [],
            "warnings": ["Playwright timed out or failed to load the page"],
            "used_playwright": True 
            }
            return data
        finally:
            page.close()
            browser.close()

        html = page.content()
        for img in page.get_by_role("img").all()[:limit]:
            src = img.get_attribute('src') or img.get_attribute("data-src")
            if not src:
                continue

            # Normalize after the presence check. Some image elements have no
            # src at all, and some have relative or HTML-escaped URLs.
            normalized_src = _normalize_image_url(src, url)
            if not normalized_src:
                continue

            if normalized_src not in urls and len(urls) < limit:
                urls.append(normalized_src)
                # Keep alt_texts aligned with image_urls. Downstream code zips
                # these lists together, so we only append alt text when we
                # actually kept the corresponding image URL.
                alt = img.get_attribute('alt') #Might return none
                alts.append(alt)
    
        browser.close()

    data = {
    "main_url": url,
    "html": html,
    "image_urls": urls,
    "alt_texts": alts,
    "warnings": [],
    "used_playwright": True 
    }

    return data

def fetch_product_page_data(
    page_url: str,
    session: requests.Session,
    limit: int = 40
) -> t.ProductPageData:
    """
    Note this naturally enforces len(urls) = len(alts)
    Assumptions: 
        - The first limit-many images includes the product image
        - The images are sourced in the raw html

    Failure Modes:
        - curl_cffi's GET request is rejected

    To Add
        - aria-label as an attribute added to img analysis
    """

    warnings = []

    try:
        PROXY = get_proxy()
        response = session.get(page_url, headers=HEADERS, timeout=30, proxy=PROXY)
        response.raise_for_status()
        logger.info(f"Fetching {page_url}: {response.status_code}")
    except RequestException as exc:
        logger.warning(f"Failed to fetch {page_url}: {exc}")
        warnings.append(f"Failed to fetch {page_url}: {exc}")
        data : t.ProductPageData = {
            "main_url" : page_url,
            "html" : "",
            "image_urls" : [],
            "alt_texts" : [],
            "warnings" : warnings,
            "used_playwright" : False
        }
        return data

    soup = BeautifulSoup(response.text, "html.parser")
    urls : List[str] = []
    alts : List[str | None] = []

    for media in soup.find_all("div", class_="product__media"):
        if not isinstance(media, Tag):
            continue
        for a_tag in media.find_all("a", href=True):
            if not isinstance(a_tag, Tag):
                continue
            anchor = a_tag.get("href")
            if not anchor or not isinstance(anchor, str):
                continue
            urls.append(anchor)
            alts.append(None)

    for img in soup.find_all("img"):
        if not isinstance(img, Tag):
            continue
        src = img.get("src") or img.get("data-src")
        if not src or not isinstance(src, str):
            continue
        
        absolute = _normalize_image_url(src, page_url)
        if not absolute:
            continue

        if absolute not in urls and len(urls) < limit:
            urls.append(absolute)
            dummy_alt = img.get("alt")
            alt_text = dummy_alt if isinstance(dummy_alt, str) else None
            alts.append(alt_text)
    
    html = response.text
    #TODO: Fix playwright for Fendi
    if not urls: # or len(urls) < 3:
        data = _use_playwright_to_fetch_page_data(page_url, limit)
        return data
    
    data = {
            "main_url" : page_url,
            "html": html,
            "image_urls": urls,
            "alt_texts" : alts,
            "warnings" : warnings,
            "used_playwright" : False
        }

    return data

def build_images_from_page_data(data: t.ProductPageData)-> List[t.CandidateImage]:
    image_urls = data["image_urls"]
    alt_texts = data["alt_texts"]
    main_url = data["main_url"]
    candidate_images = []
    for i, (url, alt) in enumerate(zip(image_urls, alt_texts)):
        img : t.CandidateImage = {
            "page_url": main_url, 
            "src_url": url, 
            "alt_text": alt,
            "candidate_index": i}
        candidate_images.append(img)
    return candidate_images

def get_page_summary(
        page_data : t.ProductPageData, 
        candidate_images: List[t.CandidateImage],
        ) -> str:
    """
    Output:
        str (page summary of meta title, meta description, headings, body text, and image urls)

    Assumptions:
        - Meta title, description, or headings include actual product nam

    Failure Modes:
        - No information gleamed from subdata or first 4000 chars of body
    """
    page_html = page_data["html"]
    page_url = page_data["main_url"]

    soup = BeautifulSoup(page_html, "html.parser")
    title_tag = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_title = ""
    for key in ["og:title", "twitter:title"]:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if not isinstance(tag, Tag):
            continue
        if tag and tag.get("content"):
            meta_title = str(tag["content"]).strip()
            break

    meta_description = ""
    for key in ["description", "og:description", "twitter:description"]:
        tag = soup.find("meta", attrs={"name": key}) or soup.find("meta", attrs={"property": key})
        if not isinstance(tag, Tag):
            continue
        if tag and tag.get("content"):
            meta_description = str(tag["content"]).strip()
            break

    headings = []
    for selector in ["h1", "h2"]:
        for heading in soup.find_all(selector):
            text = heading.get_text(" ", strip=True)
            if text and text not in headings:
                headings.append(text)
            if len(headings) >= 8:
                break
        if len(headings) >= 8:
            break

    body_text = soup.get_text(" ", strip=True)
    body_text = re.sub(r"\s+", " ", body_text)[:4000]

    parts = []
    for candidate in candidate_images:
        i = candidate["candidate_index"]
        url = candidate["src_url"]
        alt = candidate["alt_text"]
        s = f"[{i}]\n url: {url}\n alt_text: {alt}\n"
        parts.append(s)
    image_text = "\n".join(parts)

    return "\n".join(
        [
            f"URL: {page_url}",
            f"HTML <title>: {title_tag}",
            f"Meta title: {meta_title}",
            f"Meta description: {meta_description}",
            f"Headings: {headings}",
            f"Body excerpt: {body_text}",
            f"candidate_images: {image_text}",
        ]
    )