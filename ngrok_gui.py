#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sunny-Ngrok GUI Manager
图形化管理界面，用于管理Sunny-Ngrok隧道
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import subprocess
import threading
import queue
import sys
import socket
from datetime import datetime

# 尝试导入系统托盘支持
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("提示: 安装 pystray 和 Pillow 可启用系统托盘功能")
    print("运行: pip install pystray Pillow")


class TunnelConfig:
    """隧道配置管理"""

    def __init__(self, config_file="tunnels.json"):
        self.config_file = config_file
        self.tunnels = []
        self.load()

    def load(self):
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.tunnels = json.load(f)
            except Exception as e:
                print(f"加载配置失败: {e}")
                self.tunnels = []
        else:
            self.tunnels = []

    def save(self):
        """保存配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.tunnels, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False

    def add(self, name, server, key, auto_start=False):
        """添加隧道"""
        tunnel = {
            "name": name,
            "server": server,
            "key": key,
            "auto_start": auto_start
        }
        self.tunnels.append(tunnel)
        return self.save()

    def update(self, index, name, server, key, auto_start=False):
        """更新隧道"""
        if 0 <= index < len(self.tunnels):
            self.tunnels[index] = {
                "name": name,
                "server": server,
                "key": key,
                "auto_start": auto_start
            }
            return self.save()
        return False

    def delete(self, index):
        """删除隧道"""
        if 0 <= index < len(self.tunnels):
            self.tunnels.pop(index)
            return self.save()
        return False

    def get(self, index):
        """获取隧道"""
        if 0 <= index < len(self.tunnels):
            return self.tunnels[index]
        return None

    def get_all(self):
        """获取所有隧道"""
        return self.tunnels


class AppSettings:
    """应用程序设置管理"""

    def __init__(self, settings_file="settings.json"):
        self.settings_file = settings_file
        self.settings = {
            "close_behavior": None  # None=询问, "minimize"=最小化到托盘, "exit"=退出程序
        }
        self.load()

    def load(self):
        """加载设置"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    self.settings.update(loaded_settings)
            except Exception as e:
                print(f"加载设置失败: {e}")

    def save(self):
        """保存设置"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存设置失败: {e}")
            return False

    def get(self, key, default=None):
        """获取设置"""
        return self.settings.get(key, default)

    def set(self, key, value):
        """设置值"""
        self.settings[key] = value
        return self.save()


class TunnelProcess:
    """隧道进程管理"""

    def __init__(self, tunnel_name):
        self.tunnel_name = tunnel_name
        self.process = None
        self.running = False
        self.log_queue = queue.Queue()
        self.reader_thread = None
        self.logs = []  # 存储日志历史

    def start(self, server, key, log_callback=None):
        """启动隧道"""
        if self.running:
            return False, "隧道已在运行中"

        try:
            # 检查可用的sunny客户端
            sunny_py = "sunny.py"
            sunny_exe = "sunny.exe"

            cmd = None
            client_type = None

            # 优先使用EXE版本
            if os.path.exists(sunny_exe):
                cmd = [
                    sunny_exe,
                    "-s", server,
                    "-k", key,
                    "-l", "stdout"
                ]
                client_type = "EXE版本"
            # 备选使用Python版本
            elif os.path.exists(sunny_py):
                # Python版本使用 --clientid 参数，只需要clientid（key就是clientid）
                cmd = [
                    sys.executable,  # Python解释器
                    sunny_py,
                    "--clientid=" + key  # 只需要clientid，不需要server
                ]
                client_type = "Python版本"
            else:
                # 两个都没有，提示下载
                return False, ("找不到 sunny 客户端程序\n\n"
                             "请下载以下任一版本：\n"
                             "1. EXE版本: sunny.exe（推荐）\n"
                             "2. Python版本: sunny.py\n\n"
                             "下载地址: https://www.ngrok.cc")

            # 启动进程 - 使用正确的编码设置
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
                bufsize=1,
                universal_newlines=False,  # 改为False，手动处理编码
                encoding=None,  # 不自动编码
                errors=None
            )

            self.running = True

            # 启动日志读取线程
            if log_callback:
                self.reader_thread = threading.Thread(
                    target=self._read_output,
                    args=(log_callback,),
                    daemon=True
                )
                self.reader_thread.start()

            return True, f"隧道启动成功 (使用{client_type})"

        except FileNotFoundError as e:
            return False, f"启动失败: 找不到必要的程序文件\n{str(e)}"
        except Exception as e:
            return False, f"启动失败: {str(e)}"

    def stop(self):
        """停止隧道"""
        if not self.running:
            return False, "隧道未运行"

        try:
            if self.process:
                self.process.terminate()
                self.process.wait(timeout=5)
            self.running = False
            return True, "隧道已停止"
        except subprocess.TimeoutExpired:
            if self.process:
                self.process.kill()
            self.running = False
            return True, "隧道已强制停止"
        except Exception as e:
            return False, f"停止失败: {str(e)}"

    def _read_output(self, callback):
        """读取进程输出"""
        try:
            # 尝试多种编码方式读取
            for raw_line in iter(self.process.stdout.readline, b''):
                if raw_line:
                    # 尝试多种编码解码
                    line = None
                    for encoding in ['utf-8', 'gbk', 'gb2312', 'cp936']:
                        try:
                            line = raw_line.decode(encoding).rstrip()
                            break
                        except:
                            continue

                    if line is None:
                        # 如果所有编码都失败，使用替换模式
                        line = raw_line.decode('utf-8', errors='replace').rstrip()

                    self.logs.append(line)  # 保存到历史
                    callback(self.tunnel_name, line)
                if not self.running:
                    break
        except Exception as e:
            error_msg = f"日志读取错误: {str(e)}"
            self.logs.append(error_msg)
            callback(self.tunnel_name, error_msg)

    def is_running(self):
        """检查是否运行中"""
        if self.process and self.running:
            poll = self.process.poll()
            if poll is not None:
                self.running = False
            return self.running
        return False

    def get_logs(self):
        """获取日志历史"""
        return self.logs

    def clear_logs(self):
        """清空日志"""
        self.logs = []


class TunnelDialog(tk.Toplevel):
    """隧道配置对话框"""

    def __init__(self, parent, title="添加隧道", tunnel=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("450x480")
        self.resizable(False, False)

        # 现代化配色
        self.colors = {
            'bg': '#F7F9FC',
            'card': '#FFFFFF',
            'primary': '#2563EB',
            'text_primary': '#0F172A',
            'text_secondary': '#64748B',
            'border': '#E2E8F0'
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
        card = tk.Frame(self, bg=self.colors['card'], relief='flat', bd=0)
        card.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        card.configure(highlightbackground=self.colors['border'], highlightthickness=1)

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
        self.root.title("Sunny-Ngrok 管理器")
        self.root.geometry("1000x650")

        # 现代化配色方案
        self.colors = {
            'primary': '#2563EB',       # ��ɫ�� - �ִ���ɫ
            'primary_dark': '#1D4ED8',  # ����ɫ
            'primary_light': '#DBEAFE', # ǳ��ɫ����
            'accent': '#FF7A00',        # ǿ����ɫ
            'accent_dark': '#E66A00',   # ǿ������ɫ
            'accent_light': '#FFF1E6',  # ǿ������ɫ����
            'success': '#10B981',       # �ɹ� - ��ɫ
            'success_bg': '#E8F7EF',    # �ɹ� - ����
            'danger': '#EF4444',        # Σ�� - ��ɫ
            'warning': '#F59E0B',       # ���� - ��ɫ
            'neutral_bg': '#F1F5F9',    # �м�״̬����
            'bg_main': '#F7F9FC',       # ������
            'bg_card': '#FFFFFF',       # ��Ƭ����
            'bg_header': '#F1F5F9',     # ͷ������
            'card_hover': '#F6F8FB',    # ��Ƭ��ͣ
            'card_selected': '#F1F7FF', # ��Ƭѡ��
            'text_primary': '#0F172A',  # ���ı�
            'text_secondary': '#64748B',# ��Ҫ�ı�
            'border': '#E2E8F0',        # �߿�
            'hover': '#F1F5F9'          # ��ͣ
        }
        self.menu_font = ('Microsoft YaHei UI', 10)
        self.menu_item_font = ('Microsoft YaHei UI', 9)
        self.toolbar_height = 56

        # 配置和进程管理
        self.config = TunnelConfig()
        self.settings = AppSettings()  # 添加设置管理
        self.tunnel_processes = {}  # 字典：隧道索引 -> TunnelProcess
        self.current_tunnel_index = None
        self.last_selected_index = None  # 记住最后选择的隧道

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

        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # 恢复最后选择的隧道
        self._restore_last_selection()

        # 启动自动启动的隧道
        self._auto_start_tunnels()

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
                       font=('Microsoft YaHei UI', 12, 'bold'))
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
                       font=('Microsoft YaHei UI', 9),
                       padding=(15, 8))
        style.map('Primary.TButton',
                 background=[('active', self.colors['primary_dark']),
                           ('pressed', self.colors['primary_dark']),
                           ('disabled', '#E5E7EB')],
                 foreground=[('disabled', 'black')])

        # 配置 Button 样式 - 次要按钮
        style.configure('Secondary.TButton',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       borderwidth=1,
                       focuscolor='none',
                       font=('Microsoft YaHei UI', 9),
                       padding=(12, 6))
        style.map('Secondary.TButton',
                 background=[('active', self.colors['hover'])])

        # ���� Button ��ʽ - ǿ����ť
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

        # 配置 LabelFrame 样式
        style.configure('Modern.TLabelframe',
                       background=self.colors['bg_card'],
                       borderwidth=0,
                       relief='flat')
        style.configure('Modern.TLabelframe.Label',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       font=('Microsoft YaHei UI', 10, 'bold'))

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
        self.root.lift()  # 置顶
        self.root.focus_force()  # 强制获取焦点
        self.root.attributes('-topmost', True)  # 临时置顶
        self.root.after(100, lambda: self.root.attributes('-topmost', False))  # 100ms后取消置顶

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

        # 帮助菜单
        self.help_menu = tk.Menu(self.root,
                               tearoff=0,
                               bg=self.colors['bg_card'],
                               fg=self.colors['text_primary'],
                               activebackground=self.colors['primary_light'],
                               activeforeground=self.colors['primary'],
                               relief='flat',
                               borderwidth=1,
                               font=self.menu_item_font)
        self.help_menu.add_command(label="   关于", command=self._show_about)

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

    def _show_help_menu(self, event=None):
        """显示帮助菜单"""
        self._popup_menu(self.help_menu, self.help_button)

    def _create_widgets(self):
        """创建主界面控件"""
        # Top app bar
        app_bar = tk.Frame(self.root, bg=self.colors['bg_card'], height=self.toolbar_height)
        app_bar.pack(fill=tk.X)
        app_bar.pack_propagate(False)
        app_bar.configure(highlightbackground=self.colors['border'], highlightthickness=1)

        brand_frame = tk.Frame(app_bar, bg=self.colors['bg_card'])
        brand_frame.pack(side=tk.LEFT, padx=16)

        brand_dot = tk.Canvas(brand_frame, width=12, height=12, bg=self.colors['bg_card'], highlightthickness=0)
        brand_dot.create_oval(0, 0, 12, 12, fill=self.colors['accent'], outline=self.colors['accent'])
        brand_dot.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(
            brand_frame,
            text="Sunny-Ngrok",
            font=('Microsoft YaHei UI', 13, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary']
        ).pack(side=tk.LEFT)

        tk.Label(
            brand_frame,
            text="GUI",
            font=('Microsoft YaHei UI', 9),
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary']
        ).pack(side=tk.LEFT, padx=(6, 0))

        actions = tk.Frame(app_bar, bg=self.colors['bg_card'])
        actions.pack(side=tk.LEFT, padx=(6, 12))

        self.help_button = tk.Menubutton(
            actions,
            text="帮助",
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary'],
            activebackground=self.colors['primary_light'],
            activeforeground=self.colors['primary'],
            relief='flat',
            borderwidth=0,
            font=self.menu_font,
            padx=8,
            pady=2
        )
        self.help_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.help_button.configure(menu=self.help_menu)
        self.help_button.bind("<Button-1>", self._show_help_menu)

        self.settings_button = tk.Menubutton(
            actions,
            text="设置",
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary'],
            activebackground=self.colors['primary_light'],
            activeforeground=self.colors['primary'],
            relief='flat',
            borderwidth=0,
            font=self.menu_font,
            padx=8,
            pady=2
        )
        self.settings_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.settings_button.configure(menu=self.settings_menu)
        self.settings_button.bind("<Button-1>", self._show_settings_menu)


        main_container = tk.Frame(self.root, bg=self.colors['bg_main'])
        main_container.pack(fill=tk.BOTH, expand=True)

        # 创建左右分栏布局
        # 左侧面板 - 隧道列表
        left_panel = tk.Frame(main_container, bg=self.colors['bg_main'], width=320)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=(10, 5), pady=(1, 10))
        left_panel.pack_propagate(False)

        # 左侧卡片容器
        left_card = tk.Frame(left_panel, bg=self.colors['bg_card'], relief='flat', bd=0)
        left_card.pack(fill=tk.BOTH, expand=True)

        # 添加阴影效果（通过边框模拟）
        left_card.configure(highlightbackground=self.colors['border'], highlightthickness=1)

        # 隧道列表标题区域
        header_frame = tk.Frame(left_card, bg=self.colors['bg_card'], height=50)
        header_frame.pack(fill=tk.X, padx=15, pady=(15, 10))
        header_frame.pack_propagate(False)

        title_label = tk.Label(
            header_frame,
            text="隧道列表",
            font=('Microsoft YaHei UI', 12, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary']
        )
        title_label.pack(side=tk.LEFT, anchor='w')

        # 隧道列表容器 - 使用Canvas和Scrollbar实现可滚动的卡片列表
        list_container = tk.Frame(left_card, bg=self.colors['bg_card'])
        list_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))

        # 创建Canvas和Scrollbar
        self.tunnel_canvas = tk.Canvas(
            list_container,
            bg=self.colors['bg_card'],
            highlightthickness=0,
            bd=0
        )
        self.tunnel_scrollbar = tk.Scrollbar(list_container, command=self.tunnel_canvas.yview, width=12)
        self.tunnel_list_frame = tk.Frame(self.tunnel_canvas, bg=self.colors['bg_card'])

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
        button_frame.pack(fill=tk.X, padx=15, pady=(5, 15))

        # 使用现代化按钮样式
        add_btn = ttk.Button(button_frame, text="新增", command=self._add_tunnel, style='Secondary.TButton')
        add_btn.pack(side=tk.LEFT, padx=(0, 5))

        edit_btn = ttk.Button(button_frame, text="编辑", command=self._edit_tunnel, style='Secondary.TButton')
        edit_btn.pack(side=tk.LEFT, padx=5)

        delete_btn = ttk.Button(button_frame, text="删除", command=self._delete_tunnel, style='Secondary.TButton')
        delete_btn.pack(side=tk.LEFT, padx=5)

        # 右侧面板 - 控制和日志
        right_panel = tk.Frame(main_container, bg=self.colors['bg_main'])
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 10), pady=(1, 10))

        # 控制区域卡片
        control_card = tk.Frame(right_panel, bg=self.colors['bg_card'], relief='flat', bd=0)
        control_card.pack(fill=tk.X, pady=(0, 10))
        control_card.configure(highlightbackground=self.colors['border'], highlightthickness=1)

        # 控制区域标题
        control_header = tk.Frame(control_card, bg=self.colors['bg_card'])
        control_header.pack(fill=tk.X, padx=20, pady=(15, 10))

        tk.Label(
            control_header,
            text="隧道控制",
            font=('Microsoft YaHei UI', 11, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary']
        ).pack(side=tk.LEFT)

        # 状态显示区域
        status_frame = tk.Frame(control_card, bg=self.colors['bg_card'])
        status_frame.pack(fill=tk.X, padx=20, pady=(0, 15))

        # 当前隧道信息
        info_row1 = tk.Frame(status_frame, bg=self.colors['bg_card'])
        info_row1.pack(fill=tk.X, pady=3)

        tk.Label(
            info_row1,
            text="当前隧道:",
            font=('Microsoft YaHei UI', 9),
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary']
        ).pack(side=tk.LEFT)

        self.current_tunnel_label = tk.Label(
            info_row1,
            text="\u672a\u9009\u62e9",
            font=('Microsoft YaHei UI', 9, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary']
        )
        self.current_tunnel_label.pack(side=tk.LEFT, padx=10)

        # 运行状态
        info_row2 = tk.Frame(status_frame, bg=self.colors['bg_card'])
        info_row2.pack(fill=tk.X, pady=3)

        tk.Label(
            info_row2,
            text="运行状态:",
            font=('Microsoft YaHei UI', 9),
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary']
        ).pack(side=tk.LEFT)

        self.status_label = tk.Label(
            info_row2,
            text="\u672a\u8fd0\u884c",
            font=('Microsoft YaHei UI', 9, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary']
        )
        self.status_label.pack(side=tk.LEFT, padx=10)

        # 控制按钮区域
        control_buttons = tk.Frame(control_card, bg=self.colors['bg_card'])
        control_buttons.pack(fill=tk.X, padx=20, pady=(0, 15))

        self.start_button = ttk.Button(
            control_buttons,
            text="\u542f\u52a8\u9690\u9053",
            command=self._start_tunnel,
            style='Primary.TButton',
            state=tk.DISABLED
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_button = ttk.Button(
            control_buttons,
            text="\u505c\u6b62\u9690\u9053",
            command=self._stop_tunnel,
            style='Danger.TButton',
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT)
        self._sync_control_cursors()

        # 日志区域卡片
        log_card = tk.Frame(right_panel, bg=self.colors['bg_card'], relief='flat', bd=0)
        log_card.pack(fill=tk.BOTH, expand=True)
        log_card.configure(highlightbackground=self.colors['border'], highlightthickness=1)

        # 日志标题栏
        log_header = tk.Frame(log_card, bg=self.colors['bg_card'])
        log_header.pack(fill=tk.X, padx=20, pady=(15, 10))

        tk.Label(
            log_header,
            text="运行日志",
            font=('Microsoft YaHei UI', 11, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary']
        ).pack(side=tk.LEFT)

        # 清空日志按钮
        clear_log_btn = ttk.Button(
            log_header,
            text="\u6e05\u7a7a",
            command=self._clear_log,
            style='Secondary.TButton'
        )
        clear_log_btn.pack(side=tk.RIGHT)

        # 日志文本区域
        log_container = tk.Frame(log_card, bg=self.colors['bg_card'])
        log_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))

        self.log_text = scrolledtext.ScrolledText(
            log_container,
            wrap=tk.WORD,
            font=('Consolas', 9),
            bg='#1E1E1E',  # 深色背景，类似代码编辑器
            fg='#D4D4D4',  # 浅色文字
            insertbackground='white',
            relief='flat',
            bd=0,
            state=tk.DISABLED,
            highlightthickness=1,
            highlightbackground=self.colors['border']
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

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
        border = self.colors['primary'] if selected else self.colors['border']
        thickness = 2 if selected else 1

        card.configure(bg=bg, highlightbackground=border, highlightthickness=thickness)
        for widget in getattr(card, 'bg_widgets', []):
            try:
                widget.configure(bg=bg)
            except tk.TclError:
                pass

        if getattr(card, 'name_label', None):
            card.name_label.configure(
                fg=self.colors['primary'] if selected else self.colors['text_primary']
            )

    def _set_card_hover(self, card, hovering):
        if self.current_tunnel_index == getattr(card, 'index', None):
            return

        bg = self.colors['card_hover'] if hovering else self.colors['bg_card']
        border = self.colors['primary'] if hovering else self.colors['border']
        card.configure(bg=bg, highlightbackground=border, highlightthickness=1)
        for widget in getattr(card, 'bg_widgets', []):
            try:
                widget.configure(bg=bg)
            except tk.TclError:
                pass

    def _set_button_cursor(self, button, enabled):
        button.configure(cursor='hand2' if enabled else 'no')

    def _sync_control_cursors(self):
        self._set_button_cursor(self.start_button, self.start_button.instate(['!disabled']))
        self._set_button_cursor(self.stop_button, self.stop_button.instate(['!disabled']))

    def _create_tunnel_card(self, tunnel, index, is_running):
        card = tk.Frame(
            self.tunnel_list_frame,
            bg=self.colors['bg_card'],
            relief='flat',
            bd=0,
            cursor='hand2'
        )
        card.pack(fill=tk.X, pady=(0, 8))
        card.configure(
            highlightbackground=self.colors['border'],
            highlightthickness=1
        )
        card.index = index

        content = tk.Frame(card, bg=self.colors['bg_card'])
        content.pack(fill=tk.BOTH, padx=12, pady=10)

        name_row = tk.Frame(content, bg=self.colors['bg_card'])
        name_row.pack(fill=tk.X, pady=(0, 6))

        initial = (tunnel.get('name') or '').strip()[:1]
        if not initial:
            initial = str(index + 1)
        avatar = tk.Label(
            name_row,
            text=initial.upper(),
            font=('Microsoft YaHei UI', 9, 'bold'),
            bg=self.colors['accent_light'],
            fg=self.colors['accent'],
            padx=6,
            pady=2
        )
        avatar.pack(side=tk.LEFT, padx=(0, 8))

        name_label = tk.Label(
            name_row,
            text=tunnel['name'],
            font=('Microsoft YaHei UI', 11, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary'],
            anchor='w'
        )
        name_label.pack(side=tk.LEFT)

        status_bg = self.colors['success_bg'] if is_running else self.colors['neutral_bg']
        status_fg = self.colors['success'] if is_running else self.colors['text_secondary']
        status_text = "运行中" if is_running else "未运行"
        status_indicator = tk.Label(
            name_row,
            text=status_text,
            font=('Microsoft YaHei UI', 8),
            bg=status_bg,
            fg=status_fg,
            padx=8,
            pady=2
        )
        status_indicator.pack(side=tk.RIGHT)

        info_row = tk.Frame(content, bg=self.colors['bg_card'])
        info_row.pack(fill=tk.X)

        auto_start_enabled = tunnel.get('auto_start', False)
        auto_start_icon = tk.Label(
            info_row,
            text="⟳",
            font=('Microsoft YaHei UI', 9, 'bold'),
            bg=self.colors['bg_card'],
            fg=self.colors['success'] if auto_start_enabled else '#94A3B8',
            padx=4,
            pady=0
        )
        auto_start_icon.pack(side=tk.LEFT)

        server_label = tk.Label(
            info_row,
            text=tunnel['server'],
            font=('Microsoft YaHei UI', 8),
            bg=self.colors['bg_card'],
            fg=self.colors['primary'],
            anchor='w'
        )
        server_label.pack(side=tk.LEFT, padx=(2, 0))

        def on_click(event):
            self._select_tunnel_card(index)

        widgets = [card, content, name_row, name_label, info_row, status_indicator, server_label, avatar, auto_start_icon]

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

        card.bg_widgets = [content, name_row, info_row, name_label, server_label, auto_start_icon]
        card.name_label = name_label

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
            self.current_tunnel_label.config(text=tunnel['name'], fg=self.colors['primary'])

            is_running = (index in self.tunnel_processes and
                         self.tunnel_processes[index].is_running())

            if is_running:
                self.status_label.config(text="运行中", fg=self.colors['success'])
                self.start_button.config(state=tk.DISABLED)
                self.stop_button.config(state=tk.NORMAL)
            else:
                self.status_label.config(text="未运行", fg=self.colors['text_secondary'])
                self.start_button.config(state=tk.NORMAL)
                self.stop_button.config(state=tk.DISABLED)

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
            is_running = i in self.tunnel_processes and self.tunnel_processes[i].is_running()
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

        if self.current_tunnel_index in self.tunnel_processes:
            logs = self.tunnel_processes[self.current_tunnel_index].get_logs()
            for log in logs:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.log_text.insert(tk.END, f"[{timestamp}] {log}\n")
            self.log_text.see(tk.END)

        self.log_text.config(state=tk.DISABLED)

    def _save_last_selection(self):
        try:
            with open('.last_selection', 'w') as f:
                f.write(str(self.last_selected_index))
        except:
            pass

    def _restore_last_selection(self):
        try:
            if os.path.exists('.last_selection'):
                with open('.last_selection', 'r') as f:
                    index = int(f.read().strip())
                    if 0 <= index < len(self.config.get_all()):
                        self._select_tunnel_card(index)
        except:
            pass

    def _update_tunnel_status(self):
        if self.current_tunnel_index is None:
            return

        is_running = (self.current_tunnel_index in self.tunnel_processes and
                     self.tunnel_processes[self.current_tunnel_index].is_running())

        if is_running:
            self.status_label.config(text="运行中", fg=self.colors['success'])
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
        else:
            self.status_label.config(text="未运行", fg=self.colors['text_secondary'])
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
        self._sync_control_cursors()

    def _add_tunnel(self):
        dialog = TunnelDialog(self.root, "新增隐道")
        self.root.wait_window(dialog)

        if dialog.result:
            self.config.add(
                dialog.result['name'],
                dialog.result['server'],
                dialog.result['key'],
                dialog.result['auto_start']
            )
            self._load_tunnels()
            self._log_system("新增隐道: " + dialog.result['name'])


    def _edit_tunnel(self):
        """编辑隧道"""
        print(f"[DEBUG] 开始编辑，current_tunnel_index = {self.current_tunnel_index}")

        if self.current_tunnel_index is None:
            messagebox.showwarning("警告", "请先选择一个隧道")
            return

        # 保存当前索引，防止对话框打开时失去焦点导致索引被清空
        edit_index = self.current_tunnel_index

        tunnel = self.config.get(edit_index)
        print(f"[DEBUG] 获取到的隧道数据: {tunnel}")

        if not tunnel:
            return

        dialog = TunnelDialog(self.root, "编辑隧道", tunnel)
        self.root.wait_window(dialog)

        print(f"[DEBUG] 对话框关闭，result = {dialog.result}")

        if dialog.result:
            print(f"[DEBUG] 准备更新索引 {edit_index}")
            print(f"[DEBUG] 新数据: {dialog.result}")

            success = self.config.update(
                edit_index,  # 使用保存的索引
                dialog.result['name'],
                dialog.result['server'],
                dialog.result['key'],
                dialog.result['auto_start']
            )

            print(f"[DEBUG] 更新结果: {success}")
            print(f"[DEBUG] 更新后的配置: {self.config.get_all()}")

            if success:
                # 恢复索引
                self.current_tunnel_index = edit_index
                self._load_tunnels()
                self._restore_selection_after_reload()  # 恢复选中状态
                print(f"[DEBUG] 刷新后 current_tunnel_index = {self.current_tunnel_index}")
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
            if self.current_tunnel_index in self.tunnel_processes:
                process = self.tunnel_processes[self.current_tunnel_index]
                if process.is_running():
                    process.stop()
                del self.tunnel_processes[self.current_tunnel_index]

            self.config.delete(self.current_tunnel_index)
            self._load_tunnels()
            self.current_tunnel_index = None
            self.start_button.config(state=tk.DISABLED)
            self._sync_control_cursors()
            self._log_system("删除隧道: " + tunnel['name'])

    def _start_tunnel(self):
        if self.current_tunnel_index is None:
            return

        if (self.current_tunnel_index in self.tunnel_processes and
            self.tunnel_processes[self.current_tunnel_index].is_running()):
            messagebox.showwarning("提示", "隐道已经在运行")
            return

        tunnel = self.config.get(self.current_tunnel_index)
        if not tunnel:
            return

        process = TunnelProcess(tunnel['name'])
        self.tunnel_processes[self.current_tunnel_index] = process

        self._log_to_tunnel(self.current_tunnel_index, f"开始启动隐道: {tunnel['name']}")
        self._log_to_tunnel(self.current_tunnel_index, f"服务器: {tunnel['server']}")
        self._log_to_tunnel(self.current_tunnel_index, f"密钥: {tunnel['key']}")

        success, message = process.start(
            tunnel['server'],
            tunnel['key'],
            self._on_tunnel_log
        )

        if success:
            self.status_label.config(text="运行中", fg=self.colors['success'])
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self._log_to_tunnel(self.current_tunnel_index, message)
            self._load_tunnels()
            self._restore_selection_after_reload()
            self._sync_control_cursors()
        else:
            self.status_label.config(text="未运行", fg=self.colors['text_secondary'])
            self._log_to_tunnel(self.current_tunnel_index, f"错误: {message}")
            messagebox.showerror("错误", message)
            self._sync_control_cursors()

    def _stop_tunnel(self):
        if self.current_tunnel_index is None:
            return

        if self.current_tunnel_index not in self.tunnel_processes:
            return

        process = self.tunnel_processes[self.current_tunnel_index]
        if not process.is_running():
            return

        self._log_to_tunnel(self.current_tunnel_index, "正在停止隐道...")
        success, message = process.stop()

        self.status_label.config(text="未运行", fg=self.colors['text_secondary'])
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self._log_to_tunnel(self.current_tunnel_index, message)
        self._load_tunnels()
        self._restore_selection_after_reload()
        self._sync_control_cursors()

    def _restore_selection_after_reload(self):
        if self.current_tunnel_index is not None and self.current_tunnel_index < len(self.tunnel_cards):
            card = self.tunnel_cards[self.current_tunnel_index]
            self._set_card_selected(card, True)

    def _on_tunnel_log(self, tunnel_name, message):
        if self.current_tunnel_index is not None:
            tunnel = self.config.get(self.current_tunnel_index)
            if tunnel and tunnel['name'] == tunnel_name:
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_message = f"[{timestamp}] {message}\n"

                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, log_message)
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)

    def _log_to_tunnel(self, tunnel_index, message):
        """记录日志到指定隧道"""
        if tunnel_index in self.tunnel_processes:
            self.tunnel_processes[tunnel_index].logs.append(message)

        # 如果是当前选中的隧道，实时显示
        if tunnel_index == self.current_tunnel_index:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_message = f"[{timestamp}] {message}\n"

            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, log_message)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

    def _clear_log(self):
        """清空当前隧道的日志"""
        if self.current_tunnel_index is not None and self.current_tunnel_index in self.tunnel_processes:
            self.tunnel_processes[self.current_tunnel_index].clear_logs()

        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _auto_start_tunnels(self):
        """自动启动标记为自启的隧道"""
        for i, tunnel in enumerate(self.config.get_all()):
            if tunnel.get('auto_start', False):
                # 选择隧道卡片
                self._select_tunnel_card(i)
                self._log_to_tunnel(i, f"自动启动隧道: {tunnel['name']}")
                self._start_tunnel()

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
        for idx, process in self.tunnel_processes.items():
            if process.is_running():
                tunnel = self.config.get(idx)
                if tunnel:
                    running_tunnels.append(tunnel['name'])

        if running_tunnels:
            tunnel_list = "\n".join(running_tunnels)
            if messagebox.askyesno("确认", f"以下隧道正在运行中：\n{tunnel_list}\n\n确定要退出吗？"):
                # 停止所有运行中的隧道
                for idx, process in self.tunnel_processes.items():
                    if process.is_running():
                        process.stop()
                # 关闭单实例服务器
                if self.instance_server:
                    try:
                        self.instance_server.close()
                    except:
                        pass
                self.root.quit()
        else:
            # 关闭单实例服务器
            if self.instance_server:
                try:
                    self.instance_server.close()
                except:
                    pass
            self.root.quit()

    def _log_system(self, message):
        """添加系统日志（不属于任何隧道的日志）"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"

        # 只在当前没有选中隧道时显示系统日志
        if self.current_tunnel_index is None:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, log_message)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

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
        for idx, process in self.tunnel_processes.items():
            if process.is_running():
                tunnel = self.config.get(idx)
                if tunnel:
                    running_tunnels.append(tunnel['name'])

        if running_tunnels:
            tunnel_list = "\n".join(running_tunnels)
            if messagebox.askyesno("确认", f"以下隧道正在运行中：\n{tunnel_list}\n\n确定要退出吗？"):
                # 停止所有运行中的隧道
                for idx, process in self.tunnel_processes.items():
                    if process.is_running():
                        process.stop()
                # 关闭单实例服务器
                if self.instance_server:
                    try:
                        self.instance_server.close()
                    except:
                        pass
                self.root.destroy()
        else:
            # 关闭单实例服务器
            if self.instance_server:
                try:
                    self.instance_server.close()
                except:
                    pass
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
