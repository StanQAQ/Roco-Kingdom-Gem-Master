from __future__ import annotations

import secrets
from collections.abc import Callable


MAX_SEED = 2**32 - 1


def generate_random_seed() -> int:
    """生成可显示、可复现的 32 位随机种子。"""
    return secrets.randbelow(MAX_SEED + 1)


def prompt_for_seed(input_func: Callable[[str], str] = input) -> tuple[int, str]:
    """在终端中让玩家选择固定或随机开局。"""
    while True:
        mode = input_func("开局方式 [f=固定种子, r=随机种子]（默认 f）：").strip().lower()
        if mode in {"", "f", "fixed", "固定"}:
            raw_seed = input_func("输入固定种子（默认 1）：").strip()
            if not raw_seed:
                return 1, "fixed"
            try:
                return int(raw_seed), "fixed"
            except ValueError:
                print("种子必须是整数，请重新选择。")
                continue
        if mode in {"r", "random", "随机"}:
            return generate_random_seed(), "random"
        print("请输入 f 或 r。")


def select_seed(fixed_seed: int | None, random_requested: bool) -> tuple[int, str]:
    """优先使用启动参数；未传参时进入交互选择。"""
    if fixed_seed is not None:
        return fixed_seed, "fixed"
    if random_requested:
        return generate_random_seed(), "random"
    return prompt_for_seed()


def seed_description(seed: int, mode: str) -> str:
    label = "随机" if mode == "random" else "固定"
    return f"{label}种子：{seed}"
