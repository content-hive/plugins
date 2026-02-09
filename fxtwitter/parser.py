"""Parser platform for FXTwitter plugin."""

import re
from typing import Any, Dict, Optional
from pydantic import HttpUrl
import aiohttp

from contenthive.models.parser import (
    ParserResult,
    ParserMediaInfo,
    ParserAuthorInfo,
    ParserPlatformInfo
)
from contenthive.plugins.context import PluginContext

from .const import (
    DOMAIN,
    API_BASE_URL,
    URL_PATTERN,
    PLATFORM_CODE,
    PLATFORM_NAME,
    PLATFORM_URL,
    PLATFORM_ICON
)

async def async_setup_entry(context: PluginContext, entry, async_add_entities):
    """Set up parser entities from a config entry."""
    parser = FXTwitterParser(context, entry)
    await parser.async_setup()
    await async_add_entities([parser])

    if context.register_service:
        context.register_service(DOMAIN, "can_parse", parser.can_parse)
        context.register_service(DOMAIN, "parse", parser.parse)

    context.logger.info(f"{DOMAIN} parser platform setup completed")

class FXTwitterParser:
    """Twitter/X.com content parser using fxtwitter API."""
    
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
    
    def can_parse(self, data: Dict[str, Any]) -> bool:
        """Check if URL can be parsed by this parser."""
        url = data.get("url")
        if not url:
            return False
        return bool(re.match(URL_PATTERN, url))
    
    async def parse(self, data: Dict[str, Any]) -> ParserResult:
        """Parse Twitter content using fxtwitter API."""
        if not self._session:
            raise Exception("Parser not initialized - session is None")
        
        url = data.get("url")
        if not url:
            raise ValueError("No URL provided for parsing")
        
        try:
            api_url = self._convert_to_api_url(url)
            self.context.logger.info(f"Fetching content from: {api_url}")
            
            data = await self._fetch_api_data(api_url)
            tweet = self._validate_response(data)
            
            return self._build_result(tweet)
            
        except Exception as e:
            self.context.logger.error(f"Failed to parse {url}: {e}")
            raise Exception(f"Failed to parse Twitter URL: {e}")
    
    def _convert_to_api_url(self, url: str) -> str:
        """Convert twitter.com/x.com URL to fxtwitter API URL."""
        return (url.replace('twitter.com', API_BASE_URL)
                   .replace('x.com', API_BASE_URL))
    
    async def _fetch_api_data(self, api_url: str) -> dict:
        """Fetch data from fxtwitter API."""
        if not self._session:
            raise Exception("HTTP session not initialized")
        
        try:
            async with self._session.get(api_url) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"API request failed with status {response.status}: {text}")
                return await response.json()
        except aiohttp.ClientError as e:
            raise Exception(f"HTTP request failed: {e}")
    
    def _validate_response(self, data: dict) -> dict:
        """Validate API response and extract tweet data."""
        if data.get('code') != 200:
            error_msg = data.get('message', 'Unknown error')
            raise Exception(f"API returned error: {error_msg}")
        
        return data['tweet']
    
    def _build_result(self, tweet: dict) -> ParserResult:
        """Build ParserResult from tweet data."""
        return ParserResult(
            pid=tweet['id'],
            url=HttpUrl(tweet['url']),
            content=tweet['text'],
            media=self._parse_media(tweet),
            author=self._parse_author(tweet),
            platform=self._get_platform_info(),
            created_time=tweet['created_timestamp'] * 1000,
            parser='fxtwitter',
            state='success'
        )
    
    def _parse_media(self, tweet: dict) -> list[ParserMediaInfo]:
        """Parse media from tweet data."""
        media_list = []
        
        if 'media' not in tweet:
            return media_list
        
        media = tweet['media']
        
        # Parse photos
        if 'photos' in media:
            for photo in media['photos']:
                media_list.append(ParserMediaInfo(
                    url=HttpUrl(photo['url']),
                    type='image',
                    title=None,
                    cover=None
                ))
        
        # Parse videos
        if 'videos' in media:
            for video in media['videos']:
                media_info = ParserMediaInfo(
                    url=HttpUrl(video['url']),
                    type='video',
                    title=None,
                    cover=HttpUrl(video['thumbnail_url']) if 'thumbnail_url' in video else None
                )
                media_list.append(media_info)
        
        return media_list
    
    def _parse_author(self, tweet: dict) -> ParserAuthorInfo:
        """Parse author information from tweet data."""
        author_data = tweet['author']
        
        return ParserAuthorInfo(
            uid=author_data['id'],
            name=author_data['name'],
            username=author_data['screen_name'],
            avatar=HttpUrl(author_data['avatar_url']),
            url=HttpUrl(author_data['url'])
        )
    
    def _get_platform_info(self) -> ParserPlatformInfo:
        """Get platform information."""
        return ParserPlatformInfo(
            code=PLATFORM_CODE,
            name=PLATFORM_NAME,
            url=HttpUrl(PLATFORM_URL),
            icon_url=HttpUrl(PLATFORM_ICON)
        )
    
    async def async_will_remove(self):
        """Clean up when removing."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self.context.logger.info(f"{DOMAIN} parser session closed")
