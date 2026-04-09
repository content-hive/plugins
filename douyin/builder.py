"""ParserResult builder helpers for the Douyin parser plugin."""

from pydantic import HttpUrl

from contenthive.models.enumerates import MediaType, ParserResultStatus
from contenthive.models.parser import (
    ParserAuthorInfo,
    ParserMediaInfo,
    ParserPlatformInfo,
    ParserResult,
)

from .const import (
    DOMAIN,
    GALLERY_AWEME_TYPES,
    PLATFORM_CODE,
    PLATFORM_ICON,
    PLATFORM_NAME,
    PLATFORM_URL,
)
from .utils import extract_first_url, iter_gallery_items, pick_first_url


def detect_media_type(aweme: dict) -> str:
    """Return 'gallery' or 'video' based on aweme fields."""
    if aweme.get("image_post_info") or aweme.get("images") or aweme.get("image_list"):
        return "gallery"
    aweme_type = aweme.get("aweme_type")
    if isinstance(aweme_type, int) and aweme_type in GALLERY_AWEME_TYPES:
        return "gallery"
    return "video"


def build_video_media(aweme: dict) -> list[ParserMediaInfo]:
    """Build a single-item list with the video's ParserMediaInfo."""
    video = aweme.get("video") or {}
    play_addr = video.get("play_addr") or {}
    url_list = [u for u in (play_addr.get("url_list") or []) if u]
    if not url_list:
        return []

    # Prefer no-watermark URLs
    url_list.sort(key=lambda u: 0 if "watermark=0" in u else 1)
    video_url = url_list[0]

    cover_url = extract_first_url(video.get("cover"))
    duration = video.get("duration")  # milliseconds
    width = video.get("width") or play_addr.get("width")
    height = video.get("height") or play_addr.get("height")

    return [
        ParserMediaInfo(
            url=HttpUrl(video_url),
            type=MediaType.VIDEO,
            title=None,
            cover=HttpUrl(cover_url) if cover_url else None,
            duration=duration,
            width=width,
            height=height,
        )
    ]


def build_gallery_media(aweme: dict) -> list[ParserMediaInfo]:
    """Build a list of ParserMediaInfo for each image/live-photo in the gallery."""
    media_list: list[ParserMediaInfo] = []

    for item in iter_gallery_items(aweme):
        if not isinstance(item, dict):
            continue

        image_url = pick_first_url(
            item.get("download_url"),
            item.get("download_addr"),
            item.get("display_image"),
            item.get("owner_watermark_image"),
        )
        if not image_url:
            continue

        # Live photo: the gallery item embeds a short video clip
        video = item.get("video") if isinstance(item.get("video"), dict) else {}
        live_url = pick_first_url(
            video.get("play_addr"),
            video.get("download_addr"),
            item.get("video_play_addr"),
            item.get("video_download_addr"),
        )

        if live_url:
            media_list.append(
                ParserMediaInfo(
                    url=HttpUrl(live_url),
                    type=MediaType.LIVEPHOTO,
                    title=None,
                    cover=HttpUrl(image_url),
                    duration=None,
                    width=item.get("width"),
                    height=item.get("height"),
                )
            )
        else:
            media_list.append(
                ParserMediaInfo(
                    url=HttpUrl(image_url),
                    type=MediaType.IMAGE,
                    title=None,
                    cover=None,
                    duration=None,
                    width=item.get("width"),
                    height=item.get("height"),
                )
            )

    return media_list


def build_author(aweme: dict) -> ParserAuthorInfo:
    """Build a ParserAuthorInfo from aweme author data."""
    author = aweme.get("author") or {}
    uid = str(author.get("uid") or "")
    sec_uid = author.get("sec_uid") or ""
    nickname = author.get("nickname") or ""
    short_id = author.get("short_id") or ""
    avatar_url = author.get("avatar_thumb", {}).get("url_list", [None])[0] or author.get("avatar_medium", {}).get("url_list", [None])[0]
    profile_url = f"{PLATFORM_URL}/user/{sec_uid}" if sec_uid else None

    return ParserAuthorInfo(
        uid=uid,
        name=nickname or None,
        username=short_id or uid,
        avatar=HttpUrl(avatar_url) if avatar_url else None,
        url=HttpUrl(profile_url) if profile_url else None,
        banner=None,
        description=author.get("signature") or None,
    )


def build_platform() -> ParserPlatformInfo:
    """Get platform information."""
    return ParserPlatformInfo(
        code=PLATFORM_CODE,
        name=PLATFORM_NAME,
        url=HttpUrl(PLATFORM_URL),
        icon_url=HttpUrl(PLATFORM_ICON)
    )


def build_result(url: str, aweme: dict) -> ParserResult:
    """Assemble a complete ParserResult from a raw aweme dict."""
    media_type = detect_media_type(aweme)
    return ParserResult(
        pid=str(aweme["aweme_id"]),
        url=HttpUrl(url),
        title=None,
        content=aweme.get("desc") or None,
        media=(
            build_video_media(aweme)
            if media_type == "video"
            else build_gallery_media(aweme)
        ),
        author=build_author(aweme),
        platform=build_platform(),
        post_time=aweme.get("create_time") or None,
        parser=DOMAIN,
        state=ParserResultStatus.SUCCESS,
    )
