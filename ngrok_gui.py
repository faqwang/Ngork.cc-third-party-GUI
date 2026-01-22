#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sunny-Ngrok GUI Manager
图形化管理界面，用于管理Sunny-Ngrok隧道
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, scrolledtext
import os
import threading
import queue
import sys
import socket
import ctypes
from ctypes import wintypes
from datetime import datetime
import webbrowser

from ngrok_core import (
    CORE_DIR,
    get_sunny_exe_path,
    TUNNELS_FILE,
    SETTINGS_FILE,
    LAST_SELECTION_FILE,
    SUNNY_DOWNLOAD_PAGE,
    ensure_app_dirs,
    DownloadController,
    _download_and_extract_sunny_core,
    TunnelConfig,
    AppSettings,
    TunnelProcess
)

# 尝试导入系统托盘支持
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("提示: 安装 pystray 和 Pillow 可启用系统托盘功能")
    print("运行: pip install pystray Pillow")


LOG_MAX_LINES = 1000
LOG_DRAIN_BATCH = 200


def _build_missing_sunny_layout(parent, on_action):
    colors = {
        "bg": "#FAFAF9",
        "card": "#FFFFFF",
        "card_shadow": "#E7E5E4",
        "card_highlight": "#FFFFFF",
        "text_primary": "#0C0A09",
        "text_secondary": "#57534E",
        "border": "#E7E5E4"
    }

    parent.configure(bg=colors["bg"])
    shell = tk.Frame(parent, bg=colors["card_shadow"])
    shell.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

    container = tk.Frame(shell, bg=colors["card"], padx=24, pady=10)
    container.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
    tk.Frame(container, bg=colors["card_highlight"], height=1).pack(fill=tk.X, side=tk.TOP)

    tk.Label(
        container,
        text="缺少核心文件",
        font=('Microsoft YaHei UI', 12, 'bold'),
        bg=colors["card"],
        fg=colors["text_primary"],
        anchor='w',
        justify=tk.LEFT
    ).pack(fill=tk.X, pady=(0, 6))

    tk.Label(
        container,
        text="检测到 core\\sunny.exe 不存在。请选择下载方式：",
        font=('Microsoft YaHei UI', 10),
        bg=colors["card"],
        fg=colors["text_primary"],
        anchor='w',
        justify=tk.LEFT
    ).pack(fill=tk.X, pady=(0, 6))

    tk.Label(
        container,
        text="自动下载会从官方地址获取并解压到 core 文件夹。",
        font=('Microsoft YaHei UI', 9),
        bg=colors["card"],
        fg=colors["text_secondary"],
        anchor='w',
        justify=tk.LEFT
    ).pack(fill=tk.X, pady=(0, 18))

    button_frame = tk.Frame(container, bg=colors["card"])
    button_frame.pack(fill=tk.X, pady=8)
    button_frame.columnconfigure(0, weight=1)
    button_frame.columnconfigure(1, weight=1)

    ttk.Button(
        button_frame,
        text="手动下载（推荐）",
        command=lambda: on_action("manual"),
        style='Primary.TButton'
    ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))

    ttk.Button(
        button_frame,
        text="自动下载并安装",
        command=lambda: on_action("auto"),
        style='Secondary.TButton'
    ).grid(row=1, column=0, sticky="ew", padx=(0, 8))

    ttk.Button(
        button_frame,
        text="取消退出",
        command=lambda: on_action("cancel"),
        style='Secondary.TButton'
    ).grid(row=1, column=1, sticky="ew", padx=(8, 0))


def _prompt_missing_sunny(root):
    """提示用户选择 sunny.exe 的处理方式（主界面已运行时）"""
    dialog = tk.Toplevel(root)
    dialog.title("缺少核心文件")
    dialog.geometry("560x280")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
    dialog.geometry(f"+{x}+{y}")

    result = {"action": "close"}

    def set_action(action):
        result["action"] = action
        dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", lambda: set_action("close"))

    _build_missing_sunny_layout(dialog, set_action)

    dialog.wait_window()
    return result["action"]


def _show_manual_download_dialog(root):
    dialog = tk.Toplevel(root)
    dialog.title("手动下载指引")
    dialog.geometry("560x195")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
    dialog.geometry(f"+{x}+{y}")

    container = tk.Frame(dialog, padx=24, pady=20)
    container.pack(fill=tk.BOTH, expand=True)

    tk.Label(
        container,
        text="如何安装内核",
        font=('Microsoft YaHei UI', 12, 'bold'),
        anchor='w',
        justify=tk.LEFT
    ).pack(fill=tk.X, pady=(0, 8))

    tk.Label(
        container,
        text="1. 打开下载页面，下载 Windows 版本。\n"
             "2. 解压后找到 sunny.exe。\n"
             "3. 将 sunny.exe 放入程序目录的 core 文件夹中。",
        font=('Microsoft YaHei UI', 10),
        anchor='w',
        justify=tk.LEFT
    ).pack(fill=tk.X, pady=(0, 16))

    button_frame = tk.Frame(container)
    button_frame.pack(anchor='e')

    def open_page():
        webbrowser.open(SUNNY_DOWNLOAD_PAGE)

    def open_dir():
        try:
            os.makedirs(CORE_DIR, exist_ok=True)
            os.startfile(CORE_DIR)
        except Exception:
            pass

    ttk.Button(
        button_frame,
        text="打开下载页面",
        command=open_page,
        style='Primary.TButton'
    ).pack(side=tk.LEFT, padx=(0, 8))

    ttk.Button(
        button_frame,
        text="打开程序Core目录",
        command=open_dir,
        style='Secondary.TButton'
    ).pack(side=tk.LEFT, padx=(0, 8))

    ttk.Button(
        button_frame,
        text="关闭",
        command=dialog.destroy,
        style='Secondary.TButton'
    ).pack(side=tk.LEFT)

    dialog.wait_window()


def _download_and_extract_sunny(root):
    """下载并解压 sunny.exe 到 core 目录"""
    if root is None:
        return _download_and_extract_sunny_core(None, None)

    controller = DownloadController()
    result = {"success": False, "message": "下载失败"}

    dialog = tk.Toplevel(root)
    dialog.title("正在下载")
    dialog.geometry("480x110")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
    dialog.geometry(f"+{x}+{y}")

    container = tk.Frame(dialog, padx=20, pady=20)
    container.pack(fill=tk.BOTH, expand=True)

    status_var = tk.StringVar(value="正在下载核心文件，请稍候…")
    tk.Label(
        container,
        textvariable=status_var,
        font=('Microsoft YaHei UI', 10),
        anchor='w',
        justify=tk.LEFT
    ).pack(fill=tk.X, pady=(0, 14))

    progress = ttk.Progressbar(container, mode='indeterminate')
    progress.pack(fill=tk.X, pady=(0, 14))
    progress.start(10)

    btn_frame = tk.Frame(container)
    btn_frame.pack()

    def on_cancel():
        controller.cancel()
        status_var.set("正在取消下载…")

    ttk.Button(
        btn_frame,
        text="取消",
        command=on_cancel,
        style='Secondary.TButton'
    ).pack()

    def progress_callback(downloaded, total):
        if total:
            if progress['mode'] != 'determinate':
                progress.stop()
                progress.configure(mode='determinate', maximum=total, value=0)
            progress['value'] = downloaded
            percent = int(downloaded * 100 / total)
            status_var.set(f"正在下载核心文件… {percent}%")

    def worker():
        success, message = _download_and_extract_sunny_core(controller, progress_callback)
        result["success"] = success
        result["message"] = message

        def finish():
            try:
                progress.stop()
            except Exception:
                pass
            dialog.destroy()

        root.after(0, finish)

    threading.Thread(target=worker, daemon=True).start()
    dialog.wait_window()
    return result["success"], result["message"]


def ensure_sunny_ready(root=None, startup=False):
    """确保 sunny.exe 可用，不可用时提示用户处理"""
    if os.path.exists(get_sunny_exe_path()):
        return "ready"

    if startup:
        return "missing"

    action = _prompt_missing_sunny(root)
    if action == "auto":
        success, message = _download_and_extract_sunny(root)
        if success:
            messagebox.showinfo("成功", message)
            return "ready"
        if "已取消" in message:
            return "cancel"
        messagebox.showerror("错误", message)
        if messagebox.askyesno("提示", "自动下载失败，是否打开手动下载页面？"):
            webbrowser.open(SUNNY_DOWNLOAD_PAGE)
        return "failed"
    if action == "manual":
        _show_manual_download_dialog(root)
        return "manual"
    if action == "close":
        return "close"
    return "cancel"


