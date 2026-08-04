"""X(Twitter) content parser plugin."""

import re
from email.utils import parsedate_to_datetime

from contenthive.plugins.context import PluginContext
from contenthive.plugins.contracts import (
    MediaType,
    ParserAuthorInfo,
    ParserMediaInfo,
    ParserPlatformInfo,
    ParserResult,
    ParserResultStatus,
)

from .api_client import TwitterAPIClient
from .const import (
    AVATAR_HQ_SUFFIX,
    AVATAR_NORMAL_SUFFIX,
    DOMAIN,
    PLATFORM_CODE,
    PLATFORM_ICON,
    PLATFORM_NAME,
    PLATFORM_URL,
    URL_PATTERN,
)


async def async_setup_entry(context: PluginContext, entry, async_add_entities):
    """Set up parser entities from a config entry."""
    parser = TwitterParser(context, entry)
    await async_add_entities([parser])

    if context.register_service:
        context.register_service(DOMAIN, "can_parse", parser.can_parse)
        context.register_service(DOMAIN, "parse", parser.parse)

    context.logger.info(f"{DOMAIN} parser platform setup completed")


class TwitterParser:
    """Parser for X(Twitter) content via GraphQL API."""

    def __init__(self, context: PluginContext, entry):
        self.context = context
        self.entry = entry
        self.domain = DOMAIN
        self._client: TwitterAPIClient = context.data[DOMAIN]["client"]

    def can_parse(self, data: dict) -> bool:
        """Check if the URL is a Twitter/X tweet URL."""
        url = data.get("url")
        if not url:
            return False
        return bool(re.match(URL_PATTERN, url))

    @staticmethod
    def _extract_tweet_id(url: str) -> str | None:
        """Extract the numeric tweet ID from a tweet URL."""
        match = re.match(URL_PATTERN, url)
        return match.group(3) if match else None

    def _parse_content(self, tweet: dict) -> str | None:
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
                text = full_text[int(display_range[0]) : int(display_range[1])]
            except (TypeError, ValueError):
                text = full_text
        else:
            text = re.sub(r"\s*https://t\.co/\S+$", "", full_text).rstrip()

        return text.strip() or None

    @staticmethod
    def _parse_created_at(created_at: str | None) -> int | None:
        """Parse RFC 2822 tweet timestamp to Unix seconds."""
        if not created_at:
            return None
        try:
            return int(parsedate_to_datetime(created_at).timestamp())
        except Exception:
            return None

    def _select_best_video_variant(self, variants: list[dict]) -> dict | None:
        """Select the highest-bitrate mp4 variant, excluding m3u8/HLS."""
        mp4_variants = [v for v in variants if v.get("content_type") == "video/mp4" and v.get("url")]
        if not mp4_variants:
            return None
        return max(mp4_variants, key=lambda v: v.get("bitrate", 0))

    def _parse_media(self, tweet: dict) -> list[ParserMediaInfo]:
        """Parse media list from tweet GraphQL entity data."""
        media_items = (
            (tweet.get("extended_entities") or {}).get("media") or (tweet.get("entities") or {}).get("media") or []
        )
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

                result.append(
                    ParserMediaInfo(
                        url=best["url"],
                        type=MediaType.VIDEO if media_type == "video" else MediaType.GIF,
                        cover=cover_url,
                        duration=video_info.get("duration_millis"),
                        width=original.get("width"),
                        height=original.get("height"),
                    )
                )

            elif media_type == "photo":
                base_url = item.get("media_url_https") or ""
                if not base_url:
                    continue
                # Append :orig to get the original-resolution image via Twitter CDN.
                img_url = f"{base_url}:orig"
                original = item.get("original_info", {})
                sizes = item.get("sizes", {})
                large_size = sizes.get("large", {})
                result.append(
                    ParserMediaInfo(
                        url=img_url,
                        type=MediaType.IMAGE,
                        cover=None,
                        duration=None,
                        width=original.get("width") or large_size.get("w"),
                        height=original.get("height") or large_size.get("h"),
                    )
                )
            else:
                self.context.logger.debug(f"{DOMAIN}: unknown media type {media_type!r}, skipping")

        return result

    def _parse_author(self, user: dict) -> ParserAuthorInfo:
        """Parse author information from a user entity dict."""
        if not user:
            self.context.logger.warning(f"{DOMAIN}: _parse_author received empty user dict — author info will be empty")
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
        """Parse a Twitter/X tweet and return ParserResult."""
        if not self._client:
            raise Exception("Parser not initialized - client is None")

        url = data.get("url")
        if not url:
            raise ValueError("No URL provided for parsing")

        try:
            tweet_id = self._extract_tweet_id(url)
            if not tweet_id:
                raise ValueError(f"Cannot extract tweet ID from URL: {url!r}")

            tweet, user = await self._client.fetch_tweet(tweet_id)

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
            raise Exception(f"Failed to parse Twitter URL: {e}") from e
