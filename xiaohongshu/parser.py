"""
Xiaohongshu (Little Red Book) content parser plugin.
"""
import json
import re
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from pydantic import HttpUrl
from contenthive.models.parser import (
    ParserResult,
    ParserMediaInfo,
    ParserAuthorInfo, 
    ParserPlatformInfo
)
from contenthive.models.enumerates import MediaType, ParserResultStatus
from contenthive.plugins.context import PluginContext
from .const import (
    DOMAIN,
    IMAGE_CDN_URL,
    PLATFORM_CODE,
    PLATFORM_NAME,
    PLATFORM_URL,
    PLATFORM_ICON,
    STREAM_CODEC_PRIORITY,
    REQUEST_HEADERS,
    JS_INVALID_TOKENS,
    VIDEO_CDN_URL,
    URL_PATTERN
)


async def async_setup_entry(context: PluginContext, entry, async_add_entities):
    """Set up parser entities from a config entry."""
    parser = XiaohongshuParser(context, entry)
    await parser.async_setup()
    await async_add_entities([parser])

    if context.register_service:
        context.register_service(DOMAIN, "can_parse", parser.can_parse)
        context.register_service(DOMAIN, "parse", parser.parse)

    context.logger.info(f"{DOMAIN} parser platform setup completed")


class XiaohongshuParser:
    """Parser for Xiaohongshu (Little Red Book) content."""
    def __init__(self, context: PluginContext, entry):
        self.context = context
        self.entry = entry
        self.domain = DOMAIN
        self._session: Optional[aiohttp.ClientSession] = None

    async def async_setup(self):
        """Initialize parser."""
        try:
            self._session = aiohttp.ClientSession(trust_env=True)
            self.context.logger.info(f"{DOMAIN} parser initialized")
        except Exception as e:
            self.context.logger.error(f"Failed to initialize parser: {e}")
            await self.async_will_remove()
            raise

    def can_parse(self, data: dict) -> bool:
        """Check if the URL is a Xiaohongshu note URL."""
        url = data.get("url")
        if not url:
            return False
        return bool(re.match(URL_PATTERN, url))

    async def _fetch_state(self, url: str) -> dict:
        """Fetch a Xiaohongshu page and extract window.__INITIAL_STATE__ as a dict.

        Args:
            url: The page URL to fetch.

        Returns:
            Parsed state dict.

        Raises:
            Exception: If the request fails or the state JSON cannot be found/parsed.
        """
        if not self._session:
            raise Exception("Parser not initialized - session is None")
        try:
            async with self._session.get(url, headers=REQUEST_HEADERS) as resp:
                html = await resp.text()
                if resp.status != 200:
                    preview = html[:500].replace("\n", " ") if html else ""
                    raise Exception(
                        f"HTTP {resp.status} fetching {url!r}; body preview: {preview!r}"
                    )
            match = re.search(r"window\.__INITIAL_STATE__=({.*?})</script>", html, re.DOTALL)
            if not match:
                raise Exception("No window.__INITIAL_STATE__ JSON found")
            # Replace JS-only tokens with JSON null using word boundaries
            # to avoid corrupting occurrences inside string values.
            state_json = re.compile(JS_INVALID_TOKENS).sub("null", match.group(1))
            return json.loads(state_json)
        except Exception as e:
            self.context.logger.error(f"Failed to fetch or parse {url}: {e}")
            raise Exception(f"Failed to fetch or parse page: {e}")

    def _extract_master_url(self, stream: dict) -> Optional[str]:
        """Extract the best available video master URL from a stream dict.

        Iterate codecs in priority order and return the masterUrl of the
        first stream entry found.

        Args:
            stream: Stream dict containing codec keys (h264, h265, h266, av1).

        Returns:
            masterUrl string, or None if no valid stream entry is found.
        """
        for codec in STREAM_CODEC_PRIORITY:
            entries = stream.get(codec) or []
            if entries and entries[0].get("masterUrl"):
                url = entries[0]["masterUrl"]
                url = re.sub(r"^https?://[^/]+", VIDEO_CDN_URL, url)
                return url
        return None

    def _extract_trace_id(self, url: str) -> Optional[str]:
        """Extract traceId from a Xiaohongshu URL.

        Args:
            url: The URL string to extract from.
        Returns:
            traceId string if found, else None.
        """
        path = urlparse(url).path
        trace_id = path.split("/")[-1].split("!")[0]
        if "spectrum" in path:
            return "spectrum/" + trace_id
        if "notes_pre_post" in path:
            return "notes_pre_post/" + trace_id
        if "notes_uhdr" in path:
            return "notes_uhdr/" + trace_id
        return trace_id

    def _get_img_url_by_trace_id(self, trace_id: str) -> Optional[str]:
        """Construct image URL from traceId.

        Args:
            trace_id: The traceId extracted from the URL.

        Returns:
            Constructed image URL string.
        """
        return f"{IMAGE_CDN_URL}/{trace_id}?imageView2/format/webp"
    
    def _parse_media(self, note: dict) -> list[ParserMediaInfo]:
        """Parse media list from note data.

        Args:
            note: Note data dict from noteDetailMap.

        Returns:
            List of ParserMediaInfo objects.
        """
        media_list = []
        note_type = note.get("type", "normal")

        if note_type == "video":
            # Video note: imageList[0] is cover, video is in note.video.media.stream
            cover = (note.get("imageList") or [{}])[0].get("urlDefault")
            cover_trace_id = self._extract_trace_id(cover) if cover else None
            cover_url = self._get_img_url_by_trace_id(cover_trace_id) if cover_trace_id else None

            stream = (
                note.get("video", {})
                    .get("media", {})
                    .get("stream", {})
            )
            vid_url = self._extract_master_url(stream)
            if vid_url:
                media_list.append(ParserMediaInfo(
                    url=HttpUrl(vid_url),
                    type=MediaType.VIDEO,
                    title=None,
                    cover=HttpUrl(cover_url) if cover_url else None
                ))
        else:
            # Image note: iterate imageList, distinguish normal image and live photo
            for img in note.get("imageList", []):
                img_trace_id = self._extract_trace_id(img.get("urlDefault")) if img.get("urlDefault") else None
                img_url = self._get_img_url_by_trace_id(img_trace_id) if img_trace_id else None
                if not img_url:
                    continue
                if img.get("livePhoto", False):
                    # Live photo: video in stream, cover is image
                    vid_url = self._extract_master_url(img.get("stream", {}))
                    if vid_url:
                        media_list.append(ParserMediaInfo(
                            url=HttpUrl(vid_url),
                            type=MediaType.LIVEPHOTO,
                            title=None,
                            cover=HttpUrl(img_url)
                        ))
                else:
                    # Normal image
                    media_list.append(ParserMediaInfo(
                        url=HttpUrl(img_url),
                        type=MediaType.IMAGE,
                        title=None,
                        cover=None
                    ))

        return media_list

    async def _parse_author(self, note: dict) -> ParserAuthorInfo:
        """Parse author information from note data.

        Fetches the user profile page to retrieve redId, which is not
        available in the note page state.

        Args:
            note: Note data dict from noteDetailMap.

        Returns:
            ParserAuthorInfo object.
        """
        user = note.get("user", {})
        user_id = user.get("userId", "")
        if not user_id:
            self.context.logger.warning("No userId found in note data")
            return ParserAuthorInfo(
                uid="",
                name=user.get("nickname", ""),
                username=user_id,
                avatar=HttpUrl(user.get("avatar")) if user.get("avatar") else None,
                url=None
            )
        
        profile_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
        
        red_id = ""
        try:
            profile_state = await self._fetch_state(profile_url)
            red_id = (
                profile_state.get("user", {})
                            .get("userPageData", {})
                            .get("basicInfo", {})
                            .get("redId", "")
            )
        except Exception as e:
            self.context.logger.warning(f"Failed to fetch redId for user {user_id}: {e}")

        return ParserAuthorInfo(
            uid=user_id,
            name=user.get("nickname", ""),
            username=red_id or user_id,
            avatar=HttpUrl(user.get("avatar")) if user.get("avatar") else None,
            url=HttpUrl(profile_url)
        )

    def _parse_platform(self) -> ParserPlatformInfo:
        """Build platform information for Xiaohongshu.

        Returns:
            ParserPlatformInfo object.
        """
        return ParserPlatformInfo(
            code=PLATFORM_CODE,
            name=PLATFORM_NAME,
            url=HttpUrl(PLATFORM_URL),
            icon_url=HttpUrl(PLATFORM_ICON)
        )

    async def parse(self, data: dict) -> ParserResult:
        """Parse Xiaohongshu note page and return ParserResult."""

        if not self._session:
            raise Exception("Parser not initialized - session is None")

        url = data.get("url")
        if not url:
            raise ValueError("No URL provided for parsing")

        try:
            state = await self._fetch_state(url)

            # Extract note ID
            note_id = state.get("note", {}).get("currentNoteId")
            note_map = state.get("note", {}).get("noteDetailMap", {})
            note_detail = note_map.get(note_id) if note_id and note_map else None
            note = note_detail.get("note") if note_detail else None
            if not note:
                raise Exception("No note data found in JSON")

            # Title and content
            title = note.get("title")
            content = note.get("desc")

            # Publish time
            post_time = note.get("lastUpdateTime") / 1000 if note.get("lastUpdateTime") else None

            return ParserResult(
                pid=note_id,
                url=HttpUrl(url),
                title=title,
                content=content,
                media=self._parse_media(note),
                author=await self._parse_author(note),
                platform=self._parse_platform(),
                post_time=post_time,
                parser=DOMAIN,
                state=ParserResultStatus.SUCCESS
            )
        except Exception as e:
            self.context.logger.error(f"Failed to parse {url}: {e}")
            raise Exception(f"Failed to parse Xiaohongshu URL: {e}")

    async def async_will_remove(self):
        """Clean up resources when removing parser."""
        if hasattr(self, '_session') and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self.context.logger.info(f"{DOMAIN} parser session closed")