from fastapi import APIRouter
from contenthive.models.content import URLParserResult
from contenthive.plugins.base import ContentParserPlugin


class Plugin(ContentParserPlugin):
    def on_load(self, context):
        self.context = context
        self.context.logger.info("Example Plugin loaded.")
        
    def on_enable(self):
        self.context.logger.info("Example Plugin enabled.")

    def on_disable(self):
        self.context.logger.info("Example Plugin disabled.")

    def on_unload(self):
        self.context.logger.info("Example Plugin unloaded.")
    
    def can_parse(self, url: str) -> bool:
        """
        Check if this plugin can parse the URL.
        Example: only handles example.com URLs
        """
        return True
    
    def parse(self, url: str) -> URLParserResult:
        """
        Parse content from the URL.
        """
        self.context.logger.info(f"Parsing URL: {url}")
        
        # Simple data extraction example
        
        parsed_data = {
  "id": "2018945688248127679",
  "url": "https://x.com/earthcurated/status/2018945688248127679?s=46",
  "images": [
    {
      "url": "https://pbs.twimg.com/media/HAS8ZOyW8AELbO6.jpg:orig"
    },
    {
      "url": "https://pbs.twimg.com/media/HAS8ZO5WwAAxGAj.jpg:orig"
    },
    {
      "url": "https://pbs.twimg.com/media/HAS8ZOHWkAAaG4w.jpg:orig"
    },
    {
      "url": "https://pbs.twimg.com/media/HAS8ZOrWEAAvTRh.jpg:orig"
    }
  ],
  "videos": [],
  "content": "— nature’s masterpiece https://t.co/Ddsb4mN4Fb",
  "author": {
    "uid": "1038150281794646017",
    "name": "Earth",
    "userName": "earthcurated",
    "avatar": "https://pbs.twimg.com/profile_images/1590966054800564225/3hZ1EhAD_normal.jpg",
    "url": "https://x.com/earthcurated"
  },
  "createdTime": 1770189136000,
  "parser": "x_0",
  "state": "success",
  "platform": {
    "name": "X",
    "code": "x",
    "url": "https://x.com/",
    "iconUrl": "https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/d8/88/a7/d888a76a-2b0c-d68a-ab65-83eb09740f43/ProductionAppIcon-0-0-1x_U007emarketing-0-7-0-0-0-85-220.png/512x512bb.jpg"
  }
}

        return URLParserResult(**parsed_data)