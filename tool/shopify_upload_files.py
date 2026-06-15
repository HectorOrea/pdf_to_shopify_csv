"""Functions to upload local images to Shopify Files and return public URLs.
    This involves 'staging' (producing urls to http put to), putting to the stages,
    creating files based on these stages, and finally getting the files public URLs.
    These URLs must be public to be valid in the eventual returned CSV. 

    Uses shopify's graphql admin api

    """

from __future__ import annotations

import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast
import logging

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException
from tool.shopify_auth import get_shopify_auth
import tool.types as t

logger = logging.getLogger(__name__)

@dataclass
class ShopifyFilesConfig:
    shop_domain: str = "test-moda-2.myshopify.com"
    access_token: str = ""
    api_version: str = "2026-04"
    poll_interval_seconds: float = 2.0
    poll_timeout_seconds: float = 120.0

    # The url the requests go to
    @property
    def graphql_url(self) -> str:
        return f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json"


# Queries my shop with given query and variables by sending the post request and
# returning the data
def _graphql(image: t.WeakImage, config: ShopifyFilesConfig, query: str, variables: t.MyShopifyVariables) -> t.MyShopifyResponse | None:
    response = requests.post(
        config.graphql_url,
        headers={
            "Content-Type": "application/json", # let's machine know a json is being sent
            "X-Shopify-Access-Token": config.access_token, # authentication
        },
        json={"query": query, "variables": variables},
        timeout=60,
    )
    try:
        response.raise_for_status()
    except RequestException as exc:
        image["errors"].append(f"Shopify GraphQL error: {exc}")
        return None
    payload = response.json()
    if payload.get("errors"):
        image["errors"].append(f"Shopify GraphQL error: {payload['errors']}")
        return None
    return payload["data"]


