"""Mindcraft WebSocket 服务端。

MoFox 作为 WebSocket 服务端，等待 Mindcraft Bridge（客户端）连接。
使用 ``websockets`` 库实现，支持单连接、心跳、自动重连。

参考 SnowLuma adapter 的 server 模式（[`plugins/snowluma_adapter/plugin.py`](plugins/snowluma_adapter/plugin.py:280)），
但 Mindcraft 场景为单 Bridge 连接，实现更简洁。
"""

from __future__ import annotations

from typing import Any, Protocol

import orjson
import websockets
from websockets.asyncio.server import ServerConnection

from src.app.plugin_system.api.log_api import get_logger

logger = get_logger("mindcraft_adapter")


class _AdapterLike(Protocol):
    """适配器回调接口（避免循环导入）。"""

    def _on_bridge_connected(self, agent_name: str) -> None: ...
    def _on_bridge_disconnected(self) -> None: ...
    async def _on_message(self, data: dict[str, Any]) -> None: ...


class MCWebSocketServer:
    """WebSocket 服务端，等待 Mindcraft Bridge 连接。

    Attributes:
        _host: 监听地址
        _port: 监听端口
        _server: websockets 服务端实例
        _conn: 当前连接的客户端
        _adapter: 适配器回调
    """

    def __init__(self, adapter: _AdapterLike) -> None:
        """初始化 WebSocket 服务端。

        Args:
            adapter: 适配器实例，用于消息回调
        """
        self._adapter = adapter
        self._host: str = "127.0.0.1"
        self._port: int = 8081
        self._server: Any = None
        self._conn: ServerConnection | None = None
        self._running = False

    def is_connected(self) -> bool:
        """检查是否有 Bridge 连接。"""
        return self._conn is not None

    async def start(self, host: str, port: int) -> None:
        """启动 WebSocket 服务端。

        Args:
            host: 监听地址
            port: 监听端口
        """
        self._host = host
        self._port = port
        self._running = True

        self._server = await websockets.serve(
            self._handle_connection,
            host,
            port,
            ping_interval=30,
            ping_timeout=60,
            max_size=2**20,
        )
        logger.info(f"Mindcraft WebSocket 服务端已启动: ws://{host}:{port}")

    async def stop(self) -> None:
        """停止 WebSocket 服务端。"""
        self._running = False
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        logger.info("Mindcraft WebSocket 服务端已停止")

    async def send(self, data: dict[str, Any]) -> None:
        """向 Bridge 发送 JSON 消息。

        Args:
            data: 要发送的 JSON 消息字典

        Raises:
            RuntimeError: Bridge 未连接
        """
        if self._conn is None:
            raise RuntimeError("Mindcraft Bridge 未连接")
        await self._conn.send(orjson.dumps(data).decode("utf-8"))

    async def _handle_connection(self, conn: ServerConnection) -> None:
        """处理新的 Bridge 连接。

        每次只允许一个 Bridge 连接，新连接到来时关闭旧连接。

        Args:
            conn: WebSocket 连接对象
        """
        if self._conn is not None:
            logger.warning("已有 Bridge 连接，关闭旧连接")
            try:
                await self._conn.close()
            except Exception:
                pass
            self._adapter._on_bridge_disconnected()

        self._conn = conn
        logger.info("Mindcraft Bridge 已连接")

        try:
            async for raw in conn:
                try:
                    data = orjson.loads(raw)
                    if isinstance(data, dict):
                        await self._adapter._on_message(data)
                except Exception as e:
                    logger.error(f"处理 Bridge 消息失败: {e}")
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Bridge 连接异常: {e}")
        finally:
            if self._conn is conn:
                self._conn = None
                self._adapter._on_bridge_disconnected()
                logger.info("Mindcraft Bridge 已断开")
