"""
网页摸鱼保镖 - 主程序

功能概述：
1. 读取/生成配置文件 (config.json)
2. 内嵌 HTTP 服务器，提供工作看板页面
3. 全局快捷键监听，切换伪装模式
4. 窗口管理：最小化浏览器、打开看板、恢复窗口
5. 系统音量控制（Windows）
6. 系统托盘（可选）
"""

import json
import logging
import os
import platform
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from functools import partial

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("FishGuardian")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
TODOS_PATH = os.path.join(SCRIPT_DIR, "todos.json")
DEFAULT_CONFIG: Dict[str, Any] = {
    "hotkey": "ctrl+`",
    "role": "developer",
    "port": 0,
    "transition_duration_ms": 800,
    "muted_browsers": [
        "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "vivaldi.exe"
    ],
}

# ---------------------------------------------------------------------------
# 第三方库导入（可选依赖优雅降级）
# ---------------------------------------------------------------------------
try:
    import pynput
    from pynput import keyboard
except ImportError:
    pynput = None
    keyboard = None
    logger.warning("pynput 未安装，全局快捷键功能不可用。请执行: pip install pynput")

# Windows 音量控制
if platform.system() == "Windows":
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        _pycaw_available = True
    except ImportError:
        _pycaw_available = False
        logger.warning("pycaw 未安装，音量控制不可用。请执行: pip install pycaw comtypes")
else:
    _pycaw_available = False

# 系统托盘
try:
    import pystray
    from PIL import Image, ImageDraw

    _pystray_available = True
except ImportError:
    _pystray_available = False
    logger.info("pystray / Pillow 未安装，系统托盘功能不可用。将以控制台模式运行。")

# 窗口管理（Windows）
if platform.system() == "Windows":
    try:
        import ctypes
        import ctypes.wintypes

        _win32_available = True
    except ImportError:
        _win32_available = False
else:
    _win32_available = False


# ===========================================================================
# 配置管理
# ===========================================================================

