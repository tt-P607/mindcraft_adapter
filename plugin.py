"""Mindcraft 适配器插件入口。

核心流程：
1. 启动 WebSocket 服务端，等待 Mindcraft Bridge 连接
2. Bridge 上报游戏事件 → ``_on_message`` → 构造 ``MessageEnvelope`` → CoreSink
3. CoreSink 回复 → ``_send_platform_message`` → WebSocket → Bridge → 游戏内发言
4. Extension Tool 调用 ``send_mc_action`` → 下发 ``execute_action`` → 等待 ``action_result``

参考实现：[`plugins/snowluma_adapter/plugin.py`](plugins/snowluma_adapter/plugin.py:50)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, cast

from mofox_wire import CoreSink, MessageBuilder, MessageEnvelope

from src.app.plugin_system.api.log_api import get_logger
from src.core.components.base import BaseAdapter, BasePlugin
from src.core.components.types import PlatformSendResult
from src.core.components.loader import register_plugin

from .config import MindcraftAdapterConfig
from .protocol import (
    EVENT_WORLD_STATE,
    MSG_ACTION_RESULT,
    MSG_CHAT_REPLY,
    MSG_EXECUTE_ACTION,
    MSG_GAME_EVENT,
    MSG_REGISTER,
)
from .ws_server import MCWebSocketServer

logger = get_logger("mindcraft_adapter")

# 消息段格式（用于 MessageBuilder.format_info）
_ACCEPT_FORMAT = ["text"]

# MC 固定虚拟群聊 ID 与群名：所有玩家共用同一恒定 stream_id
# （prompt_injector 可用 "group:minecraft_world" 排除 MC 流，与直播流的
#  "group:live_room" 处理一致）。
_MC_VIRTUAL_GROUP_ID = "minecraft_world"
_MC_GROUP_NAME = "Minecraft 世界"


class MindcraftAdapter(BaseAdapter):
    """Mindcraft 适配器 — 将 Minecraft 作为聊天平台接入 MoFox。

    通过 WebSocket 与 Mindcraft Bridge 通信，实现：
    - 游戏内聊天消息收发
    - 游戏事件上报（死亡/低血量/生成等）
    - MC 动作命令远程执行（供 Extension Tool 调用）
    """

    name = "mindcraft_adapter"
    description = "将 Minecraft 作为聊天平台接入 MoFox"
    platform = "minecraft"

    def __init__(
        self,
        core_sink: CoreSink,
        plugin: BasePlugin | None = None,
        **kwargs: Any,
    ) -> None:
        """初始化适配器。

        Args:
            core_sink: 核心消息接收器
            plugin: 所属插件实例
            **kwargs: 传递给父类的其他参数
        """
        super().__init__(core_sink, plugin=plugin, **kwargs)

        self.ws_server = MCWebSocketServer(self)
        self._bridge_connected = False
        self._agent_name: str = ""
        self._pending_actions: dict[str, asyncio.Future[str]] = {}
        self._mc_world_state: dict[str, Any] = {}

    # ── 内部辅助 ──────────────────────────────────────────────────

    def _get_config(self) -> MindcraftAdapterConfig | None:
        """从插件实例获取配置对象。"""
        if self.plugin and self.plugin.config:
            return self.plugin.config  # type: ignore[return-value]
        return None

    # ── 生命周期 ──────────────────────────────────────────────────

    async def on_adapter_loaded(self) -> None:
        """适配器加载：启动 WebSocket 服务端。"""
        config = self._get_config()
        if config is None:
            logger.error("无法获取适配器配置，跳过启动")
            return

        host = config.server.host
        port = config.server.port
        await self.ws_server.start(host, port)

    async def on_adapter_unloaded(self) -> None:
        """适配器卸载：停止 WebSocket 服务端并清理资源。"""
        await self.ws_server.stop()

        for future in self._pending_actions.values():
            if not future.done():
                future.cancel("适配器已卸载")
        self._pending_actions.clear()
        self._bridge_connected = False

    async def health_check(self) -> bool:
        """健康检查：Bridge 是否已连接。"""
        return self._bridge_connected

    async def reconnect(self) -> None:
        """重连：server 模式下只需清理状态，等待 Bridge 重新连接。"""
        self._bridge_connected = False
        for future in self._pending_actions.values():
            if not future.done():
                future.cancel("连接重置")
        self._pending_actions.clear()
        logger.info("Mindcraft 适配器重连：已清理状态，等待 Bridge 重新连接")

    # ── Bridge 连接回调 ───────────────────────────────────────────

    def _on_bridge_connected(self, agent_name: str) -> None:
        """Bridge 连接成功回调。"""
        self._bridge_connected = True
        self._agent_name = agent_name
        logger.info(f"Mindcraft Bridge 已连接: agent={agent_name}")

    def _on_bridge_disconnected(self) -> None:
        """Bridge 断开回调。"""
        self._bridge_connected = False
        for future in self._pending_actions.values():
            if not future.done():
                future.cancel("Bridge 断开")
        self._pending_actions.clear()
        logger.info("Mindcraft Bridge 已断开")

    async def _on_message(self, data: dict[str, Any]) -> None:
        """收到 Bridge 消息的回调。

        根据消息 type 分发处理：
        - ``register``: 注册身份
        - ``game_event``: 转换为 MessageEnvelope 推送给 CoreSink
        - ``action_result``: 匹配 pending Future

        Args:
            data: JSON 消息字典
        """
        msg_type = data.get("type")

        if msg_type == MSG_REGISTER:
            agent_name = str(data.get("agent_name", "unknown"))
            self._on_bridge_connected(agent_name)
            return

        if msg_type == MSG_ACTION_RESULT:
            request_id = str(data.get("request_id", ""))
            result = str(data.get("result", ""))
            success = bool(data.get("success", True))

            future = self._pending_actions.pop(request_id, None)
            if future is not None and not future.done():
                if success:
                    future.set_result(result)
                else:
                    future.set_exception(RuntimeError(result or "动作执行失败"))
            return

        if msg_type == MSG_GAME_EVENT:
            # world_state 事件不产生消息信封，只更新环境快照缓存供 GameAgent 查询
            if data.get("event_type") == EVENT_WORLD_STATE:
                self._mc_world_state = dict(data)
                logger.debug("已更新 MC world_state 快照")
                return
            envelope = await self.from_platform_message(data)
            if envelope is not None:
                await self.core_sink.send(envelope)
            return

        logger.warning(f"未知消息类型: {msg_type}")

    # ── BaseAdapter 抽象方法 ─────────────────────────────────────

    async def from_platform_message(self, raw: dict[str, Any]) -> MessageEnvelope | None:
        """将 Mindcraft 游戏事件转换为 MessageEnvelope。

        处理以下事件类型：
        - ``chat``: 公聊消息，构造标准 incoming 消息信封
        - ``whisper``: 私聊消息，构造标准 incoming 消息信封
        - ``self_prompt``: 自主目标推进消息，构造 system 消息信封

        其他事件类型（death/spawn 等）不产生消息信封。

        Args:
            raw: Bridge 上报的 JSON 消息

        Returns:
            MessageEnvelope 或 None（非聊天事件返回 None）
        """
        event_type = raw.get("event_type", "")
        agent_name = str(raw.get("agent_name", ""))
        username = str(raw.get("username", ""))
        message = str(raw.get("message", ""))

        if event_type not in ("chat", "whisper", "self_prompt"):
            logger.debug(f"非聊天事件，跳过消息信封构造: {event_type}")
            return None

        if not message:
            logger.warning(f"事件缺少 message: {raw}")
            return None

        # self_prompt 事件使用 system 作为 username
        if event_type == "self_prompt":
            username = username or "system"

        message_id = f"mc_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        builder = MessageBuilder()
        (
            builder.direction("incoming")
            .message_id(message_id)
            .timestamp_ms(int(time.time() * 1000))
            .from_user(
                user_id=username,
                platform="minecraft",
                nickname=username,
            )
            # 所有玩家共用一个固定群聊流（恒定 stream_id），使 prompt_injector
            # 能以 "group:minecraft_world" 排除 MC 流，与直播流 "group:live_room"
            # 的处理方式一致（见 bilibili_live_adapter / douyin_live_adapter）。
            .from_group(
                group_id=_MC_VIRTUAL_GROUP_ID,
                platform="minecraft",
                name=_MC_GROUP_NAME,
            )
        )

        builder.format_info(
            content_format=["text"],
            accept_format=_ACCEPT_FORMAT,
        )

        builder.seg_list([{"type": "text", "data": message}])

        # 所有 MC 事件都汇入同一个固定群聊流（chat_type 由 group_info 决定），
        # 不再写 per-事件 的 chat_type 标记，避免与私有标记冲突。
        metadata: dict[str, Any] = {
            "event_type": event_type,
            "agent_name": agent_name,
        }
        if event_type == "self_prompt":
            metadata["self_prompt"] = str(raw.get("prompt", ""))
        builder.metadata(metadata)

        return builder.build()

    async def _send_platform_message(self, envelope: MessageEnvelope) -> PlatformSendResult:
        """将 MoFox 回复发送到 Mindcraft（游戏内聊天）。

        从 envelope 的消息段中提取纯文本，发送 ``chat_reply`` 给 Bridge。

        Args:
            envelope: 要发送的消息信封

        Returns:
            PlatformSendResult: 发送结果
        """
        raw_segs = envelope.get("message_segment", []) or []
        text_parts: list[str] = []
        for seg in raw_segs:
            if not isinstance(seg, dict):
                continue
            seg_type = str(seg.get("type", ""))
            seg_data = seg.get("data", "")
            if seg_type == "text" and seg_data:
                text_parts.append(str(seg_data))

        text = "\n".join(text_parts).strip()
        if not text:
            return PlatformSendResult(success=True, message_id=None)

        try:
            await self.ws_server.send({"type": MSG_CHAT_REPLY, "message": text})
            return PlatformSendResult(success=True, message_id=None)
        except Exception as e:
            logger.error(f"发送 Mindcraft 消息失败: {e}")
            return PlatformSendResult(success=False, error=str(e))

    def get_world_state(self) -> dict[str, Any]:
        """获取最新的 MC 世界状态快照（Bot 全局）。

        由 Mindcraft JS 侧 ``update()`` 循环按 ``world_state_interval`` 周期上报
        ``getFullState()`` 结果。GameAgent 据此感知位置、血量、背包、周围实体等。

        Returns:
            最新 world_state 快照字典；尚未收到任何快照时返回空字典。
        """
        return dict(self._mc_world_state)

    async def get_bot_info(self) -> dict[str, Any]:
        """获取 Bot 信息。

        Returns:
            包含 bot_id、bot_name、platform 的字典
        """
        config = self._get_config()
        bot_name = config.bot.bot_name if config else "MoFox"
        return {
            "bot_id": "mindcraft_bot",
            "bot_name": bot_name,
            "platform": "minecraft",
        }

    # ── MC 动作执行（供 Extension Tool 调用） ────────────────────

    async def send_mc_action(self, command: str, args: list[Any], timeout: float = 120.0) -> str:
        """发送 MC 动作命令并等待结果。

        供 ``mindcraft_extension`` 插件的 Tool 组件调用。
        通过 WebSocket 下发 ``execute_action``，等待 Bridge 返回 ``action_result``。

        Args:
            command: Mindcraft 命令字符串，如 ``!goToPlayer``
            args: 命令参数列表
            timeout: 超时时间（秒），默认 120 秒

        Returns:
            动作执行结果文本

        Raises:
            RuntimeError: Bridge 未连接
            TimeoutError: 动作执行超时
        """
        if not self._bridge_connected:
            raise RuntimeError("Mindcraft Bridge 未连接")

        request_id = str(uuid.uuid4())
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._pending_actions[request_id] = future

        await self.ws_server.send({
            "type": MSG_EXECUTE_ACTION,
            "request_id": request_id,
            "command": command,
            "args": args,
        })

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except TimeoutError:
            self._pending_actions.pop(request_id, None)
            raise TimeoutError(f"MC 动作超时: {command}")
        except asyncio.CancelledError:
            self._pending_actions.pop(request_id, None)
            raise


@register_plugin
class MindcraftAdapterPlugin(BasePlugin):
    """Mindcraft 适配器插件。"""

    plugin_name = "mindcraft_adapter"
    configs: list[type] = [MindcraftAdapterConfig]

    def get_components(self) -> list[type]:
        """返回插件包含的组件类列表。"""
        if self.config is not None:
            cfg = cast(MindcraftAdapterConfig, self.config)
            if hasattr(cfg, "plugin") and not cfg.plugin.enabled:
                return []

        return [MindcraftAdapter]