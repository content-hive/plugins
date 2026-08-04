"""
Jike Parser Plugin for ContentHive
Parses Jike (即刻) content for ContentHive.
"""

from contenthive.plugins.context import PluginContext

from .const import DOMAIN


async def async_setup(context: PluginContext) -> bool:
    context.logger.info(f"{DOMAIN} plugin setup")
    return True


async def async_setup_entry(context: PluginContext, entry):
    if context.async_forward_entry_setup:
        await context.async_forward_entry_setup(entry, "parser")
    context.logger.info(f"{DOMAIN} plugin entry setup completed")
    return True


async def async_unload_entry(context: PluginContext, entry):
    if context.async_unload_platforms:
        success = await context.async_unload_platforms(entry, ["parser"])
    else:
        success = True
    if success:
        context.logger.info(f"{DOMAIN} plugin entry unloaded")
    return success
