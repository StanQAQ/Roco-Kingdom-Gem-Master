# 洛克王国：魔法宝石

《洛克王国：魔法宝石》是一款以宠物卡、属性灵碎和魔法师卡为主题的四人策略桌游。你可以和三名 AI 对战，也可以观看四名 AI 自动对局。项目提供 Qt 桌面界面、命令行玩法和 Windows 单文件程序构建流程。

## 游戏玩法

- 每回合选择一项行动：领取资源、购买市场或预购区中的宠物卡，或预购一张市场宠物卡。
- 领取资源时，可以拿取三种不同属性各 1 枚，或拿取同一种属性 2 枚；后一种方式要求该属性公共资源池至少剩余 4 枚。玩家最多持有 10 枚资源，贤者碎晶也计入上限。
- 购买宠物卡会消耗对应属性资源。已购买的单属性宠物提供该属性的永久折扣；每次购买时，还可为每张已购双属性宠物选择其所属的一种属性作为本次折扣。
- 预购会从市场保留一张卡，并获得 1 枚贤者碎晶；每名玩家最多预购 3 张卡，之后可用资源购买预购卡。
- 单属性宠物会推进对应的属性专精门槛。水、火、草、萌、恶专精可能改变市场卡、取得资源、发动攻击或获得防御效果；双属性宠物不计入专精张数。
- 每回合结算时，玩家可能根据已购宠物的属性组合获得公开的魔法师卡，每张魔法师卡加 3 分。双属性宠物同时计入两种属性。
- 任一玩家达到 18 分时立即结束；如果公共市场全部耗尽，则完成本轮后结束。

游戏规则和卡池明细见[游戏说明](./洛克王国魔法宝石.md)及[卡片资料](./卡片.md)。

## 运行要求

- 命令行模式需要 Python 3.11 或更高版本
- Qt 图形界面建议使用 Python 3.12 或更高版本，并安装 PySide6

在项目根目录安装依赖：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## 启动游戏

启动桌面版：

```bash
python3 -m src.cli --gui
```

标题页面可选择单人模式、四 AI 对战或查看规则；单人模式还可选择简单或困难 AI。AI 名称为：简单模式“米米、米莎、米蒂”，困难模式“可丽希亚、菲尔特、卡普”。

GUI 会在选择对局模式后才生成本局随机种子；种子记录在本局行动记录中。可通过 `--seed` 固定种子以复现同一局。对局结束后可以查看战局或返回标题。

启动单人命令行对局：

```bash
python3 -m src.cli
```

在命令行模式下可使用 `水`、`火`、`草`、`萌`、`恶` 作为属性输入。

固定种子启动 GUI 或命令行：

```bash
python3 -m src.cli --gui --seed 42
python3 -m src.cli --seed 42
```

显式使用随机种子：

```bash
python3 -m src.cli --gui --random-seed
```

## AI 对战

快速运行一局四 AI 命令行对战：

```bash
python3 -m src.cli --ai-battle --random-seed --interval 0
```

在 GUI 中观看四 AI 对战：

```bash
python3 -m src.cli --gui --ai-battle --random-seed --interval 0.5
```

困难 AI 会综合当前卡片分数、魔法师卡进度、专精门槛和资源成本进行选择，并在攻击时考虑对手的免疫状态；简单 AI 的决策更随机、短视。

`--interval` 设置 AI 行动间隔秒数，不能小于 0。命令行参数说明：

```bash
python3 -m src.cli --help
```

常用参数：

| 参数 | 用途 |
|---|---|
| `--gui` | 启动 Qt 桌面界面 |
| `--seed N` | 使用固定种子，便于复现对局 |
| `--random-seed` | 明确要求使用随机种子 |
| `--ai-battle` | 启动四 AI 对战 |
| `--ai-only` | 运行无人操作的命令行对局 |
| `--interval N` | 设置 AI 行动间隔秒数 |

`--seed` 和 `--random-seed` 不能同时使用。GUI 未指定种子时默认使用随机种子；纯命令行未指定时会询问种子模式。

## Windows 单文件程序

在 Windows 电脑上安装 64 位 Python 3.12 和 Python Launcher，然后运行项目根目录中的 `build_windows_exe.bat`。打包完成后可直接运行：

```text
dist/Roco Kingdom Gem Master.exe
```

程序会将 `media` 资源一并打包，不需要另外安装 Python、PySide6 或复制资源目录。也可以在 GitHub Actions 中运行 `Build Windows EXE` 工作流并下载 `RocoKingdomGemMaster-Windows-x64` 构建产物。首次构建需要联网安装构建依赖。

## 音乐、音效与开源资源致谢

感谢开源软件和免费资源创作者，让本项目可以使用桌面界面、字体和游戏音效：

- [Python](https://www.python.org/) 与 [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/)：提供游戏运行环境和桌面 GUI 框架。
- [Kingnam Bobohei 字体项目](https://github.com/maoken-fonts/KNBobohei)：项目使用其字体文件；字体随项目附带的 [OFL 1.1 许可证](./media/fonts/LICENSE.txt) 分发。字体文件中的版权信息署名为 The Bobohei Project Authors。
- [Mixkit 免费音效](https://mixkit.co/free-sound-effects/)：购买音效来自 “Clinking coins”，预购音效来自 “Poker card flick”；项目中使用的是经过裁剪和音量调整的版本。Mixkit 的免费音效许可允许将音效用于游戏等成品，不能把素材本身作为独立素材重新分发；感谢 Mixkit 提供免费音效。详见 [Mixkit 音效许可](https://mixkit.co/license/modal/sfxFree/)。
- [Freesound：marbles，声音编号 63784](https://freesound.org/s/63784/)：资源获取音效使用其处理后的片段。感谢原作者和 Freesound 社区；该音频的具体许可应以原声音页面为准。

背景音乐和 WAV 音效由 Qt Multimedia 播放，可在对局右上角“设置 → 音量合成器”分别调节音量。该曲目的来源和授权信息尚未记录在仓库中；如计划公开分发游戏，请先确认使用与再分发许可。属性图标、零碎图标及其他项目素材的来源和授权范围也应以各自原始来源为准。

Linux 若提示 `libpulse.so.0` 缺失，可在 Debian/Ubuntu 安装 `libpulse0`；若 Qt Multimedia 仍不可用，可安装 `mpv`、`ffplay` 或 VLC 作为背景音乐播放器，并安装 `paplay`、`pw-play` 或 `aplay` 播放音效。

## 日志与问题排查

Qt 每局对战会单独写入 `logs/`，日志名以 `RocoKingdomGemMaster_` 开头，包含随机种子、玩家行动和专精结算记录。

若遇到 `No module named src`，请先切换到包含 `pyproject.toml` 和 `src/` 的项目根目录。Qt 图形界面请使用 Python 3.12+ 对应的虚拟环境；例如：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m src.cli --gui
```
