# mindcraft_adapter

Minecraft（Mindcraft）MoFox 适配器插件：将 Minecraft 作为聊天平台接入 MoFox AI 聊天框架。

## 功能

- 通过 WebSocket 与 Mindcraft Bridge（JS 侧）通信
- 游戏内聊天消息收发（chat / whisper）
- 游戏事件上报（死亡 / 低血量 / 生成等）
- MC 动作命令远程执行（`execute_action` → `action_result`，供 `mindcraft_extension` 的 Tool 调用）
- 世界状态快照上报（`getFullState()` → MoFox 缓存，供 GameAgent 查询）
- **固定群聊流**：所有玩家共用同一个恒定 stream_id（`group_id = "minecraft_world"`），
  可在 `prompt_injector` 中以 `"group:minecraft_world"` 排除，处理方式与直播流的
  `"group:live_room"` 一致。

## 依赖

- MoFox 核心 `>= 1.2.0-rc.2`
- `websockets >= 12.0`
- 配套插件：[`mindcraft_extension`](https://github.com/tt-P607/mindcraft_extension)（MC 操作 Tool）
- 配套插件：[`mindcraft_chatter`](https://github.com/tt-P607/mindcraft_chatter)（Actor / GameAgent 会话）
- Mindcraft 本体：[`mindcraft`](https://github.com/tt-P607/mindcraft)（MoFox 定制版 JS Bridge）

## 安装

将本插件目录放入 MoFox 的 `plugins/` 目录，在 `config/plugins/mindcraft_adapter/config.toml`
中配置 WebSocket 服务端口与 Bot 名称，然后在 Mindcraft 侧配置 `mofox` profile 连接本适配器。

## 通信协议

```
MoFox (WebSocket 服务端)  <──>  Mindcraft Bridge (客户端)
```

- `register`：Bridge 注册身份（agent_name）
- `game_event`：游戏事件 → 消息信封 → CoreSink
- `action_result`：动作执行结果 → 匹配 pending Future
- `chat_reply`：MoFox 回复 → 游戏内聊天
- `execute_action`：执行 MC 动作命令

## 组件

| signature | 类型 | 作用 |
|-----------|------|------|
| `mindcraft_adapter:adapter:mindcraft_adapter` | Adapter | Minecraft 平台接入 |

## 配置

见 [`config.py`](config.py:1) 与 MoFox 配置系统，主要包含：

- `[server]`：WebSocket 监听地址 / 端口
- `[bot]`：游戏内 Bot 身份
- `[plugin]`：插件开关

## 验证

```bash
uv run ruff check plugins/mindcraft_adapter
```

启动后：

1. Mindcraft Bridge 连接成功（日志显示 agent_name）。
2. 游戏内任意玩家发消息 → MoFox 收到并回复。
3. 多个玩家进入游戏 → 所有消息进入**同一个固定群聊流**（stream_id 恒定）。

## 开源协议

[MIT](LICENSE)
