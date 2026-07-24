# -*- coding: utf-8 -*-
"""小红书抓取与分析（wonisoft API + 通义千问）"""
from __future__ import annotations

import copy
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import requests

XHS_HOST = "https://server.wonisoft.cn"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PRESETS_PATH = DATA_DIR / "xhs_presets.json"
REPORTS_DIR = BASE_DIR / "xhs-reports"

ANALYSIS_TYPES = {
    "category_scene": "品类场景洞察",
    "competitor_sentiment": "竞品舆情深挖",
    "competitor_seeding": "竞品种草对比",
}

REPORT_OUTLINES = {
    "category_scene": """
请输出完整 Markdown 报告，严格按以下章节（保留标题）：
# 品类场景与种草形式分析报告
## 一、报告概述
（样本量、时间范围、高互动门槛、品牌覆盖、创作者类型）
## 二、品类流量格局
（赞藏比特征、内容热力层级、受众特征）
## 三、内容场景深度拆解
（按认知→决策→购买→分享链路归纳场景；每场景含：核心需求、标题特征、内容形式、互动特征、种草逻辑）
## 四、种草形式分析
（列出主流种草形式；给核心公式与适用时机）
## 五、品牌提及与竞争格局
## 六、热门选题与内容公式
## 七、机会点与对基诺浦的策略建议
（必须可执行；只能使用品牌资料中的真实信息）
## 八、数据局限说明
""".strip(),
    "competitor_sentiment": """
请输出完整 Markdown 报告，严格按以下章节（保留标题）：
# 竞品舆情深度分析报告
## 一、核心发现摘要
## 二、数据概览与方法论
## 三、帖子内容类型分布
## 四、舆情分析（正面/中立/负面）
（归纳引爆点；勿编造未出现在样本中的事实）
## 五、高互动帖拆解
## 六、用户讨论焦点
## 七、竞品提及与品牌认知
## 八、应对与内容策略建议（对基诺浦的启示）
## 九、数据局限说明
""".strip(),
    "competitor_seeding": """
请输出完整 Markdown 报告，严格按以下章节（保留标题）：
# 竞品种草对比报告
## 一、分析对象概况
（仅基于抓取样本描述，禁止编造营收、门店、销量等未提供数据）
## 二、小红书种草现状
## 三、内容类型与风格
## 四、与基诺浦及其他品牌的内容差异
## 五、品类热点与趋势
## 六、机会点与可执行建议
## 七、数据局限说明
""".strip(),
    "custom": """
请输出完整 Markdown 报告，严格按以下章节（保留标题）：
# {title}
## 一、报告概述
## 二、样本数据概览
## 三、内容主题与结构拆解
## 四、互动表现与高表现内容
## 五、机会点与对基诺浦的策略建议
## 六、数据局限说明
""".strip(),
}

DEFAULT_PRESETS_DOC = {
    "presets": [
        {
            "id": "sys_category_scene",
            "name": "品类场景洞察",
            "system": True,
            "analysis_type": "category_scene",
            "keyword": "学步鞋",
            "sort_type": "general",
            "note_time": "一周内",
            "fetch_count": 20,
            "fetch_comments": False,
            "use_weather": False,
            "weather_city": "全国",
            "weather_province": "",
            "extra_prompt": "重点拆解内容场景与种草形式，给出可复用的选题公式。",
        },
        {
            "id": "sys_competitor_sentiment",
            "name": "竞品舆情深挖",
            "system": True,
            "analysis_type": "competitor_sentiment",
            "keyword": "稳稳鞋",
            "sort_type": "general",
            "note_time": "一周内",
            "fetch_count": 20,
            "fetch_comments": True,
            "use_weather": False,
            "weather_city": "全国",
            "weather_province": "",
            "extra_prompt": "重点看口碑正负向、价格/广告/质量争议，以及对基诺浦的启示。",
        },
        {
            "id": "sys_competitor_seeding",
            "name": "竞品种草对比",
            "system": True,
            "analysis_type": "competitor_seeding",
            "keyword": "泰兰尼斯",
            "sort_type": "general",
            "note_time": "一周内",
            "fetch_count": 20,
            "fetch_comments": False,
            "use_weather": False,
            "weather_city": "全国",
            "weather_province": "",
            "extra_prompt": "对比种草策略与内容差异，找出基诺浦可跟进的机会点。",
        },
    ],
    "last_selection": {
        "preset_id": "sys_category_scene",
        "analysis_type": "category_scene",
        "keyword": "学步鞋",
        "sort_type": "general",
        "note_time": "一周内",
        "fetch_count": 20,
        "fetch_comments": False,
        "use_weather": False,
        "weather_city": "全国",
        "weather_province": "",
        "extra_prompt": "重点拆解内容场景与种草形式，给出可复用的选题公式。",
    },
}