class TunnelDialog(tk.Toplevel):
    """隧道配置对话框"""

    def __init__(self, parent, title="添加隧道", tunnel=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("450x480")
        self.resizable(False, False)

        # 现代化配色
        self.colors = {
            'bg': '#FAFAF9',
            'card': '#FFFFFF',
            'primary': '#1C1917',
            'text_primary': '#0C0A09',
            'text_secondary': '#57534E',
            'border': '#E7E5E4'
        }

        self.configure(bg=self.colors['bg'])

        self.result = None
        self.tunnel = tunnel

        # 使对话框模态
        self.transient(parent)
        self.grab_set()

        # 先创建控件
        self._create_widgets()

        # 如果是编辑模式，填充数据
        if tunnel:
            self.name_var.set(tunnel.get("name", ""))
            self.server_var.set(tunnel.get("server", ""))
            self.key_var.set(tunnel.get("key", ""))
            self.auto_start_var.set(tunnel.get("auto_start", False))

        # 居中显示
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        """创建控件"""
        # 主卡片容器
        card_shell = tk.Frame(self, bg=self.colors['border'])
        card_shell.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        card = tk.Frame(card_shell, bg=self.colors['card'], relief='flat', bd=0)
        card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        tk.Frame(card, bg='white', height=1).pack(fill=tk.X, side=tk.TOP)

        # 内容区域
        content = tk.Frame(card, bg=self.colors['card'])
        content.pack(fill=tk.BOTH, expand=True, padx=25, pady=25)

        # 名称
        name_frame = tk.Frame(content, bg=self.colors['card'])
        name_frame.pack(fill=tk.X, pady=8)

        tk.Label(
            name_frame,
            text="隧道名称",
            font=('Microsoft YaHei UI', 9),
            bg=self.colors['card'],
            fg=self.colors['text_secondary']
        ).pack(anchor='w', pady=(0, 5))

        self.name_var = tk.StringVar()
        name_entry = tk.Entry(
            name_frame,
            textvariable=self.name_var,
            font=('Microsoft YaHei UI', 10),
            relief='flat',
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors['border'],
            highlightcolor=self.colors['primary']
        )
        name_entry.pack(fill=tk.X, ipady=8, ipadx=10)

        # 服务器
        server_frame = tk.Frame(content, bg=self.colors['card'])
        server_frame.pack(fill=tk.X, pady=8)

        tk.Label(
            server_frame,
            text="服务器地址",
            font=('Microsoft YaHei UI', 9),
            bg=self.colors['card'],
            fg=self.colors['text_secondary']
        ).pack(anchor='w', pady=(0, 5))

        self.server_var = tk.StringVar(value="server.example.com:443")
        server_entry = tk.Entry(
            server_frame,
            textvariable=self.server_var,
            font=('Microsoft YaHei UI', 10),
            relief='flat',
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors['border'],
            highlightcolor=self.colors['primary']
        )
        server_entry.pack(fill=tk.X, ipady=8, ipadx=10)

        # 密钥
        key_frame = tk.Frame(content, bg=self.colors['card'])
        key_frame.pack(fill=tk.X, pady=8)

        tk.Label(
            key_frame,
            text="隧道密钥",
            font=('Microsoft YaHei UI', 9),
            bg=self.colors['card'],
            fg=self.colors['text_secondary']
        ).pack(anchor='w', pady=(0, 5))

        self.key_var = tk.StringVar()
        key_entry = tk.Entry(
            key_frame,
            textvariable=self.key_var,
            font=('Microsoft YaHei UI', 10),
            relief='flat',
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors['border'],
            highlightcolor=self.colors['primary']
        )
        key_entry.pack(fill=tk.X, ipady=8, ipadx=10)

        # 自动启动
        self.auto_start_var = tk.BooleanVar()
        auto_start_check = tk.Checkbutton(
            content,
            text="自动启动此隧道",
            variable=self.auto_start_var,
            font=('Microsoft YaHei UI', 9),
            bg=self.colors['card'],
            fg=self.colors['text_primary'],
            activebackground=self.colors['card'],
            selectcolor=self.colors['card']
        )
        auto_start_check.pack(anchor='w', pady=(15, 20))

        # 按钮区域
        button_frame = tk.Frame(content, bg=self.colors['card'])
        button_frame.pack(fill=tk.X, pady=(10, 0))

        # 应用ttk样式
        style = ttk.Style()
        style.configure('Dialog.Primary.TButton',
                       background=self.colors['primary'],
                       foreground='white',
                       font=('Microsoft YaHei UI', 9),
                       padding=(20, 8))

        ok_btn = ttk.Button(
            button_frame,
            text="确定",
            command=self._on_ok,
            style='Dialog.Primary.TButton'
        )
        ok_btn.pack(side=tk.LEFT, padx=(0, 10))

        cancel_btn = ttk.Button(
            button_frame,
            text="取消",
            command=self._on_cancel,
            style='Secondary.TButton'
        )
        cancel_btn.pack(side=tk.LEFT)

    def _on_ok(self):
        """确定按钮"""
        name = self.name_var.get().strip()
        server = self.server_var.get().strip()
        key = self.key_var.get().strip()

        if not name:
            messagebox.showwarning("警告", "请输入隧道名称")
            return

        if not server:
            messagebox.showwarning("警告", "请输入服务器地址")
            return

        if not key:
            messagebox.showwarning("警告", "请输入隧道密钥")
            return

        self.result = {
            "name": name,
            "server": server,
            "key": key,
            "auto_start": self.auto_start_var.get()
        }

        self.destroy()

    def _on_cancel(self):
        """取消按钮"""
        self.result = None
        self.destroy()


class NgrokGUI:
    """主GUI应用"""

    def __init__(self, root):
        self.root = root
        self.app_title = "Sunny-Ngrok 管理器"
        self.root.title(self.app_title)
        self.root.geometry("1000x650")
        self._is_maximized = False
        self._normal_geometry = None
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._win32_hook_installed = False
        self._orig_wndproc = None
        self._wndproc = None
        self._taskbar_toggle_guard = False
        self._enable_custom_titlebar()

        # 现代化配色方案
        self.colors = {
            'primary': '#1C1917',        # 主色 - 深色按钮
            'primary_dark': '#0C0A09',   # 主色加深
            'primary_light': '#F5F5F4',  # 主色浅背景
            'accent': '#CA8A04',         # 强调色 - 琥珀
            'accent_dark': '#A16207',    # 强调色加深
            'accent_light': '#FEF3C7',   # 强调色浅背景
            'success': '#16A34A',        # 成功 - 绿色
            'success_bg': '#DCFCE7',     # 成功 - 背景
            'danger': '#DC2626',         # 危险 - 红色
            'danger_dark': '#B91C1C',    # 危险 - 深红
            'danger_light': '#FEE2E2',   # 危险 - 浅红
            'warning': '#F59E0B',        # 警告 - 黄色
            'neutral_bg': '#F5F5F4',     # 中性状态背景
            'bg_main': '#FAFAF9',        # 页面背景
            'bg_card': '#FFFFFF',        # 卡片背景
            'bg_header': '#FFFFFF',      # 顶部栏背景
            'bg_list': '#F5F5F4',        # 列表区域背景
            'card_hover': '#F5F5F4',     # 卡片悬停
            'card_selected': '#FFFBEB',  # 卡片选中
            'card_shadow': '#E7E5E4',    # 卡片阴影
            'card_highlight': '#FFFFFF', # 卡片高光
            'text_primary': '#0C0A09',   # 主文本
            'text_secondary': '#57534E', # 次级文本
            'text_muted': '#A8A29E',     # 弱化文本
            'border': '#E7E5E4',         # 边框
            'hover': '#F5F5F4',          # 悬停
            'terminal_bg': '#0F172A',    # 终端背景
            'terminal_header': '#111827',# 终端头部
            'terminal_text': '#E2E8F0',  # 终端文本
            'terminal_muted': '#94A3B8', # 终端弱化
            'terminal_border': '#1F2937',# 终端边框
            'status_off': '#D6D3D1',     # 未运行指示
            'button_bg': '#F5F5F4',      # 次级按钮背景
            'button_shadow': '#E7E5E4',  # 按钮阴影
            'button_danger_bg': '#FEE2E2', # 危险按钮背景
            'titlebar_btn_bg': '#F5F5F4',  # 标题栏按钮背景
            'titlebar_btn_hover': '#E7E5E4', # 标题栏按钮悬停
            'titlebar_close': '#E81123',  # 关闭按钮背景
            'titlebar_close_hover': '#F1707A', # 关闭按钮悬停
            'titlebar_glyph': '#1C1917'   # 标题栏图标色
        }
        self.menu_font = ('Microsoft YaHei UI', 9)
        self.menu_item_font = ('Microsoft YaHei UI', 9)
        self.toolbar_height = 64

        # 配置和进程管理
        self.config = TunnelConfig(TUNNELS_FILE)
        self.settings = AppSettings(SETTINGS_FILE)  # 添加设置管理
        self.tunnel_processes = {}  # 字典：隧道ID -> TunnelProcess
        self.current_tunnel_index = None
        self.last_selected_index = None  # 记住最后选择的隧道
        self.last_selection_file = LAST_SELECTION_FILE
        self.log_queue = queue.Queue()

        # 系统托盘
        self.tray_icon = None

        # 初始化设置菜单引用
        self.settings_menu = None

        # 单实例通信服务器
        self.instance_server = None
        self._start_instance_server()

        # 应用现代化样式
        self._apply_modern_style()

        # 创建界面
        self._create_menu()
        self._create_widgets()
        self._load_tunnels()
        self.root.update_idletasks()
        self._normal_geometry = self.root.geometry()
        self.root.after(80, self._ensure_window_visible)
        self.root.after(100, self._drain_log_queue)
        self.root.after(350, self._install_taskbar_toggle)

        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # 恢复最后选择的隧道
        self._restore_last_selection()

        # 启动自动启动的隧道（延迟以避免启动白屏）
        self.root.after(400, self._auto_start_tunnels)

    def _apply_modern_style(self):
        """应用现代化样式"""
        style = ttk.Style()

        # 设置主题
        style.theme_use('clam')

        # 配置整体背景
        self.root.configure(bg=self.colors['bg_main'])

        # 配置 Frame 样式
        style.configure('Modern.TFrame', background=self.colors['bg_card'])
        style.configure('Header.TFrame', background=self.colors['bg_header'])
        style.configure('Main.TFrame', background=self.colors['bg_main'])

        # 配置 Label 样式
        style.configure('Title.TLabel',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       font=('Microsoft YaHei UI', 13, 'bold'))
        style.configure('Header.TLabel',
                       background=self.colors['bg_header'],
                       foreground=self.colors['text_primary'],
                       font=('Microsoft YaHei UI', 10, 'bold'))
        style.configure('Modern.TLabel',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_secondary'],
                       font=('Microsoft YaHei UI', 9))
        style.configure('Status.TLabel',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       font=('Microsoft YaHei UI', 9, 'bold'))

        # 配置 Button 样式 - 主按钮
        style.configure('Primary.TButton',
                       background=self.colors['primary'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       font=('Microsoft YaHei UI', 9, 'bold'),
                       padding=(22, 10))
        style.map('Primary.TButton',
                 background=[('active', self.colors['primary_dark']),
                           ('pressed', self.colors['primary_dark']),
                           ('disabled', '#E5E7EB')],
                 foreground=[('disabled', self.colors['text_secondary'])])

        # 配置 Button 样式 - 次要按钮
        style.configure('Secondary.TButton',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       borderwidth=1,
                       focuscolor='none',
                       font=('Microsoft YaHei UI', 9),
                       padding=(14, 7))
        style.map('Secondary.TButton',
                 background=[('active', self.colors['hover']),
                            ('pressed', self.colors['primary_light'])],
                 foreground=[('disabled', self.colors['text_secondary'])])

        # 配置 Button 样式 - 强调按钮
        style.configure('Accent.TButton',
                       background=self.colors['accent'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       font=('Microsoft YaHei UI', 9, 'bold'),
                       padding=(16, 8))
        style.map('Accent.TButton',
                 background=[('active', self.colors['accent_dark']),
                           ('pressed', self.colors['accent_dark']),
                           ('disabled', '#E5E7EB')],
                 foreground=[('disabled', 'black')])

        style.configure('Ghost.TButton',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_secondary'],
                       borderwidth=0,
                       focuscolor='none',
                       font=('Microsoft YaHei UI', 9),
                       padding=(8, 6))
        style.map('Ghost.TButton',
                 background=[('active', self.colors['hover'])],
                 foreground=[('active', self.colors['text_primary'])])

        style.configure('DangerGhost.TButton',
                       background=self.colors['bg_card'],
                       foreground=self.colors['danger'],
                       borderwidth=0,
                       focuscolor='none',
                       font=('Microsoft YaHei UI', 9),
                       padding=(8, 6))
        style.map('DangerGhost.TButton',
                 background=[('active', self.colors['danger_light'])])

        # 配置 Button 样式 - 危险按钮
        style.configure('Danger.TButton',
                       background=self.colors['danger'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       font=('Microsoft YaHei UI', 9),
                       padding=(12, 6))
        style.map('Danger.TButton',
                 background=[('active', '#DC2626'),  # 深红色悬停
                           ('pressed', '#B91C1C'),  # 更深的红色按下
                           ('disabled', '#E5E7EB')],
                 foreground=[('disabled', 'black')])

        style.configure('DangerPrimary.TButton',
                       background=self.colors['danger'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       font=('Microsoft YaHei UI', 9, 'bold'),
                       padding=(22, 10))
        style.map('DangerPrimary.TButton',
                 background=[('active', self.colors['danger_dark']),
                           ('pressed', self.colors['danger_dark']),
                           ('disabled', '#E5E7EB')],
                 foreground=[('disabled', self.colors['text_secondary'])])

        # 配置 LabelFrame 样式
        style.configure('Modern.TLabelframe',
                       background=self.colors['bg_card'],
                       borderwidth=0,
                       relief='flat')
        style.configure('Modern.TLabelframe.Label',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       font=('Microsoft YaHei UI', 10, 'bold'))

    def _enable_custom_titlebar(self):
        """启用自定义标题栏"""
        try:
            # 记录初始尺寸，避免无边框导致几何变化
            self._normal_geometry = self.root.geometry()
            self.root.after(200, self._apply_custom_titlebar)
        except Exception:
            pass

    def _apply_custom_titlebar(self):
        """应用无边框并确保窗口可见"""
        try:
            self.root.overrideredirect(True)
            self.root.update_idletasks()
            geom = self._normal_geometry or self.root.geometry()
            try:
                size_part = geom.split('+')[0]
                width, height = [int(x) for x in size_part.split('x')]
            except Exception:
                width, height = 1000, 650
            if width < 200 or height < 200:
                width, height = 1000, 650
            x = max(0, (self.root.winfo_screenwidth() - width) // 2)
            y = max(0, (self.root.winfo_screenheight() - height) // 2)
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            self.root.deiconify()
            self._ensure_window_visible()
            self._ensure_taskbar_icon()
            self._install_taskbar_toggle()
            self.root.lift()
            self.root.attributes('-topmost', True)
            self.root.after(80, lambda: self.root.attributes('-topmost', False))
        except Exception:
            try:
                self.root.overrideredirect(False)
            except Exception:
                pass

    def _get_hwnd(self):
        hwnd = self.root.winfo_id()
        parent = ctypes.windll.user32.GetParent(hwnd)
        return parent if parent else hwnd

    def _get_window_long(self, hwnd, index):
        if ctypes.sizeof(ctypes.c_void_p) == ctypes.sizeof(ctypes.c_long):
            return ctypes.windll.user32.GetWindowLongW(hwnd, index)
        fn = ctypes.windll.user32.GetWindowLongPtrW
        fn.restype = ctypes.c_void_p
        value = fn(hwnd, index)
        return value.value if isinstance(value, ctypes.c_void_p) else value

    def _set_window_long(self, hwnd, index, value):
        if ctypes.sizeof(ctypes.c_void_p) == ctypes.sizeof(ctypes.c_long):
            return ctypes.windll.user32.SetWindowLongW(hwnd, index, int(value))
        fn = ctypes.windll.user32.SetWindowLongPtrW
        fn.restype = ctypes.c_void_p
        return fn(hwnd, index, ctypes.c_void_p(int(value)))

    def _ensure_taskbar_icon(self):
        """确保无边框窗口显示在任务栏（Windows）"""
        if sys.platform != "win32":
            return
        try:
            hwnd = self._get_hwnd()
            GWL_EXSTYLE = -20
            GWL_STYLE = -16
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            WS_MINIMIZEBOX = 0x00020000
            WS_SYSMENU = 0x00080000
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            ex_style = self._get_window_long(hwnd, GWL_EXSTYLE)
            ex_style = ex_style | WS_EX_APPWINDOW
            ex_style = ex_style & ~WS_EX_TOOLWINDOW
            self._set_window_long(hwnd, GWL_EXSTYLE, ex_style)
            style = self._get_window_long(hwnd, GWL_STYLE)
            style = style | WS_MINIMIZEBOX | WS_SYSMENU
            self._set_window_long(hwnd, GWL_STYLE, style)
            if getattr(self, "app_title", None):
                try:
                    ctypes.windll.user32.SetWindowTextW(hwnd, self.app_title)
                except Exception:
                    self.root.title(self.app_title)
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                0,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
            )
            # 确保窗口处于可见状态
            self.root.state('normal')
            self.root.deiconify()
            # 初次刷新时短暂隐藏/显示以强制任务栏更新
            if not getattr(self, "_taskbar_icon_refreshed", False):
                self._taskbar_icon_refreshed = True
                self.root.withdraw()
                self.root.after(20, self.root.deiconify)
        except Exception:
            pass

    def _is_window_minimized(self):
        if sys.platform == "win32":
            try:
                return bool(ctypes.windll.user32.IsIconic(self._get_hwnd()))
            except Exception:
                return False
        return self.root.state() == "iconic"

    def _is_window_visible(self):
        if sys.platform == "win32":
            try:
                return bool(ctypes.windll.user32.IsWindowVisible(self._get_hwnd()))
            except Exception:
                return True
        return self.root.winfo_viewable()

    def _install_taskbar_toggle(self):
        """拦截任务栏点击，实现最小化/显示切换（Windows）"""
        if sys.platform != "win32" or self._win32_hook_installed:
            return
        try:
            hwnd = self._get_hwnd()

            GWL_WNDPROC = -4
            WM_SYSCOMMAND = 0x0112
            SC_MINIMIZE = 0xF020
            SC_RESTORE = 0xF120

            self._orig_wndproc = self._get_window_long(hwnd, GWL_WNDPROC)
            if not self._orig_wndproc:
                return

            @ctypes.WINFUNCTYPE(
                wintypes.LRESULT, wintypes.HWND, wintypes.UINT,
                wintypes.WPARAM, wintypes.LPARAM
            )
            def _wndproc(h, msg, wparam, lparam):
                if msg == WM_SYSCOMMAND:
                    cmd = wparam & 0xFFF0
                    if cmd in (SC_MINIMIZE, SC_RESTORE):
                        if not self._taskbar_toggle_guard:
                            self._toggle_taskbar_visibility()
                        return 0
                return ctypes.windll.user32.CallWindowProcW(
                    ctypes.c_void_p(self._orig_wndproc), h, msg, wparam, lparam
                )

            self._wndproc = _wndproc
            self._set_window_long(
                hwnd,
                GWL_WNDPROC,
                ctypes.cast(self._wndproc, ctypes.c_void_p).value
            )
            self._win32_hook_installed = True
        except Exception:
            self._win32_hook_installed = False

    def _uninstall_taskbar_toggle(self):
        if sys.platform != "win32" or not self._win32_hook_installed or not self._orig_wndproc:
            return
        try:
            hwnd = self._get_hwnd()
            GWL_WNDPROC = -4
            self._set_window_long(hwnd, GWL_WNDPROC, self._orig_wndproc)
        except Exception:
            pass
        self._win32_hook_installed = False

    def _toggle_taskbar_visibility(self):
        self._taskbar_toggle_guard = True
        try:
            if self._is_window_minimized() or not self._is_window_visible():
                self._show_window()
            else:
                self._minimize_window()
        finally:
            self.root.after(120, lambda: setattr(self, "_taskbar_toggle_guard", False))

    def _start_move(self, event):
        if self._is_maximized:
            self._toggle_maximize()
        self._drag_offset_x = event.x_root - self.root.winfo_x()
        self._drag_offset_y = event.y_root - self.root.winfo_y()

    def _on_move(self, event):
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.root.geometry(f"+{x}+{y}")

    def _minimize_window(self):
        """最小化窗口"""
        if sys.platform == "win32":
            try:
                hwnd = self.root.winfo_id()
                parent = ctypes.windll.user32.GetParent(hwnd)
                if parent:
                    hwnd = parent
                ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                try:
                    self.root.state('iconic')
                except Exception:
                    pass
                return
            except Exception:
                pass
        self.root.iconify()

    def _toggle_maximize(self, event=None):
        if self._is_maximized:
            self.root.state('normal')
            if self._normal_geometry:
                self.root.geometry(self._normal_geometry)
            self._is_maximized = False
            if getattr(self, 'max_button', None):
                self.max_button.config(text="□")
        else:
            self._normal_geometry = self.root.geometry()
            self.root.state('zoomed')
            self._is_maximized = True
            if getattr(self, 'max_button', None):
                self.max_button.config(text="❐")

    def _start_instance_server(self):
        """启动单实例通信服务器"""
        def handle_client():
            while True:
                try:
                    conn, addr = server_sock.accept()
                    # 收到连接请求，显示窗口
                    self.root.after(0, self._show_window)
                    conn.close()
                except:
                    break

        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.bind(('127.0.0.1', 59877))
            server_sock.listen(1)
            self.instance_server = server_sock

            # 在后台线程中监听连接
            threading.Thread(target=handle_client, daemon=True).start()
        except:
            pass

    def _show_window(self):
        """显示窗口并置顶"""
        self.root.deiconify()  # 显示窗口
        self._ensure_window_visible()
        self._ensure_taskbar_icon()
        self.root.lift()  # 置顶
        self.root.focus_force()  # 强制获取焦点
        self.root.attributes('-topmost', True)  # 临时置顶
        self.root.after(100, lambda: self.root.attributes('-topmost', False))  # 100ms后取消置顶

    def _ensure_window_visible(self):
        """确保窗口在屏幕可见区域内"""
        try:
            self.root.update_idletasks()
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            if width <= 1 or height <= 1:
                geom = self.root.geometry().split('+')[0]
                if 'x' in geom:
                    width, height = [int(x) for x in geom.split('x')]
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            max_x = max(0, screen_w - width)
            max_y = max(0, screen_h - height)
            if x < 0 or y < 0 or x > max_x or y > max_y:
                x = max_x // 2
                y = max_y // 2
                self.root.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass

    def _create_menu(self):
        """创建菜单"""
        # 设置菜单
        self.settings_menu = tk.Menu(self.root,
                                    tearoff=0,
                                    bg=self.colors['bg_card'],
                                    fg=self.colors['text_primary'],
                                    activebackground=self.colors['primary_light'],
                                    activeforeground=self.colors['primary'],
                                    relief='flat',
                                    borderwidth=1,
                                    font=self.menu_item_font)
        self._update_startup_menu()
        if TRAY_AVAILABLE:
            self.settings_menu.add_command(label="   最小化到托盘", command=self._minimize_to_tray)
            self.settings_menu.add_separator()
            self.settings_menu.add_command(label="   关闭按钮行为", command=self._change_close_behavior)

    def _popup_menu(self, menu, widget):
        """在按钮下方弹出菜单"""
        try:
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _show_settings_menu(self, event=None):
        """显示设置菜单"""
        self._popup_menu(self.settings_menu, self.settings_button)

    def _create_widgets(self):
        """创建主界面控件"""
        # Top app bar
        app_bar = tk.Frame(self.root, bg=self.colors['bg_header'], height=self.toolbar_height)
        app_bar.pack(fill=tk.X)
        app_bar.pack_propagate(False)
        app_bar.configure(highlightthickness=0)
        tk.Frame(app_bar, bg=self.colors['card_highlight'], height=1).pack(fill=tk.X, side=tk.TOP)
        tk.Frame(app_bar, bg=self.colors['border'], height=1).pack(fill=tk.X, side=tk.BOTTOM)

        brand_frame = tk.Frame(app_bar, bg=self.colors['bg_header'])
        brand_frame.pack(side=tk.LEFT, padx=16)

        brand_icon = tk.Label(
            brand_frame,
            text="S",
            font=('Microsoft YaHei UI', 11, 'bold'),
            bg=self.colors['accent'],
            fg='white',
            padx=6,
            pady=2
        )
        brand_icon.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(
            brand_frame,
            text="Sunny-Ngrok",
            font=('Microsoft YaHei UI', 13, 'bold'),
            bg=self.colors['bg_header'],
            fg=self.colors['text_primary']
        ).pack(side=tk.LEFT)

        tk.Label(
            brand_frame,
            text="GUI Pro",
            font=('Microsoft YaHei UI', 8, 'bold'),
            bg=self.colors['accent_light'],
            fg=self.colors['accent_dark'],
            padx=6,
            pady=2
        ).pack(side=tk.LEFT, padx=(8, 0))

        actions = tk.Frame(app_bar, bg=self.colors['bg_header'])
        actions.pack(side=tk.LEFT, padx=(10, 0))

        drag_area = tk.Frame(app_bar, bg=self.colors['bg_header'])
        drag_area.pack(side=tk.LEFT, fill=tk.X, expand=True)

        right_frame = tk.Frame(app_bar, bg=self.colors['bg_header'])
        right_frame.pack(side=tk.RIGHT, padx=8)

        def open_official_site():
            webbrowser.open("https://www.ngrok.cc/")

        use_mdl2 = sys.platform == "win32"
        if use_mdl2:
            try:
                use_mdl2 = "Segoe MDL2 Assets" in tkfont.families(self.root)
            except Exception:
                use_mdl2 = False

        def _create_toolbar_button(parent, icon_text, label_text, command):
            btn = tk.Frame(parent, bg=self.colors['button_bg'], padx=10, pady=4, cursor='hand2')
            icon = None
            if use_mdl2 and icon_text:
                icon = tk.Label(
                    btn,
                    text=icon_text,
                    font=('Segoe MDL2 Assets', 10),
                    bg=self.colors['button_bg'],
                    fg=self.colors['text_secondary']
                )
                icon.pack(side=tk.LEFT)
            label = tk.Label(
                btn,
                text=label_text,
                font=self.menu_font,
                bg=self.colors['button_bg'],
                fg=self.colors['text_primary']
            )
            label.pack(side=tk.LEFT, padx=(4, 0) if icon else (0, 0))

            def on_enter(_):
                btn.configure(bg=self.colors['hover'])
                if icon:
                    icon.configure(bg=self.colors['hover'], fg=self.colors['text_primary'])
                label.configure(bg=self.colors['hover'])

            def on_leave(_):
                btn.configure(bg=self.colors['button_bg'])
                if icon:
                    icon.configure(bg=self.colors['button_bg'], fg=self.colors['text_secondary'])
                label.configure(bg=self.colors['button_bg'])

            def on_click(_):
                command()

            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            widgets = [btn, label]
            if icon:
                widgets.append(icon)
            for widget in widgets:
                widget.bind("<Button-1>", on_click)
                widget.configure(cursor='hand2')

            return btn

        self.official_button = _create_toolbar_button(
            actions,
            "\uE774",
            "官网",
            open_official_site
        )
        self.official_button.pack(side=tk.LEFT, padx=(0, 8))

        self.settings_button = _create_toolbar_button(
            actions,
            "\uE713",
            "设置",
            self._show_settings_menu
        )
        self.settings_button.pack(side=tk.LEFT, padx=(0, 8))

        self.help_button = _create_toolbar_button(
            actions,
            "\uE897",
            "关于",
            self._show_about
        )
        self.help_button.pack(side=tk.LEFT)

        window_controls = tk.Frame(right_frame, bg=self.colors['bg_header'])
        window_controls.pack(side=tk.RIGHT)

        self.min_button = tk.Button(
            window_controls,
            text="—",
            command=self._minimize_window,
            font=('Segoe UI', 9),
            bg=self.colors['bg_header'],
            fg=self.colors['titlebar_glyph'],
            activebackground=self.colors['titlebar_btn_hover'],
            activeforeground=self.colors['titlebar_glyph'],
            relief='flat',
            bd=0,
            highlightthickness=0,
            width=2,
            height=1,
            cursor='hand2'
        )
        self.min_button.pack(side=tk.LEFT, padx=3)
        self.min_button.bind('<Enter>', lambda e: self.min_button.config(bg=self.colors['titlebar_btn_hover']))
        self.min_button.bind('<Leave>', lambda e: self.min_button.config(bg=self.colors['bg_header']))

        self.max_button = tk.Button(
            window_controls,
            text="□",
            command=self._toggle_maximize,
            font=('Segoe UI', 11),
            bg=self.colors['bg_header'],
            fg=self.colors['titlebar_glyph'],
            activebackground=self.colors['titlebar_btn_hover'],
            activeforeground=self.colors['titlebar_glyph'],
            relief='flat',
            bd=0,
            highlightthickness=0,
            width=2,
            height=1,
            cursor='hand2'
        )
        self.max_button.pack(side=tk.LEFT, padx=3)
        self.max_button.bind('<Enter>', lambda e: self.max_button.config(bg=self.colors['titlebar_btn_hover']))
        self.max_button.bind('<Leave>', lambda e: self.max_button.config(bg=self.colors['bg_header']))

        self.close_button = tk.Button(
            window_controls,
            text="×",
            command=self._on_closing,
            font=('Segoe UI', 13),
            bg=self.colors['bg_header'],
            fg=self.colors['titlebar_glyph'],
            activebackground=self.colors['titlebar_close_hover'],
            activeforeground='white',
            relief='flat',
            bd=0,
            highlightthickness=0,
            width=2,
            height=1,
            cursor='hand2'
        )
        self.close_button.pack(side=tk.LEFT, padx=3)
        self.close_button.bind('<Enter>', lambda e: self.close_button.config(bg=self.colors['titlebar_close_hover']))
        self.close_button.bind('<Leave>', lambda e: self.close_button.config(bg=self.colors['bg_header']))

        drag_widgets = [app_bar, drag_area, brand_frame, brand_icon]
        for widget in drag_widgets:
            widget.bind('<ButtonPress-1>', self._start_move)
            widget.bind('<B1-Motion>', self._on_move)
            widget.bind('<Double-Button-1>', self._toggle_maximize)

        main_container = tk.Frame(self.root, bg=self.colors['bg_main'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # 创建左右分栏布局
        # 左侧面板 - 隧道列表
        left_panel = tk.Frame(main_container, bg=self.colors['bg_main'], width=280)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 4), pady=(0, 0))
        left_panel.pack_propagate(False)

        # 左侧卡片容器
        left_shell = tk.Frame(left_panel, bg=self.colors['card_shadow'])
        left_shell.pack(fill=tk.BOTH, expand=True)

        left_card = tk.Frame(left_shell, bg=self.colors['bg_card'], relief='flat', bd=0)
        left_card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        tk.Frame(left_card, bg=self.colors['card_highlight'], height=1).pack(fill=tk.X, side=tk.TOP)

        # 隧道列表标题区域
        header_frame = tk.Frame(left_card, bg=self.colors['bg_card'], height=48)
        header_frame.pack(fill=tk.X, padx=16, pady=(16, 10))
        header_frame.pack_propagate(False)

        title_label = tk.Label(
            header_frame,
            text="我的隧道",
            font=('Microsoft YaHei UI', 11, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary']
        )
        title_label.pack(side=tk.LEFT, anchor='w')

        self.add_button = tk.Button(
            header_frame,
            text="+",
            command=self._add_tunnel,
            font=('Microsoft YaHei UI', 12, 'bold'),
            bg=self.colors['accent'],
            fg='white',
            activebackground=self.colors['accent_dark'],
            activeforeground='white',
            relief='flat',
            borderwidth=0,
            highlightthickness=0,
            padx=6,
            pady=0,
            cursor='hand2'
        )
        self.add_button.pack(side=tk.RIGHT)

        # 隧道列表容器 - 使用Canvas和Scrollbar实现可滚动的卡片列表
        list_container = tk.Frame(left_card, bg=self.colors['bg_list'])
        list_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        # 创建Canvas和Scrollbar
        self.tunnel_canvas = tk.Canvas(
            list_container,
            bg=self.colors['bg_list'],
            highlightthickness=0,
            bd=0
        )
        self.tunnel_scrollbar = tk.Scrollbar(list_container, command=self.tunnel_canvas.yview, width=12)
        self.tunnel_list_frame = tk.Frame(self.tunnel_canvas, bg=self.colors['bg_list'])

        # 配置Canvas
        self.tunnel_canvas.configure(yscrollcommand=self.tunnel_scrollbar.set)

        # 布局Canvas（滚动条初始不显示）
        self.tunnel_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 在Canvas中创建窗口
        self.canvas_frame = self.tunnel_canvas.create_window(
            (0, 0),
            window=self.tunnel_list_frame,
            anchor='nw'
        )

        # 绑定配置事件以更新滚动区域
        self.tunnel_list_frame.bind('<Configure>', self._on_frame_configure)
        self.tunnel_canvas.bind('<Configure>', self._on_canvas_configure)

        # 绑定鼠标滚轮事件到canvas和list_frame
        self.tunnel_canvas.bind('<MouseWheel>', self._on_mousewheel)
        self.tunnel_canvas.bind('<Button-4>', self._on_mousewheel)  # Linux向上滚动
        self.tunnel_canvas.bind('<Button-5>', self._on_mousewheel)  # Linux向下滚动
        self.tunnel_list_frame.bind('<MouseWheel>', self._on_mousewheel)
        self.tunnel_list_frame.bind('<Button-4>', self._on_mousewheel)
        self.tunnel_list_frame.bind('<Button-5>', self._on_mousewheel)

        # 存储卡片引用
        self.tunnel_cards = []

        # 按钮区域
        button_frame = tk.Frame(left_card, bg=self.colors['bg_card'])
        button_frame.pack(fill=tk.X, padx=16, pady=(6, 16))

        btn_row = tk.Frame(button_frame, bg=self.colors['bg_card'])
        btn_row.pack(fill=tk.X)
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)

        edit_shadow = tk.Frame(btn_row, bg=self.colors['button_shadow'])
        edit_shadow.grid(row=0, column=0, sticky='ew', padx=(0, 6))
        edit_btn = tk.Button(
            edit_shadow,
            text="编辑",
            command=self._edit_tunnel,
            font=('Microsoft YaHei UI', 9, 'bold'),
            bg=self.colors['button_bg'],
            fg=self.colors['text_primary'],
            activebackground=self.colors['hover'],
            activeforeground=self.colors['text_primary'],
            relief='flat',
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=6,
            cursor='hand2'
        )
        edit_btn.pack(fill=tk.X, padx=1, pady=1)

        delete_shadow = tk.Frame(btn_row, bg=self.colors['button_shadow'])
        delete_shadow.grid(row=0, column=1, sticky='ew', padx=(6, 0))
        delete_btn = tk.Button(
            delete_shadow,
            text="删除",
            command=self._delete_tunnel,
            font=('Microsoft YaHei UI', 9, 'bold'),
            bg=self.colors['button_danger_bg'],
            fg=self.colors['danger'],
            activebackground=self.colors['danger_light'],
            activeforeground=self.colors['danger'],
            relief='flat',
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=6,
            cursor='hand2'
        )
        delete_btn.pack(fill=tk.X, padx=1, pady=1)

        # 右侧面板 - 控制和日志
        right_panel = tk.Frame(main_container, bg=self.colors['bg_main'])
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 0), pady=(0, 0))

        # 控制区域卡片
        control_shell = tk.Frame(right_panel, bg=self.colors['card_shadow'])
        control_shell.pack(fill=tk.X, pady=(0, 4))

        control_card = tk.Frame(control_shell, bg=self.colors['bg_card'], relief='flat', bd=0)
        control_card.pack(fill=tk.X, padx=1, pady=1)
        tk.Frame(control_card, bg=self.colors['card_highlight'], height=1).pack(fill=tk.X, side=tk.TOP)

        # 控制区域标题
        control_header = tk.Frame(control_card, bg=self.colors['bg_card'])
        control_header.pack(fill=tk.X, padx=20, pady=(18, 12))

        title_group = tk.Frame(control_header, bg=self.colors['bg_card'])
        title_group.pack(side=tk.LEFT, fill=tk.X, expand=True)

        title_row = tk.Frame(title_group, bg=self.colors['bg_card'])
        title_row.pack(anchor='w')

        self.current_tunnel_label = tk.Label(
            title_row,
            text="\u672a\u9009\u62e9",
            font=('Microsoft YaHei UI', 14, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary']
        )
        self.current_tunnel_label.pack(side=tk.LEFT)

        self.protocol_badge = tk.Label(
            title_row,
            text="HTTP/TCP",
            font=('Microsoft YaHei UI', 8, 'bold'),
            bg=self.colors['neutral_bg'],
            fg=self.colors['text_secondary'],
            padx=8,
            pady=2
        )
        self.protocol_badge.pack(side=tk.LEFT, padx=(8, 0))

        control_actions = tk.Frame(control_header, bg=self.colors['bg_card'])
        control_actions.pack(side=tk.RIGHT)

        self.start_button = ttk.Button(
            control_actions,
            text="启动隧道",
            command=self._start_tunnel,
            style='Primary.TButton',
            state=tk.DISABLED
        )
        self.start_button.pack(side=tk.RIGHT)

        self.stop_button = ttk.Button(
            control_actions,
            text="停止隧道",
            command=self._stop_tunnel,
            style='DangerPrimary.TButton',
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.RIGHT)
        self.stop_button.pack_forget()

        # 状态信息行
        status_frame = tk.Frame(control_card, bg=self.colors['bg_card'])
        status_frame.pack(fill=tk.X, padx=20, pady=(0, 18))

        address_group = tk.Frame(status_frame, bg=self.colors['bg_card'])
        address_group.pack(side=tk.LEFT, padx=(0, 24))

        tk.Label(
            address_group,
            text="地址:",
            font=('Microsoft YaHei UI', 9),
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary']
        ).pack(side=tk.LEFT)

        self.address_label = tk.Label(
            address_group,
            text="--",
            font=('Microsoft YaHei UI', 9, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary']
        )
        self.address_label.pack(side=tk.LEFT, padx=(6, 0))

        status_group = tk.Frame(status_frame, bg=self.colors['bg_card'])
        status_group.pack(side=tk.LEFT)

        tk.Label(
            status_group,
            text="状态:",
            font=('Microsoft YaHei UI', 9),
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary']
        ).pack(side=tk.LEFT)

        self.status_dot = tk.Canvas(
            status_group,
            width=8,
            height=8,
            bg=self.colors['bg_card'],
            highlightthickness=0
        )
        self.status_dot.pack(side=tk.LEFT, padx=(6, 6))
        self.status_dot_id = self.status_dot.create_oval(
            0, 0, 8, 8,
            fill=self.colors['status_off'],
            outline=self.colors['status_off']
        )

        self.status_label = tk.Label(
            status_group,
            text="\u672a\u8fd0\u884c",
            font=('Microsoft YaHei UI', 8, 'bold'),
            bg=self.colors['neutral_bg'],
            fg=self.colors['text_secondary'],
            padx=8,
            pady=2
        )
        self.status_label.pack(side=tk.LEFT)
        self._sync_control_cursors()

        # 日志区域卡片
        log_shell = tk.Frame(right_panel, bg=self.colors['card_shadow'])
        log_shell.pack(fill=tk.BOTH, expand=True)

        log_card = tk.Frame(log_shell, bg=self.colors['bg_card'], relief='flat', bd=0)
        log_card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        tk.Frame(log_card, bg=self.colors['card_highlight'], height=1).pack(fill=tk.X, side=tk.TOP)

        terminal_frame = tk.Frame(log_card, bg=self.colors['terminal_bg'], bd=0)
        terminal_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        terminal_header = tk.Frame(terminal_frame, bg=self.colors['terminal_header'], height=34)
        terminal_header.pack(fill=tk.X)
        terminal_header.pack_propagate(False)

        dots = tk.Frame(terminal_header, bg=self.colors['terminal_header'])
        dots.pack(side=tk.LEFT, padx=10)
        for dot_color in ['#FF5F56', '#FFBD2E', '#27C93F']:
            dot = tk.Canvas(dots, width=8, height=8, bg=self.colors['terminal_header'], highlightthickness=0)
            dot.create_oval(0, 0, 8, 8, fill=dot_color, outline=dot_color)
            dot.pack(side=tk.LEFT, padx=3)

        tk.Label(
            terminal_header,
            text="Terminal Output",
            font=('Consolas', 9, 'bold'),
            bg=self.colors['terminal_header'],
            fg=self.colors['terminal_text']
        ).pack(side=tk.LEFT, padx=(6, 0))

        clear_log_btn = tk.Button(
            terminal_header,
            text="\u6e05\u7a7a",
            command=self._clear_log,
            font=('Microsoft YaHei UI', 9),
            bg=self.colors['terminal_header'],
            fg=self.colors['terminal_text'],
            activebackground=self.colors['terminal_bg'],
            activeforeground=self.colors['terminal_text'],
            relief='flat',
            borderwidth=0,
            padx=8,
            pady=2,
            cursor='hand2'
        )
        clear_log_btn.pack(side=tk.RIGHT, padx=10)

        log_container = tk.Frame(terminal_frame, bg=self.colors['terminal_bg'])
        log_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_container,
            wrap=tk.WORD,
            font=('Consolas', 9),
            bg=self.colors['terminal_bg'],
            fg=self.colors['terminal_text'],
            insertbackground=self.colors['terminal_text'],
            relief='flat',
            bd=0,
            state=tk.DISABLED,
            highlightthickness=1,
            highlightbackground=self.colors['terminal_border']
        )
        self.log_scrollbar = tk.Scrollbar(
            log_container,
            orient=tk.VERTICAL,
            command=self.log_text.yview,
            bg=self.colors['terminal_border'],
            activebackground=self.colors['terminal_border'],
            troughcolor=self.colors['terminal_bg'],
            relief='flat',
            bd=0,
            highlightthickness=0,
            width=10
        )
        self.log_text.configure(yscrollcommand=self.log_scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # 隐藏滚动条（保留滚动能力）

    def _on_frame_configure(self, event=None):
        """更新Canvas滚动区域并控制滚动条显示"""
        self.tunnel_canvas.configure(scrollregion=self.tunnel_canvas.bbox('all'))

        # 使用after确保在布局完成后检查
        self.root.after(10, self._check_scrollbar_needed)

    def _check_scrollbar_needed(self):
        """检查是否需要显示滚动条"""
        try:
            # 获取内容区域和可见区域的高度
            bbox = self.tunnel_canvas.bbox('all')
            canvas_height = self.tunnel_canvas.winfo_height()

            # 如果canvas高度为0或1，说明还没有完成布局，稍后再试
            if canvas_height <= 1:
                self.root.after(50, self._check_scrollbar_needed)
                return

            if bbox and bbox[3] > canvas_height:
                # 内容超过可见区域，显示滚动条
                if not self.tunnel_scrollbar.winfo_ismapped():
                    self.tunnel_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
                    # 重新调整canvas宽度
                    self.tunnel_canvas.pack_forget()
                    self.tunnel_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            else:
                # 内容未超过可见区域，隐藏滚动条
                if self.tunnel_scrollbar.winfo_ismapped():
                    self.tunnel_scrollbar.pack_forget()
                    # 重新调整canvas宽度
                    self.tunnel_canvas.pack_forget()
                    self.tunnel_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        except:
            pass

    def _on_canvas_configure(self, event):
        """调整Canvas内部窗口宽度"""
        canvas_width = event.width
        self.tunnel_canvas.itemconfig(self.canvas_frame, width=canvas_width)
        # 重新检查是否需要滚动条
        self.root.after(10, self._check_scrollbar_needed)

    def _on_mousewheel(self, event):
        """处理鼠标滚轮事件"""
        # 只在滚动条显示时才允许滚动
        if not self.tunnel_scrollbar.winfo_ismapped():
            return

        # Windows和MacOS
        if event.num == 4 or event.delta > 0:
            self.tunnel_canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.tunnel_canvas.yview_scroll(1, "units")

    def _set_card_selected(self, card, selected):
        bg = self.colors['card_selected'] if selected else self.colors['bg_card']
        border = self.colors['accent'] if selected else self.colors['border']
        thickness = 2 if selected else 1

        card.configure(bg=bg, highlightbackground=border, highlightthickness=thickness)
        if getattr(card, 'accent_bar', None):
            card.accent_bar.configure(bg=self.colors['accent'] if selected else bg)
        for widget in getattr(card, 'bg_widgets', []):
            try:
                widget.configure(bg=bg)
            except tk.TclError:
                pass

        if getattr(card, 'name_label', None):
            card.name_label.configure(
                fg=self.colors['text_primary']
            )

    def _set_card_hover(self, card, hovering):
        if self.current_tunnel_index == getattr(card, 'index', None):
            return

        bg = self.colors['card_hover'] if hovering else self.colors['bg_card']
        border = self.colors['accent'] if hovering else self.colors['border']
        card.configure(bg=bg, highlightbackground=border, highlightthickness=1)
        if getattr(card, 'accent_bar', None):
            card.accent_bar.configure(bg=self.colors['accent'] if hovering else bg)
        for widget in getattr(card, 'bg_widgets', []):
            try:
                widget.configure(bg=bg)
            except tk.TclError:
                pass

    def _set_button_cursor(self, button, enabled):
        button.configure(cursor='hand2' if enabled else 'no')

    def _sync_control_cursors(self):
        self._set_button_cursor(self.start_button, self._is_button_enabled(self.start_button))
        self._set_button_cursor(self.stop_button, self._is_button_enabled(self.stop_button))

    def _is_button_enabled(self, button):
        if hasattr(button, 'instate'):
            return button.instate(['!disabled'])
        return str(button.cget('state')) != 'disabled'

    def _set_status_badge(self, is_running):
        if is_running:
            self.status_label.config(
                text="运行中",
                bg=self.colors['success_bg'],
                fg=self.colors['success']
            )
            if getattr(self, 'status_dot', None):
                self.status_dot.itemconfig(
                    self.status_dot_id,
                    fill=self.colors['success'],
                    outline=self.colors['success']
                )
        else:
            self.status_label.config(
                text="未运行",
                bg=self.colors['neutral_bg'],
                fg=self.colors['text_secondary']
            )
            if getattr(self, 'status_dot', None):
                self.status_dot.itemconfig(
                    self.status_dot_id,
                    fill=self.colors['status_off'],
                    outline=self.colors['status_off']
                )

    def _sync_control_buttons(self, is_running, enabled=True):
        if not enabled:
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.DISABLED)
            self.stop_button.pack_forget()
            self.start_button.pack(side=tk.RIGHT)
            return

        if is_running:
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.start_button.pack_forget()
            self.stop_button.pack(side=tk.RIGHT)
        else:
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.stop_button.pack_forget()
            self.start_button.pack(side=tk.RIGHT)

    def _create_tunnel_card(self, tunnel, index, is_running):
        card = tk.Frame(
            self.tunnel_list_frame,
            bg=self.colors['bg_card'],
            relief='flat',
            bd=0,
            cursor='hand2'
        )
        card.pack(fill=tk.X, pady=6)
        card.configure(
            highlightbackground=self.colors['border'],
            highlightthickness=1
        )
        card.index = index

        accent_bar = tk.Frame(card, bg=self.colors['bg_card'], width=4)
        accent_bar.pack(side=tk.LEFT, fill=tk.Y)

        content = tk.Frame(card, bg=self.colors['bg_card'])
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=12, pady=8)

        name_row = tk.Frame(content, bg=self.colors['bg_card'])
        name_row.pack(fill=tk.X)

        name_label = tk.Label(
            name_row,
            text=tunnel['name'],
            font=('Microsoft YaHei UI', 10, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary'],
            anchor='w'
        )
        name_label.pack(side=tk.LEFT)

        status_dot = tk.Canvas(
            name_row,
            width=8,
            height=8,
            bg=self.colors['bg_card'],
            highlightthickness=0
        )
        dot_color = self.colors['success'] if is_running else self.colors['status_off']
        status_dot_id = status_dot.create_oval(0, 0, 8, 8, fill=dot_color, outline=dot_color)
        status_dot.pack(side=tk.RIGHT)

        info_row = tk.Frame(content, bg=self.colors['bg_card'])
        info_row.pack(fill=tk.X, pady=(6, 0))

        server_label = tk.Label(
            info_row,
            text=tunnel['server'],
            font=('Microsoft YaHei UI', 8),
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary'],
            anchor='w'
        )
        server_label.pack(side=tk.LEFT)

        auto_start_enabled = tunnel.get('auto_start', False)
        if auto_start_enabled:
            auto_label = tk.Label(
                info_row,
                text="自动启动",
                font=('Microsoft YaHei UI', 7, 'bold'),
                bg=self.colors['accent_light'],
                fg=self.colors['accent'],
                padx=6,
                pady=1
            )
            auto_label.pack(side=tk.RIGHT)

        def on_click(event):
            self._select_tunnel_card(index)

        widgets = [card, accent_bar, content, name_row, name_label, info_row, server_label, status_dot]
        if auto_start_enabled:
            widgets.append(auto_label)

        for widget in widgets:
            widget.bind('<Button-1>', on_click)
            widget.bind('<MouseWheel>', self._on_mousewheel)
            widget.bind('<Button-4>', self._on_mousewheel)
            widget.bind('<Button-5>', self._on_mousewheel)

        def on_enter(event):
            self._set_card_hover(card, True)

        def on_leave(event):
            self._set_card_hover(card, False)

        card.bind('<Enter>', on_enter)
        card.bind('<Leave>', on_leave)

        card.bg_widgets = [content, name_row, info_row, name_label, server_label, status_dot]
        card.name_label = name_label
        card.accent_bar = accent_bar
        card.dot_canvas = status_dot
        card.dot_id = status_dot_id

        return card

    def _select_tunnel_card(self, index):
        if self.current_tunnel_index is not None and self.current_tunnel_index < len(self.tunnel_cards):
            old_card = self.tunnel_cards[self.current_tunnel_index]
            self._set_card_selected(old_card, False)

        self.current_tunnel_index = index
        self.last_selected_index = index
        self._save_last_selection()

        if index < len(self.tunnel_cards):
            card = self.tunnel_cards[index]
            self._set_card_selected(card, True)

        tunnel = self.config.get(index)
        if tunnel:
            self.current_tunnel_label.config(text=tunnel['name'], fg=self.colors['text_primary'])
            self.address_label.config(text=tunnel.get('server', '--'), fg=self.colors['text_secondary'])
            tunnel_id = tunnel.get("id")
            is_running = (tunnel_id in self.tunnel_processes and
                         self.tunnel_processes[tunnel_id].is_running())

            self._set_status_badge(is_running)
            self._sync_control_buttons(is_running, enabled=True)
            self._sync_control_cursors()
            self._display_tunnel_logs()

    def _load_tunnels(self):
        """加载隧道列表"""
        # 清空现有卡片
        for card in self.tunnel_cards:
            card.destroy()
        self.tunnel_cards = []

        # 创建新卡片
        for i, tunnel in enumerate(self.config.get_all()):
            tunnel_id = tunnel.get("id")
            is_running = tunnel_id in self.tunnel_processes and self.tunnel_processes[tunnel_id].is_running()
            card = self._create_tunnel_card(tunnel, i, is_running)
            self.tunnel_cards.append(card)

        # 更新滚动区域
        self.tunnel_list_frame.update_idletasks()
        self.tunnel_canvas.configure(scrollregion=self.tunnel_canvas.bbox('all'))

        # 延迟检查滚动条显示（确保布局完成）
        self.root.after(100, self._on_frame_configure)

    def _display_tunnel_logs(self):
        """显示当前选中隧道的日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)

        if self.current_tunnel_index is not None:
            tunnel = self.config.get(self.current_tunnel_index)
            tunnel_id = tunnel.get("id") if tunnel else None
            if tunnel_id in self.tunnel_processes:
                logs = self.tunnel_processes[tunnel_id].get_logs()
                if len(logs) > LOG_MAX_LINES:
                    logs = logs[-LOG_MAX_LINES:]
                if logs:
                    self.log_text.insert(tk.END, "".join(
                        f"[{timestamp}] {log}\n" for timestamp, log in logs
                    ))
                    self.log_text.see(tk.END)

        self.log_text.config(state=tk.DISABLED)

    def _save_last_selection(self):
        try:
            with open(self.last_selection_file, 'w', encoding='utf-8') as f:
                f.write(str(self.last_selected_index))
        except Exception:
            pass

    def _restore_last_selection(self):
        try:
            if os.path.exists(self.last_selection_file):
                with open(self.last_selection_file, 'r', encoding='utf-8') as f:
                    index = int(f.read().strip())
                    if 0 <= index < len(self.config.get_all()):
                        self._select_tunnel_card(index)
        except Exception:
            pass

    def _update_tunnel_status(self):
        if self.current_tunnel_index is None:
            return

        tunnel = self.config.get(self.current_tunnel_index)
        tunnel_id = tunnel.get("id") if tunnel else None
        is_running = (tunnel_id in self.tunnel_processes and
                     self.tunnel_processes[tunnel_id].is_running())

        self._set_status_badge(is_running)
        self._sync_control_buttons(is_running, enabled=True)
        self._sync_control_cursors()

    def _add_tunnel(self):
        dialog = TunnelDialog(self.root, "新增隧道")
        self.root.wait_window(dialog)

        if dialog.result:
            self.config.add(
                dialog.result['name'],
                dialog.result['server'],
                dialog.result['key'],
                dialog.result['auto_start']
            )
            self._load_tunnels()
            self._log_system("新增隧道: " + dialog.result['name'])


    def _edit_tunnel(self):
        """编辑隧道"""
        if self.current_tunnel_index is None:
            messagebox.showwarning("警告", "请先选择一个隧道")
            return

        # 保存当前索引，防止对话框打开时失去焦点导致索引被清空
        edit_index = self.current_tunnel_index

        tunnel = self.config.get(edit_index)
        if not tunnel:
            return

        dialog = TunnelDialog(self.root, "编辑隧道", tunnel)
        self.root.wait_window(dialog)

        if dialog.result:
            success = self.config.update(
                edit_index,  # 使用保存的索引
                dialog.result['name'],
                dialog.result['server'],
                dialog.result['key'],
                dialog.result['auto_start']
            )

            if success:
                # 恢复索引
                self.current_tunnel_index = edit_index
                self._load_tunnels()
                self._restore_selection_after_reload()  # 恢复选中状态
                self._log_system("更新隧道: " + dialog.result['name'])
            else:
                messagebox.showerror("错误", "保存配置失败")

    def _delete_tunnel(self):
        """删除隧道"""
        if self.current_tunnel_index is None:
            messagebox.showwarning("警告", "请先选择一个隧道")
            return

        tunnel = self.config.get(self.current_tunnel_index)
        if not tunnel:
            return

        if messagebox.askyesno("确认", f"确定要删除隧道 '{tunnel['name']}' 吗？"):
            # 如果隧道正在运行，先停止
            tunnel_id = tunnel.get("id")
            if tunnel_id in self.tunnel_processes:
                process = self.tunnel_processes[tunnel_id]
                if process.is_running():
                    process.stop()
                del self.tunnel_processes[tunnel_id]

            self.config.delete(self.current_tunnel_index)
            self._load_tunnels()
            self.current_tunnel_index = None
            self.current_tunnel_label.config(text="\u672a\u9009\u62e9", fg=self.colors['text_primary'])
            self.address_label.config(text="--", fg=self.colors['text_secondary'])
            self._set_status_badge(False)
            self._sync_control_buttons(False, enabled=False)
            self._sync_control_cursors()
            self._log_system("删除隧道: " + tunnel['name'])

    def _start_tunnel(self):
        if self.current_tunnel_index is None:
            return

        ready_state = ensure_sunny_ready(self.root)
        if ready_state != "ready":
            if ready_state == "cancel":
                self._quit_application()
            return

        tunnel = self.config.get(self.current_tunnel_index)
        if not tunnel:
            return

        tunnel_id = tunnel.get("id")
        if (tunnel_id in self.tunnel_processes and
            self.tunnel_processes[tunnel_id].is_running()):
            messagebox.showwarning("提示", "隧道已经在运行")
            return

        process = TunnelProcess(tunnel_id, tunnel['name'])
        self.tunnel_processes[tunnel_id] = process

        self._log_to_tunnel(tunnel_id, f"开始启动隧道: {tunnel['name']}")
        self._log_to_tunnel(tunnel_id, f"服务器: {tunnel['server']}")
        self._log_to_tunnel(tunnel_id, f"密钥: {tunnel['key']}")

        success, message = process.start(
            tunnel['server'],
            tunnel['key'],
            lambda msg, tid=tunnel_id: self._on_tunnel_log(tid, msg)
        )

        if success:
            self._set_status_badge(True)
            self._sync_control_buttons(True, enabled=True)
            self._log_to_tunnel(tunnel_id, message)
            self._load_tunnels()
            self._restore_selection_after_reload()
            self._sync_control_cursors()
        else:
            self._set_status_badge(False)
            self._sync_control_buttons(False, enabled=True)
            self._log_to_tunnel(tunnel_id, f"错误: {message}")
            messagebox.showerror("错误", message)
            self._sync_control_cursors()

    def _stop_tunnel(self):
        if self.current_tunnel_index is None:
            return

        tunnel = self.config.get(self.current_tunnel_index)
        tunnel_id = tunnel.get("id") if tunnel else None
        if tunnel_id not in self.tunnel_processes:
            return

        process = self.tunnel_processes[tunnel_id]
        if not process.is_running():
            return

        self._log_to_tunnel(tunnel_id, "正在停止隧道...")
        success, message = process.stop()

        self._set_status_badge(False)
        self._sync_control_buttons(False, enabled=True)
        self._log_to_tunnel(tunnel_id, message)
        self._load_tunnels()
        self._restore_selection_after_reload()
        self._sync_control_cursors()

    def _restore_selection_after_reload(self):
        if self.current_tunnel_index is not None and self.current_tunnel_index < len(self.tunnel_cards):
            card = self.tunnel_cards[self.current_tunnel_index]
            self._set_card_selected(card, True)

    def _drain_log_queue(self):
        try:
            count = 0
            while count < LOG_DRAIN_BATCH:
                tunnel_id, timestamp, message = self.log_queue.get_nowait()
                self._log_to_tunnel(tunnel_id, message, timestamp)
                count += 1
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log_queue)

    def _append_log_text(self, log_message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_message)
        self._trim_log_text()
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _trim_log_text(self):
        line_count = int(self.log_text.index('end-1c').split('.')[0])
        overflow = line_count - LOG_MAX_LINES
        if overflow > 0:
            self.log_text.delete('1.0', f'{overflow + 1}.0')

    def _on_tunnel_log(self, tunnel_id, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put((tunnel_id, timestamp, message))

    def _log_to_tunnel(self, tunnel_id, message, timestamp=None):
        """记录日志到指定隧道"""
        if timestamp is None:
            timestamp = datetime.now().strftime("%H:%M:%S")

        process = self.tunnel_processes.get(tunnel_id)
        if process:
            process.add_log(message, timestamp)

        current_tunnel_id = None
        if self.current_tunnel_index is not None:
            tunnel = self.config.get(self.current_tunnel_index)
            current_tunnel_id = tunnel.get("id") if tunnel else None

        # 如果是当前选中的隧道，实时显示
        if tunnel_id == current_tunnel_id:
            log_message = f"[{timestamp}] {message}\n"
            self._append_log_text(log_message)

    def _clear_log(self):
        """清空当前隧道的日志"""
        tunnel_id = None
        if self.current_tunnel_index is not None:
            tunnel = self.config.get(self.current_tunnel_index)
            tunnel_id = tunnel.get("id") if tunnel else None
        if tunnel_id in self.tunnel_processes:
            self.tunnel_processes[tunnel_id].clear_logs()

        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _auto_start_tunnels(self):
        """自动启动标记为自启的隧道"""
        if not os.path.exists(get_sunny_exe_path()):
            self._log_system("缺少 core\\sunny.exe，已跳过自动启动。")
            return

        auto_indexes = [
            i for i, tunnel in enumerate(self.config.get_all())
            if tunnel.get('auto_start', False)
        ]

        if not auto_indexes:
            return

        def start_next(pos=0):
            if pos >= len(auto_indexes):
                return
            i = auto_indexes[pos]
            if 0 <= i < len(self.config.get_all()):
                tunnel = self.config.get(i)
                if tunnel:
                    tunnel_id = tunnel.get("id")
                    self._select_tunnel_card(i)
                    self._log_to_tunnel(tunnel_id, f"自动启动隧道: {tunnel['name']}")
                    self._start_tunnel()
            self.root.after(200, lambda: start_next(pos + 1))

        self.root.after(200, lambda: start_next(0))

    def _toggle_startup(self):
        """切换开机自启动"""
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            app_name = "SunnyNgrokGUI"

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)

            try:
                winreg.QueryValueEx(key, app_name)
                # 已存在，删除
                winreg.DeleteValue(key, app_name)
                winreg.CloseKey(key)
                self._update_startup_menu()
                messagebox.showinfo("成功", "已取消开机自启动")
                self._log_system("已取消开机自启动")
            except FileNotFoundError:
                # 不存在，添加
                exe_path = os.path.abspath(sys.argv[0])
                if exe_path.endswith('.py'):
                    # Python脚本，使用pythonw启动
                    python_path = sys.executable.replace('python.exe', 'pythonw.exe')
                    exe_path = f'"{python_path}" "{exe_path}"'
                else:
                    # 已打包的exe
                    exe_path = f'"{exe_path}"'

                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
                winreg.CloseKey(key)
                self._update_startup_menu()
                messagebox.showinfo("成功", "已设置开机自启动")
                self._log_system("已设置开机自启动")

        except Exception as e:
            messagebox.showerror("错误", f"设置失败: {str(e)}")
            self._log_system(f"开机自启动设置失败: {str(e)}")

    def _check_startup_enabled(self):
        """检查是否已设置开机自启动"""
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            app_name = "SunnyNgrokGUI"

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, app_name)
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        except Exception:
            return False

    def _update_startup_menu(self):
        """更新开机自启动菜单项的显示"""
        if self.settings_menu is None:
            return

        # 清除现有的开机自启动菜单项
        self.settings_menu.delete(0)

        # 根据当前状态添加菜单项
        if self._check_startup_enabled():
            self.settings_menu.insert_command(0, label="   ✅ 开机自启动", command=self._toggle_startup)
        else:
            self.settings_menu.insert_command(0, label="   ⬜ 开机自启动", command=self._toggle_startup)

    def _minimize_to_tray(self):
        """最小化到系统托盘"""
        if not TRAY_AVAILABLE:
            messagebox.showinfo("提示", "系统托盘功能需要安装 pystray 和 Pillow\n运行: pip install pystray Pillow")
            return

        self.root.withdraw()

        if not self.tray_icon:
            # 创建托盘图标
            def create_image():
                width = 64
                height = 64
                image = Image.new('RGB', (width, height), color='white')
                dc = ImageDraw.Draw(image)
                dc.rectangle([0, 0, width, height], fill='#4CAF50')
                dc.text((10, 20), 'SN', fill='white')
                return image

            def on_quit(icon, item):
                icon.stop()
                self._quit_application()

            def on_show(icon, item):
                self.root.after(0, self._show_window)

            menu = pystray.Menu(
                pystray.MenuItem('显示窗口', on_show, default=True),
                pystray.MenuItem('退出', on_quit)
            )

            self.tray_icon = pystray.Icon(
                "SunnyNgrok",
                create_image(),
                "Sunny-Ngrok 管理器",
                menu
            )

            # 在新线程中运行托盘图标
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _change_close_behavior(self):
        """修改关闭按钮行为设置"""
        # 创建设置对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("关闭按钮行为设置")
        dialog.geometry("400x340")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=self.colors['bg_main'])

        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        # 主卡片
        card = tk.Frame(dialog, bg=self.colors['bg_card'], relief='flat', bd=0)
        card.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        card.configure(highlightbackground=self.colors['border'], highlightthickness=1)

        # 内容区域
        content = tk.Frame(card, bg=self.colors['bg_card'])
        content.pack(fill=tk.BOTH, expand=True, padx=25, pady=25)

        # 提示文本
        tk.Label(
            content,
            text="点击窗口关闭按钮时：",
            font=('Microsoft YaHei UI', 11, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary']
        ).pack(anchor='w', pady=(0, 20))

        # 获取当前设置
        current_behavior = self.settings.get("close_behavior")

        # 单选按钮变量
        behavior_var = tk.StringVar(value=current_behavior if current_behavior else "ask")

        # 单选按钮区域
        radio_frame = tk.Frame(content, bg=self.colors['bg_card'])
        radio_frame.pack(fill=tk.X, pady=5)

        # 创建现代化单选按钮
        options = [
            ("ask", "每次询问"),
            ("minimize", "最小化到托盘"),
            ("exit", "直接退出程序")
        ]

        for value, text in options:
            rb = tk.Radiobutton(
                radio_frame,
                text=text,
                variable=behavior_var,
                value=value,
                font=('Microsoft YaHei UI', 10),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary'],
                activebackground=self.colors['bg_card'],
                selectcolor=self.colors['bg_card'],
                highlightthickness=0,
                bd=0
            )
            rb.pack(anchor=tk.W, pady=8, padx=10)

        # 按钮框架
        button_frame = tk.Frame(content, bg=self.colors['bg_card'])
        button_frame.pack(pady=(20, 0))

        def on_save():
            selected = behavior_var.get()
            if selected == "ask":
                self.settings.set("close_behavior", None)
            else:
                self.settings.set("close_behavior", selected)
            messagebox.showinfo("成功", "设置已保存")
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        # 应用样式
        style = ttk.Style()

        ttk.Button(button_frame, text="保存", command=on_save, style='Primary.TButton').pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="取消", command=on_cancel, style='Secondary.TButton').pack(side=tk.LEFT)

    def _show_about(self):
        """显示关于对话框"""
        about_text = """Sunny-Ngrok GUI 管理器
        
一个用于管理 Sunny-Ngrok 隧道的图形化工具

功能特性:
• 隧道配置管理
• 一键启动/停止
• 实时日志显示
• 开机自启动
• 系统托盘支持

官网: www.ngrok.cc
"""
        messagebox.showinfo("关于", about_text)

    def _quit_application(self):
        """真正退出应用程序"""
        # 检查是否有隧道在运行
        running_tunnels = []
        for tunnel_id, process in self.tunnel_processes.items():
            if process.is_running():
                tunnel = self.config.get_by_id(tunnel_id)
                if tunnel:
                    running_tunnels.append(tunnel['name'])
                else:
                    running_tunnels.append(process.tunnel_name)

        if running_tunnels:
            tunnel_list = "\n".join(running_tunnels)
            if messagebox.askyesno("确认", f"以下隧道正在运行中：\n{tunnel_list}\n\n确定要退出吗？"):
                # 停止所有运行中的隧道
                for process in self.tunnel_processes.values():
                    if process.is_running():
                        process.stop()
                # 关闭单实例服务器
                if self.instance_server:
                    try:
                        self.instance_server.close()
                    except:
                        pass
                self._uninstall_taskbar_toggle()
                self.root.quit()
        else:
            # 关闭单实例服务器
            if self.instance_server:
                try:
                    self.instance_server.close()
                except:
                    pass
            self._uninstall_taskbar_toggle()
            self.root.quit()

    def _log_system(self, message):
        """添加系统日志（不属于任何隧道的日志）"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"

        # 只在当前没有选中隧道时显示系统日志
        if self.current_tunnel_index is None:
            self._append_log_text(log_message)

    def _on_closing(self):
        """关闭窗口"""
        # 如果安装了托盘支持，根据设置决定行为
        if TRAY_AVAILABLE:
            close_behavior = self.settings.get("close_behavior")

            # 如果已经设置了默认行为，直接执行
            if close_behavior == "minimize":
                self._minimize_to_tray()
                return
            elif close_behavior == "exit":
                self._quit_application()
                return

            # 第一次使用，询问用户并记住选择
            # 创建自定义对话框
            dialog = tk.Toplevel(self.root)
            dialog.title("关闭选项")
            dialog.geometry("420x230")
            dialog.resizable(False, False)
            dialog.transient(self.root)
            dialog.grab_set()
            dialog.configure(bg=self.colors['bg_main'])

            # 居中显示
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
            y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")

            result = {'action': None}

            # 主卡片
            card = tk.Frame(dialog, bg=self.colors['bg_card'], relief='flat', bd=0)
            card.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
            card.configure(highlightbackground=self.colors['border'], highlightthickness=1)

            # 内容区域
            content = tk.Frame(card, bg=self.colors['bg_card'])
            content.pack(fill=tk.BOTH, expand=True, padx=22, pady=18)

            # 提示文本
            tk.Label(
                content,
                text="请选择关闭方式：",
                font=('Microsoft YaHei UI', 11, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary']
            ).pack(anchor='w', pady=(0, 10))

            # 记住选择的复选框
            remember_var = tk.BooleanVar(value=True)
            tk.Checkbutton(
                content,
                text="记住我的选择（可在设置中修改）",
                variable=remember_var,
                font=('Microsoft YaHei UI', 9),
                bg=self.colors['bg_card'],
                fg=self.colors['text_secondary'],
                activebackground=self.colors['bg_card'],
                selectcolor=self.colors['bg_card'],
                highlightthickness=0,
                bd=0
            ).pack(anchor='w', pady=(0, 16))

            # 按钮框架
            button_frame = tk.Frame(content, bg=self.colors['bg_card'])
            button_frame.pack()

            def on_minimize():
                result['action'] = 'minimize'
                result['remember'] = remember_var.get()
                dialog.destroy()

            def on_exit():
                result['action'] = 'exit'
                result['remember'] = remember_var.get()
                dialog.destroy()

            def on_cancel():
                result['action'] = 'cancel'
                dialog.destroy()

            ttk.Button(
                button_frame,
                text="最小化到托盘",
                command=on_minimize,
                style='Primary.TButton'
            ).pack(side=tk.LEFT, padx=6)

            ttk.Button(
                button_frame,
                text="退出程序",
                command=on_exit,
                style='Secondary.TButton'
            ).pack(side=tk.LEFT, padx=6)

            ttk.Button(
                button_frame,
                text="取消",
                command=on_cancel,
                style='Secondary.TButton'
            ).pack(side=tk.LEFT, padx=6)

            # 等待对话框关闭
            self.root.wait_window(dialog)

            if result['action'] == 'minimize':
                # 如果选择记住，保存设置
                if result.get('remember', False):
                    self.settings.set("close_behavior", "minimize")
                self._minimize_to_tray()
            elif result['action'] == 'exit':
                # 如果选择记住，保存设置
                if result.get('remember', False):
                    self.settings.set("close_behavior", "exit")
                self._quit_application()
            # 如果是 cancel 或关闭对话框，什么都不做

            return

        # 没有托盘支持时，检查是否有隧道在运行
        running_tunnels = []
        for tunnel_id, process in self.tunnel_processes.items():
            if process.is_running():
                tunnel = self.config.get_by_id(tunnel_id)
                if tunnel:
                    running_tunnels.append(tunnel['name'])
                else:
                    running_tunnels.append(process.tunnel_name)

        if running_tunnels:
            tunnel_list = "\n".join(running_tunnels)
            if messagebox.askyesno("确认", f"以下隧道正在运行中：\n{tunnel_list}\n\n确定要退出吗？"):
                # 停止所有运行中的隧道
                for process in self.tunnel_processes.values():
                    if process.is_running():
                        process.stop()
                # 关闭单实例服务器
                if self.instance_server:
                    try:
                        self.instance_server.close()
                    except:
                        pass
                self._uninstall_taskbar_toggle()
                self.root.destroy()
        else:
            # 关闭单实例服务器
            if self.instance_server:
                try:
                    self.instance_server.close()
                except:
                    pass
            self._uninstall_taskbar_toggle()
            self.root.destroy()


def check_single_instance():
    """检查是否已有实例在运行"""
    try:
        # 创建一个socket作为互斥锁
        # 使用特定端口来确保只有一个实例
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', 59876))  # 使用一个不常用的端口
        return sock  # 返回socket对象，保持绑定状态
    except socket.error:
        # 端口已被占用，说明已有实例在运行
        return None


def notify_existing_instance():
    """通知已存在的实例显示窗口"""
    try:
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(('127.0.0.1', 59877))
        client_sock.close()
        return True
    except:
        return False


def main():
    """主函数"""
    # 检查单实例
    lock_socket = check_single_instance()

    if lock_socket is None:
        # 已有实例在运行，通知它显示窗口
        notify_existing_instance()
        sys.exit(0)

    ensure_app_dirs()

    ensure_sunny_ready(startup=True)
    # 创建主窗口
    root = tk.Tk()
    app = NgrokGUI(root)

    try:
        root.mainloop()
    finally:
        # 清理socket
        if lock_socket:
            lock_socket.close()


if __name__ == "__main__":
    main()
