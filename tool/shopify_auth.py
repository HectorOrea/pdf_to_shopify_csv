"""Shopify authentication with a persistent token cache.
    get_shopify_auth called by shopify_upload_files.py.
    Cache implemented as a one line JSON file that gets updated """

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from curl_cffi import requests

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_CACHE_PATH = Path(__file__).resolve().parent / "moda_shopify_token_cache.json"
TOKEN_REFRESH_BUFFER_SECONDS = 1200


@dataclass
class ShopifyAuth:
    shop_domain: str
    access_token: str


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float | None
    cache_key: str | None = None


def _cache_path() -> Path:
    configured_path = os.environ.get("SHOPIFY_TOKEN_CACHE_PATH")
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_TOKEN_CACHE_PATH


def _shop_domain_from_env() -> str:
    shop = os.environ.get("SHOPIFY_SHOP")
    if not shop:
        raise RuntimeError("Missing required environment variable: SHOPIFY_SHOP")

    shop = shop.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"
    return shop


def _load_token(cache_key: str | None = None) -> _CachedToken | None:
    """
    Returns cachedtoken if it exists for given cache_key. Otherwise returns None
    """
    cache_path = _cache_path()
    try:
        data: Any = json.loads(cache_path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring unreadable Shopify token cache at %s: %s", cache_path, exc)
        return None

    if not isinstance(data, dict):
        return None

    access_token = data.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return None

    saved_cache_key = data.get("cache_key")
    if saved_cache_key != cache_key:
        return None
    if saved_cache_key is not None and not isinstance(saved_cache_key, str):
        saved_cache_key = None

    expires_at = data.get("expires_at")
    if expires_at is not None:
        try:
            expires_at = float(expires_at)
        except (TypeError, ValueError):
            return None

    return _CachedToken(
        access_token=access_token,
        expires_at=expires_at,
        cache_key=saved_cache_key,
    )


def _save_token(token: _CachedToken) -> None:
    cache_path = _cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "access_token": token.access_token,
        "expires_at": token.expires_at,
        "cache_key": token.cache_key,
    }
    temp_path = cache_path.with_name(f"{cache_path.name}.tmp")
    temp_path.write_text(json.dumps(payload))
    temp_path.chmod(0o600)
    temp_path.replace(cache_path)
    cache_path.chmod(0o600)


def _token_is_usable(
    token: _CachedToken,
    refresh_buffer_seconds: int = TOKEN_REFRESH_BUFFER_SECONDS,
) -> bool:
    if token.expires_at is None:
        return True
    return time.time() < token.expires_at - refresh_buffer_seconds


def _token_from_response(
    access_token: str,
    expires_in: object,
    cache_key: str | None = None,
) -> _CachedToken:
    expires_at = None
    if expires_in is not None:
        try:
            expires_at = time.time() + float(expires_in)
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid Shopify token expires_in value: %r", expires_in)

    return _CachedToken(
        access_token=access_token,
        expires_at=expires_at,
        cache_key=cache_key,
    )


def get_shopify_auth() -> ShopifyAuth:
    client_id = os.environ.get("SHOPIFY_CLIENT_ID")
    client_secret = os.environ.get("SHOPIFY_CLIENT_SECRET")
    shop_domain = _shop_domain_from_env()
    cache_key = f"{shop_domain}:{client_id}" if client_id else shop_domain

    cached_token = _load_token(cache_key=cache_key)
    if cached_token and _token_is_usable(cached_token):
        return ShopifyAuth(shop_domain=shop_domain, access_token=cached_token.access_token)

    missing_values = [
        name
        for name, value in {
            "SHOPIFY_CLIENT_ID": client_id,
            "SHOPIFY_CLIENT_SECRET": client_secret,
        }.items()
        if not value
    ]
    if missing_values:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing_values)}")

    response = requests.post(
        f"https://{shop_domain}/admin/oauth/access_token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    access_token = data.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Shopify token response did not include an access_token")

    cached_token = _token_from_response(
        access_token,
        data.get("expires_in"),
        cache_key=cache_key,
    )
    _save_token(cached_token)
    return ShopifyAuth(shop_domain=shop_domain, access_token=access_token)
