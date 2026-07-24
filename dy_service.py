# -*- coding: utf-8 -*-
"""抖音内容抓取与分析（TikHub API + 通义千问）"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import requests

TIKHUB_HOST = "https://api.tikhub.io"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DY_PRESETS_PATH = DATA_DIR / "dy_presets.json"
REPORTS_DIR = BASE_DIR / "dy-reports"

ANALYSIS_TYPES = {
    "category_scene": "品类场景洞察",
    "competitor_sentiment": "竞品舆情深挖",
    "competitor_seeding": "竞品种草对比",
}

REPORT_OUTLINES = {
    "category_scene": """
请输出完整 Markdown 报告，严格按以下章节（保留标题）：
# 抖音品类场景与种草形式分析报告
## 一、报告概述
（样本量、时间范围、高互动门槛、品牌覆盖、创作者类型）
## 二、品类流量格局
（赞评比特征、内容热力层级、受众特征）
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
# 抖音竞品舆情深度分析报告
## 一、核心发现摘要
## 二、数据概览与方法论
## 三、视频内容类型分布
## 四、舆情分析（正面/中立/负面）
（归纳引爆点；勿编造未出现在样本中的事实）
## 五、高互动视频拆解
## 六、用户评论焦点分析
## 七、竞品提及与品牌认知
## 八、应对与内容策略建议（对基诺浦的启示）
## 九、数据局限说明
""".strip(),
    "competitor_seeding": """
请输出完整 Markdown 报告，严格按以下章节（保留标题）：
# 抖音竞品种草对比报告
## 一、分析对象概况
（仅基于抓取样本描述，禁止编造营收、门店、销量等未提供数据）
## 二、抖音种草现状
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
            "id": "sys_dy_category_scene",
            "name": "品类场景洞察",
            "system": True,
            "analysis_type": "category_scene",
            "keyword": "学步鞋",
            "sort_type": "general",
            "note_time": "一周内",
            "fetch_count": 20,
            "fetch_comments": False,
            "extra_prompt": "重点拆解内容场景与种草形式，给出可复用的选题公式。",
        },
        {
            "id": "sys_dy_competitor_sentiment",
            "name": "竞品舆情深挖",
            "system": True,
            "analysis_type": "competitor_sentiment",
            "keyword": "稳稳鞋",
            "sort_type": "general",
            "note_time": "一周内",
            "fetch_count": 20,
            "fetch_comments": True,
            "extra_prompt": "重点看口碑正负向、价格/广告/质量争议，以及对基诺浦的启示。",
        },
        {
            "id": "sys_dy_competitor_seeding",
            "name": "竞品种草对比",
            "system": True,
            "analysis_type": "competitor_seeding",
            "keyword": "泰兰尼斯",
            "sort_type": "general",
            "note_time": "一周内",
            "fetch_count": 20,
            "fetch_comments": False,
            "extra_prompt": "对比种草策略与内容差异，找出基诺浦可跟进的机会点。",
        },
    ],
    "last_selection": {
        "preset_id": "sys_dy_category_scene",
        "analysis_type": "category_scene",
        "keyword": "学步鞋",
        "sort_type": "general",
        "note_time": "一周内",
        "fetch_count": 20,
        "fetch_comments": False,
        "extra_prompt": "重点拆解内容场景与种草形式，给出可复用的选题公式。",
    },
}


# ---------------------------------------------------------------------------
# 预设管理（复用小红书的逻辑模式）
# ---------------------------------------------------------------------------