def load_config() -> Dict[str, Any]:
    """
    加载配置文件。

    如果 config.json 不存在，则自动生成默认配置并写入文件。
    返回合并后的配置字典。
    """
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            logger.info("已加载配置文件: %s", CONFIG_PATH)
            # 合并默认值，确保新增字段也有默认值
            merged = DEFAULT_CONFIG.copy()
            merged.update(cfg)
            return merged
        except (json.JSONDecodeError, IOError) as e:
            logger.error("配置文件读取失败: %s，将使用默认配置", e)
    else:
        logger.info("配置文件不存在，将生成默认配置: %s", CONFIG_PATH)

    # 写入默认配置
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: Dict[str, Any]) -> None:
    """将配置字典写入 config.json 文件。"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        logger.info("配置已保存到: %s", CONFIG_PATH)
    except IOError as e:
        logger.error("保存配置文件失败: %s", e)


# ===========================================================================
# 待办存储
# ===========================================================================

def load_todos() -> List[Dict[str, Any]]:
    """从 todos.json 加载待办数据。"""
    if os.path.exists(TODOS_PATH):
        try:
            with open(TODOS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("待办文件读取失败: %s，将使用空列表", e)
    return []


def save_todos(todos: List[Dict[str, Any]]) -> None:
    """将待办列表写入 todos.json 文件。"""
    try:
        with open(TODOS_PATH, "w", encoding="utf-8") as f:
            json.dump(todos, f, indent=2, ensure_ascii=False)
    except IOError as e:
        logger.error("保存待办文件失败: %s", e)


# ===========================================================================
# 快捷键解析
# ===========================================================================

def parse_hotkey(hotkey_str: str) -> Tuple[List[Any], Any]:
    """
    解析快捷键字符串，返回 (修饰键列表, 主键)。

    支持的格式示例：
      - "ctrl+`"
      - "f9"
      - "ctrl+shift+h"
      - "alt+tab"

    返回值中的修饰键为 pynput.keyboard.Key 枚举或键盘按键字符，
    主键为 pynput.keyboard.Key 枚举或字符。
    """
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    modifiers: List[Any] = []
    main_key: Any = None

    # 修饰键映射
    modifier_map = {
        "ctrl": keyboard.Key.ctrl,
        "control": keyboard.Key.ctrl,
        "alt": keyboard.Key.alt,
        "shift": keyboard.Key.shift,
        "cmd": keyboard.Key.cmd,
        "super": keyboard.Key.cmd,
        "win": keyboard.Key.cmd,
        "meta": keyboard.Key.cmd,
    }

    # 特殊键映射
    special_key_map = {
        "tab": keyboard.Key.tab,
        "esc": keyboard.Key.esc,
        "escape": keyboard.Key.esc,
        "space": keyboard.Key.space,
        "enter": keyboard.Key.enter,
        "return": keyboard.Key.enter,
        "backspace": keyboard.Key.backspace,
        "delete": keyboard.Key.delete,
        "insert": keyboard.Key.insert,
        "home": keyboard.Key.home,
        "end": keyboard.Key.end,
        "page_up": keyboard.Key.page_up,
        "page_down": keyboard.Key.page_down,
        "up": keyboard.Key.up,
        "down": keyboard.Key.down,
        "left": keyboard.Key.left,
        "right": keyboard.Key.right,
        "f1": keyboard.Key.f1,
        "f2": keyboard.Key.f2,
        "f3": keyboard.Key.f3,
        "f4": keyboard.Key.f4,
        "f5": keyboard.Key.f5,
        "f6": keyboard.Key.f6,
        "f7": keyboard.Key.f7,
        "f8": keyboard.Key.f8,
        "f9": keyboard.Key.f9,
        "f10": keyboard.Key.f10,
        "f11": keyboard.Key.f11,
        "f12": keyboard.Key.f12,
        # 反引号在 Windows 上通过 vk 码匹配（pynput 的 key.char 可能为 None）
        "`": keyboard.KeyCode.from_vk(0xC0),  # VK_OEM_3 = 反引号/波浪号键
        "~": keyboard.KeyCode.from_vk(0xC0),
    }

    for part in parts:
        if part in modifier_map:
            modifiers.append(modifier_map[part])
        elif part in special_key_map:
            main_key = special_key_map[part]
        else:
            # 普通字符键（如字母、数字、符号）
            main_key = part

    if main_key is None:
        raise ValueError(f"无法解析快捷键: {hotkey_str}")

    return modifiers, main_key


# ===========================================================================
# 音量控制
# ===========================================================================

class VolumeController:
    """
    系统音量控制器。

    Windows 下使用 pycaw 控制主音量，其他平台优雅跳过。
    """

    def __init__(self) -> None:
        """初始化音量控制器，保存当前音量值。"""
        self._original_volume: Optional[float] = None
        self._volume_interface: Any = None
        self._available = False

        if not _pycaw_available:
            logger.info("当前平台不支持音量控制，将跳过音量操作")
            return

        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None
            )
            self._volume_interface = cast(interface, POINTER(IAudioEndpointVolume))
            # 获取当前音量 (0.0 ~ 1.0)
            self._original_volume = self._volume_interface.GetMasterVolumeLevelScalar()
            self._available = True
            logger.info("音量控制已就绪，当前音量: %.0f%%", self._original_volume * 100)
        except Exception as e:
            logger.error("初始化音量控制失败: %s", e)
            self._available = False

    @property
    def available(self) -> bool:
        """音量控制是否可用。"""
        return self._available

    def mute(self) -> None:
        """将系统主音量设为 0（静音）。"""
        if not self._available:
            return
        try:
            self._volume_interface.SetMasterVolumeLevelScalar(0.0, None)
            logger.info("已静音系统音量")
        except Exception as e:
            logger.error("静音失败: %s", e)

    def restore(self) -> None:
        """恢复之前的系统音量。"""
        if not self._available or self._original_volume is None:
            return
        try:
            self._volume_interface.SetMasterVolumeLevelScalar(self._original_volume, None)
            logger.info("已恢复系统音量: %.0f%%", self._original_volume * 100)
        except Exception as e:
            logger.error("恢复音量失败: %s", e)


# ===========================================================================
# 窗口管理
# ===========================================================================

class WindowInfo:
    """保存窗口信息的数据类。"""

    def __init__(self, hwnd: Any, title: str, process_name: str,
                 rect: Optional[Tuple[int, int, int, int]] = None) -> None:
        self.hwnd = hwnd          # 窗口句柄
        self.title = title        # 窗口标题
        self.process_name = process_name  # 进程名
        self.rect = rect          # (left, top, right, bottom)

    def __repr__(self) -> str:
        return (f"WindowInfo(title={self.title!r}, process={self.process_name!r}, "
                f"rect={self.rect})")


class WindowManager:
    """
    窗口管理器。

    负责获取前台窗口、最小化/恢复窗口、打开看板等操作。
    """

    def __init__(self) -> None:
        self._system = platform.system()
        self._saved_window: Optional[WindowInfo] = None
        self._dashboard_process: Optional[subprocess.Popen] = None

    def get_foreground_window_info(self) -> Optional[WindowInfo]:
        """
        获取当前前台活动窗口的信息。

        返回 WindowInfo 或 None（获取失败时）。
        """
        try:
            if self._system == "Windows":
                return self._get_foreground_windows()
            elif self._system == "Darwin":
                return self._get_foreground_macos()
            else:
                return self._get_foreground_linux()
        except Exception as e:
            logger.error("获取前台窗口信息失败: %s", e)
            return None

    def _get_foreground_windows(self) -> Optional[WindowInfo]:
        """Windows 平台：使用 ctypes 获取前台窗口信息。"""
        if not _win32_available:
            logger.warning("Windows ctypes 不可用，无法获取窗口信息")
            return None

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()

        # 获取窗口标题
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value

        # 获取窗口位置和大小
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        window_rect = (rect.left, rect.top, rect.right, rect.bottom)

        # 获取窗口所属进程名
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = self._get_process_name_by_pid(pid.value)

        return WindowInfo(hwnd, title, process_name, window_rect)

    def _get_foreground_macos(self) -> Optional[WindowInfo]:
        """macOS 平台：使用 AppleScript 获取前台窗口信息。"""
        try:
            script = '''
            tell application "System Events"
                set frontApp to name of first application process whose frontmost is true
                set frontWindow to name of first window of process frontApp
            end tell
            return frontApp & "|" & frontWindow
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and "|" in result.stdout:
                app_name, window_title = result.stdout.strip().split("|", 1)
                return WindowInfo(None, window_title, app_name.lower())
        except Exception as e:
            logger.error("macOS 获取前台窗口失败: %s", e)
        return None

    def _get_foreground_linux(self) -> Optional[WindowInfo]:
        """Linux 平台：使用 wmctrl 或 xdotool 获取前台窗口信息。"""
        try:
            # 尝试使用 xdotool
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                title = result.stdout.strip()
                # 获取窗口对应的进程名
                pid_result = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowpid"],
                    capture_output=True, text=True, timeout=5
                )
                process_name = ""
                if pid_result.returncode == 0:
                    pid = pid_result.stdout.strip()
                    try:
                        with open(f"/proc/{pid}/comm", "r") as f:
                            process_name = f.read().strip()
                    except (IOError, FileNotFoundError):
                        pass
                return WindowInfo(None, title, process_name)
        except FileNotFoundError:
            logger.warning("xdotool 未安装，无法获取 Linux 窗口信息")
        except Exception as e:
            logger.error("Linux 获取前台窗口失败: %s", e)
        return None

    @staticmethod
    def _get_process_name_by_pid(pid: int) -> str:
        """通过 PID 获取进程名（Windows）。"""
        try:
            import psutil
            proc = psutil.Process(pid)
            return proc.name().lower()
        except ImportError:
            pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # 回退方案：使用 tasklist
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                # 输出格式: "name","pid","session","session#","mem"
                parts = result.stdout.strip().strip('"').split('","')
                if parts:
                    return parts[0].lower()
        except Exception:
            pass

        return ""

    def is_browser(self, process_name: str, muted_browsers: List[str]) -> bool:
        """
        判断进程名是否为浏览器。

        Args:
            process_name: 窗口所属进程名（小写）
            muted_browsers: 配置中的浏览器进程名列表

        Returns:
            如果是浏览器返回 True
        """
        name_lower = process_name.lower()
        # 去掉 .exe 后缀进行比较
        name_no_ext = name_lower.replace(".exe", "")
        for browser in muted_browsers:
            browser_lower = browser.lower().replace(".exe", "")
            if name_no_ext == browser_lower or name_lower == browser_lower:
                return True
        return False

    def minimize_window(self, window: WindowInfo) -> None:
        """最小化指定窗口。"""
        try:
            if self._system == "Windows" and window.hwnd and _win32_available:
                user32 = ctypes.windll.user32
                user32.ShowWindow(window.hwnd, 6)  # SW_MINIMIZE = 6
                logger.info("已最小化窗口: %s", window.title)
            elif self._system == "Darwin":
                subprocess.run(
                    ["osascript", "-e",
                     f'tell application "{window.process_name}" to set miniaturized of window 1 to true'],
                    timeout=5
                )
                logger.info("已最小化窗口: %s", window.title)
            else:
                # Linux: 使用 wmctrl 或 xdotool
                try:
                    subprocess.run(
                        ["xdotool", "getactivewindow", "windowminimize"],
                        timeout=5
                    )
                    logger.info("已最小化窗口: %s", window.title)
                except FileNotFoundError:
                    logger.warning("无法最小化窗口：xdotool 未安装")
        except Exception as e:
            logger.error("最小化窗口失败: %s", e)

    def restore_window(self, window: WindowInfo) -> None:
        """恢复之前被最小化的窗口。"""
        try:
            if self._system == "Windows" and window.hwnd and _win32_available:
                user32 = ctypes.windll.user32
                user32.ShowWindow(window.hwnd, 9)  # SW_RESTORE = 9
                user32.SetForegroundWindow(window.hwnd)
                logger.info("已恢复窗口: %s", window.title)
            elif self._system == "Darwin":
                subprocess.run(
                    ["osascript", "-e",
                     f'tell application "{window.process_name}" to activate'],
                    timeout=5
                )
                logger.info("已恢复窗口: %s", window.title)
            else:
                try:
                    subprocess.run(
                        ["xdotool", "getactivewindow", "windowactivate"],
                        timeout=5
                    )
                    logger.info("已尝试恢复窗口: %s", window.title)
                except FileNotFoundError:
                    logger.warning("无法恢复窗口：xdotool 未安装")
        except Exception as e:
            logger.error("恢复窗口失败: %s", e)

    def open_dashboard(self, url: str) -> None:
        """
        使用浏览器的"应用模式"打开看板 URL。

        Args:
            url: 看板的完整 URL
        """
        self._system = platform.system()
        try:
            if self._system == "Windows":
                self._open_dashboard_windows(url)
            elif self._system == "Darwin":
                self._open_dashboard_macos(url)
            else:
                self._open_dashboard_linux(url)
            logger.info("已打开看板: %s", url)
        except Exception as e:
            logger.error("打开看板失败: %s，将使用默认浏览器打开", e)
            webbrowser.open(url)

    def _open_dashboard_windows(self, url: str) -> None:
        """Windows 平台：尝试使用 Chrome 或 Edge 的应用模式。"""
        # 优先尝试 Chrome
        chrome_paths = [
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        ]
        for chrome_path in chrome_paths:
            if os.path.exists(chrome_path):
                self._dashboard_process = subprocess.Popen(
                    [chrome_path, f"--app={url}"],
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
                return

        # 尝试 Edge
        edge_paths = [
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        ]
        for edge_path in edge_paths:
            if os.path.exists(edge_path):
                self._dashboard_process = subprocess.Popen(
                    [edge_path, f"--app={url}"],
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
                return

        # 回退：尝试 PATH 中的命令
        try:
            self._dashboard_process = subprocess.Popen(
                ["chrome.exe", f"--app={url}"],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            return
        except FileNotFoundError:
            pass
        try:
            self._dashboard_process = subprocess.Popen(
                ["msedge.exe", f"--app={url}"],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            return
        except FileNotFoundError:
            pass

        # 最终回退
        webbrowser.open(url)

    def _open_dashboard_macos(self, url: str) -> None:
        """macOS 平台：使用 open 命令打开 Chrome 应用模式。"""
        try:
            self._dashboard_process = subprocess.Popen(
                ["open", "-a", "Google Chrome", "--args", f"--app={url}"]
            )
            return
        except FileNotFoundError:
            pass
        try:
            self._dashboard_process = subprocess.Popen(
                ["open", "-a", "Microsoft Edge", "--args", f"--app={url}"]
            )
            return
        except FileNotFoundError:
            pass
        webbrowser.open(url)

    def _open_dashboard_linux(self, url: str) -> None:
        """Linux 平台：尝试使用 google-chrome 的应用模式。"""
        chrome_commands = [
            "google-chrome", "google-chrome-stable", "chromium-browser",
            "chromium", "microsoft-edge-stable", "brave-browser",
        ]
        for cmd in chrome_commands:
            try:
                self._dashboard_process = subprocess.Popen([cmd, f"--app={url}"])
                return
            except FileNotFoundError:
                continue
        webbrowser.open(url)

    def close_dashboard(self) -> None:
        """关闭看板窗口（终止看板浏览器进程）。"""
        if self._dashboard_process is not None:
            try:
                self._dashboard_process.terminate()
                self._dashboard_process.wait(timeout=5)
                logger.info("已关闭看板窗口")
            except subprocess.TimeoutExpired:
                self._dashboard_process.kill()
                logger.info("已强制关闭看板窗口")
            except Exception as e:
                logger.error("关闭看板窗口失败: %s", e)
            finally:
                self._dashboard_process = None

    @property
    def saved_window(self) -> Optional[WindowInfo]:
        """获取保存的窗口信息。"""
        return self._saved_window

    @saved_window.setter
    def saved_window(self, value: Optional[WindowInfo]) -> None:
        """设置保存的窗口信息。"""
        self._saved_window = value


# ===========================================================================
# 内嵌 HTTP 服务器
# ===========================================================================

class DashboardHandler(SimpleHTTPRequestHandler):
    """
    自定义 HTTP 请求处理器。

    提供以下路由：
      - GET /              -> 返回 work_dashboard.html
      - GET /exit          -> 触发看板退出（仅后端内部调用）
      - GET /exit_status   -> 前端轮询检查退出状态
      - GET /config        -> 返回当前配置 JSON
      - GET /api/todos     -> 返回待办列表
      - POST /api/todos    -> 保存待办列表
      - 其他               -> 静态文件服务
    """

    # 类变量，由外部设置
    config: Dict[str, Any] = {}
    exit_event: Optional[threading.Event] = None
    _exit_signaled: bool = False  # 防止重复触发

    def log_message(self, format: str, *args: Any) -> None:
        """重写日志方法，使用统一的日志格式。"""
        logger.debug("HTTP: %s", format % args)

    def do_GET(self) -> None:  # noqa: N802
        """处理 GET 请求。"""
        parsed = urlparse(self.path)

        if parsed.path == "/" or parsed.path == "":
            self._serve_dashboard()
        elif parsed.path == "/exit":
            self._handle_exit()
        elif parsed.path == "/exit_status":
            self._handle_exit_status()
        elif parsed.path == "/config":
            self._serve_config()
        elif parsed.path == "/api/todos":
            self._serve_todos()
        else:
            # 尝试提供静态文件
            super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        """处理 POST 请求。"""
        parsed = urlparse(self.path)

        if parsed.path == "/api/todos":
            self._save_todos()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_dashboard(self) -> None:
        """提供 work_dashboard.html 页面。"""
        dashboard_path = os.path.join(SCRIPT_DIR, "work_dashboard.html")
        if os.path.exists(dashboard_path):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(dashboard_path, "rb") as f:
                self.wfile.write(f.read())
            logger.debug("已提供 work_dashboard.html")
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("work_dashboard.html 文件未找到".encode("utf-8"))
            logger.warning("work_dashboard.html 文件不存在: %s", dashboard_path)

    def _handle_exit(self) -> None:
        """处理 /exit 请求，触发退出事件（仅后端内部调用）。"""
        if DashboardHandler._exit_signaled:
            return  # 已触发过，忽略重复请求
        DashboardHandler._exit_signaled = True

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        response = {"status": "ok", "message": "exit signal received"}
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        logger.info("收到退出信号")

        # 触发退出事件
        if DashboardHandler.exit_event is not None:
            DashboardHandler.exit_event.set()

    def _handle_exit_status(self) -> None:
        """前端轮询检查退出状态。"""
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        response = {"exit": DashboardHandler._exit_signaled}
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))

    def _serve_config(self) -> None:
        """返回当前配置的 JSON。"""
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(DashboardHandler.config, indent=2, ensure_ascii=False).encode("utf-8"))

    def _serve_todos(self) -> None:
        """返回待办列表 JSON。"""
        todos = load_todos()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(todos, ensure_ascii=False).encode("utf-8"))

    def _save_todos(self) -> None:
        """保存待办列表。"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            todos = json.loads(body.decode("utf-8"))
            save_todos(todos)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}, ensure_ascii=False).encode("utf-8"))
        except (json.JSONDecodeError, IOError) as e:
            logger.error("保存待办失败: %s", e)
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False).encode("utf-8"))


