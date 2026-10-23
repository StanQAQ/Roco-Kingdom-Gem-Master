# 洛克王国：魔法宝石

《洛克王国：魔法宝石》是一款以宠物卡、属性灵碎和魔法师卡为主题的四人策略桌游。你可以和三名 AI 对战，也可以观看四名 AI 自动对局。项目提供 Qt 桌面界面、命令行玩法和 Windows 单文件程序构建流程。

## 游戏玩法

- 每回合选择一项行动：领取资源、购买市场或预购区中的宠物卡，或预购一张市场宠物卡。
- 领取资源时，可以拿取三种不同属性各 1 枚，或拿取同一种属性 2 枚；后一种方式要求该属性公共资源池至少剩余 4 枚。玩家最多持有 10 枚资源，贤者碎晶也计入上限。
- 购买宠物卡会消耗对应属性资源。已购买的单属性宠物提供该属性的永久折扣；每次购买时，还可为每张已购双属性宠物选择其所属的一种属性作为本次折扣。
- 自己的回合中，可拖动已购买的双属性宠物卡到它的任一属性栏，调整当前折扣属性；购买时也可重新选择。
- 预购会从市场保留一张卡，并获得 1 枚贤者碎晶；每名玩家最多预购 3 张卡，之后可用资源购买预购卡。
- 单属性宠物会推进对应的属性专精门槛。水、火、草、萌、恶专精可能改变市场卡、取得资源、发动攻击或获得防御效果；双属性宠物不计入专精张数。
- 每局随机公开 5 张魔法师卡，玩家可在回合结算时根据已购宠物的属性组合获得，每张加 3 分；获得后保留原卡位为空，本局不再补充。双属性宠物同时计入两种属性。
- 所有一级宠物的基础分数均为 0 分，仍可通过属性专精改变分数。对局结算会显示当前玩家本局新达成的成就。
- “做题区”成就：一局内获得五张魔法师卡；获得第五张时立即解锁，不要求赢得对局。
- 胜负只在整轮结束后结算：轮末仍有至少 20 分的玩家才有获胜资格，资格玩家中最高分者获胜，并列则共同获胜。若无人达标且公共市场未耗尽，则继续游戏；市场耗尽时本轮结束后结束对局，若无人达到 20 分则无人获胜。

游戏规则和卡池明细见[游戏说明](./洛克王国魔法宝石.md)及[卡片资料](./卡片.md)。

## 运行要求

- 命令行模式需要 Python 3.11 或更高版本
- Qt 图形界面建议使用 Python 3.12 或更高版本，并安装 PySide6 与 PySide6-Addons（包含 Qt Multimedia）

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

普通 GUI 启动后先在游戏窗口输入昵称。已有昵称会载入本机账号，新昵称会建立独立档案；首页右上角显示“当前玩家：昵称”，单人对局中显示玩家昵称。首页的“退出登录”会返回昵称输入页，但不会删除账号文件。账号以明文 JSON 保存在系统用户数据目录的 `RocoKingdomGemMaster/profile/`，账号仅凭本机昵称识别，没有密码和云同步。新账号首次登录时会收到新手教程邀请；首页“规则介绍”页面也提供“新手教程”入口，可随时重开。教程使用简单 AI 的独立随机对局。开局提供欢迎介绍、获取零碎、预购卡片和胜利结算四页；首次能够购买卡片、首次获得宠物卡、首次触发属性专精、首次获得魔法师卡时，会按固定顺序加入对应规则页并切换到新页。玩家可翻页查看已解锁内容；提示会保留到完成行动，不限制合法行动。教程对局同样记录成就。

标题页面可选择单人模式、规则介绍、音量设置、退出登录或退出游戏。“规则介绍”内可查看游戏规则、属性专精细则并开启新手教程，均在主窗口内显示；对局内的“规则速查”和属性专精入口仍使用原有弹窗。单人模式可选择简单或困难 AI。四 AI 对战只能通过命令行参数启动，不要求玩家账号。AI 名称为：简单模式“米米、米莎、米蒂”，困难模式“可丽希亚、菲尔特、卡普”。

点击“开始游戏”后选择“标准模式”或“自定义模式”。标准模式继续提供简单、困难两种难度。自定义模式可设置目标分数（15–50，默认20，支持左右加减和键盘输入）、最大回合数（不限/10/20/30）、AI 难度（简单/困难/大师）、玩家行动顺序（1/2/3/4/随机），以及勾选后输入整数固定种子。大师模式由三个 DeepSeek 对手参与，需要预先配置 `.env.deepseek`；请求失败时由本地困难 AI 接管。玩家状态列表按实际行动顺序排列，玩家显示在所选顺位。达到目标分数后于整轮结束结算；达到回合上限时，所有玩家中最高分者获胜，并列共同获胜。重新开始会保留自定义规则；使用固定种子时可复现初始牌局和随机行动顺序。