def _mime_type_for_path(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type or "application/octet-stream"


def _staged_target_for_image(image: t.WeakImage, config: ShopifyFilesConfig) -> t.StagedTarget| None:
    """
    Gets 'stage' I'll upload my image to
    Outputs:
        - stagedTargets Object as a Dict
    """

    path = image["local_path"]

    if path is None:
        image["errors"].append("image has no local path")
        return None

    mutation = """
    mutation ($input: [StagedUploadInput!]!) {
      stagedUploadsCreate(input: $input) {
        stagedTargets {
          url
          resourceUrl
          parameters {
            name
            value
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    variables : t.StagedUploadsVariables = {
        "input": [
            {
                "filename": path.name,
                "mimeType": _mime_type_for_path(path),
                "resource": "IMAGE",
                "httpMethod": "PUT",
            }
        ]
    }
    data = _graphql(image, config, mutation, variables)
    if data is None:
        return None
    data = cast(t.StagedUploadsCreateData, data)
    stagedUploadsCreate : t.StagedUploadsCreate= data["stagedUploadsCreate"]
    if stagedUploadsCreate["userErrors"]:
        image["errors"].append(f"Shopify staged upload error: {stagedUploadsCreate['userErrors']}")
        return None
    return stagedUploadsCreate["stagedTargets"][0]


def _upload_to_staged_target(image: t.WeakImage, staged_target: t.StagedTarget) -> bool:
    """
        - Uploads image found at Path to the url given by staged_target
    """
    headers = {
        str(parameter["name"]): str(parameter["value"])
        for parameter in staged_target.get("parameters", [])
    }
    path = image["local_path"]
    
    # Extra error handling for mypy
    if path is None:
        image["errors"].append("image has no local path")
        return False
    
    try:
        with path.open("rb") as image_file:
            response = requests.put(
                str(staged_target["url"]),
                headers=headers,
                data=image_file.read(),
                timeout=120,
            )
        response.raise_for_status()
    except RequestException as exc:
        image["errors"].append(f"Shopify staged upload failed: {exc}")
        return False
    return True

def _register_uploaded_file(resource_url: str, alt_text: str, image: t.WeakImage, config: ShopifyFilesConfig) -> str | None:
    """
    Inputs:
        - the resource_url (the 'tracking id' from my stagedTarget object)
    Outputs / Effects:
        - Creates file in my shop's files and returns the file id (which is different from the resource_url)
    
    """
    mutation = """
    mutation ($files: [FileCreateInput!]!) {
      fileCreate(files: $files) {
        files {
          id
          fileStatus
          alt
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    variables : t.FileCreateVariables = {
        "files": [
            {
                "originalSource": resource_url,
                "alt": alt_text,
                "contentType": "IMAGE",
            }
        ]
    }
    data = _graphql(image, config, mutation, variables)
    if data is None:
        return None
    data = cast(t.FileCreateData, data)
    response : t.FileCreate = data["fileCreate"]
    if response["userErrors"]:
        image["errors"].append(f"Shopify fileCreate error: {response['userErrors']}")
        return None
    return str(response["files"][0]["id"])


# queries the CheckFileStatus
# Had a bug here where I returned without waiting long enough for it to actually process
def _wait_for_file_url(file_id: str, image: t.WeakImage, config: ShopifyFilesConfig) -> str | None:
    """
    - Given file id, gets a public url of it
    - Passes image for error logging purposes
    - Assumes the timeout_seconds and interval_seconds in config are reasonable
    """

    # This query returns the shown fields of the file object with global_id id
    query = """
    query CheckFileStatus($id: ID!) {
      node(id: $id) {
        ... on File {
          fileStatus
          preview {
            image {
              url
            }
          }
        }
      }
    }
    """
    variables : t.CheckFileStatusVariables = {"id" : file_id}
    deadline = time.time() + config.poll_timeout_seconds
    while time.time() < deadline:
        data = _graphql(image, config, query, variables)
        if data is None:
            return None
        data = cast(t.CheckFileStatusData, data)
        if data.get("node") is None:
            image["errors"].append(f"None node for {file_id}")
            return None
        node : t.CheckFileStatusNode = data["node"]
        file_status = node.get("fileStatus") or "FAILED"
        if file_status == "FAILED":
            image["errors"].append(f"Shopify file processing failed for {file_id}")
            return None
        
        preview = node.get("preview")
        image_info = preview.get("image") if preview else None
        url = image_info.get("url") if image_info else None

        if url is None:
            time.sleep(config.poll_interval_seconds)
            continue

        if file_status == "READY" and url:
            return str(url)
        
        time.sleep(config.poll_interval_seconds)

    image["errors"].append(f"Timed out waiting for Shopify file to become READY: {file_id}")
    return None

def upload_local_image_to_shopify(
    image: t.WeakImage,
    config: ShopifyFilesConfig,
    alt_text: str = "",
) -> str | None:
    """
    Orchestrates shopify functions to upload image to Shopify files and get a public url
    Failures:
        - One of the images is an empty jpg
    """
    path = image["local_path"]
    if path is None:
        image["errors"].append("image has no local path")
        return None
    
    path = path.expanduser().resolve()
    if not path.exists():
        image["errors"].append("local path doesn't exist")
        return None
    

    # IF SIZE OF FILE AT PATH = 0, return empty string
    if path.stat().st_size == 0:
        image["errors"].append("image has size 0")
        return None

    staged_target = _staged_target_for_image(image, config)
    if not staged_target:
        return None
    upload_status = _upload_to_staged_target(image, staged_target)
    if not upload_status:
        return None
    file_id = _register_uploaded_file(str(staged_target["resourceUrl"]), alt_text, image, config)
    if not file_id:
        return None
    return _wait_for_file_url(file_id, image, config)

def upload_enriched_table_images_to_shopify(
    enriched_table: t.EnrichedOrderTable
) -> t.EnrichedOrderTable:
    """
    Input
        Populates image's public_urls

    Assumptions
        - upload_local_image_to_shopify works
        - the paths in the images list don't start with https unless they're public ???

    To Add 
        - A way of detecting when image src_urls are already public and don't 
        need to be uploaded to Shopify files
    """
    auth = get_shopify_auth()
    config = ShopifyFilesConfig(
        shop_domain=auth.shop_domain,
        access_token=auth.access_token,
    )
    enriched_orders = enriched_table["orders"]

    # For each order (i.e. product), update with "public_image_urls" (returned)
    l = len(enriched_orders)
    for (i, order) in enumerate(enriched_orders, start=1):
        for image in order["images"]:
            shop_url = upload_local_image_to_shopify(image, config, alt_text=order["title"])
            if shop_url:
                image["public_url"] = shop_url
            # Otherwise some error explains what went wrong
            for err in image["errors"]:
                order["warnings"].append(f"Error for image idx {image['candidate_index']} : {err}")
        logger.info(f"finished uploading files for order {i} of {l}")

    return enriched_table
