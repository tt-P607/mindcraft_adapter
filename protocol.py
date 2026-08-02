"""Mindcraft 适配器通信协议常量。

定义 MoFox ↔ Mindcraft 之间 WebSocket JSON 消息的 ``type`` 字段值。
所有消息均为 JSON 文本帧，顶层必须包含 ``type`` 字段。

上行（Mindcraft → MoFox）：
    - ``register``: Bot 注册身份
    - ``game_event``: 游戏事件上报
    - ``action_result``: 动作执行结果返回

下行（MoFox → Mindcraft）：
    - ``chat_reply``: 在游戏内发送聊天
    - ``execute_action``: 执行 MC 命令
    - ``send_message``: 模拟收到消息
"""

from __future__ import annotations

# ── 上行消息类型（Mindcraft → MoFox） ──────────────────────────────

MSG_REGISTER = "register"
"""Bot 注册身份。字段：``agent_name: str``。"""

MSG_GAME_EVENT = "game_event"
"""游戏事件上报。字段：``event_type: str``, ``agent_name: str``,
``username?: str``, ``message?: str``, ``data?: dict``。"""

MSG_ACTION_RESULT = "action_result"
"""动作执行结果返回。字段：``request_id: str``, ``result: str``,
``success: bool``。"""

# ── 下行消息类型（MoFox → Mindcraft） ──────────────────────────────

MSG_CHAT_REPLY = "chat_reply"
"""在游戏内发送聊天。字段：``message: str``。"""

MSG_EXECUTE_ACTION = "execute_action"
"""执行 MC 命令。字段：``request_id: str``, ``command: str``,
``args: list``。command 格式为 ``!commandName`` 或
``!commandName("arg1", 1.2, true)``。"""

MSG_SEND_MESSAGE = "send_message"
"""模拟收到消息。字段：``from: str``, ``message: str``。"""

# ── game_event 的 event_type 取值 ──────────────────────────────────

EVENT_CHAT = "chat"
"""公聊消息。data 含 ``username``, ``message``。"""

EVENT_WHISPER = "whisper"
"""私聊消息。data 含 ``username``, ``message``。"""

EVENT_DEATH = "death"
"""Bot 死亡。data 可含 ``message``。"""

EVENT_LOW_HEALTH = "low_health"
"""低血量警告。data 可含 ``health``。"""

EVENT_SPAWN = "spawn"
"""Bot 生成/重生。"""

EVENT_SYSTEM = "system"
"""系统消息。data 含 ``message``。"""

EVENT_IDLE = "idle"
"""Bot 空闲。"""

EVENT_SELF_PROMPT = "self_prompt"
"""自主目标推进。data 含 ``username``, ``message``, ``prompt``。"""

EVENT_WORLD_STATE = "world_state"
"""完整世界状态快照。data 为 ``getFullState()`` 的 JSON，供 GameAgent 感知环境。"""

# ── 所有上行消息类型集合 ───────────────────────────────────────────

UPLINK_TYPES: frozenset[str] = frozenset({
    MSG_REGISTER,
    MSG_GAME_EVENT,
    MSG_ACTION_RESULT,
})

# ── 所有下行消息类型集合 ───────────────────────────────────────────

DOWNLINK_TYPES: frozenset[str] = frozenset({
    MSG_CHAT_REPLY,
    MSG_EXECUTE_ACTION,
    MSG_SEND_MESSAGE,
})

# ── 所有 game_event 类型集合 ───────────────────────────────────────

GAME_EVENT_TYPES: frozenset[str] = frozenset({
    EVENT_CHAT,
    EVENT_WHISPER,
    EVENT_DEATH,
    EVENT_LOW_HEALTH,
    EVENT_SPAWN,
    EVENT_SYSTEM,
    EVENT_IDLE,
    EVENT_SELF_PROMPT,
    EVENT_WORLD_STATE,
})
