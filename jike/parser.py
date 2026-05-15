"""
Jike (即刻) content parser plugin.
"""

import json
import re
from datetime import datetime

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
    MEDIA_PLAY_API,
    MEDIA_PLAY_HEADERS,
    PLATFORM_CODE,
    PLATFORM_ICON,
    PLATFORM_NAME,
    PLATFORM_URL,
    REQUEST_HEADERS,
    URL_PATTERN,
    WEB_POST_ID_RE,
)


async def async_setup_entry(context: PluginContext, entry, async_add_entities):
    """Set up parser entities from a config entry."""
    parser = JikeParser(context, entry)
    await parser.async_setup()
    await async_add_entities([parser])

    if context.register_service:
        context.register_service(DOMAIN, "can_parse", parser.can_parse)
        context.register_service(DOMAIN, "parse", parser.parse)

    context.logger.info(f"{DOMAIN} parser platform setup completed")


class JikeParser:
    """Parser for Jike (即刻) content."""

    def __init__(self, context: PluginContext, entry):
        self.context = context
        self.entry = entry
        self.domain = DOMAIN
        self._session: aiohttp.ClientSession | None = None

    async def async_setup(self):
        """Initialize parser."""
        self._session = aiohttp.ClientSession(trust_env=True)
        self.context.logger.debug(f"{DOMAIN} parser initialized")

    def can_parse(self, data: dict) -> bool:
        """Check if the URL is a Jike post URL."""
        url = data.get("url")
        if not url:
            return False
        return bool(re.match(URL_PATTERN, url))

    def _normalize_url(self, url: str) -> str:
        """Convert a web.okjike.com share URL to the m.okjike.com fetch URL.

        web.okjike.com/u/<username>/post/<id> → m.okjike.com/originalPosts/<id>
        m.okjike.com URLs are returned unchanged.
        """
        match = re.search(WEB_POST_ID_RE, url)
        if match:
            post_id = match.group(1)
            return f"https://m.okjike.com/originalPosts/{post_id}"
        return url

    async def _fetch_next_data(self, url: str) -> dict:
        """Fetch a Jike post page and extract __NEXT_DATA__ as a dict.

        Args:
            url: The post URL to fetch (will be normalized if needed).

        Returns:
            Post dict from props.pageProps.post.

        Raises:
            Exception: If the request fails or the JSON cannot be found/parsed.
        """
        if not self._session:
            raise Exception("Parser not initialized - session is None")

        fetch_url = self._normalize_url(url)
        try:
            async with self._session.get(fetch_url, headers=REQUEST_HEADERS) as resp:
                html = await resp.text()
                if resp.status != 200:
                    preview = html[:500].replace("\n", " ") if html else ""
                    raise Exception(f"HTTP {resp.status} fetching {fetch_url!r}; body preview: {preview!r}")

            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                html,
                re.DOTALL,
            )
            if not match:
                raise Exception("No __NEXT_DATA__ JSON found in page")

            data = json.loads(match.group(1))
            post = data.get("props", {}).get("pageProps", {}).get("post")
            if not post:
                raise Exception("No post data found in __NEXT_DATA__")
            return post
        except Exception as e:
            self.context.logger.exception(f"Failed to fetch or parse {fetch_url}")
            raise Exception(f"Failed to fetch or parse page: {e}") from e

    async def _fetch_video_url(self, post_id: str, post_type: str) -> str | None:
        """Fetch the signed video URL from the Jike media play API.

        The video URL is not embedded in __NEXT_DATA__ — it must be fetched
        separately via a signed URL API that requires no authentication.

        Args:
            post_id: The post ID.
            post_type: The post type string (e.g. "ORIGINAL_POST").

        Returns:
            Signed CDN video URL, or None if unavailable.
        """
        if not self._session:
            return None
        try:
            params = {"type": post_type, "id": post_id}
            async with self._session.post(MEDIA_PLAY_API, params=params, headers=MEDIA_PLAY_HEADERS) as resp:
                if resp.status != 200:
                    self.context.logger.warning(f"mediaMeta/play returned HTTP {resp.status} for post {post_id}")
                    return None
                result = await resp.json()
                return result.get("url")
        except Exception:
            self.context.logger.warning(f"Failed to fetch video URL for post {post_id}", exc_info=True)
            return None

    def _parse_media(self, post: dict, video_url: str | None) -> list[ParserMediaInfo]:
        """Parse media list from post data.

        Args:
            post: Post dict from pageProps.post.

        Returns:
            List of ParserMediaInfo objects.
        """
        media_list = []
        for pic in post.get("pictures", []):
            pic_url = pic.get("picUrl")
            if not pic_url:
                continue
            width = pic.get("width")
            height = pic.get("height")
            live_photo = pic.get("livePhoto")
            if live_photo and live_photo.get("videoUrl"):
                media_list.append(
                    ParserMediaInfo(
                        url=live_photo["videoUrl"],
                        type=MediaType.LIVEPHOTO,
                        cover=pic_url,
                        width=width,
                        height=height,
                    )
                )
            else:
                media_list.append(
                    ParserMediaInfo(
                        url=pic_url,
                        type=MediaType.IMAGE,
                        width=width,
                        height=height,
                    )
                )

        video = post.get("video")
        if video and video_url:
            cover = (video.get("image") or {}).get("picUrl")
            media_list.append(
                ParserMediaInfo(
                    url=video_url,
                    type=MediaType.VIDEO,
                    cover=cover or None,
                    duration=video.get("duration"),
                    width=video.get("width"),
                    height=video.get("height"),
                )
            )

        return media_list

    def _parse_author(self, post: dict) -> ParserAuthorInfo:
        """Parse author information from post data.

        All user fields are embedded in the post JSON — no extra request needed.

        Args:
            post: Post dict from pageProps.post.

        Returns:
            ParserAuthorInfo object.
        """
        user = post.get("user", {})
        uid = user.get("id", "")
        username = user.get("username") or uid
        name = user.get("screenName", "")
        avatar = (user.get("avatarImage") or {}).get("picUrl")
        banner = (user.get("backgroundImage") or {}).get("picUrl")
        description = user.get("briefIntro") or user.get("bio") or ""
        profile_url = f"https://m.okjike.com/users/{username}" if username else None

        return ParserAuthorInfo(
            uid=uid,
            name=name,
            username=username,
            avatar=avatar or None,
            url=profile_url,
            banner=banner or None,
            description=description,
        )

    def _parse_content(self, post: dict) -> str:
        """Assemble post content, appending linkInfo as a Markdown link if present.

        Args:
            post: Post dict from pageProps.post.

        Returns:
            Content string with optional link appended.
        """
        content = post.get("content") or ""
        link_info = post.get("linkInfo")
        if link_info and link_info.get("linkUrl"):
            link_title = link_info.get("title") or link_info["linkUrl"]
            content = f"{content}\n\n[{link_title}]({link_info['linkUrl']})"
        return content

    def _parse_platform(self) -> ParserPlatformInfo:
        """Build platform information for Jike."""
        return ParserPlatformInfo(
            code=PLATFORM_CODE,
            name=PLATFORM_NAME,
            url=PLATFORM_URL,
            icon_url=PLATFORM_ICON,
        )

    async def parse(self, data: dict) -> ParserResult:
        """Parse Jike post page and return ParserResult."""
        if not self._session:
            raise Exception("Parser not initialized - session is None")

        url = data.get("url")
        if not url:
            raise ValueError("No URL provided for parsing")

        try:
            post = await self._fetch_next_data(url)

            post_id = post.get("id")
            if not post_id:
                raise Exception("No post id found in __NEXT_DATA__")

            created_at = post.get("createdAt")
            post_time: float | None = None
            if created_at:
                try:
                    post_time = datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    self.context.logger.warning(f"Failed to parse createdAt: {created_at!r}")

            video_url: str | None = None
            if post.get("video"):
                video_url = await self._fetch_video_url(post_id, post.get("type", "ORIGINAL_POST"))

            return ParserResult(
                pid=post_id,
                url=url,
                title=None,
                content=self._parse_content(post),
                media=self._parse_media(post, video_url),
                author=self._parse_author(post),
                platform=self._parse_platform(),
                post_time=int(post_time) if post_time is not None else None,
                parser=DOMAIN,
                state=ParserResultStatus.SUCCESS,
            )
        except Exception as e:
            self.context.logger.exception(f"Failed to parse {url}")
            raise Exception(f"Failed to parse Jike URL: {e}") from e

    async def async_will_remove(self):
        """Clean up resources when removing parser."""
        if hasattr(self, "_session") and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self.context.logger.info(f"{DOMAIN} parser session closed")
