"""规则层与成就判定器之间传递的结构化对局事件。"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GameEvent:
    match_id: str
    sequence: int
    action_number: int
    event_type: str
    actor_index: int | None = None
    target_index: int | None = None
    card_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
