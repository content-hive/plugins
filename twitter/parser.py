"""
X(Twitter) content parser plugin.
Scrapes tweet pages and extracts window.__INITIAL_STATE__ data.
"""
import html
import json
import re
from datetime import datetime
from typing import Optional

import aiohttp

from contenthive.plugins.context import PluginContext
from contenthive.plugins.contracts import (
    MediaType, ParserResultStatus,
    ParserAuthorInfo, ParserMediaInfo, ParserPlatformInfo, ParserResult,
)

from .const import (
    DOMAIN,
    PLATFORM_CODE,
    PLATFORM_NAME,
    PLATFORM_URL,
    PLATFORM_ICON,
    REQUEST_HEADERS,
    JS_INVALID_TOKENS,
    URL_PATTERN,
    AVATAR_NORMAL_SUFFIX,
    AVATAR_HQ_SUFFIX,
)


async def async_setup_entry(context: PluginContext, entry, async_add_entities):
    """Set up parser entities from a config entry."""
    parser = TwitterParser(context, entry)
    await parser.async_setup()
    await async_add_entities([parser])

    if context.register_service:
        context.register_service(DOMAIN, "can_parse", parser.can_parse)
        context.register_service(DOMAIN, "parse", parser.parse)

    context.logger.info(f"{DOMAIN} parser platform setup completed")


