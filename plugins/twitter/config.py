"""Twitter plugin configuration schema."""

from pydantic import Field
from contenthive.plugins.contracts import PluginConfigSchema


class ConfigSchema(PluginConfigSchema):
    cookies: str = Field(
        default="",
        title="Cookie",
        description="Optional. X(Twitter) account cookie string. When provided, enables access to restricted content.",
        json_schema_extra={"secret": True},
    )


CONFIG_SCHEMA = ConfigSchema
