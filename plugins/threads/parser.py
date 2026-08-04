"""
Threads content parser plugin.
"""

import json
import re

import aiohttp

from contenthive.plugins.context import PluginContext
from contenthive.plugins.contracts import (
    MediaType,
    ParserAuthorInfo,
    ParserMediaInfo,
    ParserPlatformInfo,
    ParserResult,
    ParserResultStatus,
)

from .const import (
    DOMAIN,
    MEDIA_TYPE_CAROUSEL,
    MEDIA_TYPE_VIDEO,
    PLATFORM_CODE,
    PLATFORM_ICON,
    PLATFORM_NAME,
    PLATFORM_URL,
    RELAY_POST_KEY,
    RELAY_PROFILE_KEY,
    REQUEST_HEADERS,
    URL_PATTERN,
)


async def async_setup_entry(context: PluginContext, entry, async_add_entities):
    """Set up parser entities from a config entry."""
    parser = ThreadsParser(context, entry)
    await parser.async_setup()
    await async_add_entities([parser])

    if context.register_service:
        context.register_service(DOMAIN, "can_parse", parser.can_parse)
        context.register_service(DOMAIN, "parse", parser.parse)

    context.logger.info(f"{DOMAIN} parser platform setup completed")


class ThreadsParser:
    """Parser for Threads content."""

    def __init__(self, context: PluginContext, entry):
        self.context = context
        self.entry = entry
        self.domain = DOMAIN
        self._session: aiohttp.ClientSession | None = None
        self._cookies: dict[str, str] = {}
        self._on_cookies_updated = None

    async def async_setup(self):
        """Initialize parser."""
        entry_data = self.context.data.get(DOMAIN, {})
        cookies = entry_data.get("cookies") or {}
        self._cookies = dict(cookies)
        self._on_cookies_updated = entry_data.get("on_cookies_updated")
        self._session = aiohttp.ClientSession(
            trust_env=True,
            cookies=cookies if cookies else None,
        )
        self.context.logger.debug(f"{DOMAIN} parser initialized")

    def can_parse(self, data: dict) -> bool:
        """Check if the URL is a Threads post URL."""
        url = data.get("url")
        if not url:
            return False
        return bool(re.match(URL_PATTERN, url))

    @staticmethod
    def _extract_json_scripts(html: str) -> list[str]:
        """Return the text content of all <script type="application/json"> tags."""
        return re.findall(
            r'<script[^>]+type="application/json"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )

    def _find_relay_data(self, html: str, relay_key: str) -> dict | None:
        """Return the Relay result data dict whose preloader name starts with relay_key,
        or None if not found.

        Threads embeds multiple <script type="application/json"> payloads.
        Each Relay data script has the structure:
            {"require": [["ScheduledServerJS", "handle", null,
                [{"__bbox": {"require": [
                    ["RelayPrefetchedStreamCache[@hash]", "next", [],
                        ["<preloader_name>", {"__bbox": {"result": {"data": {...}}}}]]
                ]}}]]]}
        Mobile pages append a hash to the cache key: "RelayPrefetchedStreamCache@<hash>".
        """
        for raw in self._extract_json_scripts(html):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if not isinstance(data, dict):
                continue

            for top_item in data.get("require") or []:
                if not (isinstance(top_item, list) and top_item and top_item[0] == "ScheduledServerJS"):
                    continue
                try:
                    bbox_require = top_item[3][0]["__bbox"].get("require") or []
                except (IndexError, KeyError, TypeError):
                    continue
                for item in bbox_require:
                    if not (isinstance(item, list) and item and str(item[0]).startswith("RelayPrefetchedStreamCache")):
                        continue
                    try:
                        preloader_name = item[3][0]
                        if not isinstance(preloader_name, str) or not preloader_name.startswith(relay_key):
                            continue
                        return item[3][1]["__bbox"]["result"]["data"]
                    except (IndexError, KeyError, TypeError):
                        continue
        return None

    def _sync_session_cookies(self) -> None:
        if not self._session or self._session.closed:
            return
        session_cookies = {m.key: m.value for m in self._session.cookie_jar if m.value}
        if session_cookies != self._cookies:
            if self._on_cookies_updated:
                try:
                    self._on_cookies_updated(dict(session_cookies))
                except Exception as e:
                    self.context.logger.warning(f"{DOMAIN}: failed to persist cookies: {e}")
                    return
            self._cookies = session_cookies

    async def _fetch_html(self, url: str) -> str:
        """Fetch url and return the response HTML text."""
        if not self._session:
            raise Exception("Parser not initialized - session is None")
        async with self._session.get(url, headers=REQUEST_HEADERS) as resp:
            html = await resp.text()
            if resp.status != 200:
                preview = html[:500].replace("\n", " ") if html else ""
                raise Exception(f"HTTP {resp.status} fetching {url!r}; body: {preview!r}")
        self._sync_session_cookies()
        return html

    async def _fetch_relay_data(self, url: str, relay_key: str) -> dict:
        """Fetch url and return the Relay result data dict for relay_key."""
        html = await self._fetch_html(url)
        result = self._find_relay_data(html, relay_key)
        if result is None:
            raise Exception(f"No Relay data with preloader prefix {relay_key!r} found in {url!r}")
        return result

    async def _fetch_media_data(self, url: str) -> dict:
        """Fetch the post page and extract the post dict.

        With the mobile UA, both logged-in and logged-out pages use
        RELAY_POST_KEY → data['data']['edges'][n]['node']['thread_items'][n]['post'].
        """
        try:
            html = await self._fetch_html(url)
        except Exception as e:
            self.context.logger.exception(f"Failed to fetch {url}")
            raise Exception(f"Failed to fetch page: {e}") from e

        result = self._find_relay_data(html, RELAY_POST_KEY)
        if result is not None:
            for edge in (result.get("data") or {}).get("edges") or []:
                for thread_item in (edge.get("node") or {}).get("thread_items") or []:
                    post = thread_item.get("post")
                    if post and post.get("pk"):
                        return post

        raise Exception("No media data found in Threads post response")

    async def _fetch_user_data(self, username: str) -> dict:
        """Fetch the user profile dict for username. Returns empty dict on failure."""
        profile_url = f"https://www.threads.com/@{username}"
        try:
            result = await self._fetch_relay_data(profile_url, RELAY_PROFILE_KEY)
            return result.get("user") or {}
        except Exception as e:
            self.context.logger.warning(f"Failed to fetch profile for @{username}: {e}")
            return {}

    def _best_image_url(self, image_versions2: dict) -> str | None:
        """Return the URL of the largest candidate from image_versions2."""
        candidates = (image_versions2 or {}).get("candidates") or []
        if not candidates:
            return None
        return candidates[0].get("url")

    def _parse_carousel_item(self, item: dict) -> ParserMediaInfo | None:
        """Parse a single carousel item into a ParserMediaInfo."""
        video_versions = item.get("video_versions") or []
        if video_versions:
            video = video_versions[0]
            cover = self._best_image_url(item.get("image_versions2") or {})
            return ParserMediaInfo(
                url=video["url"],
                type=MediaType.VIDEO,
                cover=cover,
                duration=None,
                width=item.get("original_width"),
                height=item.get("original_height"),
            )
        img_url = self._best_image_url(item.get("image_versions2") or {})
        if img_url:
            return ParserMediaInfo(
                url=img_url,
                type=MediaType.IMAGE,
                width=item.get("original_width"),
                height=item.get("original_height"),
            )
        return None

    def _parse_media(self, media: dict) -> list[ParserMediaInfo]:
        """Parse all media from the post media dict."""
        media_type = media.get("media_type")
        result: list[ParserMediaInfo] = []

        if media_type == MEDIA_TYPE_CAROUSEL:
            for item in media.get("carousel_media") or []:
                parsed = self._parse_carousel_item(item)
                if parsed:
                    result.append(parsed)
        elif media_type == MEDIA_TYPE_VIDEO:
            video_versions = media.get("video_versions") or []
            if video_versions:
                video = video_versions[0]
                cover = self._best_image_url(media.get("image_versions2") or {})
                result.append(
                    ParserMediaInfo(
                        url=video["url"],
                        type=MediaType.VIDEO,
                        cover=cover,
                        duration=None,
                        width=media.get("original_width"),
                        height=media.get("original_height"),
                    )
                )
        else:
            # Single image (media_type == 1) or unknown
            img_url = self._best_image_url(media.get("image_versions2") or {})
            if img_url:
                result.append(
                    ParserMediaInfo(
                        url=img_url,
                        type=MediaType.IMAGE,
                        width=media.get("original_width"),
                        height=media.get("original_height"),
                    )
                )

        return result

    def _parse_author(self, post_user: dict, user_data: dict) -> ParserAuthorInfo:
        """Build ParserAuthorInfo from post user dict and optional profile user_data."""
        uid = str(post_user.get("pk") or post_user.get("id") or "")
        username = post_user.get("username") or ""
        name = user_data.get("full_name") or post_user.get("full_name") or username

        hd_pics = user_data.get("hd_profile_pic_versions") or []
        if hd_pics:
            avatar = hd_pics[-1].get("url")
        else:
            avatar = user_data.get("profile_pic_url") or post_user.get("profile_pic_url")

        description = user_data.get("biography") or ""
        profile_url = f"https://www.threads.com/@{username}" if username else None

        return ParserAuthorInfo(
            uid=uid,
            name=name,
            username=username,
            avatar=avatar or None,
            url=profile_url,
            description=description or None,
        )

    def _parse_platform(self) -> ParserPlatformInfo:
        return ParserPlatformInfo(
            code=PLATFORM_CODE,
            name=PLATFORM_NAME,
            url=PLATFORM_URL,
            icon_url=PLATFORM_ICON,
        )

    async def parse(self, data: dict) -> ParserResult:
        """Parse a Threads post URL and return ParserResult."""
        if not self._session:
            raise Exception("Parser not initialized - session is None")

        url = data.get("url")
        if not url:
            raise ValueError("No URL provided for parsing")

        try:
            media = await self._fetch_media_data(url)

            post_id = str(media.get("pk") or "")
            if not post_id:
                raise Exception("No pk found in media data")

            caption = media.get("caption") or {}
            content = caption.get("text") or None
            taken_at = media.get("taken_at")

            post_user = media.get("user") or {}
            username = post_user.get("username") or ""
            user_data = await self._fetch_user_data(username) if username else {}

            return ParserResult(
                pid=post_id,
                url=url,
                title=None,
                content=content,
                media=self._parse_media(media),
                author=self._parse_author(post_user, user_data),
                platform=self._parse_platform(),
                post_time=taken_at,
                parser=DOMAIN,
                state=ParserResultStatus.SUCCESS,
            )
        except Exception as e:
            self.context.logger.exception(f"Failed to parse {url}")
            raise Exception(f"Failed to parse Threads URL: {e}") from e

    async def async_will_remove(self):
        """Clean up resources when removing parser."""
        if hasattr(self, "_session") and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self.context.logger.info(f"{DOMAIN} parser session closed")
