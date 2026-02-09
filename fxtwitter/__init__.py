"""
FXTwitter Parser Plugin for ContentHive
Parses Twitter/X.com URLs using the fxtwitter API.
"""

from contenthive.plugins.context import PluginContext

from .const import DOMAIN


async def async_setup(context: PluginContext, config: dict) -> bool:
    """
    Set up the FXTwitter plugin.
    
    This is called when the plugin is first loaded.
    
    Args:
        context: PluginContext instance
        config: Plugin configuration dictionary
        
    Returns:
        True if setup successful, False otherwise
    """
    context.logger.info(f"{DOMAIN} plugin setup")
    return True


async def async_setup_entry(context: PluginContext, entry):
    """
    Set up from a config entry.
    
    This is called when a configuration entry is added.
    Loads the parser platform.
    
    Args:
        context: PluginContext instance
        entry: PluginEntryData with entry_id, domain, and data
        
    Returns:
        True if setup successful, False otherwise
    """
    # Load parser platform using HA-style forward setup
    await context.async_forward_entry_setup(entry, "parser")
    
    context.logger.info(f"{DOMAIN} plugin entry setup completed")
    return True


async def async_unload_entry(context: PluginContext, entry):
    """
    Unload a config entry.
    
    This is called when a configuration entry is removed.
    Unloads the parser platform.
    
    Args:
        context: PluginContext instance
        entry: PluginEntryData being unloaded
        
    Returns:
        True if unload successful, False otherwise
    """
    # Unload parser platform using HA-style unload
    success = await context.async_unload_platforms(entry, ["parser"])
    
    if success:
        context.logger.info(f"{DOMAIN} plugin entry unloaded")
    
    return success