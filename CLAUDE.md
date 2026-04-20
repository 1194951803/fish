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
| `main.py` | Python 后端 — 快捷键监听、窗口管理、HTTP 服务器、音量控制、系统托盘、待办存储、反向代理、阅读模式 |
| `work_dashboard.html` | 前端看板 — 单文件 HTML/CSS/JS，作为静态内容提供服务 |
| `config.json` | 运行时配置（快捷键、角色、端口、过渡动画时长、浏览器列表） |
| `todos.json` | 待办数据持久化存储（自动生成） |

### 后端 (`main.py`) — 核心类

- **`FishGuardian`** — 主控制器，协调所有模块
- **`DashboardServer`** / **`DashboardHandler`** — 嵌入式 HTTP 服务器。路由见下方
- **`WindowManager`** — 跨平台窗口管理（Windows 通过 ctypes，macOS 通过 AppleScript，Linux 通过 xdotool）
- **`VolumeController`** — Windows 专用系统音量静音/恢复（通过 pycaw）
- **`TrayIcon`** — 系统托盘（通过 pystray，可选，不可用时降级为控制台模式）
- **`HTMLReadabilityParser`** — 基于 `HTMLParser` 的正文提取器，不依赖第三方库

### HTTP 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 返回 `work_dashboard.html` |
| `/exit` | GET | 触发看板退出（仅后端内部调用，一次性） |
| `/exit_status` | GET | 前端轮询检查退出状态，返回 `{"exit": true/false}` |
| `/config` | GET | 返回当前配置 JSON |
| `/api/todos` | GET | 返回待办列表 |
| `/api/todos` | POST | 保存待办列表（请求体为 JSON 数组） |
| `/api/proxy` | GET | 反向代理（绕过 X-Frame-Options/CSP 限制） |
| `/api/readability` | GET | 阅读模式（抓取网页 HTML，提取正文，返回 JSON） |
| 其他 | GET/OPTIONS | 静态文件服务 / CORS 预检 |

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

### 反向代理 (`/api/proxy`)

用于让 iframe 可以嵌入原本禁止嵌入的网站（X-Frame-Options / CSP frame-ancestors 限制）：

- 接受 `?url=` 参数，代理请求目标 URL
- 使用浏览器 User-Agent 模拟请求，10 秒超时
- 剥离响应头中的 `X-Frame-Options` 和 CSP 的 `frame-ancestors` 指令
- 对 HTML 内容重写资源路径（`src`、`href`、`action` 属性及 `url()` CSS 函数），将相对路径转为绝对路径
- SSRF 防护：禁止访问内网地址（localhost、私有 IP 段、`.local` 域名），通过 `ipaddress` 模块校验
- 请求头中注入 `Access-Control-Allow-Origin: *`

### 阅读模式 (`/api/readability`)

抓取指定 URL 的网页内容，提取正文（标题 + 内容 + 图片），返回干净 JSON 供前端渲染阅读视图：

- 接受 `?url=` 参数
- 抓取目标 HTML，自动检测编码（从 Content-Type 头）
- 使用 `HTMLReadabilityParser` 解析：基于文本密度分析（文本长度 / 子标签数），选择最密集的块级元素作为正文容器
- 正文提取策略：`<article>` → 带 content/article 等 class 的 div → `<main>` → 连续 `<p>` 标签 → `<body>` 兜底
- 返回 JSON：`{title, content, images, source, site_name, publish_time, error}`
- 标题兜底：`<title>` → `<h1>`；站点名兜底：从 URL 域名提取

### 前端 (`work_dashboard.html`) — 核心功能

- **4 种职业模式**：程序员（代码 Diff + 终端）、设计师（Figma 风格画板）、产品经理（PRD 文档）、运营（数据看板）
- **角色选择**：首次使用弹出选择框，结果持久化到 `localStorage`，可通过设置齿轮图标切换
- **待办面板**：数据持久化到 `todos.json`，支持添加、删除、拖拽排序
- **嵌入面板（参考文档）**：侧边栏，支持三种加载模式（见下方），通过导航栏"书本"图标切换
- **退出检测**：轮询 `/exit_status` 端点；退出时触发模糊动画
- **进入/退出动画**：三段式 Windows 任务视图风格切换动画

### 嵌入面板三种模式

| 模式 | 说明 | 实现 |
|------|------|------|
| 直接 (direct) | 传统 iframe 嵌入 | 沙盒 iframe，原始 URL |
| 代理 (proxy) | 通过后端代理绕过嵌入限制 | 沙盒 iframe，指向 `/api/proxy?url=...` |
| 阅读 (read) | 提取网页正文渲染为阅读视图 | 调用 `/api/readability?url=...`，前端渲染标题+正文 |

- 模式切换通过面板头部按钮切换，当前模式持久化到 `localStorage`（键名 `wsp_embed_mode`）
- URL 输入模态框（`#url-modal`）用于添加/编辑嵌入的网址
- 最近使用的 URL 历史存储在 `localStorage`，键名为 `wsp_embed_history`
- 当前 URL 存储在 `localStorage`，键名为 `wsp_embed_url`
- 关键函数：`loadDirect()`、`loadViaProxy()`、`loadViaReadability()`、`renderReadView()`

### 前后端通信

1. Python 启动 HTTP 服务器 → 以 Chrome/Edge `--app` 模式打开看板
2. 看板页面通过 URL 参数接收 `?role=xxx`
3. 待办操作：前端通过 `GET/POST /api/todos` 与后端同步数据
4. 嵌入面板：前端通过 `/api/proxy` 和 `/api/readability` 获取内容
5. 快捷键切换退出时：Python 调用 `GET /exit` → 设置退出标志 → 前端轮询 `/exit_status` 感知退出 → 播放动画

### 角色 URL 参数

后端通过 URL 传递角色：`http://127.0.0.1:{port}/?role={role}`。前端在 `getRoleFromURL()` 中读取，未设置时回退到 `localStorage`。

### 同源策略

- 后端绑定 `127.0.0.1`，前端所有 API 请求使用 `location.hostname` 动态构建 URL（而非硬编码 `localhost`），避免 CORS 问题
- `getBaseUrl()` 和 `startExitPolling()` 均使用 `location.protocol` + `location.hostname` + `location.port` 构建请求地址

## 注意事项

- 角色、嵌入 URL/历史、嵌入模式使用 `localStorage` 存储（键名以 `wsp_` 为前缀）；待办数据使用 `todos.json` 文件存储
- HTML 文件完全自包含 —— 无外部依赖、无构建工具
- Python 导入为可选/优雅降级 —— pynput、pycaw、pystray 各有回退行为
- `_exit_signaled` 是类变量，每次服务器启动时在 `DashboardServer.__init__` 中重置
- `HTMLReadabilityParser` 基于标准库 `HTMLParser` 实现，不依赖 BeautifulSoup 等第三方库
