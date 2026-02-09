import re

from pydantic import HttpUrl
import aiohttp
from contenthive.models.parser import (
    ParserResult, 
    ParserMediaInfo, 
    ParserAuthorInfo, 
    ParserPlatformInfo
)
from contenthive.plugins.context import PluginContext
from contenthive.plugins.manager import ContentParserPlugin

class Plugin(ContentParserPlugin):
    """
    A plugin for parsing Twitter(X) content from fxtwitter.com.
    """
    def on_load(self, context: PluginContext):
        self.context = context
        self.context.logger.info("FXTwitter Parser Plugin loaded.")
    
    def on_enable(self):
        self.context.logger.info("FXTwitter Parser Plugin enabled.")
    
    def on_disable(self):
        self.context.logger.info("FXTwitter Parser Plugin disabled.")
    
    def on_unload(self):
        self.context.logger.info("FXTwitter Parser Plugin unloaded.")
    
    def can_parse(self, url: str) -> bool:
        return bool(re.match(r'https?://(www\.)?(twitter\.com|x\.com)/.+/status/\d+', url))
    
    def platform_info_x(self) -> ParserPlatformInfo:
        return ParserPlatformInfo(
            code='x',
            name='X',
            url=HttpUrl('https://x.com'),
            icon_url=HttpUrl('https://raw.githubusercontent.com/content-hive/assets/main/IconSet/X.png')
        )
    
    async def parse(self, url: str) -> ParserResult:
        """
        Parse Twitter content using fxtwitter API.
        
        Args:
            url: Twitter/X.com URL to parse
            
        Returns:
            ParserResult with parsed content
        """
        try:
            # Convert twitter.com/x.com to fxtwitter.com API URL
            api_url = url.replace('twitter.com', 'api.fxtwitter.com').replace('x.com', 'api.fxtwitter.com')
            self.context.logger.info(f"Fetching Twitter content from API URL: {api_url}")

            # Make API request
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        raise Exception(f"API request failed with status {response.status}")
                    
                    data = await response.json()
            
            # Check if response is successful
            if data.get('code') != 200:
                raise Exception(f"API returned error: {data.get('message', 'Unknown error')}")
            
            tweet = data['tweet']
            
            # Parse media
            media_list = []
            if 'media' in tweet:
                # Parse photos
                if 'photos' in tweet['media']:
                    for photo in tweet['media']['photos']:
                        media_list.append(ParserMediaInfo(
                            url=HttpUrl(photo['url']),
                            type='image',
                            title=None,
                            cover=None
                        ))
                
                # Parse videos
                if 'videos' in tweet['media']:
                    for video in tweet['media']['videos']:
                        media_info = ParserMediaInfo(
                            url=HttpUrl(video['url']),
                            type='video',
                            title=None,
                            cover=None
                        )
                        # Add thumbnail if available
                        if 'thumbnail_url' in video:
                            media_info.cover = HttpUrl(video['thumbnail_url'])
                        media_list.append(media_info)
            
            # Parse author info
            author = ParserAuthorInfo(
                uid=tweet['author']['id'],
                name=tweet['author']['name'],
                username=tweet['author']['screen_name'],
                avatar=HttpUrl(tweet['author']['avatar_url']),
                url=HttpUrl(tweet['author']['url'])
            )
            
            # Convert timestamp from seconds to milliseconds
            created_time = tweet['created_timestamp'] * 1000
            
            # Create and return ParserResult
            return ParserResult(
                pid=tweet['id'],
                url=HttpUrl(tweet['url']),
                content=tweet['text'],
                media=media_list,
                author=author,
                platform=self.platform_info_x(),
                created_time=created_time,
                parser='fxtwitter',
                state='success'
            )
            
        except Exception as e:
            self.context.logger.error(f"Failed to parse Twitter URL {url}: {str(e)}")
            # Return error result
            raise Exception(f"Failed to parse Twitter URL {url}: {str(e)}")