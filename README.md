# onlyoffice-custom

ONLYOFFICE Desktop Editors 定制优化补丁集与 GitHub Actions 自动打包仓库（当前已支持 macOS `x86_64` 与 `arm64` 自动构建发布，仓库结构按跨平台子模块补丁组织，后续可直接扩展 Windows / Linux 构建工作流）。

基于上游官方发行版采用**增量叠加构建（Overlay Build）**：不重编庞大的 `core` 内核（直接复用同版本官方安装包中的 `x2t`、`converter` 动态库、`CEF` 与界面资源），仅对修改涉及的 `desktop-sdk`、`desktop-apps`、`web-apps` 打补丁重编并重新打包。

## 功能与修复清单

1. **可配置的「自定义字体目录」**（`设置 → 常规 → 自定义字体目录 *`）
   - 无任何硬编码私人路径；仅加载用户在设置项中明确配置的目录（支持 `~/...` 展开及 `;` 分隔多个目录，留空则仅使用系统与内置字体，变更后自动重建字体缓存）。
   - 支持直接输入路径或点击右侧 **「浏览」** 调用原生文件夹选择框。
2. **简体中文界面修正**
   - 修正底栏 `縮放 → 缩放`、`設定文字語言 → 设置文本语言`，以及全套 `web-apps` / macOS 菜单中 100+ 处繁体字残留与错译（如 `XY散佈圖 → XY（散点图）`、`反正切函數 → 反余切函数`、`Right to Left` 误译等）。
   - 修复 `Localizable.stringsdict` 复数占位符 `%#@days@` / `%#@documents@` 被机翻导致退出多文档未保存弹窗显示 `#@文档@` 的问题。
3. **拼写检查设置持久化**
   - 修复首页「拼写语言检测」（自动 / 已启用 / 已停用）三态保存与重启读回不一致的问题；运行中关闭语言检测立即对已打开文档生效。
   - 修复编辑器 `LocalStorage.getBool` 将 `"false"` / `"off"` 误判为开启的问题。
4. **修复底栏文本语言无故跳回英文**
   - 修复 macOS 简繁输入法（`zh-Hans` / `zh-Hant`）缺少地区子标签导致映射为中性 LCID `0x0004` 的问题（现正确映射为 `0x0804` / `0x0404`）。
   - 修复在设置页点击「应用」后新建空白文档回退到 `en-US` 英文模板的问题；关闭自动更新检查以免被官方版覆盖。

## 下载与安装

1. 前往本仓库 [**Releases**](../../releases) 按芯片下载最新的 DMG：Intel 芯片选 `ONLYOFFICE-v*-macos-x86_64-custom.dmg`，Apple Silicon（M 系列）选 `ONLYOFFICE-v*-macos-arm64-custom.dmg`。
2. 打开 DMG 将 `ONLYOFFICE.app` 拖入 `/Applications`。
3. 因采用本地 ad-hoc 签名（未做 Apple 公证），首次打开若提示无法验证开发者，在终端执行一次：
   ```sh
   xattr -cr /Applications/ONLYOFFICE.app
   ```
4. 如需加载额外字体目录，启动后进入 **设置 → 常规 → 自定义字体目录 \*** 选择文件夹并点击「应用」重启即可。

## 使用 GitHub Actions 自动构建 / 升级新版本

1. 打开仓库 **Actions → Build ONLYOFFICE macOS → Run workflow**。
2. 填入上游版本号（如 `v10.0.0`，未来上游发布新版时填 `v10.1.0` 等），勾选 `publish_release` 点击运行。
3. 流水线按 matrix 并行构建 Intel（`macos-15-intel`）与 Apple Silicon（`macos-15`）两个架构：自动拉取对应 Tag 源码、应用 `patches/*.patch`（开启 `--3way` 三方合并）、编译增量模块并产出两份 `.dmg` 一并发布到 Releases。
   - 若未来某次上游版本升级导致某个补丁报冲突，只需按需浅克隆冲突的单个子仓库（如 `git clone --depth 1 --branch v10.1.0 https://github.com/ONLYOFFICE/desktop-apps.git`），解决冲突后导出更新对应的 `patches/*.patch` 即可。

## 许可证

遵循上游 [GNU AGPL v3.0](https://www.gnu.org/licenses/agpl-3.0.html) 协议。