class DashboardServer:
    """
    看板 HTTP 服务器。

    在后台线程中运行 HTTP 服务器，提供工作看板页面。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        初始化服务器。

        Args:
            config: 配置字典
        """
        self._config = config
        self._port: int = config.get("port", 0)
        self._server: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._exit_event = threading.Event()

        # 重置退出状态，避免上次运行残留
        DashboardHandler._exit_signaled = False
        # 设置类变量，供 Handler 使用
        DashboardHandler.config = config
        DashboardHandler.exit_event = self._exit_event

    @property
    def port(self) -> int:
        """获取服务器实际监听的端口号。"""
        if self._server:
            return self._server.server_address[1]
        return self._port

    @property
    def exit_event(self) -> threading.Event:
        """获取退出事件对象。"""
        return self._exit_event

    def start(self) -> None:
        """启动 HTTP 服务器（后台线程）。"""
        try:
            self._server = HTTPServer(("127.0.0.1", self._port), DashboardHandler)
            actual_port = self._server.server_address[1]
            self._port = actual_port

            # 在后台线程中运行服务器
            self._server_thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="DashboardHTTPServer",
            )
            self._server_thread.start()

            logger.info("看板服务器已启动: http://127.0.0.1:%d", actual_port)
        except OSError as e:
            logger.error("启动 HTTP 服务器失败: %s", e)
            raise

    def stop(self) -> None:
        """停止 HTTP 服务器。"""
        if self._server:
            logger.info("正在停止看板服务器...")
            self._server.shutdown()
            self._server = None
            logger.info("看板服务器已停止")

    def get_dashboard_url(self, role: Optional[str] = None) -> str:
        """
        获取看板的完整 URL。

        Args:
            role: 用户角色（可选，默认从配置读取）

        Returns:
            看板 URL 字符串
        """
        if role is None:
            role = self._config.get("role", "developer")
        return f"http://127.0.0.1:{self.port}/?role={role}"


