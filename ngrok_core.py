#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sunny-Ngrok Core Utilities
非 UI 的核心逻辑：配置、下载与隧道进程管理
"""

import json
import os
import sys
import subprocess
import threading
from datetime import datetime
from collections import deque
import locale
import shutil
import tempfile
import urllib.request
import urllib.error
import zipfile
import time
import uuid


def _get_app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _get_app_base_dir()
CORE_DIR = os.path.join(BASE_DIR, "core")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
SUNNY_EXE_PATH = os.path.join(CORE_DIR, "sunny.exe")
BUNDLE_DIR = getattr(sys, "_MEIPASS", None)
BUNDLE_CORE_DIR = os.path.join(BUNDLE_DIR, "core") if BUNDLE_DIR else None
BUNDLE_SUNNY_EXE_PATH = os.path.join(BUNDLE_CORE_DIR, "sunny.exe") if BUNDLE_CORE_DIR else None
TUNNELS_FILE = os.path.join(CONFIG_DIR, "tunnels.json")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
LAST_SELECTION_FILE = os.path.join(CONFIG_DIR, ".last_selection")

SUNNY_ZIP_URL = "https://www.ngrok.cc/sunny/windows_amd64.zip"
SUNNY_DOWNLOAD_PAGE = "https://www.ngrok.cc/download.html"

LOG_MAX_ENTRIES = 2000


def ensure_app_dirs():
    """确保 core 和 config 目录存在，并迁移旧文件"""
    os.makedirs(CORE_DIR, exist_ok=True)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    _migrate_legacy_files()


def _migrate_legacy_files():
    legacy_files = [
        (TUNNELS_FILE, os.path.join(BASE_DIR, "tunnels.json")),
        (SETTINGS_FILE, os.path.join(BASE_DIR, "settings.json")),
        (LAST_SELECTION_FILE, os.path.join(BASE_DIR, ".last_selection")),
    ]
    for new_path, old_path in legacy_files:
        if not os.path.exists(new_path) and os.path.exists(old_path):
            try:
                shutil.move(old_path, new_path)
            except Exception:
                shutil.copy2(old_path, new_path)

    legacy_sunny = os.path.join(BASE_DIR, "sunny.exe")
    if not os.path.exists(SUNNY_EXE_PATH) and os.path.exists(legacy_sunny):
        try:
            shutil.move(legacy_sunny, SUNNY_EXE_PATH)
        except Exception:
            shutil.copy2(legacy_sunny, SUNNY_EXE_PATH)


def get_sunny_exe_path():
    """获取可用的 sunny.exe 路径（开发/打包兼容）"""
    if os.path.exists(SUNNY_EXE_PATH):
        return SUNNY_EXE_PATH
    if BUNDLE_SUNNY_EXE_PATH and os.path.exists(BUNDLE_SUNNY_EXE_PATH):
        return BUNDLE_SUNNY_EXE_PATH
    return SUNNY_EXE_PATH


class DownloadController:
    def __init__(self):
        self.stop_event = threading.Event()
        self.process = None
        self.canceled = False

    def cancel(self):
        self.canceled = True
        self.stop_event.set()
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass


def _download_and_extract_sunny_core(controller, progress_callback):
    try:
        os.makedirs(CORE_DIR, exist_ok=True)

        fd, zip_path = tempfile.mkstemp(suffix=".zip", dir=CORE_DIR)
        os.close(fd)
        _download_file(SUNNY_ZIP_URL, zip_path, controller, progress_callback)

        if controller and controller.stop_event.is_set():
            try:
                os.remove(zip_path)
            except Exception:
                pass
            return False, "已取消下载。"

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            _safe_extract_zip(zip_ref, CORE_DIR)

        try:
            os.remove(zip_path)
        except Exception:
            pass

        exe_path = None
        for walk_root, _, files in os.walk(CORE_DIR):
            for filename in files:
                if filename.lower() == "sunny.exe":
                    exe_path = os.path.join(walk_root, filename)
                    break
            if exe_path:
                break

        if not exe_path:
            return False, "下载完成，但未找到 sunny.exe，请尝试手动下载。"

        target_path = SUNNY_EXE_PATH
        if os.path.abspath(exe_path) != os.path.abspath(target_path):
            shutil.move(exe_path, target_path)

        _cleanup_core_dir(target_path)

        return True, "下载并安装完成。"
    except Exception as e:
        return False, f"自动下载失败: {str(e)}"


def _cleanup_core_dir(keep_path):
    """清理 core 目录，只保留指定核心文件"""
    keep_abs = os.path.abspath(keep_path)
    for name in os.listdir(CORE_DIR):
        item_path = os.path.join(CORE_DIR, name)
        if os.path.abspath(item_path) == keep_abs:
            continue
        try:
            if os.path.isdir(item_path):
                shutil.rmtree(item_path, ignore_errors=True)
            else:
                os.remove(item_path)
        except Exception:
            pass


def _safe_extract_zip(zip_ref, target_dir):
    target_dir_abs = os.path.abspath(target_dir)
    for member in zip_ref.infolist():
        member_path = os.path.abspath(os.path.join(target_dir_abs, member.filename))
        if not member_path.startswith(target_dir_abs + os.sep):
            raise Exception("压缩包包含非法路径")
    zip_ref.extractall(target_dir)


def _download_file(url, dest_path, controller=None, progress_callback=None):
    try:
        _download_file_curl(url, dest_path, controller)
        return
    except Exception as first_error:
        try:
            _download_file_urllib(url, dest_path, controller, progress_callback)
            return
        except Exception as second_error:
            try:
                _download_file_powershell(url, dest_path, controller)
                return
            except Exception as third_error:
                raise Exception(
                    f"curl失败: {first_error}; urllib失败: {second_error}; PowerShell失败: {third_error}"
                )


def _download_file_curl(url, dest_path, controller=None):
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
    referer = "https://www.ngrok.cc/"
    curl_cmds = [
        ["curl", "-L", "--fail", "-sS", "-o", dest_path, "-A", user_agent, "-e", referer, url],
        ["curl.exe", "-L", "--fail", "-sS", "-o", dest_path, "-A", user_agent, "-e", referer, url],
    ]
    last_error = None
    for cmd in curl_cmds:
        try:
            if controller and controller.stop_event.is_set():
                raise Exception("已取消下载")

            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if controller:
                controller.process = process

            while True:
                if controller and controller.stop_event.is_set():
                    try:
                        process.terminate()
                    except Exception:
                        pass
                    process.wait(timeout=5)
                    raise Exception("已取消下载")
                if process.poll() is not None:
                    break
                time.sleep(0.1)

            if process.returncode == 0:
                return

            stderr = process.stderr.read() if process.stderr else ""
            last_error = (stderr or "").strip()
        except Exception as e:
            last_error = str(e)
    raise Exception(last_error or "curl 返回错误")


def _download_file_urllib(url, dest_path, controller=None, progress_callback=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Referer": "https://www.ngrok.cc/"
    }
    if controller and controller.stop_event.is_set():
        raise Exception("已取消下载")

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        status = getattr(resp, "status", None)
        if status and status != 200:
            raise urllib.error.HTTPError(url, status, "Bad Status", resp.headers, None)
        total = resp.getheader("Content-Length")
        total = int(total) if total and total.isdigit() else None
        downloaded = 0
        with open(dest_path, "wb") as f:
            while True:
                if controller and controller.stop_event.is_set():
                    raise Exception("已取消下载")
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)


def _download_file_powershell(url, dest_path, controller=None):
    if controller and controller.stop_event.is_set():
        raise Exception("已取消下载")
    safe_url = url.replace("'", "''")
    safe_dest = dest_path.replace("'", "''")
    ps_script = (
        "$ProgressPreference='SilentlyContinue';"
        "$headers=@{ 'User-Agent'='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36'; 'Referer'='https://www.ngrok.cc/' };"
        f"Invoke-WebRequest -Uri '{safe_url}' -OutFile '{safe_dest}' -Headers $headers"
    )
    process = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", ps_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if controller:
        controller.process = process
    while True:
        if controller and controller.stop_event.is_set():
            try:
                process.terminate()
            except Exception:
                pass
            process.wait(timeout=5)
            raise Exception("已取消下载")
        if process.poll() is not None:
            break
        time.sleep(0.1)
    if process.returncode != 0:
        stderr = process.stderr.read() if process.stderr else ""
        stdout = process.stdout.read() if process.stdout else ""
        error_text = (stderr or stdout or "").strip()
        raise Exception(error_text or "PowerShell 返回错误")


class TunnelConfig:
    """隧道配置管理"""

    def __init__(self, config_file=TUNNELS_FILE):
        self.config_file = config_file
        self.tunnels = []
        self.load()

    def load(self):
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.tunnels = loaded if isinstance(loaded, list) else []
            except Exception as e:
                print(f"加载配置失败: {e}")
                self.tunnels = []
        else:
            self.tunnels = []
        self._ensure_ids()

    def _ensure_ids(self):
        changed = False
        for tunnel in self.tunnels:
            if isinstance(tunnel, dict) and not tunnel.get("id"):
                tunnel["id"] = str(uuid.uuid4())
                changed = True
        if changed:
            self.save()

    def save(self):
        """保存配置"""
        try:
            tmp_path = f"{self.config_file}.tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(self.tunnels, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.config_file)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False

    def add(self, name, server, key, auto_start=False):
        """添加隧道"""
        tunnel = {
            "id": str(uuid.uuid4()),
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
            tunnel_id = self.tunnels[index].get("id") or str(uuid.uuid4())
            self.tunnels[index] = {
                "id": tunnel_id,
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

    def get_by_id(self, tunnel_id):
        """通过ID获取隧道"""
        for tunnel in self.tunnels:
            if tunnel.get("id") == tunnel_id:
                return tunnel
        return None


class AppSettings:
    """应用程序设置管理"""

    def __init__(self, settings_file=SETTINGS_FILE):
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
            tmp_path = f"{self.settings_file}.tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.settings_file)
            return True
        except Exception as e:
            print(f"保存设置失败: {e}")
            return False

    def get(self, key, default=None):
        """获取设置"""
        return self.settings.get(key, default)

    def set(self, key, value):
        """设置保存"""
        self.settings[key] = value
        return self.save()


class TunnelProcess:
    """隧道进程管理"""

    def __init__(self, tunnel_id, tunnel_name):
        self.tunnel_id = tunnel_id
        self.tunnel_name = tunnel_name
        self.process = None
        self.running = False
        self.reader_thread = None
        self.logs = deque(maxlen=LOG_MAX_ENTRIES)  # 存储日志历史
        self._encoding = None
        self._encodings = self._build_encodings()

    def start(self, server, key, log_callback=None):
        """启动隧道"""
        if self.running:
            return False, "隧道已在运行中"

        try:
            cmd = None
            client_type = None
            exe_path = get_sunny_exe_path()

            if os.path.exists(exe_path):
                cmd = [
                    exe_path,
                    "-s", server,
                    "-k", key,
                    "-l", "stdout"
                ]
                client_type = "EXE版本"
            else:
                return False, ("找不到 core\\sunny.exe\n\n"
                             "请在启动时选择自动下载，或前往下载页：\n"
                             "https://www.ngrok.cc/download.html\n"
                             "下载后解压并将 sunny.exe 放入 core 文件夹。")

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
            if self.process and self.process.stdout:
                try:
                    self.process.stdout.close()
                except Exception:
                    pass
            if self.reader_thread and self.reader_thread.is_alive():
                self.reader_thread.join(timeout=1)
            self.process = None
            return True, "隧道已停止"
        except subprocess.TimeoutExpired:
            if self.process:
                self.process.kill()
            self.running = False
            if self.process and self.process.stdout:
                try:
                    self.process.stdout.close()
                except Exception:
                    pass
            if self.reader_thread and self.reader_thread.is_alive():
                self.reader_thread.join(timeout=1)
            self.process = None
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
                    if self._encoding:
                        try:
                            line = raw_line.decode(self._encoding).rstrip()
                        except Exception:
                            self._encoding = None

                    if line is None:
                        for encoding in self._encodings:
                            try:
                                line = raw_line.decode(encoding).rstrip()
                                self._encoding = encoding
                                break
                            except Exception:
                                continue

                    if line is None:
                        # 如果所有编码都失败，使用替换模式
                        fallback = self._encodings[0] if self._encodings else "utf-8"
                        line = raw_line.decode(fallback, errors='replace').rstrip()

                    if callback:
                        callback(line)
                if not self.running:
                    break
        except Exception as e:
            error_msg = f"日志读取错误: {str(e)}"
            if callback:
                callback(error_msg)

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
        return list(self.logs)

    def clear_logs(self):
        """清空日志"""
        self.logs = deque(maxlen=LOG_MAX_ENTRIES)

    def add_log(self, message, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append((timestamp, message))

    def _build_encodings(self):
        preferred = locale.getpreferredencoding(False)
        encodings = []
        for enc in [preferred, 'utf-8', 'gbk', 'gb2312', 'cp936']:
            if not enc:
                continue
            key = enc.lower()
            if key not in encodings:
                encodings.append(key)
        return encodings
