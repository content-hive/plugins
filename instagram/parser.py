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
    MEDIA_TYPE_CAROUSEL,
    MEDIA_TYPE_IMAGE,
    MEDIA_TYPE_VIDEO,
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

    async def parse(self, data: dict) -> ParserResult:
        """Parse an Instagram post URL and return a ParserResult."""
        url = data.get("url")
        if not url:
            raise ValueError("No URL provided for parsing")

        try:
            shortcode = self._extract_shortcode(url)
            if not shortcode:
                raise ValueError(f"Cannot extract shortcode from URL: {url!r}")

            raw_item = await self._client.fetch_post(shortcode)

            return ParserResult(
                pid=shortcode,
                url=url,
                title=None,
                content=(raw_item.get("caption") or {}).get("text") or None,
                media=self._collect_media(raw_item),
                author=await self._parse_author(raw_item.get("user") or {}),
                platform=self._parse_platform(),
                post_time=raw_item.get("taken_at"),
                parser=DOMAIN,
                state=ParserResultStatus.SUCCESS,
            )

        except Exception as e:
            self.context.logger.exception(f"Failed to parse {url}")
            raise Exception(f"Failed to parse Instagram URL: {e}") from e

    @staticmethod
    def _extract_shortcode(url: str) -> str | None:
        """Extract the shortcode from an Instagram post URL."""
        match = re.match(URL_PATTERN, url)
        return match.group(1) if match else None

    @staticmethod
    def _best_image_candidate(media_item: dict) -> dict | None:
        candidates = (media_item.get("image_versions2") or {}).get("candidates") or []
        return candidates[0] if candidates else None

    def _parse_media_item(self, media_item: dict) -> ParserMediaInfo | None:
        media_type = media_item.get("media_type")

        if media_type == MEDIA_TYPE_VIDEO:
            versions = media_item.get("video_versions") or []
            if not versions:
                return None
            best = versions[0]
            cover = self._best_image_candidate(media_item)
            duration_s = media_item.get("video_duration")
            return ParserMediaInfo(
                url=best.get("url") or "",
                type=MediaType.VIDEO,
                cover=cover.get("url") if cover else None,
                duration=int(duration_s * 1000) if duration_s else None,
                width=best.get("width"),
                height=best.get("height"),
            )

        if media_type == MEDIA_TYPE_IMAGE:
            best = self._best_image_candidate(media_item)
            if not best or not best.get("url"):
                return None
            return ParserMediaInfo(
                url=best["url"],
                type=MediaType.IMAGE,
                cover=None,
                duration=None,
                width=best.get("width"),
                height=best.get("height"),
            )

        self.context.logger.debug(f"{DOMAIN}: unknown private API media_type={media_type}, skipping")
        return None

    def _collect_media(self, item: dict) -> list[ParserMediaInfo]:
        media_type = item.get("media_type")
        result: list[ParserMediaInfo] = []

        if media_type == MEDIA_TYPE_CAROUSEL:
            for child in item.get("carousel_media") or []:
                parsed = self._parse_media_item(child)
                if parsed:
                    result.append(parsed)
        else:
            parsed = self._parse_media_item(item)
            if parsed:
                result.append(parsed)

        return result

    async def _parse_author(self, user: dict) -> ParserAuthorInfo:
        """Build ParserAuthorInfo, enriching with full profile data when available."""
        username = user.get("username") or ""
        if username:
            try:
                self.context.logger.debug(f"{DOMAIN}: enriching user info (username={username})")
                user = await self._client.fetch_user(username)
            except Exception:
                self.context.logger.warning(f"{DOMAIN}: failed to enrich user info, using post author data")

        uid = str(user.get("pk") or "")
        hd_info = user.get("hd_profile_pic_url_info") or {}
        versions = user.get("hd_profile_pic_versions") or []
        avatar = hd_info.get("url") or (versions[-1].get("url") if versions else None) or user.get("profile_pic_url")
        username = user.get("username") or uid

        return ParserAuthorInfo(
            uid=uid,
            name=user.get("full_name") or None,
            username=username,
            avatar=avatar,
            url=f"https://www.instagram.com/{username}/" if username else None,
            banner=None,
            description=user.get("biography") or None,
        )

    @staticmethod
    def _parse_platform() -> ParserPlatformInfo:
        return ParserPlatformInfo(
            code=PLATFORM_CODE,
            name=PLATFORM_NAME,
            url=PLATFORM_URL,
            icon_url=PLATFORM_ICON,
        )