def _ensure_presets_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PRESETS_PATH.is_file():
        PRESETS_PATH.write_text(
            json.dumps(DEFAULT_PRESETS_DOC, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_presets_doc() -> dict:
    _ensure_presets_file()
    try:
        doc = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        doc = copy.deepcopy(DEFAULT_PRESETS_DOC)
        save_presets_doc(doc)
        return doc
    if not isinstance(doc.get("presets"), list) or not doc["presets"]:
        doc = copy.deepcopy(DEFAULT_PRESETS_DOC)
        save_presets_doc(doc)
    return doc


def save_presets_doc(doc: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PRESETS_PATH.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_analysis_type(raw: str) -> tuple[str, str]:
    """返回 (outline_key, display_name)。支持系统 key、中文名或自定义文案。"""
    text = (raw or "").strip()
    if not text:
        return "category_scene", ANALYSIS_TYPES["category_scene"]
    if text in ANALYSIS_TYPES:
        return text, ANALYSIS_TYPES[text]
    reverse = {name: key for key, name in ANALYSIS_TYPES.items()}
    if text in reverse:
        key = reverse[text]
        return key, text
    return "custom", text


def selection_fields(data: dict) -> dict:
    fetch_count = int(data.get("fetch_count") or 20)
    fetch_count = max(1, min(fetch_count, 50))
    analysis_raw = (data.get("analysis_type") or "category_scene").strip()
    weather_city = (data.get("weather_city") or "全国").strip() or "全国"
    weather_province = (data.get("weather_province") or "").strip()
    return {
        "preset_id": data.get("preset_id") or "",
        "analysis_type": analysis_raw,
        "keyword": (data.get("keyword") or "").strip(),
        "sort_type": data.get("sort_type") or "general",
        "note_time": data.get("note_time") or "一周内",
        "fetch_count": fetch_count,
        "fetch_comments": bool(data.get("fetch_comments")),
        "use_weather": bool(data.get("use_weather")),
        "weather_city": weather_city,
        "weather_province": weather_province,
        "extra_prompt": (data.get("extra_prompt") or "").strip(),
    }


def update_last_selection(fields: dict) -> dict:
    doc = load_presets_doc()
    doc["last_selection"] = selection_fields(fields)
    save_presets_doc(doc)
    return doc["last_selection"]


def create_preset(payload: dict) -> dict:
    doc = load_presets_doc()
    fields = selection_fields(payload)
    name = (payload.get("name") or "").strip() or f"自定义预设-{fields['keyword'] or '未命名'}"
    preset = {
        "id": f"user_{uuid.uuid4().hex[:10]}",
        "name": name,
        "system": False,
        **fields,
    }
    # preset_id inside fields is for selection, not needed on preset object
    preset.pop("preset_id", None)
    doc["presets"].append(preset)
    save_presets_doc(doc)
    return preset


def update_preset(preset_id: str, payload: dict) -> dict:
    doc = load_presets_doc()
    for i, p in enumerate(doc["presets"]):
        if p.get("id") != preset_id:
            continue
        fields = selection_fields(payload)
        name = (payload.get("name") or p.get("name") or "").strip()
        updated = {
            **p,
            "name": name or p.get("name"),
            "analysis_type": fields["analysis_type"],
            "keyword": fields["keyword"],
            "sort_type": fields["sort_type"],
            "note_time": fields["note_time"],
            "fetch_count": fields["fetch_count"],
            "fetch_comments": fields["fetch_comments"],
            "use_weather": fields["use_weather"],
            "weather_city": fields["weather_city"],
            "weather_province": fields["weather_province"],
            "extra_prompt": fields["extra_prompt"],
        }
        # keep system flag
        updated["system"] = bool(p.get("system"))
        doc["presets"][i] = updated
        save_presets_doc(doc)
        return updated
    raise KeyError("预设不存在")


def delete_preset(preset_id: str) -> None:
    doc = load_presets_doc()
    target = next((p for p in doc["presets"] if p.get("id") == preset_id), None)
    if not target:
        raise KeyError("预设不存在")
    if target.get("system"):
        raise PermissionError("系统预设不可删除")
    doc["presets"] = [p for p in doc["presets"] if p.get("id") != preset_id]
    if doc.get("last_selection", {}).get("preset_id") == preset_id:
        doc["last_selection"]["preset_id"] = "sys_category_scene"
    save_presets_doc(doc)


def xhs_headers(api_key: str, session: str | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if session:
        headers["session"] = session
    return headers


def xhs_get(api_key: str, path: str, params: dict | None = None, session: str | None = None) -> dict:
    url = f"{XHS_HOST}{path}"
    resp = requests.get(url, params=params or {}, headers=xhs_headers(api_key, session), timeout=45)
    resp.raise_for_status()
    data = resp.json()
    code = data.get("code")
    if code not in (200, 0, "200", "0", None) and data.get("msg") not in ("success", "成功", None):
        # some APIs only return data without code
        if "data" not in data and code not in (None,):
            raise RuntimeError(data.get("msg") or f"小红书接口失败: {path}")
    if isinstance(code, int) and code >= 400:
        raise RuntimeError(data.get("msg") or f"小红书接口失败: {path}")
    return data


def _dig(obj: Any, *keys: str, default=None):
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _as_int(v, default=0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return default


def normalize_search_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    note = item.get("note_card") or item.get("noteCard") or item.get("note") or item
    if not isinstance(note, dict):
        return None
    note_id = (
        note.get("note_id")
        or note.get("noteId")
        or note.get("id")
        or item.get("note_id")
        or item.get("id")
    )
    if not note_id or str(note_id) in ("", "0"):
        # skip ads / non-note
        model = str(item.get("model_type") or item.get("modelType") or "")
        if model and model not in ("note", "normal"):
            return None
        return None
    xsec = (
        note.get("xsec_token")
        or note.get("xsecToken")
        or item.get("xsec_token")
        or item.get("xsecToken")
        or ""
    )
    interact = note.get("interact_info") or note.get("interactInfo") or {}
    user = note.get("user") or {}
    title = (
        note.get("display_title")
        or note.get("displayTitle")
        or note.get("title")
        or note.get("desc")
        or ""
    )
    return {
        "note_id": str(note_id),
        "xsec_token": str(xsec),
        "title": str(title).strip(),
        "type": note.get("type") or note.get("note_type") or "",
        "liked": _as_int(interact.get("liked_count") or interact.get("likedCount") or interact.get("like_count")),
        "collected": _as_int(interact.get("collected_count") or interact.get("collectedCount") or interact.get("collect_count")),
        "commented": _as_int(interact.get("comment_count") or interact.get("commentCount")),
        "shared": _as_int(interact.get("share_count") or interact.get("shareCount")),
        "author": user.get("nickname") or user.get("nick_name") or "",
        "user_id": str(user.get("user_id") or user.get("userId") or ""),
    }


def search_notes(
    api_key: str,
    keyword: str,
    fetch_count: int,
    sort_type: str = "general",
    note_time: str = "一周内",
    session: str | None = None,
) -> list[dict]:
    collected: list[dict] = []
    seen = set()
    search_id = ""
    page = 1
    while len(collected) < fetch_count and page <= 5:
        params = {
            "keyword": keyword,
            "page": page,
            "sortType": sort_type or "general",
            "filterNoteTime": note_time or "不限",
        }
        if search_id:
            params["searchId"] = search_id
        data = xhs_get(api_key, "/api/xhs/searchNote", params=params, session=session)
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        items = payload.get("items") or payload.get("notes") or []
        search_id = payload.get("searchId") or payload.get("search_id") or search_id
        if not items:
            break
        for raw in items:
            norm = normalize_search_item(raw)
            if not norm or norm["note_id"] in seen:
                continue
            seen.add(norm["note_id"])
            collected.append(norm)
            if len(collected) >= fetch_count:
                break
        has_more = payload.get("has_more")
        if has_more is False:
            break
        page += 1
        time.sleep(0.15)
    return collected[:fetch_count]


def get_note_detail(api_key: str, note_id: str, xsec_token: str, session: str | None = None) -> dict:
    params = {"noteId": note_id, "xsecToken": xsec_token or ""}
    data = xhs_get(api_key, "/api/xhs/getNoteDetail", params=params, session=session)
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(payload, dict):
        return {}
    interact = payload.get("interactInfo") or payload.get("interact_info") or {}
    user = payload.get("user") or {}
    return {
        "note_id": str(payload.get("noteId") or payload.get("note_id") or note_id),
        "title": str(payload.get("title") or "").strip(),
        "desc": str(payload.get("desc") or payload.get("content") or "").strip(),
        "type": payload.get("type") or "",
        "liked": _as_int(interact.get("likedCount") or interact.get("liked_count")),
        "collected": _as_int(interact.get("collectedCount") or interact.get("collected_count")),
        "commented": _as_int(interact.get("commentCount") or interact.get("comment_count")),
        "shared": _as_int(interact.get("shareCount") or interact.get("share_count")),
        "author": user.get("nickname") or user.get("nick_name") or "",
        "tags": payload.get("tag_list") or payload.get("hash_tag") or [],
    }


def get_note_comments(
    api_key: str,
    note_id: str,
    xsec_token: str,
    limit: int = 15,
    session: str | None = None,
) -> list[str]:
    comments: list[str] = []
    cursor = ""
    try:
        params = {"noteId": note_id, "xsecToken": xsec_token or "", "cursor": cursor}
        data = xhs_get(api_key, "/api/xhs/getCommentPage", params=params, session=session)
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        rows = payload.get("comments") or []
        for c in rows:
            if not isinstance(c, dict):
                continue
            content = c.get("content") or c.get("text") or ""
            like = _as_int(c.get("like_count") or c.get("likeCount"))
            if content:
                comments.append(f"{content}（赞{like}）")
            if len(comments) >= limit:
                break
    except Exception:
        return comments
    return comments


def enrich_notes(
    api_key: str,
    notes: list[dict],
    fetch_comments: bool = False,
    session: str | None = None,
    on_progress=None,
) -> list[dict]:
    enriched = []
    total = max(len(notes), 1)
    for i, n in enumerate(notes):
        detail = {}
        try:
            if n.get("xsec_token"):
                detail = get_note_detail(api_key, n["note_id"], n["xsec_token"], session=session)
        except Exception as e:
            detail = {"error": str(e)}
        merged = {**n, **{k: v for k, v in detail.items() if v not in ("", None, [], {})}}
        if not merged.get("title"):
            merged["title"] = n.get("title") or "(无标题)"
        if fetch_comments and n.get("xsec_token") and i < 8:
            # 仅对前 8 条拉评论，控制 token 与耗时
            try:
                merged["comments"] = get_note_comments(
                    api_key, n["note_id"], n["xsec_token"], limit=12, session=session
                )
            except Exception:
                merged["comments"] = []
            time.sleep(0.12)
        enriched.append(merged)
        if on_progress:
            try:
                on_progress(i + 1, total, merged.get("title") or "")
            except Exception:
                pass
        time.sleep(0.12)
    return enriched


def notes_to_prompt_text(notes: list[dict]) -> str:
    parts = []
    for i, n in enumerate(notes, 1):
        desc = (n.get("desc") or "")[:400]
        block = [
            f"### 笔记{i}",
            f"标题：{n.get('title') or ''}",
            f"作者：{n.get('author') or ''}",
            f"类型：{n.get('type') or ''}",
            f"互动：赞{n.get('liked', 0)} / 藏{n.get('collected', 0)} / 评{n.get('commented', 0)} / 转{n.get('shared', 0)}",
            f"正文摘要：{desc or '（无正文）'}",
        ]
        comments = n.get("comments") or []
        if comments:
            block.append("热门评论：" + "；".join(comments[:8]))
        parts.append("\n".join(block))
    return "\n\n".join(parts)


def build_xhs_analysis_messages(
    *,
    analysis_type: str,
    keyword: str,
    notes_text: str,
    brand_text: str,
    extra_prompt: str = "",
    weather_text: str = "",
    sample_count: int = 0,
    note_time: str = "",
) -> list[dict]:
    outline_key, type_name = resolve_analysis_type(analysis_type)
    outline = REPORT_OUTLINES.get(outline_key, REPORT_OUTLINES["custom"])
    if outline_key == "custom":
        outline = outline.format(title=f"{type_name}分析报告")
    weather_block = ""
    if weather_text:
        weather_block = f"\n【可选天气背景（仅在相关时引用）】\n{weather_text}\n"
    extra_block = f"\n【用户补充要求】\n{extra_prompt}\n" if extra_prompt else ""
    system = (
        "你是基诺浦（GINOBLE）的小红书内容分析顾问。"
        "基于给定笔记样本做竞品/品类洞察，输出可执行营销建议。"
        "只使用样本与品牌资料中的真实信息，禁止编造型号、SKU、虚假销量、虚假认证或未给出的营收数据。"
        "报告使用简体中文 Markdown，结论要具体，避免空话。"
    )
    user = f"""
请基于以下小红书抓取样本，完成「{type_name}」报告。

【检索关键词】{keyword}
【样本数量】{sample_count}
【时间筛选】{note_time or "未指定"}
{extra_block}{weather_block}
【报告结构要求】
{outline}

【硬性要求】
1. 先数据后观点，引用样本中的标题/互动特征时要具体。
2. 最后策略必须服务基诺浦，且只使用下方品牌资料中的真实信息。
3. 明确写出数据局限（搜索 TopN，非全站）。
4. 不要输出与报告无关的开场白。

【笔记样本】
{notes_text}

【品牌资料】
{brand_text}
""".strip()
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def safe_filename(keyword: str, analysis_type: str) -> str:
    _, type_name = resolve_analysis_type(analysis_type)
    raw = f"小红书{type_name}_{keyword or '报告'}"
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", raw).strip() or "小红书分析报告"
    return cleaned[:60]


def _ensure_reports_dir() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    keep = REPORTS_DIR / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")
    return REPORTS_DIR


def save_report(report_md: str, meta: dict) -> dict:
    """保存报告到 xhs-reports/（本地文件系统），线上同步到 PostgreSQL。"""
    _ensure_reports_dir()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    report_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
    title = (
        meta.get("title")
        or f"{meta.get('analysis_type_name') or '分析'} · {meta.get('keyword') or '未命名'}"
    )
    record = {
        **meta,
        "id": report_id,
        "title": title,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "filename_md": f"{report_id}.md",
        "filename_meta": f"{report_id}.json",
    }
    # 本地文件系统保存
    try:
        md_path = REPORTS_DIR / f"{report_id}.md"
        meta_path = REPORTS_DIR / f"{report_id}.json"
        md_path.write_text(report_md or "", encoding="utf-8")
        meta_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[fs] save report failed: {e}")
    # PostgreSQL 保存（线上持久化）
    if _get_db_url():
        _pg_save_report(report_md, record)
    return record


def list_reports(limit: int = 100) -> list[dict]:
    # 线上优先从 PostgreSQL 读取
    if _get_db_url():
        pg_items = _pg_list_reports(limit)
        if pg_items:
            return pg_items
        # 数据库为空时返回空列表（不回退到文件系统，因为线上文件系统是临时的）
        return []
    # 本地从文件系统读取
    _ensure_reports_dir()
    items: list[dict] = []
    for meta_path in REPORTS_DIR.glob("*.json"):
        if meta_path.name.startswith("."):
            continue
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not data.get("id"):
                continue
            items.append({
                "id": data.get("id"),
                "title": data.get("title") or data.get("keyword") or data.get("id"),
                "keyword": data.get("keyword") or "",
                "analysis_type": data.get("analysis_type") or "",
                "analysis_type_name": data.get("analysis_type_name") or "",
                "sample_count": data.get("sample_count") or 0,
                "created_at": data.get("created_at") or "",
                "use_weather": bool(data.get("use_weather")),
                "weather_city": data.get("weather_city") or "",
                "note_time": data.get("note_time") or "",
            })
        except (OSError, json.JSONDecodeError):
            continue
    items.sort(key=lambda x: x.get("created_at") or x.get("id") or "", reverse=True)
    return items[: max(1, min(int(limit or 100), 500))]


def get_report(report_id: str) -> dict:
    # 线上优先从 PostgreSQL 读取
    if _get_db_url():
        result = _pg_get_report(report_id)
        if result:
            return result
        raise KeyError("报告不存在")
    # 本地从文件系统读取
    _ensure_reports_dir()
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", report_id or "")
    if not safe_id:
        raise KeyError("报告不存在")
    meta_path = REPORTS_DIR / f"{safe_id}.json"
    md_path = REPORTS_DIR / f"{safe_id}.md"
    if not meta_path.is_file() or not md_path.is_file():
        raise KeyError("报告不存在")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    report_md = md_path.read_text(encoding="utf-8")
    return {"meta": meta, "report_md": report_md}


def delete_report(report_id: str) -> None:
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", report_id or "")
    if not safe_id:
        raise KeyError("报告不存在")
    deleted = False
    # 线上从 PostgreSQL 删除
    if _get_db_url():
        deleted = _pg_delete_report(report_id)
    # 本地从文件系统删除
    _ensure_reports_dir()
    meta_path = REPORTS_DIR / f"{safe_id}.json"
    md_path = REPORTS_DIR / f"{safe_id}.md"
    fs_existed = meta_path.is_file() or md_path.is_file()
    if meta_path.is_file():
        meta_path.unlink()
    if md_path.is_file():
        md_path.unlink()
    if not deleted and not fs_existed:
        raise KeyError("报告不存在")


# ---------------------------------------------------------------------------
# PostgreSQL 持久化（线上 Render 使用，本地无 DATABASE_URL 时自动跳过）
# ---------------------------------------------------------------------------

_pg_pool = None


def _get_db_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def _get_pg_conn():
    global _pg_pool
    if not _get_db_url():
        return None
    if _pg_pool is None:
        import psycopg2
        from psycopg2 import pool
        _pg_pool = pool.SimpleConnectionPool(1, 5, _get_db_url())
    return _pg_pool.getconn()


def _return_pg_conn(conn):
    global _pg_pool
    if _pg_pool and conn:
        _pg_pool.putconn(conn)


def _pg_init():
    """创建报告表（幂等）"""
    conn = _get_pg_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS xhs_reports (
                    id           TEXT PRIMARY KEY,
                    title        TEXT,
                    keyword      TEXT DEFAULT '',
                    analysis_type TEXT DEFAULT '',
                    analysis_type_name TEXT DEFAULT '',
                    sample_count INTEGER DEFAULT 0,
                    note_time    TEXT DEFAULT '',
                    sort_type    TEXT DEFAULT '',
                    fetch_comments BOOLEAN DEFAULT FALSE,
                    use_weather  BOOLEAN DEFAULT FALSE,
                    weather_city TEXT DEFAULT '',
                    created_at   TEXT,
                    report_md    TEXT,
                    meta_json    TEXT
                )
            """)
        conn.commit()
    except Exception as e:
        print(f"[pg] init table failed: {e}")
    finally:
        _return_pg_conn(conn)


def _pg_save_report(report_md: str, record: dict) -> dict:
    conn = _get_pg_conn()
    if not conn:
        return record
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO xhs_reports
                    (id, title, keyword, analysis_type, analysis_type_name,
                     sample_count, note_time, sort_type, fetch_comments,
                     use_weather, weather_city, created_at, report_md, meta_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    report_md = EXCLUDED.report_md,
                    meta_json = EXCLUDED.meta_json
            """, (
                record.get("id"),
                record.get("title"),
                record.get("keyword", ""),
                record.get("analysis_type", ""),
                record.get("analysis_type_name", ""),
                record.get("sample_count", 0),
                record.get("note_time", ""),
                record.get("sort_type", ""),
                record.get("fetch_comments", False),
                record.get("use_weather", False),
                record.get("weather_city", ""),
                record.get("created_at", ""),
                report_md,
                json.dumps(record, ensure_ascii=False),
            ))
        conn.commit()
        print(f"[pg] saved report {record.get('id')}")
    except Exception as e:
        print(f"[pg] save report failed: {e}")
    finally:
        _return_pg_conn(conn)
    return record


def _pg_list_reports(limit: int = 100) -> list[dict]:
    conn = _get_pg_conn()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, keyword, analysis_type, analysis_type_name,
                       sample_count, note_time, use_weather, weather_city, created_at
                FROM xhs_reports
                ORDER BY created_at DESC NULLS LAST
                LIMIT %s
            """, (max(1, min(limit, 500)),))
            rows = cur.fetchall()
        items = []
        for r in rows:
            items.append({
                "id": r[0],
                "title": r[1],
                "keyword": r[2] or "",
                "analysis_type": r[3] or "",
                "analysis_type_name": r[4] or "",
                "sample_count": r[5] or 0,
                "note_time": r[6] or "",
                "use_weather": bool(r[7]),
                "weather_city": r[8] or "",
                "created_at": r[9] or "",
            })
        return items
    except Exception as e:
        print(f"[pg] list reports failed: {e}")
        return []
    finally:
        _return_pg_conn(conn)


def _pg_get_report(report_id: str) -> dict | None:
    conn = _get_pg_conn()
    if not conn:
        return None
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", report_id or "")
    if not safe_id:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT meta_json, report_md FROM xhs_reports WHERE id = %s
            """, (safe_id,))
            row = cur.fetchone()
        if not row:
            return None
        meta = json.loads(row[0]) if row[0] else {}
        return {"meta": meta, "report_md": row[1] or ""}
    except Exception as e:
        print(f"[pg] get report failed: {e}")
        return None
    finally:
        _return_pg_conn(conn)


def _pg_delete_report(report_id: str) -> bool:
    conn = _get_pg_conn()
    if not conn:
        return False
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", report_id or "")
    if not safe_id:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM xhs_reports WHERE id = %s", (safe_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    except Exception as e:
        print(f"[pg] delete report failed: {e}")
        return False
    finally:
        _return_pg_conn(conn)
