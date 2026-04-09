"""Douyin content parser plugin."""

import re
from typing import Any, Optional

from contenthive.models.parser import ParserResult
from contenthive.plugins.context import PluginContext

from .api_client import DouyinAPIClient
from .builder import build_result
from .const import DOMAIN, URL_PATTERN
from .utils import parse_cookie_string

_AWEME_ID_RE = re.compile(r"/(?:video|note|gallery|slides)/(\d+)")


async def async_setup_entry(context: PluginContext, entry, async_add_entities):
    """Set up parser entities from a config entry."""
    parser = DouyinParser(context, entry)
    await parser.async_setup()
    await async_add_entities([parser])

    if context.register_service:
        context.register_service(DOMAIN, "can_parse", parser.can_parse)
        context.register_service(DOMAIN, "parse", parser.parse)

    context.logger.info(f"{DOMAIN} parser platform setup completed")


class DouyinParser:
    """Douyin content parser."""

    def __init__(self, context: PluginContext, entry):
        self.context = context
        self.entry = entry
        self.domain = DOMAIN
        self._client: Optional[DouyinAPIClient] = None

    async def async_setup(self):
        """Initialize the API client with cookies from the entry config."""
        raw_cookies = (self.entry.data or {}).get("cookies", "")
        cookies = parse_cookie_string(raw_cookies)
        self._client = DouyinAPIClient(cookies=cookies, logger=self.context.logger)
        await self._client._ensure_session()
        self.context.logger.debug(f"{DOMAIN} parser initialized")

    def can_parse(self, data: dict[str, Any]) -> bool:
        """Return True if the URL matches a supported Douyin pattern."""
        url = data.get("url")
        if not url:
            return False
        return bool(re.match(URL_PATTERN, url))

    async def parse(self, data: dict[str, Any]) -> ParserResult:
        """Parse a Douyin URL and return a ParserResult."""
        if not self._client:
            raise RuntimeError("Parser not initialized")

        url = data.get("url")
        if not url:
            raise ValueError("No URL provided for parsing")

        try:
            # Resolve short links (v.douyin.com/…) to canonical douyin.com URLs
            canonical = await self._client.resolve_short_url(url)

            aweme_id = _extract_aweme_id(canonical)
            if not aweme_id:
                raise ValueError(f"Cannot extract aweme_id from URL: {canonical}")

            aweme = await self._client.get_aweme_detail(aweme_id)
            if not aweme:
                raise Exception(f"Failed to fetch aweme detail for {aweme_id}")

            return build_result(url, aweme)

        except Exception:
            self.context.logger.exception(f"Failed to parse {url}")
            raise

    async def async_will_remove(self):
        """Clean up resources."""
        if self._client:
            await self._client.close()
            self._client = None
            self.context.logger.info(f"{DOMAIN} parser client closed")


def _extract_aweme_id(url: str) -> Optional[str]:
    match = _AWEME_ID_RE.search(url)
    return match.group(1) if match else None
