# 困难模式 PPO48

`ppo48.onnx` 为独立的原通用 PPO 第 48 轮模型。
SHA256：`b83c7519c4b2d8d55f231d5879a85b2354028ec2102813532f3cc68d71e0418a`。
局面输入 676 维，每个候选动作 45 维。

在仓库根目录运行：

```powershell
python -m training.scenario_inference --manifest models/scenarios.json --difficulty hard --games 1
```

统一路由清单位于 `models/scenarios.json`；四场景大师权重位于 `models/master/`。
