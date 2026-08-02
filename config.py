"""Mindcraft 适配器配置定义。

参考 [`plugins/snowluma_adapter/config.py`](plugins/snowluma_adapter/config.py:9) 的配置模式，
使用 ``@config_section`` + ``SectionBase`` + ``Field`` 定义 TOML 配置节。
"""

from __future__ import annotations

from typing import ClassVar

from src.core.components.base.config import BaseConfig, Field, SectionBase, config_section


class MindcraftAdapterConfig(BaseConfig):
    """Mindcraft 适配器配置。

    配置文件路径：``config/plugins/mindcraft_adapter/config.toml``
    """

    name: ClassVar[str] = "config"
    description: ClassVar[str] = "Mindcraft 适配器配置"

    @config_section("server", title="WebSocket 服务器", tag="network")
    class ServerSection(SectionBase):
        """WebSocket 服务端监听配置。

        MoFox 作为 WebSocket 服务端，等待 Mindcraft Bridge 连接。
        """

        host: str = Field(
            default="127.0.0.1",
            description="WebSocket 监听地址",
            label="监听地址",
            placeholder="127.0.0.1",
            tag="network",
        )
        port: int = Field(
            default=8081,
            description="WebSocket 监听端口",
            label="监听端口",
            ge=1,
            le=65535,
            step=1,
            tag="network",
        )

    @config_section("bot", title="Bot 配置", tag="user")
    class BotSection(SectionBase):
        """Bot 游戏内身份配置。"""

        bot_name: str = Field(
            default="MoFox",
            description="Bot 在 Minecraft 游戏内的名称",
            label="Bot 名称",
            placeholder="MoFox",
            tag="user",
        )

    @config_section("plugin", title="插件设置", tag="plugin")
    class PluginSection(SectionBase):
        """插件基本配置。"""

        enabled: bool = Field(
            default=True,
            description="是否启用 Mindcraft 适配器",
            label="启用",
            tag="plugin",
        )
        config_version: str = Field(
            default="0.1.0",
            description="配置版本号",
            label="配置版本",
            tag="plugin",
        )

    # 实例字段声明：让 Pydantic 能正确实例化各配置节
    server: ServerSection = Field(default_factory=ServerSection)
    bot: BotSection = Field(default_factory=BotSection)
    plugin: PluginSection = Field(default_factory=PluginSection)
