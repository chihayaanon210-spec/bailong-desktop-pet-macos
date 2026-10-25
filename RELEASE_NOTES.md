# 白龙桌宠 macOS 0.4.1-mac.3

这是独立社区适配的预发布版，面向 **Apple Silicon（arm64）Mac**。应用声明最低 macOS 12，目前只在 macOS 26.6.2 / Apple Silicon 实机验证；Intel Mac 不支持。

## 下载哪个文件

普通用户下载 **`BailongPet-Mac-0.4.1-mac.3-arm64.zip`**，解压后移动完整的 `BailongPet.app` 并打开。包内包含 Python、Qt、25 段透明动画和点击音效，无需另装 Python。不要将源码包或 GitHub 的 Source code 当作完整应用。

下载页：[当前 Release](https://github.com/chihayaanon210-spec/bailong-desktop-pet-macos/releases/tag/v0.4.1-mac.3) · [全部 Releases（含预发布版）](https://github.com/chihayaanon210-spec/bailong-desktop-pet-macos/releases)。发布附件中的校验文件可用于核对下载完整性。

应用使用 ad-hoc 签名，尚未获得 Developer ID 签名和 Apple 公证。确认来源与完整性后，按 macOS 正常的首次打开确认流程操作；具体见 [README](README.md#下载与安装) 和 [Apple 说明](https://support.apple.com/en-us/102445)。

## 本版内容

- 原版 25 段透明动画、随机互动、拖拽落地、气泡与菜单栏隐藏/唤回。
- Mac 后台浮窗持续显示、桌面空间支持、全屏自动隐藏适配。
- 本机 Codex 路径发现、只读额度查询、对话输入与历史界面。
- Mac 字体与 Command + Return 发送快捷键。
- 动画按需解码，128 MiB 像素缓存上限与最多 2 个解码器。
- 可选的随客户端自动启动功能，默认不启用登录监视器。

普通互动可以离线运行。额度与对话需要自己的 Codex 安装、登录和网络；对话消耗自己的额度。发布包不含发布者账号、凭证或聊天历史。

## 验证情况

75 项单元与离线回归测试通过，打包离线自检通过。用户实机确认显示、拖动、右键菜单和真实额度查询正常。

真实聊天任务、原生全屏、登录监视器及更早 macOS 仍未完成实机验收。完整范围见 [docs/TESTING.md](docs/TESTING.md)。

升级前先退出旧版桌宠；如果启用过登录监视器，应先关闭。替换应用不会主动删除 `~/Library/Application Support/BailongPetMac/` 中的本机数据。

原作者代码和素材归原权利人所有；此次发布授权不等于通用开源许可，见 [NOTICE](NOTICE.md)。
