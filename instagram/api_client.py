"""Instagram API client.

Calls the private i.instagram.com/api/v1/media/{pk}/info/ endpoint using
Android app headers and a sessionid cookie for authentication. A valid
sessionid is required; unauthenticated access is not supported.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import aiohttp

from .const import (
    API_BASE,
    APP_ID,
    BLOKS_VERSIONING_ID,
    DOMAIN,
    MEDIA_TYPE_CAROUSEL,
    MEDIA_TYPE_IMAGE,
    MEDIA_TYPE_VIDEO,
    USER_AGENT,
)
from .utils import shortcode_to_pk


class InstagramAPIError(Exception):
    """Base exception for Instagram API errors."""


class InstagramAuthError(InstagramAPIError):
    """Authentication or session error."""


class InstagramUnavailableError(InstagramAPIError):
    """Post exists but is inaccessible (private, deleted, age-gated)."""


class InstagramAPIClient:
    """Fetches Instagram post data via the private i.instagram.com API."""

    def __init__(
        self,
        logger,
        cookies: dict[str, str] | None = None,
        on_cookies_updated: Callable[[dict[str, str]], None] | None = None,
    ):
        self._logger = logger
        self._cookies: dict[str, str] = dict(cookies or {})
        self._session: aiohttp.ClientSession | None = None
        self._on_cookies_updated = on_cookies_updated
        self._device_id = str(uuid.uuid4())
        self._android_id = "android-" + uuid.uuid4().hex[:16]

    @property
    def _active_session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise InstagramAuthError("API client not initialized — call async_setup() first")
        return self._session

    async def async_setup(self) -> None:
        self._session = aiohttp.ClientSession(
            trust_env=True,
            cookies=self._cookies if self._cookies else None,
        )
        self._logger.debug(f"{DOMAIN} API client initialized")

    async def async_teardown(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self._logger.info(f"{DOMAIN} API client session closed")

    def _sync_session_cookies(self) -> None:
        if not self._session or self._session.closed:
            return
        session_cookies = {m.key: m.value for m in self._session.cookie_jar if m.value}
        if self._cookies != session_cookies:
            self._cookies = session_cookies
            if self._on_cookies_updated:
                try:
                    self._on_cookies_updated(dict(self._cookies))
                except Exception as e:
                    self._logger.warning(f"{DOMAIN}: failed to persist updated cookies: {e}")

    def _base_headers(self) -> dict[str, str]:
        return {
            "X-IG-App-ID": APP_ID,
            "X-IG-Capabilities": "3brTv10=",
            "X-IG-Connection-Type": "WIFI",
            "X-IG-App-Locale": "en_US",
            "X-IG-Device-Locale": "en_US",
            "X-IG-Mapped-Locale": "en_US",
            "X-IG-App-Startup-Country": "US",
            "X-IG-Timezone-Offset": "0",
            "X-IG-Device-ID": self._device_id,
            "X-IG-Android-ID": self._android_id,
            "X-Bloks-Version-Id": BLOKS_VERSIONING_ID,
            "X-Bloks-Is-Layout-RTL": "false",
            "X-Bloks-Is-Panorama-Enabled": "true",
            "X-IG-WWW-Claim": "0",
            "X-FB-HTTP-Engine": "Tigon/MNS/TCP",
            "X-FB-Client-IP": "True",
            "X-FB-Server-Cluster": "True",
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US",
            "Accept-Encoding": "gzip, deflate",
            "Host": "i.instagram.com",
            "Connection": "keep-alive",
        }

    # ------------------------------------------------------------------ #
    # Private API
    # ------------------------------------------------------------------ #

    async def _fetch_via_private_api(self, pk: str) -> dict:
        """Call /api/v1/media/{pk}/info/ and return normalized PostData."""
        url = f"{API_BASE}/media/{pk}/info/"
        async with self._active_session.get(url, headers=self._base_headers()) as resp:
            if resp.status == 401:
                raise InstagramAuthError("Private API auth failed (HTTP 401) — check sessionid cookie")
            if resp.status == 404:
                raise InstagramUnavailableError(f"Post not found (HTTP 404, pk={pk})")
            if resp.status != 200:
                body = await resp.text()
                raise InstagramAPIError(f"Private API HTTP {resp.status}: {body[:200]}")
            data = await resp.json(content_type=None)

        self._sync_session_cookies()

        item = (data.get("items") or [None])[0]
        if not item:
            raise InstagramAPIError("Private API returned no items")

        return self._normalize_private(item)

    def _normalize_private(self, item: dict) -> dict:
        """Convert a private API 'item' dict into a normalized PostData dict."""
        user = item.get("user") or {}
        caption_text = (item.get("caption") or {}).get("text") or None
        media_type = item.get("media_type")

        media: list[dict] = []
        if media_type == MEDIA_TYPE_CAROUSEL:
            for child in item.get("carousel_media") or []:
                entry = self._normalize_private_media(child)
                if entry:
                    media.append(entry)
        else:
            entry = self._normalize_private_media(item)
            if entry:
                media.append(entry)

        return {
            "shortcode": item.get("code") or "",
            "pk": str(item.get("pk") or ""),
            "caption": caption_text,
            "taken_at": item.get("taken_at"),
            "user": {
                "uid": str(user.get("pk") or ""),
                "username": user.get("username") or "",
                "name": user.get("full_name") or None,
                "avatar": (user.get("hd_profile_pic_url_info") or {}).get("url") or user.get("profile_pic_url") or None,
            },
            "media": media,
        }

    def _normalize_private_media(self, media_item: dict) -> dict | None:
        """Extract one normalized media entry from a private API media item."""
        media_type = media_item.get("media_type")

        if media_type == MEDIA_TYPE_VIDEO:
            versions = media_item.get("video_versions") or []
            if not versions:
                return None
            # video_versions is sorted best-first by Instagram
            best = versions[0]
            cover = self._best_image_url(media_item)
            duration_s = media_item.get("video_duration")
            return {
                "type": "video",
                "url": best.get("url") or "",
                "width": best.get("width"),
                "height": best.get("height"),
                "cover": cover,
                "duration_ms": int(duration_s * 1000) if duration_s else None,
            }

        if media_type == MEDIA_TYPE_IMAGE:
            url = self._best_image_url(media_item)
            if not url:
                return None
            candidates = (media_item.get("image_versions2") or {}).get("candidates") or []
            best = candidates[0] if candidates else {}
            return {
                "type": "image",
                "url": url,
                "width": best.get("width"),
                "height": best.get("height"),
                "cover": None,
                "duration_ms": None,
            }

        self._logger.debug(f"{DOMAIN}: unknown private API media_type={media_type}, skipping")
        return None

    @staticmethod
    def _best_image_url(media_item: dict) -> str | None:
        """Pick the highest-resolution image URL from image_versions2.candidates."""
        candidates = (media_item.get("image_versions2") or {}).get("candidates") or []
        return candidates[0].get("url") if candidates else None

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    async def fetch_post(self, shortcode: str) -> dict:
        """Fetch and return a normalized PostData dict for the given shortcode.

        Requires a valid sessionid cookie. Raises InstagramAuthError if none
        is configured.
        """
        if not self._cookies.get("sessionid"):
            raise InstagramAuthError("sessionid cookie is required to fetch posts")
        pk = shortcode_to_pk(shortcode)
        self._logger.debug(f"{DOMAIN}: fetching via private API (pk={pk})")
        return await self._fetch_via_private_api(pk)