# ===========================================================================
# 系统托盘
# ===========================================================================

class TrayIcon:
    """
    系统托盘图标管理。

    如果 pystray 可用，创建系统托盘图标，提供右键菜单。
    如果不可用，优雅降级为控制台运行。
    """

    def __init__(self, on_exit: callable) -> None:
        """
        初始化系统托盘。

        Args:
            on_exit: 退出回调函数
        """
        self._on_exit = on_exit
        self._tray: Optional[Any] = None
        self._status_text = "伪装模式: 关闭"
        self._running = False

    def create_icon_image(self) -> Any:
        """创建托盘图标图像（简单的蓝色圆形图标）。"""
        if not _pystray_available:
            return None
        try:
            width, height = 64, 64
            image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            # 绘制蓝色圆形
            draw.ellipse([4, 4, width - 4, height - 4], fill=(52, 152, 219, 255))
            # 绘制白色盾牌形状（简化）
            draw.polygon([
                (width // 2, 12),
                (width // 2 + 16, 22),
                (width // 2 + 14, 42),
                (width // 2, 52),
                (width // 2 - 14, 42),
                (width // 2 - 16, 22),
            ], fill=(255, 255, 255, 255))
            return image
        except Exception as e:
            logger.error("创建托盘图标失败: %s", e)
            return None

    def update_status(self, disguised: bool) -> None:
        """更新托盘状态文本。"""
        self._status_text = "伪装模式: 开启" if disguised else "伪装模式: 关闭"
        if self._tray and _pystray_available:
            try:
                self._tray.title = self._status_text
            except Exception:
                pass

    def _create_menu(self) -> Any:
        """创建右键菜单。"""
        if not _pystray_available:
            return None

        def show_status(icon: Any, item: Any) -> None:
            """显示当前状态。"""
            logger.info("当前状态: %s", self._status_text)

        def exit_app(icon: Any, item: Any) -> None:
            """退出程序。"""
            logger.info("通过托盘菜单退出程序")
            self._running = False
            if self._tray:
                self._tray.stop()
            if self._on_exit:
                self._on_exit()

        return pystray.Menu(
            pystray.MenuItem(self._status_text, show_status, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", exit_app),
        )

    def run(self) -> None:
        """运行系统托盘（阻塞）。"""
        if not _pystray_available:
            logger.info("系统托盘不可用，以控制台模式运行")
            return

        image = self.create_icon_image()
        if image is None:
            return

        menu = self._create_menu()
        if menu is None:
            return

        self._running = True
        self._tray = pystray.Icon(
            name="FishGuardian",
            icon=image,
            title="网页摸鱼保镖",
            menu=menu,
        )

        try:
            logger.info("系统托盘已启动")
            self._tray.run()
        except Exception as e:
            logger.error("系统托盘运行出错: %s", e)

    def stop(self) -> None:
        """停止系统托盘。"""
        if self._tray and _pystray_available:
            try:
                self._tray.stop()
            except Exception:
                pass


# ===========================================================================
# 主控制器
# ===========================================================================

class FishGuardian:
    """
    网页摸鱼保镖主控制器。

    协调配置管理、HTTP 服务器、快捷键监听、窗口管理和音量控制。
    """

    def __init__(self) -> None:
        """初始化主控制器。"""
        # 加载配置
        self._config = load_config()
        logger.info("当前配置: %s", json.dumps(self._config, indent=2, ensure_ascii=False))

        # 初始化各模块
        self._server = DashboardServer(self._config)
        self._volume = VolumeController()
        self._window_mgr = WindowManager()
        self._tray = TrayIcon(on_exit=self.shutdown)

        # 状态标志
        self._disguised = False  # 是否处于伪装模式
        self._lock = threading.Lock()  # 线程锁，防止快速重复触发

        # 快捷键监听器
        self._hotkey_listener: Any = None

    @property
    def config(self) -> Dict[str, Any]:
        """获取当前配置。"""
        return self._config

    @property
    def disguised(self) -> bool:
        """获取当前伪装模式状态。"""
        return self._disguised

    def start(self) -> None:
        """启动保镖程序。"""
        logger.info("=" * 50)
        logger.info("网页摸鱼保镖 启动中...")
        logger.info("=" * 50)
        logger.info("操作系统: %s", platform.system())
        logger.info("快捷键: %s", self._config.get("hotkey", "ctrl+`"))
        logger.info("用户角色: %s", self._config.get("role", "developer"))

        # 启动 HTTP 服务器
        try:
            self._server.start()
        except OSError as e:
            logger.error("无法启动 HTTP 服务器: %s", e)
            logger.error("请检查端口是否被占用，或修改 config.json 中的 port 字段")
            return

        dashboard_url = self._server.get_dashboard_url()
        logger.info("看板地址: %s", dashboard_url)

        # 启动快捷键监听
        if keyboard is not None:
            self._start_hotkey_listener()
        else:
            logger.warning("快捷键监听不可用（pynput 未安装），请手动访问看板地址")

        # 启动系统托盘（阻塞）
        self._tray.run()

        # 如果托盘不可用，使用控制台模式
        if not _pystray_available:
            self._console_mode()

    def _console_mode(self) -> None:
        """控制台运行模式（无系统托盘时使用）。"""
        logger.info("控制台模式运行中，按 Ctrl+C 退出")
        try:
            # 在主线程中保持运行
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到退出信号")
            self.shutdown()

    def _start_hotkey_listener(self) -> None:
        """启动全局快捷键监听。"""
        try:
            hotkey_str = self._config.get("hotkey", "ctrl+`")
            modifiers, main_key = parse_hotkey(hotkey_str)
            logger.info("快捷键已注册: %s", hotkey_str)

            # 当前按下的修饰键集合
            pressed_keys = set()

            def on_press(key: Any) -> bool:
                """按键按下回调。"""
                pressed_keys.add(key)

                # 检查修饰键是否全部按下
                mod_match = all(
                    any(k == mod for k in pressed_keys)
                    for mod in modifiers
                )

                # 检查主键是否匹配
                key_match = False
                if isinstance(main_key, keyboard.Key):
                    key_match = key == main_key
                elif isinstance(main_key, keyboard.KeyCode):
                    # 通过 KeyCode 匹配（如反引号通过 vk 码映射）
                    try:
                        if hasattr(key, "vk") and hasattr(main_key, "vk"):
                            key_match = key.vk == main_key.vk
                        if not key_match and hasattr(key, "char") and key.char and hasattr(main_key, "char") and main_key.char:
                            key_match = key.char == main_key.char
                    except (ValueError, AttributeError):
                        pass
                else:
                    # 字符键：尝试多种方式匹配
                    try:
                        if hasattr(key, "char") and key.char and key.char.lower() == main_key.lower():
                            key_match = True
                        elif hasattr(key, "vk") and key == main_key:
                            key_match = True
                    except (ValueError, AttributeError):
                        pass

                if mod_match and key_match:
                    logger.info("快捷键触发: %s", hotkey_str)
                    # 在新线程中执行切换操作，避免阻塞监听器
                    threading.Thread(target=self.toggle_disguise, daemon=True).start()

                return True

            def on_release(key: Any) -> bool:
                """按键释放回调。"""
                pressed_keys.discard(key)
                return True

            self._hotkey_listener = keyboard.Listener(
                on_press=on_press,
                on_release=on_release,
            )
            self._hotkey_listener.start()
            logger.info("全局快捷键监听已启动")

        except Exception as e:
            logger.error("启动快捷键监听失败: %s", e)

    def toggle_disguise(self) -> None:
        """
        切换伪装模式。

        使用线程锁防止快速重复触发。
        """
        with self._lock:
            if self._disguised:
                self._exit_disguise()
            else:
                self._enter_disguise()

    def _enter_disguise(self) -> None:
        """
        进入伪装模式。

        流程：
        1. 获取当前前台窗口
        2. 判断是否为浏览器
        3. 如果是浏览器，最小化窗口并记录信息
        4. 静音系统音量
        5. 打开工作看板
        """
        logger.info(">>> 进入伪装模式")

        # 1. 获取当前前台窗口
        foreground = self._window_mgr.get_foreground_window_info()
        if foreground is None:
            logger.warning("无法获取前台窗口信息，取消伪装")
            return

        logger.info("当前前台窗口: %s", foreground)

        # 2. 判断是否为浏览器
        muted_browsers = self._config.get("muted_browsers", [])
        if not self._window_mgr.is_browser(foreground.process_name, muted_browsers):
            logger.info("当前窗口不是浏览器 (%s)，不触发伪装", foreground.process_name)
            return

        # 3. 最小化浏览器窗口并记录
        self._window_mgr.saved_window = foreground
        self._window_mgr.minimize_window(foreground)

        # 4. 静音系统音量
        self._volume.mute()

        # 5. 打开工作看板
        dashboard_url = self._server.get_dashboard_url()
        self._window_mgr.open_dashboard(dashboard_url)

        self._disguised = True
        self._tray.update_status(True)
        logger.info("伪装模式已激活")

    def _exit_disguise(self) -> None:
        """
        退出伪装模式。

        流程：
        1. 向看板发送退出信号
        2. 等待过渡动画完成
        3. 关闭看板窗口
        4. 恢复被最小化的浏览器窗口
        5. 恢复系统音量
        """
        logger.info("<<< 退出伪装模式")

        # 1. 向看板发送退出信号
        exit_url = f"http://127.0.0.1:{self._server.port}/exit"
        try:
            import urllib.request
            urllib.request.urlopen(exit_url, timeout=5)
            logger.info("已发送退出信号到看板")
        except Exception as e:
            logger.warning("发送退出信号失败: %s", e)

        # 2. 等待过渡动画完成
        transition_ms = self._config.get("transition_duration_ms", 800)
        wait_seconds = max(transition_ms / 1000.0, 0.5)
        logger.info("等待过渡动画完成: %.1f 秒", wait_seconds)
        time.sleep(wait_seconds)

        # 3. 关闭看板窗口
        self._window_mgr.close_dashboard()

        # 4. 恢复被最小化的浏览器窗口
        if self._window_mgr.saved_window:
            self._window_mgr.restore_window(self._window_mgr.saved_window)
            self._window_mgr.saved_window = None

        # 5. 恢复系统音量
        self._volume.restore()

        self._disguised = False
        self._tray.update_status(False)
        logger.info("伪装模式已关闭")

    def shutdown(self) -> None:
        """关闭保镖程序，清理所有资源。"""
        logger.info("正在关闭保镖程序...")

        # 如果处于伪装模式，先退出伪装
        if self._disguised:
            try:
                self._exit_disguise()
            except Exception as e:
                logger.error("退出伪装模式时出错: %s", e)

        # 停止快捷键监听
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
                logger.info("快捷键监听已停止")
            except Exception as e:
                logger.error("停止快捷键监听失败: %s", e)

        # 停止 HTTP 服务器
        self._server.stop()

        # 停止系统托盘
        self._tray.stop()

        logger.info("保镖程序已关闭")
        sys.exit(0)


# ===========================================================================
# 入口
# ===========================================================================

def main() -> None:
    """程序入口函数。"""
    # 检查关键依赖
    if keyboard is None:
        logger.warning("=" * 50)
        logger.warning("pynput 未安装！全局快捷键功能不可用。")
        logger.warning("请执行: pip install pynput")
        logger.warning("=" * 50)

    # 创建并启动主控制器
    guardian = FishGuardian()
    guardian.start()


if __name__ == "__main__":
    main()
