"""
X(Twitter) content parser plugin.
Fetches tweet data via GraphQL API with guest token auth, falling back to
the Syndication API on rate-limit (HTTP 429).
"""

import json
import math
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

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
    API_BASE,
    AUTH_TOKEN,
    AVATAR_HQ_SUFFIX,
    AVATAR_NORMAL_SUFFIX,
    DOMAIN,
    GRAPHQL_API_BASE,
    GRAPHQL_ENDPOINT,
    GRAPHQL_FEATURES,
    PLATFORM_CODE,
    PLATFORM_ICON,
    PLATFORM_NAME,
    PLATFORM_URL,
    REQUEST_HEADERS,
    SYNDICATION_API_URL,
    URL_PATTERN,
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
    """Parser for X(Twitter) content via GraphQL API."""

    def __init__(self, context: PluginContext, entry):
        self.context = context
        self.entry = entry
        self.domain = DOMAIN
        self._session: aiohttp.ClientSession | None = None
        self._guest_token: str | None = None
        self._csrf_token: str | None = None

    async def async_setup(self):
        """Initialize parser."""
        # max_field_size raised because Twitter's CSP response headers exceed
        # aiohttp's default 8190-byte limit.
        self._session = aiohttp.ClientSession(trust_env=True, max_field_size=65536)
        await self._init_cookies()
        self.context.logger.debug(f"{DOMAIN} parser initialized")

    async def _init_cookies(self):
        """Seed the session with x.com cookies (including ct0 for CSRF).

        A plain GET to the x.com homepage sets the ct0 CSRF cookie that the
        GraphQL API requires even for guest access.  Without it, tweetResult
        is returned as an empty dict.
        """
        if not self._session:
            return
        try:
            async with self._session.get(
                "https://x.com/",
                headers=REQUEST_HEADERS,
                allow_redirects=True,
            ) as resp:
                ct0 = resp.cookies.get("ct0")
                if ct0:
                    self._csrf_token = ct0.value
                    self.context.logger.debug(f"{DOMAIN}: ct0 cookie obtained from x.com")
                else:
                    self.context.logger.debug(f"{DOMAIN}: ct0 cookie not set by x.com")
        except Exception as e:
            self.context.logger.debug(f"{DOMAIN}: failed to init cookies from x.com: {e}")

    def can_parse(self, data: dict) -> bool:
        """Check if the URL is a Twitter/X tweet URL."""
        url = data.get("url")
        if not url:
            return False
        return bool(re.match(URL_PATTERN, url))

    def _api_headers(self, guest_token: str | None = None) -> dict:
        """Build API request headers with Bearer auth and optional guest/CSRF tokens."""
        headers = {
            "Authorization": f"Bearer {AUTH_TOKEN}",
            "User-Agent": REQUEST_HEADERS["user-agent"],
            "Accept-Language": "en-US,en;q=0.9",
        }
        if guest_token:
            headers["x-guest-token"] = guest_token
        if self._csrf_token:
            headers["x-csrf-token"] = self._csrf_token
        return headers

    async def _fetch_guest_token(self) -> str:
        """Obtain a guest token from Twitter's activate endpoint.

        Also captures the ct0 cookie as x-csrf-token for subsequent GraphQL requests.
        """
        if not self._session:
            raise Exception("Parser not initialized - session is None")
        async with self._session.post(
            f"{API_BASE}guest/activate.json",
            headers=self._api_headers(),
        ) as resp:
            if resp.status != 200:
                raise Exception(f"Guest token request failed with HTTP {resp.status}")
            data = await resp.json()
            ct0 = resp.cookies.get("ct0")
            if ct0:
                self._csrf_token = ct0.value
        token = data.get("guest_token")
        if not token:
            raise Exception("No guest_token in activate.json response")
        self._guest_token = token
        self.context.logger.debug(f"{DOMAIN}: obtained guest token, csrf_token={'yes' if self._csrf_token else 'no'}")
        return token

    def _graphql_to_tweet_user(self, result: dict) -> tuple[dict, dict]:
        """Extract legacy tweet and user dicts from a GraphQL TweetResultByRestId response."""
        data_layer = result.get("data") or {}
        tweet_result_layer = data_layer.get("tweetResult") or {}
        tweet_result = tweet_result_layer.get("result") or {}
        self.context.logger.debug(
            f"{DOMAIN}: GraphQL response — "
            f"top_keys={list(result.keys())}, "
            f"data_keys={list(data_layer.keys())}, "
            f"tweetResult_keys={list(tweet_result_layer.keys())}, "
            f"result_keys={list(tweet_result.keys())}"
        )
        typename = tweet_result.get("__typename")

        # Deleted tweet — Twitter returns a tombstone with an explanation.
        if "tombstone" in tweet_result:
            cause = (
                tweet_result.get("tombstone", {}).get("text", {}).get("text", "").removesuffix(". Learn more")
            ) or "removed"
            raise Exception(f"Tweet unavailable (tombstone): {cause}")

        # Restricted / protected / NSFW tweet.
        if typename == "TweetUnavailable":
            reason = tweet_result.get("reason") or "unknown"
            raise Exception(f"Tweet unavailable (reason: {reason})")

        # Sensitivity-gated tweet — actual data is one level deeper.
        if typename == "TweetWithVisibilityResults":
            tweet_result = tweet_result.get("tweet") or {}

        tweet = tweet_result.get("legacy", {})
        core = tweet_result.get("core", {})
        user_results = core.get("user_results", {})
        user_result = user_results.get("result", {})
        user = user_result.get("legacy", {})
        # X API moved id_str out of legacy into the parent user_result as rest_id.
        # Backfill it so downstream code can rely on user["id_str"] as before.
        if user and not user.get("id_str"):
            rest_id = user_result.get("rest_id") or user_result.get("id")
            if rest_id:
                user["id_str"] = str(rest_id)
        if not tweet:
            self.context.logger.debug(
                f"{DOMAIN}: unexpected GraphQL response — typename={typename!r}, "
                f"tweetResult keys={list(tweet_result.keys())}"
            )
            raise Exception(f"GraphQL response contains no tweet data (typename={typename!r})")
        self.context.logger.debug(
            f"{DOMAIN}: user extraction — "
            f"core_keys={list(core.keys())}, "
            f"user_results_keys={list(user_results.keys())}, "
            f"user_result_keys={list(user_result.keys())}, "
            f"user_keys={list(user.keys())}"
        )
        if not user:
            self.context.logger.warning(
                f"{DOMAIN}: user data missing from GraphQL response — "
                f"core_keys={list(core.keys())}, "
                f"user_results_keys={list(user_results.keys())}, "
                f"user_result_keys={list(user_result.keys())}"
            )
        return tweet, user

    async def _call_graphql(self, tweet_id: str) -> tuple[dict, dict]:
        """Call the GraphQL TweetResultByRestId endpoint.

        Returns (tweet_legacy_dict, user_legacy_dict).
        Raises aiohttp.ClientResponseError with status 429 on rate-limit.
        """
        if not self._session:
            raise Exception("Parser not initialized - session is None")

        variables = json.dumps(
            {
                "tweetId": tweet_id,
                "withCommunity": False,
                "includePromotedContent": False,
                "withVoice": False,
            },
            separators=(",", ":"),
        )
        features = json.dumps(GRAPHQL_FEATURES, separators=(",", ":"))
        field_toggles = json.dumps({"withArticleRichContentState": False}, separators=(",", ":"))

        url = (
            f"{GRAPHQL_API_BASE}{GRAPHQL_ENDPOINT}"
            f"?{urlencode({'variables': variables, 'features': features, 'fieldToggles': field_toggles})}"
        )

        async with self._session.get(
            url,
            headers=self._api_headers(guest_token=self._guest_token),
            raise_for_status=True,
        ) as resp:
            data = await resp.json(content_type=None)

        errors = data.get("errors") or []
        if errors:
            messages = ", ".join(e.get("message", "") for e in errors)
            raise Exception(f"GraphQL error(s): {messages}")

        return self._graphql_to_tweet_user(data)

    @staticmethod
    def _generate_syndication_token(tweet_id: str) -> str:
        """Generate the token required by the Syndication API.

        Mirrors JS: ((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\\.)/g, '')
        """
        val = (int(tweet_id) / 1e15) * math.pi
        chars = "0123456789abcdefghijklmnopqrstuvwxyz"

        integer_part = int(val)
        fraction_part = val - integer_part

        if integer_part == 0:
            b36 = "0"
        else:
            b36 = ""
            n = integer_part
            while n:
                b36 = chars[n % 36] + b36
                n //= 36

        if fraction_part > 0:
            b36 += "."
            for _ in range(10):
                fraction_part *= 36
                digit = int(fraction_part)
                b36 += chars[digit]
                fraction_part -= digit
                if fraction_part == 0:
                    break

        return b36.replace("0", "").replace(".", "")

    async def _call_syndication(self, tweet_id: str) -> tuple[dict, dict]:
        """Fetch tweet via the Syndication API (rate-limit fallback)."""
        if not self._session:
            raise Exception("Parser not initialized - session is None")

        token = self._generate_syndication_token(tweet_id)
        url = f"{SYNDICATION_API_URL}?{urlencode({'id': tweet_id, 'token': token})}"

        async with self._session.get(
            url,
            headers={"User-Agent": "Googlebot"},
            raise_for_status=True,
        ) as resp:
            data = await resp.json(content_type=None)

        if not data or "id_str" not in data:
            raise Exception(f"Syndication API returned unexpected response for tweet {tweet_id}")

        self.context.logger.debug(
            f"{DOMAIN}: Syndication API response keys={list(data.keys())}, "
            f"has_extended_entities={bool(data.get('extended_entities'))}, "
            f"has_mediaDetails={bool(data.get('mediaDetails'))}"
        )
        user = data.get("user") or {}
        return data, user

    async def _fetch_tweet_data(self, tweet_id: str) -> tuple[dict, dict]:
        """Fetch tweet and user dicts, trying GraphQL first then Syndication as fallback.

        Falls back to Syndication on any GraphQL failure (rate-limit, unexpected
        response structure, HTTP error) so that transient API issues don't block parsing.
        Tombstone / truly-unavailable tweets will also fail on Syndication, but the
        Syndication error will be clearer than a generic "no legacy data" message.
        """
        if not self._guest_token:
            await self._fetch_guest_token()

        try:
            return await self._call_graphql(tweet_id)
        except aiohttp.ClientResponseError as e:
            self.context.logger.warning(
                f"{DOMAIN}: GraphQL API returned HTTP {e.status}, falling back to Syndication API"
            )
        except Exception as e:
            self.context.logger.warning(f"{DOMAIN}: GraphQL API failed ({e}), falling back to Syndication API")

        return await self._call_syndication(tweet_id)

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
        """Parse tweet timestamp to Unix seconds.

        Handles RFC 2822 (GraphQL/Legacy API: 'Thu Apr 06 15:28:43 +0000 2017')
        and ISO 8601 (Syndication API: '2017-04-06T15:28:43.000Z').
        """
        if not created_at:
            return None
        try:
            # RFC 2822 — primary path (GraphQL API)
            dt = parsedate_to_datetime(created_at)
            return int(dt.timestamp())
        except Exception:
            pass
        try:
            # ISO 8601 — Syndication API fallback
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except (ValueError, TypeError):
            return None

    def _select_best_video_variant(self, variants: list[dict]) -> dict | None:
        """Select the highest-bitrate mp4 variant, excluding m3u8/HLS."""
        mp4_variants = [v for v in variants if v.get("content_type") == "video/mp4" and v.get("url")]
        if not mp4_variants:
            return None
        return max(mp4_variants, key=lambda v: v.get("bitrate", 0))

    def _parse_media(self, tweet: dict) -> list[ParserMediaInfo]:
        """Parse media list from tweet entity data.

        Prefers extended_entities.media over entities.media because
        extended_entities includes all images in a multi-photo tweet and
        provides complete video variant data. Falls back to the top-level
        mediaDetails field returned by the Syndication API.
        """
        # Priority: extended_entities.media (GraphQL, most complete)
        #           → mediaDetails (Syndication API, also complete)
        #           → entities.media (simplified thumbnail info, last resort)
        media_items = (
            (tweet.get("extended_entities") or {}).get("media")
            or tweet.get("mediaDetails")
            or (tweet.get("entities") or {}).get("media")
            or []
        )
        self.context.logger.debug(
            f"{DOMAIN}: _parse_media — "
            f"extended_entities={bool(tweet.get('extended_entities'))}, "
            f"entities={bool(tweet.get('entities'))}, "
            f"mediaDetails={bool(tweet.get('mediaDetails'))}, "
            f"media_items_count={len(media_items)}, "
            f"first_item_keys={list(media_items[0].keys()) if media_items else []}"
        )
        result: list[ParserMediaInfo] = []

        for item in media_items:
            media_type = item.get("type")
            if media_type is None:
                # Syndication API mediaDetails items omit the type field;
                # infer it from the presence of video_info.
                media_type = "video" if item.get("video_info") else "photo"
                self.context.logger.debug(
                    f"{DOMAIN}: inferred media type={media_type!r} for item {item.get('id_str')!r}"
                )

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
        if not self._session:
            raise Exception("Parser not initialized - session is None")

        url = data.get("url")
        if not url:
            raise ValueError("No URL provided for parsing")

        try:
            tweet_id = self._extract_tweet_id(url)
            if not tweet_id:
                raise ValueError(f"Cannot extract tweet ID from URL: {url!r}")

            tweet, user = await self._fetch_tweet_data(tweet_id)

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

    async def async_will_remove(self):
        """Clean up resources when removing parser."""
        if hasattr(self, "_session") and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self.context.logger.info(f"{DOMAIN} parser session closed")
