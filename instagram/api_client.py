"""Instagram API client.

Supports two access modes:
- Authenticated (sessionid cookie present): calls the private /api/v1/media/{pk}/info/ endpoint.
- Unauthenticated: calls the public GraphQL query endpoint (doc_id 8845758582119845),
  first obtaining a CSRF token via the /api/v1/web/get_ruling_for_content/ endpoint.

Both paths normalize their response into a common PostData dict before returning.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import aiohttp

from .const import (
    API_BASE,
    APP_ID,
    ASBD_ID,
    DOMAIN,
    GRAPHQL_DOC_ID,
    GRAPHQL_URL,
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
    """Fetches Instagram post data via private API or public GraphQL fallback."""

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
            "X-ASBD-ID": ASBD_ID,
            "X-IG-WWW-Claim": "0",
            "Origin": "https://www.instagram.com",
            "Accept": "*/*",
            "User-Agent": USER_AGENT,
        }

    # ------------------------------------------------------------------ #
    # Private API path (sessionid required)
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
    # Public GraphQL path (no sessionid needed)
    # ------------------------------------------------------------------ #

    async def _setup_csrf(self, pk: str) -> str | None:
        """Hit the ruling endpoint to seed the session with a csrftoken cookie."""
        ruling_url = f"{API_BASE}/web/get_ruling_for_content/?content_type=MEDIA&target_id={pk}"
        try:
            async with self._active_session.get(ruling_url, headers=self._base_headers()) as resp:
                await resp.read()
                self._sync_session_cookies()
        except Exception as e:
            self._logger.debug(f"{DOMAIN}: CSRF setup request failed (non-fatal): {e}")
        return self._cookies.get("csrftoken")

    async def _fetch_via_graphql(self, shortcode: str, pk: str, post_url: str) -> dict:
        """Call the public GraphQL query endpoint and return normalized PostData."""
        csrf_token = await self._setup_csrf(pk)
        if not csrf_token:
            self._logger.warning(f"{DOMAIN}: no csrftoken after setup — GraphQL may fail")

        variables = json.dumps(
            {
                "shortcode": shortcode,
                "child_comment_count": 0,
                "fetch_comment_count": 0,
                "parent_comment_count": 0,
                "has_threaded_comments": False,
            },
            separators=(",", ":"),
        )

        headers = {
            **self._base_headers(),
            "X-CSRFToken": csrf_token or "",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": post_url,
        }

        async with self._active_session.get(
            GRAPHQL_URL,
            headers=headers,
            params={"doc_id": GRAPHQL_DOC_ID, "variables": variables},
        ) as resp:
            if resp.status == 401:
                raise InstagramAuthError("GraphQL endpoint requires login (HTTP 401)")
            if resp.status == 429:
                raise InstagramAPIError("Rate limited by Instagram GraphQL (HTTP 429)")
            if resp.status != 200:
                body = await resp.text()
                raise InstagramAPIError(f"GraphQL HTTP {resp.status}: {body[:200]}")
            data = await resp.json(content_type=None)

        self._sync_session_cookies()

        media = (data.get("data") or {}).get("xdt_shortcode_media") or {}
        if not media:
            error_title = (data.get("data") or {}).get("title") or ""
            error_desc = (data.get("data") or {}).get("description") or ""
            detail = f"{error_title}: {error_desc}".strip(": ") or "empty media response"
            raise InstagramUnavailableError(f"Post unavailable: {detail}")

        return self._normalize_graphql(shortcode, media)

    def _normalize_graphql(self, shortcode: str, media: dict) -> dict:
        """Convert a GraphQL xdt_shortcode_media dict into a normalized PostData dict."""
        owner = media.get("owner") or {}
        caption_text = None
        caption_edges = (media.get("edge_media_to_caption") or {}).get("edges") or []
        if caption_edges:
            caption_text = (caption_edges[0].get("node") or {}).get("text") or None

        ig_media: list[dict] = []

        # Carousel: edge_sidecar_to_children
        sidecar_edges = (media.get("edge_sidecar_to_children") or {}).get("edges") or []
        if sidecar_edges:
            for edge in sidecar_edges:
                node = edge.get("node") or {}
                entry = self._normalize_graphql_node(node)
                if entry:
                    ig_media.append(entry)
        else:
            entry = self._normalize_graphql_node(media)
            if entry:
                ig_media.append(entry)

        return {
            "shortcode": shortcode,
            "pk": shortcode_to_pk(shortcode),
            "caption": caption_text,
            "taken_at": media.get("taken_at_timestamp"),
            "user": {
                "uid": str(owner.get("id") or ""),
                "username": owner.get("username") or "",
                "name": owner.get("full_name") or None,
                "avatar": owner.get("profile_pic_url") or None,
            },
            "media": ig_media,
        }

    def _normalize_graphql_node(self, node: dict) -> dict | None:
        """Extract one normalized media entry from a GraphQL media node."""
        is_video = node.get("is_video") or node.get("__typename") == "GraphVideo"

        if is_video:
            video_url = node.get("video_url")
            if not video_url:
                return None
            dims = node.get("dimensions") or {}
            cover = self._graphql_thumbnail(node)
            duration_s = node.get("video_duration")
            return {
                "type": "video",
                "url": video_url,
                "width": dims.get("width"),
                "height": dims.get("height"),
                "cover": cover,
                "duration_ms": int(duration_s * 1000) if duration_s else None,
            }

        # Image
        display_url = node.get("display_url") or node.get("display_src")
        if not display_url:
            return None
        dims = node.get("dimensions") or {}
        return {
            "type": "image",
            "url": display_url,
            "width": dims.get("width"),
            "height": dims.get("height"),
            "cover": None,
            "duration_ms": None,
        }

    @staticmethod
    def _graphql_thumbnail(node: dict) -> str | None:
        """Pick the best thumbnail URL from a GraphQL video node."""
        resources = node.get("display_resources") or []
        if resources:
            return resources[-1].get("src") or resources[0].get("src")
        return node.get("display_url") or node.get("thumbnail_src") or None

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    async def fetch_post(self, shortcode: str, post_url: str) -> dict:
        """Fetch and return a normalized PostData dict for the given shortcode.

        Uses the private API when a sessionid cookie is present; falls back to
        the public GraphQL endpoint otherwise.
        """
        pk = shortcode_to_pk(shortcode)

        if self._cookies.get("sessionid"):
            self._logger.debug(f"{DOMAIN}: fetching via private API (pk={pk})")
            return await self._fetch_via_private_api(pk)

        self._logger.debug(f"{DOMAIN}: fetching via public GraphQL (shortcode={shortcode})")
        return await self._fetch_via_graphql(shortcode, pk, post_url)
