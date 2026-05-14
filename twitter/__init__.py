"""
Twitter Parser Plugin for ContentHive
Parses X(Twitter) content for ContentHive by scraping tweet pages.
"""

from typing import cast

from contenthive.plugins.context import PluginContext

from .api_client import TwitterAPIClient
from .config import ConfigSchema, CONFIG_SCHEMA
from .const import DOMAIN
from .utils import parse_cookie_string

__all__ = ["ConfigSchema", "CONFIG_SCHEMA"]


async def async_setup(context: PluginContext) -> bool:
    context.logger.info(f"{DOMAIN} plugin setup")
    return True


async def async_setup_entry(context: PluginContext, entry) -> bool:
    config = cast(ConfigSchema, context.get_config(DOMAIN)) if context.get_config else ConfigSchema()
    cookies = parse_cookie_string(config.cookies)
    client = TwitterAPIClient(context.logger, cookies=cookies)
    await client.async_setup()
    context.data[DOMAIN] = {"client": client, "config": config}

    if context.async_forward_entry_setup:
        await context.async_forward_entry_setup(entry, "parser")
    context.logger.info(f"{DOMAIN} plugin entry setup completed")
    return True


async def async_unload_entry(context: PluginContext, entry) -> bool:
    if context.async_unload_platforms:
        success = await context.async_unload_platforms(entry, ["parser"])
    else:
        success = True
    if success:
        entry_data = context.data.pop(DOMAIN, {})
        client: TwitterAPIClient | None = entry_data.get("client")
        if client:
            await client.async_teardown()
        context.logger.info(f"{DOMAIN} plugin entry unloaded")
    return success
