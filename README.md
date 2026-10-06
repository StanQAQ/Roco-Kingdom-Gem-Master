# 洛克王国：魔法宝石

一个使用 Python 实现的四人策略桌游原型。玩家通过获取属性灵碎、购买宠物和积累永久折扣构建资源引擎，并可触发水、火、草、萌、恶五种属性专精效果。

## 运行环境

- Python 3.11 或更高版本
- 图形界面需要 Python 的 Tkinter 支持，建议 Tk 8.6 或更新版本
- 游戏本体不需要安装第三方依赖

在项目根目录中确认 Python 版本：

```bash
python3 --version
python3 -c "import tkinter; print('Tk', tkinter.TkVersion)"
```

## 启动图形界面

推荐使用图形界面进行人机对战：

```bash
python3 -m src.cli --gui
```

如果未传入种子参数，程序会在终端中询问使用固定种子还是随机种子。

指定随机种子，便于重现同一组初始市场：

```bash
python3 -m src.cli --gui --seed 42
```

每次启动时自动生成新种子：

```bash
python3 -m src.cli --gui --random-seed
```

随机模式会在终端、GUI 顶部和对局日志中显示本局实际种子。之后使用 `--seed 数值` 即可复现该局的初始牌序。GUI 内的“重新开始”会继续使用当前种子。

图形界面中：

1. 从右侧选择获取三种灵碎或两枚同种灵碎。
2. 点击市场宠物，再选择购买或预购。
3. 购买双属性宠物后，每次购买前选择其本次提供的折扣属性。
4. 单属性宠物达到 2 张和 3 张时，界面会引导结算对应的属性专精。

## 启动命令行游戏

玩家对战三名 AI：

```bash
python3 -m src.cli
```

使用固定随机种子：

```bash
python3 -m src.cli --seed 42
```

命令行会显示市场、资源、分数和可用操作。属性输入使用中文字符：`水`、`火`、`草`、`萌`、`恶`。

## 四 AI 自动对战

在终端中快速运行一局：

```bash
python3 -m src.cli --ai-battle --random-seed --interval 0
```

以 0.5 秒的行动间隔观察对局：

```bash
python3 -m src.cli --ai-battle --seed 1 --interval 0.5
```

在图形界面中观察四 AI 对战：

```bash
python3 -m src.cli --gui --ai-battle --random-seed --interval 0.5
```

`--interval` 不能小于 0。如果不传入该参数，程序会在启动时询问行动间隔。

## 命令行参数

```bash
python3 -m src.cli --help
```

| 参数 | 用途 |
|---|---|
| `--seed N` | 使用指定的固定种子 |
| `--random-seed` | 每次启动时自动生成新种子 |
| `--gui` | 启动 Tkinter 图形界面 |
| `--ai-battle` | 启动四 AI 自动对战 |
| `--ai-only` | 直接运行无人操作的命令行对局 |
| `--interval N` | 设置 AI 每次行动的间隔秒数 |

`--seed` 和 `--random-seed` 不能同时使用。两者都未传入时，程序会交互询问开局方式；选择固定种子后直接回车，默认使用种子 `1`。

## 运行测试

先安装 pytest：

```bash
python3 -m pip install pytest
```

运行全部测试：

```bash
python3 -m pytest -q
```

测试覆盖基础资源规则、购买与预购、游戏结束条件，以及五种属性专精效果。

## 日志

图形界面会为每局对战创建独立日志，保存在：

```text
logs/magic_gems_YYYYMMDD_HHMMSS_microseconds.log
```

日志包含玩家行动、属性专精触发与结算结果，可用于还原问题或进行数值分析。

## 常见问题

### 提示 `No module named src`

请确认终端当前位于项目根目录，也就是包含 `pyproject.toml` 和 `src` 目录的位置。

### 提示 `No module named tkinter`

当前 Python 没有携带 Tkinter。请安装带 Tk 支持的 Python，或通过操作系统包管理器安装 Tkinter。命令行模式不依赖 Tkinter。

### macOS 中图形窗口未出现

可先检查 Tkinter 是否能正常启动：

```bash
python3 -m tkinter
```

如果该命令也无法打开窗口，请更换为包含 Tk 支持的 Python 安装。
macOS 自带的 `/usr/bin/python3` 可能仍是 Python 3.9 / Tk 8.5；它不满足本项目的 Python 3.11+ 要求，滚动界面也可能出现绘制重影。请用满足上述版本要求的解释器运行，例如本机已安装的 `python -m src.cli --gui`，并先用 `python --version` 和 `python -c "import tkinter; print(tkinter.TkVersion)"` 确认版本。

## 项目资料

完整玩法、卡池数值和设计思路见 [`洛克王国璀璨宝石.md`](./洛克王国璀璨宝石.md)。