GUI 会在选择对局模式后才生成本局随机局编号；随机模式使用操作系统提供的密码学随机源，编号不会暴露或推算随机状态。随机对局不能仅凭编号复现；需要复现时使用 `--seed` 固定种子。对局结束后可以查看战局或返回标题。

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

最终本地 ONNX 模型及 CPU 推理用法见 [最终运行模型](models/master/README.md)。模型可独立运行，尚未接入 GUI 的大师模式；训练过程、检查点和方案仅保留在本地。

四 AI 对战没有游戏标题页入口，只能通过命令行启动。运行命令行对战：

```bash
python3 -m src.cli --ai-battle --random-seed --interval 0
```

也可以通过命令行参数启动 Qt 界面观看自动对战：

```bash
python3 -m src.cli --gui --ai-battle --random-seed --interval 0.5
```

先在项目根目录的 `.env.deepseek` 文件中填写 `DEEPSEEK_API_KEY`。让 DeepSeek 控制其中一个座位，其余座位仍由现有困难 AI 控制：

```bash
python3 -m src.cli --gui --ai-battle --deepseek-player 1 --random-seed --interval 0.5
```

`--deepseek-player` 可选 `1` 至 `4`。若希望四个 AI 座位都由 DeepSeek 决策，则改用 `--deepseek-all`：

```bash
python3 -m src.cli --gui --ai-battle --deepseek-all --random-seed --interval 0.5
```

命令行四 AI 对战也可使用 `--deepseek-all`。每次轮到 DeepSeek 且存在多个可选行动时，游戏会向 DeepSeek API 发送本回合局面和候选行动；若规则只剩唯一行动，则直接执行，不额外发请求。返回值只接受行动编号，请求在后台执行，不阻塞游戏界面。未配置密钥时无法启动 DeepSeek 模式；单个座位请求失败后，该座位在本局后续由现有困难 AI 接管，其他座位仍独立请求 DeepSeek。密钥文件已加入忽略规则，不会随 Git 提交。

DeepSeek 请求会附带更详细的规则说明和决策目标。局面信息包括：当前轮次、行动玩家及座位、是否已触发终局；公共资源；每位玩家的分数、资源总量/上限、单属性卡专精进度、永久折扣汇总、双属性卡数量、魔法师属性进度、已购卡、魔法师卡和待触发效果；当前玩家的预购卡详情（其他玩家只发送预购数量）；公开市场卡、公开魔法师卡和完整的待结算专精队列。合法购买选项还包含支付明细、购买后剩余资源和即时得分。为控制请求规模，每张可购买卡只附带本地挑选的一个优惠支付方案。不会发送随机种子、未来牌堆顺序或其他玩家预购卡身份。API 密钥通过 HTTPS 请求头传输，不写进提示词。

DeepSeek 返回 OpenAI 兼容的 Chat Completions JSON 响应；游戏只读取其中的消息文本，并要求它是 `{"action_id":"A<n>"}` 格式。编号会与本地合法行动列表核对，通过后才执行；响应中的其他字段不参与游戏决策。

命令行四 AI 对战的单席模式也可使用同一参数：

```bash
python3 -m src.cli --ai-battle --deepseek-player 1 --random-seed --interval 0
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
| `--deepseek-player 1-4` | 将指定 AI 座位交给 DeepSeek |
| `--deepseek-all` | 将全部四个 AI 座位交给 DeepSeek |
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

背景音乐和 WAV 音效由 Qt Multimedia 播放，可在对局右上角“设置 → 音量合成器”分别调节音量。macOS 背景音乐使用 Qt/AVFoundation 播放器，支持播放过程中即时调节；请通过 `python -m pip install -e .` 安装包含 Qt Multimedia 的项目依赖，不使用只能在启动时设定音量的 `afplay`。该曲目的来源和授权信息尚未记录在仓库中；如计划公开分发游戏，请先确认使用与再分发许可。属性图标、零碎图标及其他项目素材的来源和授权范围也应以各自原始来源为准。

Linux 若提示 `libpulse.so.0` 缺失，可在 Debian/Ubuntu 安装 `libpulse0`；若 Qt Multimedia 仍不可用，可安装 `mpv`、`ffplay` 或 VLC 作为背景音乐播放器，并安装 `paplay`、`pw-play` 或 `aplay` 播放音效。

## 日志与问题排查

Qt 每局对战会单独写入 `logs/`，日志名以 `RocoKingdomGemMaster_` 开头，包含随机局编号（或固定种子）、玩家行动和专精结算记录。随机模式使用系统随机源，固定种子模式使用可复现的伪随机序列。

若遇到 `No module named src`，请先切换到包含 `pyproject.toml` 和 `src/` 的项目根目录。Qt 图形界面请使用 Python 3.12+ 对应的虚拟环境；例如：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m src.cli --gui
```
