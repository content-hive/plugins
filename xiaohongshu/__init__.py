
"""
Xiaohongshu Parser Plugin for ContentHive
Parses Xiaohongshu (Little Red Book) content for ContentHive.
"""

from contenthive.plugins.context import PluginContext

from .const import DOMAIN


async def async_setup(context: PluginContext, config: dict) -> bool:
	"""
	Called when the plugin is first loaded.
    
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
	Called when a configuration entry is added.
	Loads the parser platform.
    
	Args:
		context: PluginContext instance
		entry: PluginEntryData with entry_id, domain, and data
	Returns:
		True if setup successful, False otherwise
	"""
	if context.async_forward_entry_setup:
		await context.async_forward_entry_setup(entry, "parser")
	context.logger.info(f"{DOMAIN} plugin entry setup completed")
	return True


async def async_unload_entry(context: PluginContext, entry):
	"""
	Called when a configuration entry is removed.
	Unloads the parser platform.
    
	Args:
		context: PluginContext instance
		entry: PluginEntryData being unloaded
	Returns:
		True if unload successful, False otherwise
	"""
	if context.async_unload_platforms:
		success = await context.async_unload_platforms(entry, ["parser"])
	else:
		success = True
	if success:
		context.logger.info(f"{DOMAIN} plugin entry unloaded")
	return success