class TwitterParser:
    """Parser for X(Twitter) content via page scraping."""

    _JS_INVALID_TOKENS_RE = re.compile(JS_INVALID_TOKENS)

    def __init__(self, context: PluginContext, entry):
        self.context = context
        self.entry = entry
        self.domain = DOMAIN
        self._session: Optional[aiohttp.ClientSession] = None

    async def async_setup(self):
        """Initialize parser."""
        # max_field_size raised because Twitter's CSP response headers exceed
        # aiohttp's default 8190-byte limit.
        self._session = aiohttp.ClientSession(trust_env=True, max_field_size=65536)
        self.context.logger.debug(f"{DOMAIN} parser initialized")

    def can_parse(self, data: dict) -> bool:
        """Check if the URL is a Twitter/X tweet URL."""
        url = data.get("url")
        if not url:
            return False
        return bool(re.match(URL_PATTERN, url))

    async def _fetch_state(self, url: str) -> dict:
        """Fetch a Twitter page and extract window.__INITIAL_STATE__ as a dict.

        The script tag may contain multiple assignments in one line, e.g.:
            window.__INITIAL_STATE__={...};window.__META_DATA__={...};
        A regex over the whole tag would capture both. We instead locate the
        assignment by string search and use json.JSONDecoder.raw_decode() to
        consume exactly the first complete JSON object, stopping automatically.

        Twitter HTML-entity-encodes characters inside the embedded JSON.
        &quot; must be replaced with \" before html.unescape(), otherwise it
        becomes a bare " that breaks JSON string boundaries (the `source` field
        contains <a href="..."> with quoted attributes).

        Raises:
            Exception: If the request fails or the state JSON cannot be
                found or parsed.
        """
        if not self._session:
            raise Exception("Parser not initialized - session is None")
        try:
            async with self._session.get(url, headers=REQUEST_HEADERS) as resp:
                resp_text = await resp.text()
                if resp.status != 200:
                    preview = resp_text[:500].replace("\n", " ") if resp_text else ""
                    raise Exception(
                        f"HTTP {resp.status} fetching {url!r}; body preview: {preview!r}"
                    )
            marker = "window.__INITIAL_STATE__="
            idx = resp_text.find(marker)
            if idx == -1:
                raise Exception("No window.__INITIAL_STATE__ found in page")
            json_start = idx + len(marker)
            # Limit preprocessing to this <script> block only.
            # raw_decode will stop at the first complete JSON object regardless,
            # so </script> is a sufficient (and safe) upper bound.
            script_end = resp_text.find("</script>", json_start)
            json_raw = resp_text[json_start:script_end] if script_end != -1 else resp_text[json_start:]
            # Unescape HTML entities; &quot; → \" must come first.
            json_str = json_raw.replace("&quot;", '\\"')
            json_str = html.unescape(json_str)
            json_str = self._JS_INVALID_TOKENS_RE.sub("null", json_str)
            # raw_decode stops at the first complete object, ignoring the rest.
            state, _ = json.JSONDecoder().raw_decode(json_str)
            return state
        except Exception as e:
            self.context.logger.exception(f"Failed to fetch or parse {url}")
            raise Exception(f"Failed to fetch or parse page: {e}")

    @staticmethod
    def _extract_tweet_id(url: str) -> Optional[str]:
        """Extract the numeric tweet ID from a tweet URL."""
        match = re.match(URL_PATTERN, url)
        return match.group(3) if match else None

    def _parse_content(self, tweet: dict) -> Optional[str]:
        """Extract clean tweet text, stripping trailing media t.co URLs.

        Prefers display_text_range to slice the text to the visible range,
        which excludes trailing media attachment links. Falls back to stripping
        trailing https://t.co/... patterns when the range is unavailable.
        """
        full_text = tweet.get("full_text") or tweet.get("text") or ""
        if not full_text:
            return None

        display_range = tweet.get("display_text_range")
        if display_range and len(display_range) == 2:
            try:
                text = full_text[int(display_range[0]):int(display_range[1])]
            except (TypeError, ValueError):
                text = full_text
        else:
            text = re.sub(r'\s*https://t\.co/\S+$', '', full_text).rstrip()

        return text.strip() or None

    @staticmethod
    def _parse_created_at(created_at: Optional[str]) -> Optional[int]:
        """Parse ISO 8601 timestamp string to Unix seconds."""
        if not created_at:
            return None
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except (ValueError, TypeError):
            return None

    def _select_best_video_variant(self, variants: list[dict]) -> Optional[dict]:
        """Select the highest-bitrate mp4 variant, excluding m3u8/HLS."""
        mp4_variants = [
            v for v in variants
            if v.get("content_type") == "video/mp4" and v.get("url")
        ]
        if not mp4_variants:
            return None
        return max(mp4_variants, key=lambda v: v.get("bitrate", 0))

    def _parse_media(self, tweet: dict) -> list[ParserMediaInfo]:
        """Parse media list from tweet entity data.

        Prefers extended_entities.media over entities.media because
        extended_entities includes all images in a multi-photo tweet and
        provides complete video variant data.
        """
        extended = tweet.get("extended_entities") or tweet.get("entities") or {}
        media_items = extended.get("media") or []
        result: list[ParserMediaInfo] = []

        for item in media_items:
            media_type = item.get("type")

            if media_type in ("video", "animated_gif"):
                video_info = item.get("video_info", {})
                variants = video_info.get("variants", [])
                best = self._select_best_video_variant(variants)
                if not best:
                    self.context.logger.debug(
                        f"{DOMAIN}: no mp4 variant found for media {item.get('id_str')}, skipping"
                    )
                    continue

                cover_url = item.get("media_url_https") or None
                original = item.get("original_info", {})

                result.append(ParserMediaInfo(
                    url=best["url"],
                    type=MediaType.VIDEO if media_type == "video" else MediaType.GIF,
                    cover=cover_url,
                    duration=video_info.get("duration_millis"),
                    width=original.get("width"),
                    height=original.get("height"),
                ))

            elif media_type == "photo":
                base_url = item.get("media_url_https") or ""
                if not base_url:
                    continue
                # Append :orig to get the original-resolution image via Twitter CDN.
                img_url = f"{base_url}:orig"
                original = item.get("original_info", {})
                sizes = item.get("sizes", {})
                large_size = sizes.get("large", {})
                result.append(ParserMediaInfo(
                    url=img_url,
                    type=MediaType.IMAGE,
                    cover=None,
                    duration=None,
                    width=original.get("width") or large_size.get("w"),
                    height=original.get("height") or large_size.get("h"),
                ))
            else:
                self.context.logger.debug(
                    f"{DOMAIN}: unknown media type {media_type!r}, skipping"
                )

        return result

    def _parse_author(self, user: dict) -> ParserAuthorInfo:
        """Parse author information from a user entity dict."""
        uid = user.get("id_str", "")
        screen_name = user.get("screen_name", "") or uid

        avatar_raw = user.get("profile_image_url_https") or ""
        # Replace _normal suffix with _400x400 for a higher-resolution avatar.
        avatar = avatar_raw.replace(AVATAR_NORMAL_SUFFIX, AVATAR_HQ_SUFFIX) if avatar_raw else None

        return ParserAuthorInfo(
            uid=uid,
            name=user.get("name") or None,
            username=screen_name,
            avatar=avatar,
            url=f"https://x.com/{screen_name}" if screen_name else None,
            banner=user.get("profile_banner_url") or None,
            description=user.get("description") or None,
        )

    def _parse_platform(self) -> ParserPlatformInfo:
        return ParserPlatformInfo(
            code=PLATFORM_CODE,
            name=PLATFORM_NAME,
            url=PLATFORM_URL,
            icon_url=PLATFORM_ICON,
        )

    async def parse(self, data: dict) -> ParserResult:
        """Parse a Twitter/X tweet page and return ParserResult."""
        if not self._session:
            raise Exception("Parser not initialized - session is None")

        url = data.get("url")
        if not url:
            raise ValueError("No URL provided for parsing")

        try:
            tweet_id = self._extract_tweet_id(url)
            if not tweet_id:
                raise ValueError(f"Cannot extract tweet ID from URL: {url!r}")

            state = await self._fetch_state(url)

            entities = state.get("entities", {})
            tweets_store = entities.get("tweets", {}).get("entities", {})
            users_store = entities.get("users", {}).get("entities", {})

            tweet = tweets_store.get(tweet_id)
            if not tweet:
                raise Exception(
                    f"Tweet {tweet_id!r} not found in page state "
                    f"(available: {list(tweets_store.keys())})"
                )

            user_id = tweet.get("user", "")
            user = users_store.get(user_id)
            if not user:
                self.context.logger.warning(
                    f"{DOMAIN}: user {user_id!r} not found in state for tweet {tweet_id}"
                )
                user = {}

            return ParserResult(
                pid=tweet_id,
                url=url,
                title=None,
                content=self._parse_content(tweet),
                media=self._parse_media(tweet),
                author=self._parse_author(user),
                platform=self._parse_platform(),
                post_time=self._parse_created_at(tweet.get("created_at")),
                parser=DOMAIN,
                state=ParserResultStatus.SUCCESS,
            )

        except Exception as e:
            self.context.logger.exception(f"Failed to parse {url}")
            raise Exception(f"Failed to parse Twitter URL: {e}")

    async def async_will_remove(self):
        """Clean up resources when removing parser."""
        if hasattr(self, '_session') and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self.context.logger.info(f"{DOMAIN} parser session closed")
