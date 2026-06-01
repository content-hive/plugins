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

    @staticmethod
    def _extract_shortcode(url: str) -> str | None:
        """Extract the shortcode from an Instagram post URL."""
        match = re.match(URL_PATTERN, url)
        return match.group(1) if match else None

    @staticmethod
    def _best_image_url(media_item: dict) -> str | None:
        candidates = (media_item.get("image_versions2") or {}).get("candidates") or []
        return candidates[0].get("url") if candidates else None

    def _normalize_media_item(self, media_item: dict) -> dict | None:
        media_type = media_item.get("media_type")

        if media_type == MEDIA_TYPE_VIDEO:
            versions = media_item.get("video_versions") or []
            if not versions:
                return None
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

        self.context.logger.debug(f"{DOMAIN}: unknown private API media_type={media_type}, skipping")
        return None

    def _normalize_post_item(self, item: dict) -> dict:
        user = item.get("user") or {}
        caption_text = (item.get("caption") or {}).get("text") or None
        media_type = item.get("media_type")

        media: list[dict] = []
        if media_type == MEDIA_TYPE_CAROUSEL:
            for child in item.get("carousel_media") or []:
                entry = self._normalize_media_item(child)
                if entry:
                    media.append(entry)
        else:
            entry = self._normalize_media_item(item)
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

    @staticmethod
    def _normalize_user(user: dict) -> dict:
        versions = user.get("hd_profile_pic_versions") or []
        pic_hd = versions[-1] if versions else (user.get("hd_profile_pic_url_info") or {})
        return {
            "uid": str(user.get("pk") or ""),
            "username": user.get("username") or "",
            "name": user.get("full_name") or None,
            "avatar": pic_hd.get("url") or user.get("profile_pic_url") or None,
            "bio": user.get("biography") or None,
            "is_private": user.get("is_private") or False,
            "is_verified": user.get("is_verified") or False,
            "follower_count": user.get("follower_count"),
            "following_count": user.get("following_count"),
            "media_count": user.get("media_count"),
            "external_url": user.get("external_url") or None,
        }

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

            raw_item = await self._client.fetch_post(shortcode)
            post = self._normalize_post_item(raw_item)

            username = (post.get("user") or {}).get("username")
            if username:
                try:
                    self.context.logger.debug(f"{DOMAIN}: enriching user info (username={username})")
                    raw_user = await self._client.fetch_user(username)
                    post["user"] = self._normalize_user(raw_user)
                except Exception as e:
                    self.context.logger.warning(f"{DOMAIN}: failed to enrich user info: {e}")

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