def _ensure_presets_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DY_PRESETS_PATH.is_file():
        DY_PRESETS_PATH.write_text(
            json.dumps(DEFAULT_PRESETS_DOC, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_presets_doc() -> dict:
    import copy
    _ensure_presets_file()
    try:
        doc = json.loads(DY_PRESETS_PATH.read_text(encoding="utf-8"))
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
    DY_PRESETS_PATH.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_analysis_type(raw: str) -> tuple[str, str]:
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
    fetch_count = max(1, min(fetch_count, 200))
    analysis_raw = (data.get("analysis_type") or "category_scene").strip()
    return {
        "preset_id": data.get("preset_id") or "",
        "analysis_type": analysis_raw,
        "keyword": (data.get("keyword") or "").strip(),
        "sort_type": data.get("sort_type") or "general",
        "note_time": data.get("note_time") or "一周内",
        "fetch_count": fetch_count,
        "fetch_comments": bool(data.get("fetch_comments")),
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
            "extra_prompt": fields["extra_prompt"],
        }
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
        doc["last_selection"]["preset_id"] = "sys_dy_category_scene"
    save_presets_doc(doc)


# ---------------------------------------------------------------------------
# TikHub API 调用
# ---------------------------------------------------------------------------

def dy_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


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


def _as_str(v, default="") -> str:
    if v is None:
        return default
    return str(v).strip()


# 发布时间参数映射
NOTE_TIME_MAP = {
    "不限": 0,
    "一天内": 1,
    "一周内": 7,
    "一个月内": 30,
    "半年内": 180,
    "一年内": 365,
}

# 排序参数映射
SORT_TYPE_MAP = {
    "general": 0,        # 相关度
    "popularity_descending": 1,  # 最多点赞
    "time_descending": 2,  # 最新（近似）
    "comment_descending": 1,  # 抖音搜索无评论排序，用最多点赞近似
    "collect_descending": 1,
}


def search_videos(
    api_key: str,
    keyword: str,
    fetch_count: int,
    sort_type: str = "general",
    note_time: str = "一周内",
) -> list[dict]:
    """搜索抖音视频，返回标准化后的视频列表。

    使用 TikHub fetch_video_search_v2 接口，POST JSON body。
    参数: keyword, count, offset。
    响应结构: data.business_data 数组，type==1 为视频，data.aweme_info 含视频详情。
    翻页: data.business_config.has_more + data.business_config.next_page.cursor。
    """
    collected: list[dict] = []
    seen: set[str] = set()
    offset = 0
    page = 0

    while len(collected) < fetch_count and page < 30:
        payload = {
            "keyword": keyword,
            "count": min(fetch_count - len(collected), 20),
            "offset": offset,
        }
        try:
            resp = requests.post(
                f"{TIKHUB_HOST}/api/v1/douyin/search/fetch_video_search_v2",
                headers=dy_headers(api_key),
                json=payload,
                timeout=45,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"抖音搜索请求失败: {e}")

        inner = data.get("data") if isinstance(data.get("data"), dict) else data
        if not isinstance(inner, dict):
            break

        # v2 返回数据在 business_data 数组中，type==1 为视频条目
        business_data = _dig(inner, "business_data", default=[])
        if not business_data:
            break

        items_found = 0
        for raw in business_data:
            if not isinstance(raw, dict) or raw.get("type") != 1:
                continue
            aweme_info = _dig(raw, "data", "aweme_info")
            if not aweme_info:
                continue
            items_found += 1
            norm = normalize_search_item(aweme_info)
            if not norm or norm["aweme_id"] in seen:
                continue
            seen.add(norm["aweme_id"])
            collected.append(norm)
            if len(collected) >= fetch_count:
                break

        # 翻页: 使用 business_config.next_page.cursor 作为下一页 offset
        business_config = _dig(inner, "business_config", default={})
        has_more = _dig(business_config, "has_more", default=0)
        next_page = _dig(business_config, "next_page", default={})
        next_cursor = _dig(next_page, "cursor")
        if next_cursor is not None:
            offset = next_cursor
        else:
            offset += len(business_data)

        if has_more != 1 or items_found == 0:
            break
        page += 1
        time.sleep(0.15)

    return collected[:fetch_count]


# ---------------------------------------------------------------------------
# 童装童鞋垂直热榜（多关键词搜索 + 聚合排序）
# ---------------------------------------------------------------------------

KIDS_HOT_KEYWORDS = [
    "童鞋", "童装", "学步鞋", "宝宝鞋", "儿童服装",
    "婴儿鞋", "机能鞋", "儿童鞋", "宝宝穿搭", "母婴好物",
]


def fetch_kids_hot_list(
    api_key: str,
    top_n: int = 20,
    per_keyword: int = 10,
) -> list[dict]:
    """搜索多个童装童鞋关键词，按互动量聚合排序，返回热榜。

    每个关键词搜索 per_keyword 条，去重后按 赞+评 排序取 top_n。
    """
    aggregated: dict[str, dict] = {}

    for kw in KIDS_HOT_KEYWORDS:
        try:
            videos = search_videos(
                api_key=api_key,
                keyword=kw,
                fetch_count=per_keyword,
            )
        except Exception:
            continue
        for v in videos:
            aid = v.get("aweme_id", "")
            if not aid or aid in aggregated:
                continue
            score = v.get("liked", 0) + v.get("commented", 0)
            aggregated[aid] = {
                **v,
                "source_keyword": kw,
                "hot_score": score,
            }
        time.sleep(0.1)

    ranked = sorted(
        aggregated.values(),
        key=lambda x: x.get("hot_score", 0),
        reverse=True,
    )
    return ranked[:top_n]


def normalize_search_item(item: dict) -> dict | None:
    """标准化搜索结果中的视频条目。

    item 可以是:
    - aweme_info 本体（直接含 aweme_id / author / statistics）
    - 外层包装（含 aweme_info 或 awemeInfo 键）
    注意: aweme_info 内部也有 video 键（播放信息），不可用 item.get("video") 匹配。
    """
    if not isinstance(item, dict):
        return None
    # 若 item 自身已含 aweme_id，说明传入的就是 aweme 本体，直接使用
    if item.get("aweme_id"):
        aweme = item
    else:
        aweme = item.get("aweme_info") or item.get("awemeInfo") or item
    if not isinstance(aweme, dict):
        return None
    aweme_id = (
        aweme.get("aweme_id") or aweme.get("awemeId") or aweme.get("id") or item.get("aweme_id")
    )
    if not aweme_id or str(aweme_id) in ("", "0"):
        return None

    stats = aweme.get("statistics") or aweme.get("stats") or {}
    author = aweme.get("author") or aweme.get("user") or {}
    desc = _as_str(aweme.get("desc") or aweme.get("description") or item.get("desc"))

    return {
        "aweme_id": str(aweme_id),
        "desc": desc[:500] if desc else "",
        "title": desc[:100] if desc else "(无描述)",
        "author": _as_str(author.get("nickname") or author.get("unique_id")),
        "author_uid": _as_str(author.get("uid") or author.get("short_id")),
        "liked": _as_int(stats.get("digg_count") or stats.get("like_count")),
        "commented": _as_int(stats.get("comment_count") or stats.get("commentCount")),
        "collected": _as_int(stats.get("collect_count")),
        "shared": _as_int(stats.get("share_count") or stats.get("shareCount")),
        "played": _as_int(stats.get("play_count") or stats.get("playCount")),
        "create_time": _as_int(aweme.get("create_time")),
        "duration": _as_int(aweme.get("duration")),
    }


def get_video_detail(api_key: str, aweme_id: str) -> dict:
    """获取单个视频详情。"""
    try:
        resp = requests.get(
            f"{TIKHUB_HOST}/api/v1/douyin/web/fetch_one_video",
            headers=dy_headers(api_key),
            params={"aweme_id": aweme_id},
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}

    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(inner, dict):
        return {}

    aweme = inner.get("aweme_detail") or inner.get("item") or inner.get("video") or inner
    if not isinstance(aweme, dict):
        return {}

    stats = aweme.get("statistics") or aweme.get("stats") or {}
    author = aweme.get("author") or aweme.get("user") or {}
    desc = _as_str(aweme.get("desc"))

    return {
        "aweme_id": str(aweme.get("aweme_id") or aweme_id),
        "desc": desc[:1000] if desc else "",
        "title": desc[:100] if desc else "(无描述)",
        "author": _as_str(author.get("nickname") or author.get("unique_id")),
        "author_uid": _as_str(author.get("uid")),
        "liked": _as_int(stats.get("digg_count") or stats.get("like_count")),
        "commented": _as_int(stats.get("comment_count")),
        "collected": _as_int(stats.get("collect_count")),
        "shared": _as_int(stats.get("share_count")),
        "played": _as_int(stats.get("play_count")),
        "create_time": _as_int(aweme.get("create_time")),
        "duration": _as_int(aweme.get("duration")),
    }


def get_video_comments(
    api_key: str,
    aweme_id: str,
    limit: int = 15,
) -> list[str]:
    """获取视频评论列表，返回评论文本列表。"""
    comments: list[str] = []
    try:
        resp = requests.get(
            f"{TIKHUB_HOST}/api/v1/douyin/web/fetch_video_comments",
            headers=dy_headers(api_key),
            params={"aweme_id": aweme_id, "count": limit, "cursor": 0},
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return comments

    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(inner, dict):
        return comments

    rows = inner.get("comments") or []
    for c in rows:
        if not isinstance(c, dict):
            continue
        text = _as_str(c.get("text") or c.get("content"))
        like = _as_int(c.get("digg_count") or c.get("like_count"))
        user = c.get("user") or {}
        nickname = _as_str(user.get("nickname"))
        if text:
            comment_text = f"{text}（赞{like}）"
            if nickname:
                comment_text = f"[{nickname}] {comment_text}"
            comments.append(comment_text)
        if len(comments) >= limit:
            break
    return comments


def enrich_videos(
    api_key: str,
    videos: list[dict],
    fetch_comments: bool = False,
    on_progress=None,
) -> list[dict]:
    """批量获取视频详情和评论。"""
    enriched = []
    total = max(len(videos), 1)
    for i, v in enumerate(videos):
        detail = {}
        try:
            detail = get_video_detail(api_key, v["aweme_id"])
        except Exception as e:
            detail = {"error": str(e)}
        merged = {**v, **{k: val for k, val in detail.items() if val not in ("", None, [], {})}}
        if not merged.get("title"):
            merged["title"] = v.get("title") or "(无标题)"
        if fetch_comments and i < 8:
            try:
                merged["comments"] = get_video_comments(
                    api_key, v["aweme_id"], limit=12
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


def videos_to_prompt_text(videos: list[dict]) -> str:
    """将视频列表转换为AI分析的文本。"""
    parts = []
    for i, v in enumerate(videos, 1):
        desc = (v.get("desc") or "")[:500]
        block = [
            f"### 视频{i}",
            f"标题/描述：{v.get('title') or ''}",
            f"作者：{v.get('author') or ''}",
            f"互动：赞{v.get('liked', 0)} / 评{v.get('commented', 0)} / 藏{v.get('collected', 0)} / 转{v.get('shared', 0)} / 播{v.get('played', 0)}",
            f"正文摘要：{desc or '（无正文）'}",
        ]
        comments = v.get("comments") or []
        if comments:
            block.append("热门评论：" + "；".join(comments[:8]))
        parts.append("\n".join(block))
    return "\n\n".join(parts)


def build_dy_analysis_messages(
    *,
    analysis_type: str,
    keyword: str,
    videos_text: str,
    brand_text: str,
    extra_prompt: str = "",
    sample_count: int = 0,
    note_time: str = "",
) -> list[dict]:
    outline_key, type_name = resolve_analysis_type(analysis_type)
    outline = REPORT_OUTLINES.get(outline_key, REPORT_OUTLINES["custom"])
    if outline_key == "custom":
        outline = outline.format(title=f"{type_name}分析报告")
    extra_block = f"\n【用户补充要求】\n{extra_prompt}\n" if extra_prompt else ""
    system = (
        "你是基诺浦（GINOBLE）的抖音内容分析顾问。"
        "基于给定抖音视频样本做竞品/品类洞察，输出可执行营销建议。"
        "只使用样本与品牌资料中的真实信息，禁止编造型号、SKU、虚假销量、虚假认证或未给出的营收数据。"
        "报告使用简体中文 Markdown，结论要具体，避免空话。"
    )
    user = f"""
请基于以下抖音抓取样本，完成「{type_name}」报告。

【检索关键词】{keyword}
【样本数量】{sample_count}
【时间筛选】{note_time or "未指定"}
{extra_block}
【报告结构要求】
{outline}

【硬性要求】
1. 先数据后观点，引用样本中的标题/互动特征时要具体。
2. 最后策略必须服务基诺浦，且只使用下方品牌资料中的真实信息。
3. 明确写出数据局限（搜索 TopN，非全站）。
4. 不要输出与报告无关的开场白。

【视频样本】
{videos_text}

【品牌资料】
{brand_text}
""".strip()
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def safe_filename(keyword: str, analysis_type: str) -> str:
    _, type_name = resolve_analysis_type(analysis_type)
    raw = f"抖音{type_name}_{keyword or '报告'}"
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", raw).strip() or "抖音分析报告"
    return cleaned[:60]


# ---------------------------------------------------------------------------
# 报告持久化（复用 PostgreSQL 模式，独立 dy_reports 表）
# ---------------------------------------------------------------------------

def _ensure_reports_dir() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    keep = REPORTS_DIR / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")
    return REPORTS_DIR


def save_report(report_md: str, meta: dict) -> dict:
    """保存报告到 dy-reports/ 和 PostgreSQL。"""
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
    try:
        md_path = REPORTS_DIR / f"{report_id}.md"
        meta_path = REPORTS_DIR / f"{report_id}.json"
        md_path.write_text(report_md or "", encoding="utf-8")
        meta_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[dy-fs] save report failed: {e}")
    if _get_db_url():
        pg_ok = _pg_save_report(report_md, record)
        if not pg_ok:
            record["pg_save_failed"] = True
            print("[dy] WARNING: pg save failed, report only in local fs")
    return record


def list_reports(limit: int = 100) -> list[dict]:
    if _get_db_url():
        pg_items = _pg_list_reports(limit)
        if pg_items is not None:
            return pg_items
        print("[dy] pg list failed, fallback to filesystem")
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
            })
        except (OSError, json.JSONDecodeError):
            continue
    items.sort(key=lambda x: x.get("created_at") or x.get("id") or "", reverse=True)
    return items[: max(1, min(int(limit or 100), 500))]


def get_report(report_id: str) -> dict:
    if _get_db_url():
        result = _pg_get_report(report_id)
        if result:
            return result
        print("[dy] pg get failed or not found, fallback to filesystem")
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
    if _get_db_url():
        deleted = _pg_delete_report(report_id)
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
# PostgreSQL 持久化（独立 dy_reports 表）
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
    conn = _get_pg_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS dy_reports (
                    id           TEXT PRIMARY KEY,
                    title        TEXT,
                    keyword      TEXT DEFAULT '',
                    analysis_type TEXT DEFAULT '',
                    analysis_type_name TEXT DEFAULT '',
                    sample_count INTEGER DEFAULT 0,
                    note_time    TEXT DEFAULT '',
                    sort_type    TEXT DEFAULT '',
                    fetch_comments BOOLEAN DEFAULT FALSE,
                    created_at   TEXT,
                    report_md    TEXT,
                    meta_json    TEXT
                )
            """)
        conn.commit()
    except Exception as e:
        print(f"[dy-pg] init table failed: {e}")
    finally:
        _return_pg_conn(conn)


def _pg_save_report(report_md: str, record: dict) -> bool:
    conn = _get_pg_conn()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO dy_reports
                    (id, title, keyword, analysis_type, analysis_type_name,
                     sample_count, note_time, sort_type, fetch_comments,
                     created_at, report_md, meta_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                record.get("created_at", ""),
                report_md,
                json.dumps(record, ensure_ascii=False),
            ))
        conn.commit()
        print(f"[dy-pg] saved report {record.get('id')}")
        return True
    except Exception as e:
        print(f"[dy-pg] save report failed: {e}")
        return False
    finally:
        _return_pg_conn(conn)


def _pg_list_reports(limit: int = 100) -> list[dict] | None:
    conn = _get_pg_conn()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, keyword, analysis_type, analysis_type_name,
                       sample_count, note_time, created_at
                FROM dy_reports
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
                "created_at": r[7] or "",
            })
        return items
    except Exception as e:
        print(f"[dy-pg] list reports failed: {e}")
        return None
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
                SELECT meta_json, report_md FROM dy_reports WHERE id = %s
            """, (safe_id,))
            row = cur.fetchone()
        if not row:
            return None
        meta = json.loads(row[0]) if row[0] else {}
        return {"meta": meta, "report_md": row[1] or ""}
    except Exception as e:
        print(f"[dy-pg] get report failed: {e}")
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
            cur.execute("DELETE FROM dy_reports WHERE id = %s", (safe_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    except Exception as e:
        print(f"[dy-pg] delete report failed: {e}")
        return False
    finally:
        _return_pg_conn(conn)
