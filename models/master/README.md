# 最终运行模型

本目录保存 `training_runs/ACCEPTED_MASTER_MODEL.json` 登记的最终四场景 ONNX 权重，
以及独立的 PPO48 困难模式权重；四场景来源为 `master-v2-confirm-20261023-02/delivery/scenarios_cpu/models/`。
`scenarios.json` 使用相对路径和 SHA256 校验，不依赖本地训练目录。
20 和 30 回合场景使用相同权重；保留独立文件以对应各自的场景。

仅保留运行权重、场景清单、特征编码和 CPU 推理代码。
训练脚本、方案、过程记录、数据集、检查点和训练环境保留在本地，不纳入新的 Git 提交。
已经存在于 Git 历史中的训练文件不因忽略规则而从历史中消失。

## 运行

在项目根目录使用 Python 3.12 或更高版本：

```powershell
python -m pip install -r requirements-inference.txt
python -m training.scenario_inference --manifest models/scenarios.json --max-rounds 10 --target 20 --games 1
```

`--max-rounds` 支持 `unlimited`、`10`、`20`、`30`，`--target` 支持 15 至 50。
推理只使用 CPU、NumPy 和 ONNX Runtime，不需要 PyTorch、CUDA 或 API 密钥。
该命令运行独立无界面对局检查。GUI 的自定义大师模式也通过统一清单
`models/scenarios.json` 按最大回合数选择这四个模型，无需 DeepSeek API 密钥。

困难模式使用独立的 PPO48 权重，必须显式指定 `--difficulty hard`；它不依赖
`--max-rounds`，也不会覆盖四个回合场景模型。例如：

```powershell
python -m training.scenario_inference --manifest models/scenarios.json --difficulty hard --target 20 --games 1
```

在已有 `Game` 对局中调用：

```python
from training.scenario_inference import ScenarioPolicy

policy = ScenarioPolicy("models/scenarios.json")
action = policy.choose_action(game)
# 困难模式显式选择 PPO48；四场景模式仍按 game.max_rounds 路由。
hard_action = policy.choose_action(game, difficulty="hard")
```

模型按 `game.max_rounds` 选择，加载时校验权重 SHA256 和特征版本。
困难模式按 `difficulty="hard"` 选择，使用同一套 676 维局面编码和 45 维候选动作接口，
并独立校验 PPO48 的 SHA256。四个场景模型和困难模式模型每次只加载当前路由所需的一个权重。
GUI 的标准困难模式和自定义困难模式均使用这一 PPO48 路由。
本目录不包含训练或强度验收报告；清单中的历史状态沿用已选定交付包，
本次整理仅检查权重一致性及推理运行，不重新进行强度验收。
