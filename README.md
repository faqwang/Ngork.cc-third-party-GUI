# Sunny-Ngrok GUI 管理器

一个基于 Python + Tkinter 的图形化管理工具，用于管理 Sunny-Ngrok 内网穿透隧道。

## 功能特性

✅ **隧道配置管理** - 保存和管理多个隧道配置，快速切换
✅ **一键启动/停止** - 图形化按钮控制隧道的启动和停止
✅ **实时日志显示** - 在 GUI 中实时查看 sunny.exe 的输出日志
✅ **开机自启动** - 支持设置程序和隧道开机自动启动
✅ **系统托盘支持** - 最小化到系统托盘，后台运行（需安装可选依赖）

## 系统要求

- Windows 7 或更高版本
- Python 3.7 或更高版本
- sunny.exe（Sunny-Ngrok 客户端）

## 快速开始

### 1. 安装 Python（如果尚未安装）

从 [Python 官网](https://www.python.org/downloads/) 下载并安装 Python 3.7+

安装时请勾选 "Add Python to PATH"

### 2. 下载 Sunny Ngrok 

从 [Sunny 官网](https://www.ngrok.cc/download.html) 下载解压文件到根目录，二进制文件名sunny.exe


### 3. 启动 GUI 管理器

双击运行 `启动GUI管理器.bat`

或者在命令行中运行：
```bash
python ngrok_gui.py
```

### 3. 添加隧道配置

1. 点击左侧的 "添加" 按钮
2. 填写隧道信息：
   - **隧道名称**: 自定义名称，便于识别
   - **服务器地址**: 例如 `xxxx.xxx.com:443`
   - **隧道密钥**: 从 www.ngrok.cc 管理后台获取
   - **开机自动启动**: 勾选后该隧道会在程序启动时自动运行
3. 点击 "确定" 保存

### 4. 启动隧道

1. 在左侧列表中选择一个隧道
2. 点击右侧的 "启动隧道" 按钮
3. 在日志区域查看运行状态

## 可选功能

### 系统托盘支持

如需使用系统托盘功能（最小化到托盘），请安装可选依赖：

```bash
pip install -r requirements.txt
```

或手动安装：
```bash
pip install pystray Pillow
```

安装后，可通过 "设置" -> "最小化到托盘" 将程序最小化到系统托盘。

### 开机自启动

通过 "设置" -> "开机自启动" 菜单可以设置程序开机自动启动。

## 使用说明

### 隧道管理

- **添加隧道**: 点击 "添加" 按钮，填写隧道信息
- **编辑隧道**: 选择隧道后点击 "编辑" 按钮
- **删除隧道**: 选择隧道后点击 "删除" 按钮

### 隧道控制

- **启动隧道**: 选择隧道后点击 "启动隧道" 按钮
- **停止隧道**: 点击 "停止隧道" 按钮
- **查看日志**: 实时日志会显示在右侧日志区域
- **清空日志**: 点击 "清空日志" 按钮

### 配置文件

隧道配置保存在 `tunnels.json` 文件中，格式如下：

```json
[
  {
    "name": "我的隧道",
    "server": "xxx.xxx.com:443",
    "key": "your_tunnel_key",
    "auto_start": false
  }
]
```

## 常见问题

### Q: 提示找不到 sunny.exe

**A**: 请确保 `ngrok_gui.py` 和 `sunny.exe` 在同一目录下。

### Q: 启动失败，提示编码错误

**A**: 确保使用 UTF-8 编码保存配置文件，或重新通过 GUI 添加隧道。

### Q: 系统托盘功能不可用

**A**: 需要安装可选依赖：`pip install pystray Pillow`

### Q: 如何获取隧道密钥？

**A**: 登录 [www.ngrok.cc](https://www.ngrok.cc) 管理后台，在隧道管理页面可以看到每个隧道的密钥（key）。

## 技术说明

- **GUI 框架**: Tkinter（Python 内置）
- **进程管理**: subprocess 模块
- **配置存储**: JSON 格式
- **日志显示**: 实时读取进程输出流

## 文件说明

- `ngrok_gui.py` - 主程序文件
- `StartGUI.bat - Windows 启动脚本
- `tunnels.json` - 隧道配置文件（自动生成）
- `requirements.txt` - 可选依赖列表
- `sunny.exe` - Sunny-Ngrok 客户端程序

## 许可证

本 GUI 管理器为开源工具，仅用于方便管理 Sunny-Ngrok 客户端。

Sunny-Ngrok 服务由 www.ngrok.cc 提供，请遵守其服务条款。

## 支持

- Sunny-Ngrok 官网: [www.ngrok.cc](https://www.ngrok.cc)
