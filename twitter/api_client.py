"""Twitter GraphQL API client."""

import json
from collections.abc import Callable
from urllib.parse import urlencode

import aiohttp

from .const import (
    API_BASE,
    AUTH_TOKEN,
    DOMAIN,
    GRAPHQL_API_BASE,
    GRAPHQL_ENDPOINT,
    GRAPHQL_FEATURES,
    GRAPHQL_FIELD_TOGGLES,
    GRAPHQL_VARIABLES_DEFAULTS,
    USER_AGENT,
)


class TwitterAPIError(Exception):
    """Base exception for Twitter API errors."""


class TwitterAuthError(TwitterAPIError):
    """Session uninitialized or guest-token acquisition failed."""


class TwitterUnavailableError(TwitterAPIError):
    """Tweet exists but is inaccessible (deleted, restricted, protected)."""


class TwitterAPIClient:
    """Handles authentication and GraphQL requests against the X/Twitter API."""

    def __init__(
        self,
        logger,
        cookies: dict[str, str] | None = None,
        on_cookies_updated: Callable[[dict[str, str]], None] | None = None,
    ):
        self._logger = logger
        self._cookies: dict[str, str] = dict(cookies or {})
        self._session: aiohttp.ClientSession | None = None
        self._guest_token: str | None = None
        # ct0 from user cookies takes priority over the one from activate.json
        self._csrf_token: str | None = self._cookies.get("ct0") or None
        self._on_cookies_updated = on_cookies_updated

    @property
    def _active_session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise TwitterAuthError("API client not initialized - call async_setup() first")
        return self._session

    async def async_setup(self):
        # max_field_size raised because Twitter's CSP response headers exceed
        # aiohttp's default 8190-byte limit.
        self._session = aiohttp.ClientSession(
            trust_env=True,
            max_field_size=65536,
            cookies=self._cookies if self._cookies else None,
        )
        self._logger.debug(f"{DOMAIN} API client initialized")

    async def async_teardown(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self._logger.info(f"{DOMAIN} API client session closed")

    def _sync_session_cookies(self) -> None:
        """Sync cookies from the session jar into self._cookies; fire callback if changed."""
        if not self._session or self._session.closed:
            return
        session_cookies = {m.key: m.value for m in self._session.cookie_jar if m.value}
        if self._cookies != session_cookies:
            self._cookies = session_cookies
            self._csrf_token = session_cookies.get("ct0") or self._csrf_token
            self._notify_cookies_updated()

    def _notify_cookies_updated(self) -> None:
        if self._on_cookies_updated:
            try:
                self._on_cookies_updated(dict(self._cookies))
            except Exception as e:
                self._logger.warning(f"{DOMAIN}: failed to persist updated cookies: {e}")

    def _api_headers(self, guest_token: str | None = None) -> dict:
        """Build API request headers with Bearer auth and optional guest/CSRF tokens."""
        headers = {
            "Authorization": f"Bearer {AUTH_TOKEN}",
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
        if guest_token:
            headers["x-guest-token"] = guest_token
        if self._csrf_token:
            headers["x-csrf-token"] = self._csrf_token
        return headers

    async def _fetch_guest_token(self) -> str:
        """Obtain a guest token from Twitter's activate endpoint."""
        async with self._active_session.post(
            f"{API_BASE}guest/activate.json",
            headers=self._api_headers(),
        ) as resp:
            if resp.status != 200:
                raise TwitterAuthError(f"Guest token request failed with HTTP {resp.status}")
            data = await resp.json()
            ct0 = resp.cookies.get("ct0")
            if ct0:
                self._csrf_token = ct0.value
        token = data.get("guest_token")
        if not token:
            raise TwitterAuthError("No guest_token in activate.json response")
        self._guest_token = token
        self._logger.debug(f"{DOMAIN}: obtained guest token, csrf_token={'yes' if self._csrf_token else 'no'}")
        self._sync_session_cookies()
        return token

    def _resolve_tweet_result(self, data: dict) -> dict:
        """Navigate GraphQL response to the tweet_result node, raising on unavailable tweets."""
        tweet_result = data.get("data", {}).get("tweetResult", {}).get("result", {})
        typename = tweet_result.get("__typename")

        # Deleted tweet — Twitter returns a tombstone with an explanation.
        if "tombstone" in tweet_result:
            cause = (
                tweet_result.get("tombstone", {}).get("text", {}).get("text", "").removesuffix(". Learn more")
            ) or "removed"
            raise TwitterUnavailableError(f"Tweet unavailable (tombstone): {cause}")

        # Restricted / protected / NSFW tweet.
        if typename == "TweetUnavailable":
            reason = tweet_result.get("reason") or "unknown"
            raise TwitterUnavailableError(f"Tweet unavailable (reason: {reason})")

        # Sensitivity-gated tweet — actual data is one level deeper.
        if typename == "TweetWithVisibilityResults":
            tweet_result = tweet_result.get("tweet") or {}

        return tweet_result

    def _extract_tweet_user(self, tweet_result: dict) -> tuple[dict, dict]:
        """Extract legacy tweet and user dicts from a resolved tweet_result node."""
        tweet = tweet_result.get("legacy", {})
        if not tweet:
            typename = tweet_result.get("__typename")
            self._logger.debug(
                f"{DOMAIN}: unexpected GraphQL response — typename={typename!r}, "
                f"tweet_result keys={list(tweet_result.keys())}"
            )
            raise TwitterAPIError(f"GraphQL response contains no tweet data (typename={typename!r})")

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

        if not user:
            self._logger.warning(
                f"{DOMAIN}: user data missing from GraphQL response — "
                f"core_keys={list(core.keys())}, user_result_keys={list(user_result.keys())}"
            )

        return tweet, user

    def _graphql_to_tweet_user(self, result: dict) -> tuple[dict, dict]:
        """Extract legacy tweet and user dicts from a GraphQL TweetResultByRestId response."""
        tweet_result = self._resolve_tweet_result(result)
        return self._extract_tweet_user(tweet_result)

    async def _call_graphql(self, tweet_id: str) -> tuple[dict, dict]:
        """Call the GraphQL TweetResultByRestId endpoint."""
        variables = json.dumps(
            {"tweetId": tweet_id, **GRAPHQL_VARIABLES_DEFAULTS},
            separators=(",", ":"),
        )
        features = json.dumps(GRAPHQL_FEATURES, separators=(",", ":"))
        field_toggles = json.dumps(GRAPHQL_FIELD_TOGGLES, separators=(",", ":"))

        url = (
            f"{GRAPHQL_API_BASE}{GRAPHQL_ENDPOINT}"
            f"?{urlencode({'variables': variables, 'features': features, 'fieldToggles': field_toggles})}"
        )

        async with self._active_session.get(
            url,
            headers=self._api_headers(guest_token=self._guest_token),
            raise_for_status=True,
        ) as resp:
            data = await resp.json(content_type=None)

        self._sync_session_cookies()

        errors = data.get("errors") or []
        if errors:
            messages = ", ".join(e.get("message", "") for e in errors)
            raise TwitterAPIError(f"GraphQL error(s): {messages}")

        return self._graphql_to_tweet_user(data)

    async def fetch_tweet(self, tweet_id: str) -> tuple[dict, dict]:
        """Fetch tweet and user legacy dicts for the given tweet ID."""
        if not self._guest_token and not self._cookies.get("auth_token"):
            await self._fetch_guest_token()
        return await self._call_graphql(tweet_id)
