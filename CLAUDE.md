# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

**网页摸鱼保镖 (Web Fish Guardian)** — 一个摸鱼小工具，通过全局快捷键（默认 `Ctrl+``）一键隐藏浏览器窗口，替换为高仿真的工作看板。

## 开发命令

```bash
# 安装依赖
pip install -r requirements.txt

# 运行程序
python main.py
```

项目无构建步骤、无 lint、无测试套件 —— 一个 Python 脚本 + 单个 HTML 文件，由 Python 内置的 `http.server` 提供静态服务。

## 架构

### 两部分结构

| 文件 | 职责 |
|------|------|
| `main.py` | Python 后端 — 快捷键监听、窗口管理、HTTP 服务器、音量控制、系统托盘、待办存储 |
| `work_dashboard.html` | 前端看板 — 单文件 HTML/CSS/JS（约 1400 行），作为静态内容提供服务 |
| `config.json` | 运行时配置（快捷键、角色、端口、过渡动画时长、浏览器列表） |
| `todos.json` | 待办数据持久化存储（自动生成） |

### 后端 (`main.py`) — 核心类

- **`FishGuardian`** — 主控制器，协调所有模块
- **`DashboardServer`** / **`DashboardHandler`** — 嵌入式 HTTP 服务器。路由：`/`（看板页面）、`/exit`（退出信号，仅后端内部调用）、`/exit_status`（前端轮询检查退出状态）、`/config`（配置 JSON）、`/api/todos`（GET 读取 / POST 保存待办）
- **`WindowManager`** — 跨平台窗口管理（Windows 通过 ctypes，macOS 通过 AppleScript，Linux 通过 xdotool）
- **`VolumeController`** — Windows 专用系统音量静音/恢复（通过 pycaw）
- **`TrayIcon`** — 系统托盘（通过 pystray，可选，不可用时降级为控制台模式）

### 待办持久化

- 待办数据从 `localStorage` 迁移到 `todos.json` 文件存储，避免项目重启后丢失
- 后端提供 `GET /api/todos` 读取、`POST /api/todos` 写入两个 RESTful 端点
- 前端所有待办操作（添加、删除、勾选、拖拽）均通过 API 与后端同步
- `load_todos()` / `save_todos()` 函数在 `main.py` 中实现，读写 `todos.json`
- 若文件不存在或解析失败，后端返回空列表，前端使用内置默认待办数据

### 退出机制

- **`/exit`** — 触发退出信号（仅后端内部调用）。内置 `_exit_signaled` 标志，防止重复触发
- **`/exit_status`** — 前端每 500ms 轮询此端点，返回 `{"exit": true/false}`。收到 `true` 后播放退出动画并停止轮询
- 快捷键切换退出时：Python 调用 `GET /exit` → 设置 `_exit_signaled = True` + `threading.Event` → 前端轮询 `/exit_status` 检测到退出 → 播放动画 → Python 等待动画完成 → 关闭浏览器 → 恢复窗口
- 退出状态在服务器启动时自动重置，避免残留

### 前端 (`work_dashboard.html`) — 核心功能

- **4 种职业模式**：程序员（代码 Diff + 终端）、设计师（Figma 风格画板）、产品经理（PRD 文档）、运营（数据看板）
- **角色选择**：首次使用弹出选择框，结果持久化到 `localStorage`，可通过设置齿轮图标切换
- **待办面板**：数据持久化到 `todos.json`，支持添加、删除、拖拽排序
- **嵌入面板（参考文档）**：侧边栏，将外部 URL 嵌入沙盒 iframe 中显示。URL 通过模态框输入，历史记录存储在 localStorage。通过导航栏"书本"图标切换
- **退出检测**：轮询 `/exit_status` 端点；退出时触发模糊动画
- **进入/退出动画**：三段式 Windows 任务视图风格切换动画

### 前后端通信

1. Python 启动 HTTP 服务器 → 以 Chrome/Edge `--app` 模式打开看板
2. 看板页面通过 URL 参数接收 `?role=xxx`
3. 待办操作：前端通过 `GET/POST /api/todos` 与后端同步数据
4. 快捷键切换退出时：Python 调用 `GET /exit` → 设置退出标志 → 前端轮询 `/exit_status` 感知退出 → 播放动画

### 自定义网页 / 嵌入功能

"自定义网页"功能即前端的**嵌入面板（参考文档）**：
- 导航栏书本图标切换侧边栏面板
- URL 输入模态框（`#url-modal`）用于添加/编辑嵌入的网址
- iframe 采用沙盒模式，权限为 `allow-scripts allow-same-origin allow-forms allow-popups`
- 最近使用的 URL 历史存储在 `localStorage`，键名为 `wsp_embed_history`
- 当前 URL 存储在 `localStorage`，键名为 `wsp_embed_url`
- 禁止 iframe 嵌入的网站（X-Frame-Options、CSP 限制）会显示警告提示
- 关键函数：`loadEmbedUrl()`、`saveEmbedUrl()`、`confirmUrl()`、`closeEmbedPanel()`

### 角色 URL 参数

后端通过 URL 传递角色：`http://127.0.0.1:{port}/?role={role}`。前端在 `getRoleFromURL()` 中读取，未设置时回退到 `localStorage`。

### 同源策略

- 后端绑定 `127.0.0.1`，前端所有 API 请求使用 `location.hostname` 动态构建 URL（而非硬编码 `localhost`），避免 CORS 问题
- `getBaseUrl()` 和 `startExitPolling()` 均使用 `location.protocol` + `location.hostname` + `location.port` 构建请求地址

## 注意事项

- 角色、嵌入 URL/历史使用 `localStorage` 存储（键名以 `wsp_` 为前缀）；待办数据使用 `todos.json` 文件存储
- HTML 文件完全自包含 —— 无外部依赖、无构建工具
- Python 导入为可选/优雅降级 —— pynput、pycaw、pystray 各有回退行为
- `_exit_signaled` 是类变量，每次服务器启动时在 `DashboardServer.__init__` 中重置
