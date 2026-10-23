# 最终运行模型

本目录保存 `training_runs/ACCEPTED_MASTER_MODEL.json` 登记的最终四场景 ONNX 权重，
来源为 `master-v2-confirm-20261023-02/delivery/scenarios_cpu/models/`。
`scenarios.json` 使用相对路径和 SHA256 校验，不依赖本地训练目录。
20 和 30 回合场景使用相同权重；保留独立文件以对应各自的场景。

仅保留运行权重、场景清单、特征编码和 CPU 推理代码。
训练脚本、方案、过程记录、数据集、检查点和训练环境保留在本地，不纳入新的 Git 提交。
已经存在于 Git 历史中的训练文件不因忽略规则而从历史中消失。

## 运行

在项目根目录使用 Python 3.12 或更高版本：

```powershell
python -m pip install -r requirements-inference.txt
python -m training.scenario_inference --manifest models/master/scenarios.json --max-rounds 10 --target 20 --games 1
```

`--max-rounds` 支持 `unlimited`、`10`、`20`、`30`，`--target` 支持 15 至 50。
推理只使用 CPU、NumPy 和 ONNX Runtime，不需要 PyTorch、CUDA 或 API 密钥。
该入口运行独立无界面对局检查，不会自动替换 GUI 中的 DeepSeek 大师模式。

在已有 `Game` 对局中调用：

```python
from training.scenario_inference import ScenarioPolicy

policy = ScenarioPolicy("models/master/scenarios.json")
action = policy.choose_action(game)
```

模型按 `game.max_rounds` 选择，加载时校验权重 SHA256 和特征版本。
本目录不包含训练或强度验收报告；清单中的历史状态沿用已选定交付包，
本次整理仅检查权重一致性及推理运行，不重新进行强度验收。
