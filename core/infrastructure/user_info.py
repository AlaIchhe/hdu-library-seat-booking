"""用户 UID 解析 — 从 API 响应中启发式提取用户信息。"""

from __future__ import annotations

from ..types import UserInfo


def find_user_info(data: dict) -> UserInfo | None:
    """递归搜索 JSON 中与用户信息匹配的字段。"""
    candidates: list[UserInfo] = []

    def walk(obj: object, hint: str = "") -> None:
        if isinstance(obj, dict):
            if "name" in obj and "value" in obj and isinstance(obj.get("value"), str):
                walk(obj["value"], str(obj.get("name") or hint))
            c = _user_info_from_dict(obj, hint)
            if c:
                candidates.append(c)
            for k, v in obj.items():
                walk(v, f"{hint}.{k}" if hint else str(k))
        elif isinstance(obj, list):
            for item in obj:
                walk(item, hint)
        elif isinstance(obj, str):
            val = obj.strip()
            if val and val[0] in "[{":
                import json

                try:
                    walk(json.loads(val), hint)
                except Exception:
                    pass

    walk(data)
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    return candidates[0]


def _user_info_from_dict(data: dict, hint: str = "") -> UserInfo | None:
    """从字典中提取用户 UID 和姓名候选。"""
    id_keys = ("uid", "user_id", "userId", "booker", "id", "textRight")
    name_keys = (
        "name",
        "real_name",
        "realName",
        "bookerName",
        "username",
        "login_name",
        "nickname",
        "textRight",
    )
    title_keys = ("titleCenter", "titleLeft", "title", "titleRight")

    uid = None
    name = None
    title_context = ""

    for k in title_keys:
        v = data.get(k)
        if v and isinstance(v, str):
            title_context += v

    for k in id_keys:
        v = data.get(k)
        if v is not None and str(v).isdigit():
            uid = str(v)
            break
    for k in name_keys:
        v = data.get(k)
        if v and not str(v).isdigit():
            name = str(v)
            break

    score = 1 if name else 0
    hint_lower = (hint + title_context).lower()
    for kw in (
        "current",
        "user",
        "login",
        "lab4",
        "身份",
        "认证",
        "姓名",
        "证号",
        "书证",
        "学号",
        "学工",
        "一卡通",
        "证件",
    ):
        if kw in hint_lower:
            score += 2
    if "手机" in title_context:
        score -= 3
    if uid and (score > 0 or name):
        return {"uid": uid, "name": name, "score": max(score, 0)}
    return None
