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
            # 构建命令
            cmd = [
                "sunny.exe",
                "--server", server,
                "--key", key,
                "--log", "stdout"
            ]

            # 启动进程
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
                bufsize=1,
                universal_newlines=True,
                encoding='utf-8',
                errors='replace'
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

            return True, "隧道启动成功"

        except FileNotFoundError:
            return False, "找不到 sunny.exe，请确保程序在正确的目录中"
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
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    log_line = line.rstrip()
                    self.logs.append(log_line)  # 保存到历史
                    callback(self.tunnel_name, log_line)
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
        self.geometry("400x250")
        self.resizable(False, False)

        self.result = None
        self.tunnel = tunnel

        # 使对话框模态
        self.transient(parent)
        self.grab_set()

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
        # 主框架
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 名称
        ttk.Label(main_frame, text="隧道名称:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.name_var, width=30).grid(row=0, column=1, pady=5)

        # 服务器
        ttk.Label(main_frame, text="服务器地址:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.server_var = tk.StringVar(value="server.example.com:443")
        ttk.Entry(main_frame, textvariable=self.server_var, width=30).grid(row=1, column=1, pady=5)

        # 密钥
        ttk.Label(main_frame, text="隧道密钥:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.key_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.key_var, width=30).grid(row=2, column=1, pady=5)

        # 自动启动
        self.auto_start_var = tk.BooleanVar()
        ttk.Checkbutton(
            main_frame,
            text="开机自动启动此隧道",
            variable=self.auto_start_var
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=10)

        # 按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)

        ttk.Button(button_frame, text="确定", command=self._on_ok, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=self._on_cancel, width=10).pack(side=tk.LEFT, padx=5)

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
        self.root.geometry("900x600")

        # 配置和进程管理
        self.config = TunnelConfig()
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
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="退出", command=self._on_closing)

        # 设置菜单
        self.settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=self.settings_menu)
        self._update_startup_menu()
        if TRAY_AVAILABLE:
            self.settings_menu.add_command(label="最小化到托盘", command=self._minimize_to_tray)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="关于", command=self._show_about)

    def _create_widgets(self):
        """创建主界面控件"""
        # 主容器
        main_container = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 左侧面板 - 隧道列表
        left_frame = ttk.Frame(main_container)
        main_container.add(left_frame, weight=1)

        # 隧道列表标题
        ttk.Label(left_frame, text="隧道列表", font=("", 10, "bold")).pack(pady=5)

        # 隧道列表
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tunnel_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=("", 10)
        )
        self.tunnel_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.tunnel_listbox.yview)

        self.tunnel_listbox.bind('<<ListboxSelect>>', self._on_tunnel_select)

        # 按钮区域
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(button_frame, text="添加", command=self._add_tunnel).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="编辑", command=self._edit_tunnel).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="删除", command=self._delete_tunnel).pack(side=tk.LEFT, padx=2)

        # 右侧面板 - 控制和日志
        right_frame = ttk.Frame(main_container)
        main_container.add(right_frame, weight=2)

        # 控制区域
        control_frame = ttk.LabelFrame(right_frame, text="隧道控制", padding="10")
        control_frame.pack(fill=tk.X, padx=5, pady=5)

        # 状态显示
        status_frame = ttk.Frame(control_frame)
        status_frame.pack(fill=tk.X, pady=5)

        ttk.Label(status_frame, text="当前隧道:").pack(side=tk.LEFT)
        self.current_tunnel_label = ttk.Label(status_frame, text="未选择", foreground="gray")
        self.current_tunnel_label.pack(side=tk.LEFT, padx=10)

        ttk.Label(status_frame, text="状态:").pack(side=tk.LEFT, padx=(20, 0))
        self.status_label = ttk.Label(status_frame, text="未运行", foreground="gray")
        self.status_label.pack(side=tk.LEFT, padx=10)

        # 控制按钮
        control_buttons = ttk.Frame(control_frame)
        control_buttons.pack(fill=tk.X, pady=5)

        self.start_button = ttk.Button(
            control_buttons,
            text="启动隧道",
            command=self._start_tunnel,
            state=tk.DISABLED
        )
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = ttk.Button(
            control_buttons,
            text="停止隧道",
            command=self._stop_tunnel,
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)

        # 日志区域
        log_frame = ttk.LabelFrame(right_frame, text="运行日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 日志按钮
        log_buttons = ttk.Frame(log_frame)
        log_buttons.pack(fill=tk.X, pady=(5, 0))

        ttk.Button(log_buttons, text="清空日志", command=self._clear_log).pack(side=tk.LEFT)

    def _load_tunnels(self):
        """加载隧道列表"""
        self.tunnel_listbox.delete(0, tk.END)
        for i, tunnel in enumerate(self.config.get_all()):
            # 检查隧道是否在运行
            is_running = i in self.tunnel_processes and self.tunnel_processes[i].is_running()
            status_icon = "●" if is_running else "○"

            display_text = f"{status_icon} {tunnel['name']}"
            if tunnel.get('auto_start', False):
                display_text += " [自启]"
            self.tunnel_listbox.insert(tk.END, display_text)

    def _on_tunnel_select(self, event):
        """隧道选择事件"""
        selection = self.tunnel_listbox.curselection()
        if selection:
            self.current_tunnel_index = selection[0]
            self.last_selected_index = self.current_tunnel_index  # 记住选择
            self._save_last_selection()

            tunnel = self.config.get(self.current_tunnel_index)
            if tunnel:
                # 更新当前隧道显示
                self.current_tunnel_label.config(text=tunnel['name'], foreground="blue")

                # 检查当前隧道是否在运行
                is_running = (self.current_tunnel_index in self.tunnel_processes and
                             self.tunnel_processes[self.current_tunnel_index].is_running())

                if is_running:
                    self.status_label.config(text="运行中", foreground="green")
                    self.start_button.config(state=tk.DISABLED)
                    self.stop_button.config(state=tk.NORMAL)
                else:
                    self.status_label.config(text="未运行", foreground="gray")
                    self.start_button.config(state=tk.NORMAL)
                    self.stop_button.config(state=tk.DISABLED)

                # 显示该隧道的日志
                self._display_tunnel_logs()
        else:
            self.current_tunnel_index = None
            self.current_tunnel_label.config(text="未选择", foreground="gray")
            self.status_label.config(text="未运行", foreground="gray")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.DISABLED)

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
        """保存最后选择的隧道索引"""
        try:
            with open('.last_selection', 'w') as f:
                f.write(str(self.last_selected_index))
        except:
            pass

    def _restore_last_selection(self):
        """恢复最后选择的隧道"""
        try:
            if os.path.exists('.last_selection'):
                with open('.last_selection', 'r') as f:
                    index = int(f.read().strip())
                    if 0 <= index < len(self.config.get_all()):
                        self.tunnel_listbox.selection_clear(0, tk.END)
                        self.tunnel_listbox.selection_set(index)
                        self.tunnel_listbox.see(index)
                        # 触发选择事件
                        self.current_tunnel_index = index
                        self.last_selected_index = index
                        tunnel = self.config.get(index)
                        if tunnel:
                            self.current_tunnel_label.config(text=tunnel['name'], foreground="blue")
                            self._update_tunnel_status()
                            self._display_tunnel_logs()
        except:
            pass

    def _update_tunnel_status(self):
        """更新当前隧道的状态显示"""
        if self.current_tunnel_index is None:
            return

        is_running = (self.current_tunnel_index in self.tunnel_processes and
                     self.tunnel_processes[self.current_tunnel_index].is_running())

        if is_running:
            self.status_label.config(text="运行中", foreground="green")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
        else:
            self.status_label.config(text="未运行", foreground="gray")
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)

    def _add_tunnel(self):
        """添加隧道"""
        dialog = TunnelDialog(self.root, "添加隧道")
        self.root.wait_window(dialog)

        if dialog.result:
            self.config.add(
                dialog.result['name'],
                dialog.result['server'],
                dialog.result['key'],
                dialog.result['auto_start']
            )
            self._load_tunnels()
            self._log_system("添加隧道: " + dialog.result['name'])

    def _edit_tunnel(self):
        """编辑隧道"""
        if self.current_tunnel_index is None:
            messagebox.showwarning("警告", "请先选择一个隧道")
            return

        tunnel = self.config.get(self.current_tunnel_index)
        if not tunnel:
            return

        dialog = TunnelDialog(self.root, "编辑隧道", tunnel)
        self.root.wait_window(dialog)

        if dialog.result:
            self.config.update(
                self.current_tunnel_index,
                dialog.result['name'],
                dialog.result['server'],
                dialog.result['key'],
                dialog.result['auto_start']
            )
            self._load_tunnels()
            self._log_system("更新隧道: " + dialog.result['name'])

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
            self._log_system("删除隧道: " + tunnel['name'])

    def _start_tunnel(self):
        """启动隧道"""
        if self.current_tunnel_index is None:
            return

        # 检查当前隧道是否已在运行
        if (self.current_tunnel_index in self.tunnel_processes and
            self.tunnel_processes[self.current_tunnel_index].is_running()):
            messagebox.showwarning("警告", "该隧道已在运行中")
            return

        tunnel = self.config.get(self.current_tunnel_index)
        if not tunnel:
            return

        # 创建新的进程管理器
        process = TunnelProcess(tunnel['name'])
        self.tunnel_processes[self.current_tunnel_index] = process

        self._log_to_tunnel(self.current_tunnel_index, f"正在启动隧道: {tunnel['name']}")
        self._log_to_tunnel(self.current_tunnel_index, f"服务器: {tunnel['server']}")
        self._log_to_tunnel(self.current_tunnel_index, f"密钥: {tunnel['key']}")

        success, message = process.start(
            tunnel['server'],
            tunnel['key'],
            self._on_tunnel_log
        )

        if success:
            self.status_label.config(text="运行中", foreground="green")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self._log_to_tunnel(self.current_tunnel_index, message)
            self._load_tunnels()  # 刷新列表显示运行状态
            # 恢复选中状态
            self._restore_selection_after_reload()
        else:
            self.status_label.config(text="启动失败", foreground="red")
            self._log_to_tunnel(self.current_tunnel_index, f"错误: {message}")
            messagebox.showerror("错误", message)

    def _stop_tunnel(self):
        """停止隧道"""
        if self.current_tunnel_index is None:
            return

        if self.current_tunnel_index not in self.tunnel_processes:
            return

        process = self.tunnel_processes[self.current_tunnel_index]
        if not process.is_running():
            return

        self._log_to_tunnel(self.current_tunnel_index, "正在停止隧道...")
        success, message = process.stop()

        self.status_label.config(text="未运行", foreground="gray")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self._log_to_tunnel(self.current_tunnel_index, message)
        self._load_tunnels()  # 刷新列表显示运行状态
        # 恢复选中状态
        self._restore_selection_after_reload()

    def _restore_selection_after_reload(self):
        """在重新加载列表后恢复选中状态"""
        if self.current_tunnel_index is not None:
            # 恢复选中
            self.tunnel_listbox.selection_clear(0, tk.END)
            self.tunnel_listbox.selection_set(self.current_tunnel_index)
            self.tunnel_listbox.see(self.current_tunnel_index)
            # 确保焦点在列表上
            self.tunnel_listbox.focus_set()

    def _on_tunnel_log(self, tunnel_name, message):
        """处理隧道日志回调"""
        # 只有当前选中的隧道才实时显示日志
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
                self.current_tunnel_index = i
                self.tunnel_listbox.selection_clear(0, tk.END)
                self.tunnel_listbox.selection_set(i)
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
            self.settings_menu.insert_command(0, label="✓ 开机自启动", command=self._toggle_startup)
        else:
            self.settings_menu.insert_command(0, label="开机自启动", command=self._toggle_startup)

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
                self.root.quit()

            def on_show(icon, item):
                icon.stop()
                self.root.deiconify()

            menu = pystray.Menu(
                pystray.MenuItem('显示窗口', on_show),
                pystray.MenuItem('退出', on_quit)
            )

            self.tray_icon = pystray.Icon("SunnyNgrok", create_image(), "Sunny-Ngrok 管理器", menu)

            # 在新线程中运行托盘图标
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _show_about(self):
        """显示关于对话框"""
        about_text = """Sunny-Ngrok GUI 管理器

版本: 1.0.0

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
