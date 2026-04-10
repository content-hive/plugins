
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import aiofiles
import aiohttp

from contenthive.plugins.context import PluginContext

from .api_client import DouyinAPIClient
from .const import DOMAIN, BASE_URL, USER_AGENT
from .utils import parse_cookie_string

async def async_setup_entry(context: PluginContext, entry, async_add_entities):
    """Set up downloader entities from a config entry."""
    downloader = Downloader(context, entry)
    await downloader.async_setup()
    await async_add_entities([downloader])

    if context.register_service:
        context.register_service(DOMAIN, "download", downloader.download)

    context.logger.info(f"{DOMAIN} downloader platform setup completed")


class Downloader:
    """Douyin content downloader."""

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
        self.context.logger.debug(f"{DOMAIN} downloader initialized")

    async def download(self, data: dict[str, Any]) -> dict[str, Any]:
        """Download content from a Douyin URL."""
        media_url = data.get("media_url")
        if not media_url:
            raise ValueError("Missing 'media_url' in download data")
        cover_url: Optional[str] = data.get("media_cover")

        self.context.logger.debug(f"Starting download for media_url={media_url}, cover_url={cover_url}")
        
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": f"{BASE_URL}/",
            "Origin": BASE_URL,
            "Accept": "*/*",
        }
        media_path = await self._download_file(media_url, headers=headers)
        cover_path = await self._download_file(cover_url, headers=headers) if cover_url else None

        return {
            "media_path": str(media_path) if media_path else None,
            "cover_path": str(cover_path) if cover_path else None,
        }

    async def _download_file(self, url: str, headers: dict[str, str] | None = None) -> Optional[Path]:
        """Download a single file to the system temp directory and return its path."""
        if not self._client:
            raise RuntimeError("Downloader not initialized")

        session = await self._client.ensure_session()

        tmp_fd, tmp_path_str = tempfile.mkstemp()
        tmp_path = Path(tmp_path_str)
        os.close(tmp_fd)
        write_path = tmp_path.with_suffix(".tmp")

        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as response:
                if response.status != 200:
                    self.context.logger.debug(
                        f"Download failed for {url}, status={response.status}"
                    )
                    tmp_path.unlink(missing_ok=True)
                    return None

                expected_size = response.content_length
                written = 0
                async with aiofiles.open(write_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
                        written += len(chunk)

                if expected_size is not None and written != expected_size:
                    self.context.logger.warning(
                        f"Size mismatch for {url}: expected {expected_size}, got {written}"
                    )
                    write_path.unlink(missing_ok=True)
                    tmp_path.unlink(missing_ok=True)
                    return None

                os.replace(str(write_path), str(tmp_path))
                self.context.logger.debug(f"Downloaded file from {url} -> {tmp_path}")
                return tmp_path

        except Exception as e:
            self.context.logger.debug(f"Download error for {url}: {e}")
            write_path.unlink(missing_ok=True)
            tmp_path.unlink(missing_ok=True)
            return None

    async def async_will_remove(self):
        """Clean up resources."""
        if self._client:
            await self._client.close()
            self._client = None
            self.context.logger.info(f"{DOMAIN} downloader client closed")
