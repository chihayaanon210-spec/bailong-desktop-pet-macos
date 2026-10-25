# 白龙桌宠 macOS 社区适配版

![白龙桌宠 Mac 版预览](docs/preview.png)

把白龙娘的透明动画、点击互动和拖动功能带到 Apple Silicon Mac。此项目基于 [jingh12312-rgb/bailong-desktop-pet](https://github.com/jingh12312-rgb/bailong-desktop-pet) v0.4.1 发布源码和素材进行适配，是独立的社区预发布版本，与 OpenAI 无隶属关系，也不表示原作者对本适配版作出背书。

**当前版本：`0.4.1-mac.3`。仅支持 Apple Silicon（arm64），不支持 Intel Mac。** 应用声明最低 macOS 12；目前只在 macOS 26.6.2 / Apple Silicon 上完成实机验证，更早系统尚未实机验证。

## 下载与安装

[下载 Mac 应用](https://github.com/chihayaanon210-spec/bailong-desktop-pet-macos/releases/tag/v0.4.1-mac.3) · [查看全部 Releases（含预发布版）](https://github.com/chihayaanon210-spec/bailong-desktop-pet-macos/releases)

1. 在 Releases 的 Assets 中下载 **`BailongPet-Mac-0.4.1-mac.3-arm64.zip`**。普通使用者不需要下载源码包或 GitHub 自动生成的 Source code。
2. 解压 ZIP，把完整的 `BailongPet.app` 放进个人应用程序目录（`~/Applications`）或其他固定位置。
3. 双击打开。应用包含 Python、Qt、25 段动画和点击音效，无需另装 Python。

这是临时签名（ad-hoc）构建，尚未取得 Apple Developer ID 签名或 Apple 公证。首次打开时，macOS 可能要求额外确认。先确认下载来自本项目的 Release，并按其中的校验文件核对完整性；如果系统提示无法验证开发者，在尝试打开后前往“系统设置 → 隐私与安全性”，为这个应用选择“仍要打开”，再完成系统确认。具体界面见 [Apple 的打开应用说明](https://support.apple.com/en-us/102445)。如果提示应用会损坏电脑或文件已损坏，应停止并检查下载来源与完整性。

## 怎么使用

| 操作 | 效果 |
| --- | --- |
| 单击桌宠 | 随机互动与台词 |
| 双击桌宠 | 只读查询自己的 Codex 剩余额度 |
| 按住左键拖动 | 播放拖拽动作；松手播放落地动画 |
| 右键桌宠 | 选择动画、开关对话、查看历史、隐藏、开关全屏自动隐藏或退出 |
| 点击 macOS 菜单栏的桌宠图标 | 从菜单唤回已隐藏的桌宠 |
| 对话中按 Command + Return | 发送；Return 换行 |

共保留 25 段原版透明动画：2 套待机、15 个互动、5 个工作动作，以及查询、拖拽和落地动画。动画按需解码，像素缓存上限为 128 MiB，同时最多保留 2 个解码器；这不是整个应用的内存占用上限。

桌宠会留在其他应用上方，并支持多个桌面空间。全屏自动隐藏默认开启，可在右键菜单关闭；手动隐藏后，可从菜单栏图标选择“显示桌宠”。退出请使用菜单中的“退出桌宠”。

## Codex 额度与对话

普通动画互动可以离线使用。额度查询和对话需要在本机安装并登录自己的 Codex 客户端，并保持网络可用；对话使用自己的 Codex 额度。只登录 ChatGPT 网页不等于本机 Codex 已登录。

适配版会查找本机 Codex 命令，以及 `Codex.app` 或 Bundle ID 为 `com.openai.codex` 的 `ChatGPT.app` 中的命令。也可用 `BAILONG_CODEX` 环境变量指定可执行文件。经典 ChatGPT 应用与 Codex 客户端不同。

对话功能保留原有任务文件夹选择、进度、历史和审批界面。发送任务前，请选好任务文件夹；后续执行由本机 Codex 及其权限控制。发布包不包含发布者账号、登录凭证、额度或聊天记录。

## 设置与本机数据

偏好、历史、运行状态与诊断日志位于：

```text
~/Library/Application Support/BailongPetMac/
```

动画资源在应用包内，运行时不修改已签名的应用。历史会保留在本机；删除应用不会自动删除这些数据。`BAILONG_DATA_DIR` 可覆盖数据目录，便于开发和离线测试。

全屏检测读取窗口边界信息，不采集屏幕图像，也不要求屏幕录制或辅助功能权限。

## 可选：随客户端自动启动

默认不会创建登录监视器。若应用放在 `~/Applications`，可在普通用户终端中启用：

```bash
"$HOME/Applications/BailongPet.app/Contents/MacOS/BailongPet" --enable-autostart
```

关闭：

```bash
"$HOME/Applications/BailongPet.app/Contents/MacOS/BailongPet" --disable-autostart
```

这个可选功能仍属实验功能：登录后在后台等待，检测到支持的客户端从未运行变为运行时启动桌宠。仅关闭客户端窗口不等于退出客户端。移动或删除应用前应先关闭此功能；安装在其他位置时，请使用相应应用路径。

## 验证范围与已知限制

75 项单元与离线回归测试通过，打包后的离线自检通过。本机用户已确认显示、拖动、右键菜单和真实额度查询正常。

真实聊天任务尚未验收；原生全屏场景、可选登录监视器和更早版本 macOS 尚未完成实机验证。测试结果与复现步骤见 [测试说明](docs/TESTING.md)，版本变化见 [CHANGELOG](CHANGELOG.md)。

## 从源码构建

使用 Apple Silicon Mac 和 Python 3.12，在项目目录执行：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pyinstaller==6.22.3
.venv/bin/python scripts/fetch_assets.py
bash scripts/build-macos.sh
```

素材下载脚本从原作者 v0.4.1 发布包提取构建所需文件，不运行 Windows 程序。动画不放入 Git 历史；完成提取后才可构建完整应用。默认输出为 `dist/BailongPet.app`。

建议在普通本地文件夹构建；云盘文件提供器可能给 Qt 插件附加隐藏标记，影响插件发现。构建脚本会处理 Qt 插件的这类标记。可用 `BAILONG_BUILD_PYTHON` 指定构建解释器，用 `BAILONG_DIST_DIR` 指定输出位置。

## 来源与许可

发布者已确认取得此次公开再分发改编源码和角色素材所需的授权。该授权不等于为原作者全部代码与美术授予通用开源许可，也不表示获得官方背书。本项目未为原作者代码与美术统一套用 MIT 等许可证；来源、第三方许可和再利用说明见 [NOTICE](NOTICE.md) 与 [ASSETS](ASSETS.md)。
