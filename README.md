# 🛡️ 网页摸鱼保镖 (Web Fish Guardian)

> 一键隐藏摸鱼网页，秒变智能工作看板

## ✨ 功能亮点

- **一键切换**：按下 `Ctrl+`` 快捷键，当前浏览器窗口瞬间隐藏，展示高仿真工作看板
- **精准隐藏**：仅隐藏当前活动浏览器窗口，不影响其他工作窗口
- **4种职业模式**：程序员（代码Diff+终端）、设计师（Figma风格画板）、产品经理（PRD文档+数据看板）、运营（数据报表+社媒）
- **智能静音**：自动静音系统音量，防止摸鱼时突然出声
- **平滑过渡**：仿 Windows 任务视图的三段式切换动画
- **真实待办**：内置可用的待办事项面板，支持添加、删除、拖拽排序

## 🚀 快速开始

### 环境要求

- Python 3.9+
- Windows 10/11（推荐）/ macOS / Linux
- Chrome 或 Edge 浏览器

### 安装

```bash
# 克隆项目
cd web_fish_guardian

# 安装依赖
pip install -r requirements.txt
```

### 运行

```bash
python main.py
```

程序启动后会显示配置信息和服务器地址，然后进入监听状态。

### 使用方法

1. 打开浏览器，浏览你想浏览的任何网页
2. 老板来了！按下 `Ctrl+``
3. 浏览器窗口瞬间隐藏，弹出高仿真的工作看板
4. 老板走了！再次按下 `Ctrl+``
5. 看板关闭，浏览器窗口恢复到原来的状态

## ⌨️ 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+`` | 切换伪装模式（开/关） |

可在 `config.json` 中修改 `hotkey` 字段自定义快捷键，支持格式：
- `ctrl+`` — Ctrl + 反引号
- `ctrl+shift+h` — Ctrl + Shift + H
- `f9` — F9 功能键

## 👔 职业模式

首次启动看板时，会弹出角色选择器。选择后自动保存，后续不再显示。

| 模式 | 适用人群 | 看板内容 |
|------|----------|----------|
| 🖥️ 程序员 | 开发工程师 | GitHub 风格代码 Diff + VS Code 终端 |
| 🎨 设计师 | UI/UX 设计师 | Figma 风格设计画板 + 图层面板 |
| 📋 产品经理 | 产品经理 | 飞书风格 PRD 文档 + 数据看板 |
| 📊 运营 | 运营人员 | 数据概览卡片 + 趋势图表 + 内容列表 |

也可在 `config.json` 中预设 `role` 字段：
```json
{
  "role": "developer"
}
```

可选值：`developer`、`designer`、`pm`、`operator`

## ⚙️ 配置说明

编辑 `config.json`（首次运行自动生成）：

```json
{
  "hotkey": "ctrl+`",
  "role": "developer",
  "port": 0,
  "transition_duration_ms": 800,
  "muted_browsers": ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "vivaldi.exe"]
}
```

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `hotkey` | 全局快捷键 | `"ctrl+\`"` |
| `role` | 职业类型 | `"developer"` |
| `port` | HTTP 服务器端口（0=自动分配） | `0` |
| `transition_duration_ms` | 过渡动画时长（毫秒） | `800` |
| `muted_browsers` | 需要隐藏的浏览器进程名列表 | Chrome, Edge, Firefox, Brave, Vivaldi |

## 📁 项目结构

```
web_fish_guardian/
├── main.py                  # 主程序
├── work_dashboard.html      # 伪装看板（单文件）
├── config.json              # 配置文件
├── requirements.txt         # Python 依赖
└── README.md                # 说明文档
```

## 🔧 技术栈

| 组件 | 技术 |
|------|------|
| 主程序 | Python 3.9+ |
| 快捷键监听 | pynput |
| 窗口管理 | pygetwindow |
| 音量控制 | pycaw (Windows) |
| Web 服务器 | Python 内置 http.server |
| 前端看板 | HTML5 + CSS3 + Vanilla JavaScript |

## 📌 注意事项

1. **Windows 推荐**：音量控制功能仅支持 Windows，其他平台会自动跳过
2. **管理员权限**：某些系统可能需要管理员权限才能控制其他窗口
3. **浏览器支持**：默认支持 Chrome、Edge、Firefox、Brave、Vivaldi，可在配置中增减
4. **杀毒软件**：全局键盘钩子可能触发杀毒软件告警，请添加信任

## 🗺️ 未来计划

- [ ] 支持标签页级别隐藏（而非整个窗口）
- [ ] 支持自定义伪装页面（用户上传截图）
- [ ] 紧急模式（一键关闭所有摸鱼标签页）
- [ ] 打包为独立 exe，免安装运行
- [ ] 完整 macOS / Linux 支持
- [ ] 多显示器支持

## 📄 License

MIT License
