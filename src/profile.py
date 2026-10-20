"""本机玩家档案：每个账号独立保存为明文 JSON。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
from typing import Callable
import unicodedata


SCHEMA_VERSION = 1
MIN_PLAYER_ID = 10_000_000
PLAYER_ID_COUNT = 90_000_000
PLAYER_ID_PATTERN = re.compile(r"[1-9][0-9]{7}\Z")
RESERVED_NICKNAMES = frozenset(
    name.casefold()
    for name in (
        "米米", "米莎", "米蒂", "可丽希亚", "菲尔特", "卡普",
        "DeepSeek", *(f"DeepSeek-{index}" for index in range(1, 5)),
        *(f"AI-{index}" for index in range(1, 5)),
    )
)


class ProfileError(Exception):
    """玩家档案无法载入或保存时给界面显示的错误。"""


def profile_directory() -> Path:
    """在安装目录之外选择各平台的用户数据目录。"""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        configured = os.environ.get("XDG_DATA_HOME")
        base = Path(configured) if configured and Path(configured).is_absolute() else Path.home() / ".local" / "share"
    return base / "RocoKingdomGemMaster" / "profile"


def normalize_nickname(value: str) -> str:
    """统一登录名称，防止空白、控制字符和 AI 名称造成歧义。"""
    if not isinstance(value, str):
        raise ProfileError("请输入玩家昵称。")
    nickname = unicodedata.normalize("NFC", value.strip())
    if not 1 <= len(nickname) <= 16:
        raise ProfileError("昵称需为 1–16 个字符。")
    if any(unicodedata.category(char).startswith("C") for char in nickname):
        raise ProfileError("昵称不能包含控制字符。")
    if nickname.casefold() in RESERVED_NICKNAMES:
        raise ProfileError("该昵称已用于 AI 玩家，请换一个昵称。")
    return nickname


@dataclass
class PlayerProfile:
    player_id: str
    nickname: str
    created_at: str
    updated_at: str
    completed: list = field(default_factory=list)
    incomplete: list = field(default_factory=list)
    tutorial_invitation_answered: bool = False

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "player_id": self.player_id,
            "nickname": self.nickname,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "achievements": {
                "completed": self.completed,
                "incomplete": self.incomplete,
            },
            "tutorial_invitation_answered": self.tutorial_invitation_answered,
        }


class ProfileStore:
    def __init__(
        self,
        directory: Path | None = None,
        *,
        id_factory: Callable[[], int] | None = None,
    ) -> None:
        self.directory = Path(directory) if directory is not None else profile_directory()
        self.id_factory = id_factory or (lambda: MIN_PLAYER_ID + secrets.randbelow(PLAYER_ID_COUNT))

    def _read_file(self, path: Path) -> PlayerProfile:
        try:
            with path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
            if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("格式版本无效")
            player_id = data.get("player_id")
            if not isinstance(player_id, str) or not PLAYER_ID_PATTERN.fullmatch(player_id) or path.stem != player_id:
                raise ValueError("玩家 ID 与文件名不一致")
            nickname = data.get("nickname")
            if not isinstance(nickname, str) or normalize_nickname(nickname) != nickname:
                raise ValueError("昵称格式无效")
            created_at, updated_at = data.get("created_at"), data.get("updated_at")
            if not all(isinstance(value, str) and datetime.fromisoformat(value).tzinfo for value in (created_at, updated_at)):
                raise ValueError("时间字段无效")
            achievements = data.get("achievements")
            if not isinstance(achievements, dict) or not all(
                isinstance(achievements.get(key), list) for key in ("completed", "incomplete")
            ):
                raise ValueError("成就字段无效")
            # Existing accounts predate the tutorial invitation. Treat them as
            # answered so an upgrade does not unexpectedly interrupt login.
            tutorial_invitation_answered = data.get("tutorial_invitation_answered", True)
            if not isinstance(tutorial_invitation_answered, bool):
                raise ValueError("新手教程邀请状态无效")
            return PlayerProfile(
                player_id, nickname, created_at, updated_at,
                achievements["completed"], achievements["incomplete"],
                tutorial_invitation_answered,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, ProfileError) as error:
            raise ProfileError(f"账号文件 {path.name} 无法读取或内容损坏：{error}") from error

    def find_by_nickname(self, nickname: str) -> PlayerProfile | None:
        nickname = normalize_nickname(nickname)
        found = None
        try:
            paths = sorted(self.directory.glob("*.json")) if self.directory.exists() else []
        except OSError as error:
            raise ProfileError(f"无法读取账号目录：{error}") from error
        for path in paths:
            profile = self._read_file(path)
            if profile.nickname.casefold() == nickname.casefold():
                if found is not None:
                    raise ProfileError("多个账号使用了同一昵称，请检查账号文件。")
                found = profile
        return found

    def _write_file(self, profile: PlayerProfile, *, create_only: bool) -> None:
        target = self.directory / f"{profile.player_id}.json"
        temporary: Path | None = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix=".profile-", suffix=".tmp", dir=self.directory)
            temporary = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(profile.to_dict(), stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            if create_only:
                # 同目录硬链接具有“目标必须不存在”的语义，不覆盖其他账号。
                os.link(temporary, target)
            else:
                os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def load_or_create(self, nickname: str) -> tuple[PlayerProfile, bool]:
        nickname = normalize_nickname(nickname)
        existing = self.find_by_nickname(nickname)
        if existing is not None:
            return existing, False
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        for _attempt in range(100):
            number = self.id_factory()
            if not isinstance(number, int) or not MIN_PLAYER_ID <= number < MIN_PLAYER_ID + PLAYER_ID_COUNT:
                raise ProfileError("生成的玩家 ID 无效。")
            profile = PlayerProfile(str(number), nickname, timestamp, timestamp)
            try:
                self._write_file(profile, create_only=True)
            except FileExistsError:
                continue
            except OSError as error:
                raise ProfileError(f"无法保存玩家账号：{error}") from error
            return profile, True
        raise ProfileError("无法分配唯一玩家 ID，请稍后再试。")

    def save(self, profile: PlayerProfile) -> None:
        """供后续成就系统更新已存在的账号，不创建新的 ID 文件。"""
        target = self.directory / f"{profile.player_id}.json"
        if not target.is_file():
            raise ProfileError("玩家账号文件不存在，无法保存。")
        stored = self._read_file(target)
        if stored.nickname != profile.nickname:
            raise ProfileError("账号昵称与现有文件不一致，已拒绝覆盖。")
        previous_updated_at = profile.updated_at
        try:
            profile.updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
            self._write_file(profile, create_only=False)
        except OSError as error:
            profile.updated_at = previous_updated_at
            raise ProfileError(f"无法保存玩家账号：{error}") from error
