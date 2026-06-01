"""Instagram content parser plugin."""

import re

from contenthive.plugins.context import PluginContext
from contenthive.plugins.contracts import (
    MediaType,
    ParserAuthorInfo,
    ParserMediaInfo,
    ParserPlatformInfo,
    ParserResult,
    ParserResultStatus,
)

from .api_client import InstagramAPIClient
from .const import (
    DOMAIN,
    PLATFORM_CODE,
    PLATFORM_ICON,
    PLATFORM_NAME,
    PLATFORM_URL,
    URL_PATTERN,
)


async def async_setup_entry(context: PluginContext, entry, async_add_entities):
    """Set up parser entities from a config entry."""
    parser = InstagramParser(context, entry)
    await async_add_entities([parser])

    if context.register_service:
        context.register_service(DOMAIN, "can_parse", parser.can_parse)
        context.register_service(DOMAIN, "parse", parser.parse)

    context.logger.info(f"{DOMAIN} parser platform setup completed")


class InstagramParser:
    """Parser for Instagram posts, reels, and IGTV via Instagram API."""

    def __init__(self, context: PluginContext, entry):
        self.context = context
        self.entry = entry
        self.domain = DOMAIN
        self._client: InstagramAPIClient = context.data[DOMAIN]["client"]

    def can_parse(self, data: dict) -> bool:
        """Return True if the URL is a parseable Instagram post/reel/TV URL."""
        url = data.get("url")
        if not url:
            return False
        return bool(re.match(URL_PATTERN, url))

    @staticmethod
    def _extract_shortcode(url: str) -> str | None:
        """Extract the shortcode from an Instagram post URL."""
        match = re.match(URL_PATTERN, url)
        return match.group(1) if match else None

    def _parse_media(self, media_list: list[dict]) -> list[ParserMediaInfo]:
        result: list[ParserMediaInfo] = []
        for item in media_list:
            url = item.get("url")
            if not url:
                continue
            media_type = item.get("type")
            if media_type == "video":
                result.append(
                    ParserMediaInfo(
                        url=url,
                        type=MediaType.VIDEO,
                        cover=item.get("cover") or None,
                        duration=item.get("duration_ms"),
                        width=item.get("width"),
                        height=item.get("height"),
                    )
                )
            elif media_type == "image":
                result.append(
                    ParserMediaInfo(
                        url=url,
                        type=MediaType.IMAGE,
                        cover=None,
                        duration=None,
                        width=item.get("width"),
                        height=item.get("height"),
                    )
                )
            else:
                self.context.logger.debug(f"{DOMAIN}: unknown media type {media_type!r}, skipping")
        return result

    @staticmethod
    def _parse_author(user: dict) -> ParserAuthorInfo:
        uid = user.get("uid") or ""
        username = user.get("username") or uid
        return ParserAuthorInfo(
            uid=uid,
            name=user.get("name") or None,
            username=username,
            avatar=user.get("avatar") or None,
            url=f"https://www.instagram.com/{username}/" if username else None,
            banner=None,
            description=None,
        )

    @staticmethod
    def _parse_platform() -> ParserPlatformInfo:
        return ParserPlatformInfo(
            code=PLATFORM_CODE,
            name=PLATFORM_NAME,
            url=PLATFORM_URL,
            icon_url=PLATFORM_ICON,
        )

    async def parse(self, data: dict) -> ParserResult:
        """Parse an Instagram post URL and return a ParserResult."""
        url = data.get("url")
        if not url:
            raise ValueError("No URL provided for parsing")

        try:
            shortcode = self._extract_shortcode(url)
            if not shortcode:
                raise ValueError(f"Cannot extract shortcode from URL: {url!r}")

            post = await self._client.fetch_post(shortcode, url)

            return ParserResult(
                pid=shortcode,
                url=url,
                title=None,
                content=post.get("caption") or None,
                media=self._parse_media(post.get("media") or []),
                author=self._parse_author(post.get("user") or {}),
                platform=self._parse_platform(),
                post_time=post.get("taken_at"),
                parser=DOMAIN,
                state=ParserResultStatus.SUCCESS,
            )

        except Exception as e:
            self.context.logger.exception(f"Failed to parse {url}")
            raise Exception(f"Failed to parse Instagram URL: {e}") from e
