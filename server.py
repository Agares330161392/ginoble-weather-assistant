# -*- coding: utf-8 -*-
"""基诺浦场景小助手 - 本地服务（天气代理 + 通义千问分析 + 小红书分析）"""
import os
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import xhs_service
import dy_service

BASE_DIR = Path(__file__).resolve().parent
KEY_ENV_CANDIDATES = [BASE_DIR / "key.env", BASE_DIR.parent / "key.env"]
BRAND_FILE_CANDIDATES = [BASE_DIR / "ginoble_brand.txt", BASE_DIR.parent / "ginoble_brand.txt"]
SERVER_PORT = 5000
HOT_CACHE_DIR = BASE_DIR / "hot_cache"
WEATHER_REPORTS_DIR = BASE_DIR / "weather-reports"

app = Flask(__name__, static_folder="static")
CORS(app)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# 小红书分析任务（内存）；关闭弹窗不中断
_xhs_jobs: dict[str, dict] = {}
_xhs_jobs_lock = threading.Lock()

# 抖音分析任务（内存）；关闭弹窗不中断
_dy_jobs: dict[str, dict] = {}
_dy_jobs_lock = threading.Lock()


def _open_browser_once(url: str):
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()


def _pids_listening_on_port(port: int) -> set[int]:
    """找出占用本地端口的进程（不含当前进程）。"""
    my_pid = os.getpid()
    pids: set[int] = set()

    def _addr_port(local: str) -> str | None:
        if local.startswith("[") and "]:" in local:
            return local.rsplit("]:", 1)[-1]
        if ":" in local:
            return local.rsplit(":", 1)[-1]
        return None

    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["netstat", "-ano", "-p", "tcp"],
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
        except (OSError, subprocess.CalledProcessError):
            return pids
        for line in out.splitlines():
            if "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            if _addr_port(parts[1]) != str(port):
                continue
            try:
                pid = int(parts[-1])
            except ValueError:
                continue
            if pid > 0 and pid != my_pid:
                pids.add(pid)
    else:
        try:
            out = subprocess.check_output(
                ["lsof", "-ti", f"tcp:{port}"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for raw in out.split():
                pid = int(raw)
                if pid > 0 and pid != my_pid:
                    pids.add(pid)
        except (OSError, subprocess.CalledProcessError, ValueError):
            pass
    return pids


def _free_server_port(port: int = SERVER_PORT) -> None:
    """启动前关掉占用本端口的旧进程，避免多开冲突。

    风险：会结束任何占用该端口的程序（通常就是以前的本服务）。
    不会杀掉「所有 Python」，只动这个端口。
    """
    pids = _pids_listening_on_port(port)
    if not pids:
        print(f"[startup] port {port} is free")
        return
    print(f"[startup] freeing port {port}, kill old pid(s): {', '.join(map(str, sorted(pids)))}")
    for pid in sorted(pids):
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                os.kill(pid, 15)
        except OSError as e:
            print(f"[startup] failed to stop pid {pid}: {e}")
    # 等系统释放端口
    for _ in range(20):
        if not _pids_listening_on_port(port):
            break
        time.sleep(0.15)
    left = _pids_listening_on_port(port)
    if left:
        print(f"[startup] warning: port {port} still held by {', '.join(map(str, sorted(left)))}")
    else:
        print(f"[startup] port {port} ready")


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def _load_env_map() -> dict[str, str]:
    path = _first_existing(KEY_ENV_CANDIDATES)
    if not path:
        return {}
    env: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    bare = ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            name, value = line.split("=", 1)
            env[name.strip()] = value.strip().strip('"').strip("'")
        elif not bare:
            bare = line
    if bare and "DASHSCOPE_API_KEY" not in env:
        env["DASHSCOPE_API_KEY"] = bare
    env["_path"] = str(path)
    return env


def load_api_key() -> str:
    for name in ("DASHSCOPE_API_KEY", "API_KEY", "KEY"):
        val = os.environ.get(name, "").strip()
        if val:
            print(f"[apikey] loaded from env var {name}")
            return val
    env = _load_env_map()
    for name in ("DASHSCOPE_API_KEY", "API_KEY", "KEY"):
        if env.get(name):
            print(f"[apikey] loaded from {Path(env.get('_path', 'key.env')).name}")
            return env[name]
    if not env:
        print("[apikey] missing: put key in weather-app/key.env or set DASHSCOPE_API_KEY env var")
    else:
        print("[apikey] no usable DashScope key in key.env")
    return ""


def load_xhs_api_key() -> str:
    for name in ("XHS_API_KEY", "WONISOFT_API_KEY", "XHS_TOKEN"):
        val = os.environ.get(name, "").strip()
        if val:
            print(f"[xhs] apikey loaded from env var {name}")
            return val
    env = _load_env_map()
    for name in ("XHS_API_KEY", "WONISOFT_API_KEY", "XHS_TOKEN"):
        if env.get(name):
            print(f"[xhs] apikey loaded from {Path(env.get('_path', 'key.env')).name}")
            return env[name]
    print("[xhs] missing: put XHS_API_KEY in weather-app/key.env or set XHS_API_KEY env var")
    return ""


def load_tikhub_api_key() -> str:
    for name in ("TIKHUB_API_KEY", "DY_API_KEY", "DOUYIN_API_KEY"):
        val = os.environ.get(name, "").strip()
        if val:
            print(f"[dy] apikey loaded from env var {name}")
            return val
    env = _load_env_map()
    for name in ("TIKHUB_API_KEY", "DY_API_KEY", "DOUYIN_API_KEY"):
        if env.get(name):
            print(f"[dy] apikey loaded from {Path(env.get('_path', 'key.env')).name}")
            return env[name]
    print("[dy] missing: put TIKHUB_API_KEY in weather-app/key.env or set TIKHUB_API_KEY env var")
    return ""


def load_ginoble_knowledge() -> str:
    path = _first_existing(BRAND_FILE_CANDIDATES)
    if not path:
        print("[brand] missing: put copy in weather-app/ginoble_brand.txt")
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        print(f"[brand] empty file: {path}")
        return ""
    print(f"[brand] loaded from {path.name}")
    return text


def fetch_weather(lat: float, lon: float, days: int) -> dict:
    days = max(1, min(int(days), 16))
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "Asia/Shanghai",
        "forecast_days": days,
        "daily": ",".join([
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "precipitation_sum", "precipitation_probability_max",
            "wind_speed_10m_max", "uv_index_max",
        ]),
        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
    }
    r = requests.get(OPEN_METEO_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def build_weather_summary(city_name: str, province: str, data: dict) -> str:
    daily = data.get("daily", {})
    current = data.get("current", {})
    parts = [
        f"城市：{province} {city_name}".strip(),
        f"当前温度：{current.get('temperature_2m', '未知')}℃",
        f"当前湿度：{current.get('relative_humidity_2m', '未知')}%",
        f"当前风速：{current.get('wind_speed_10m', '未知')} km/h",
    ]
    times = daily.get("time", [])[:7]
    tmax = daily.get("temperature_2m_max", [])[:7]
    tmin = daily.get("temperature_2m_min", [])[:7]
    rain = daily.get("precipitation_sum", [])[:7]
    rain_prob = daily.get("precipitation_probability_max", [])[:7]
    wind = daily.get("wind_speed_10m_max", [])[:7]
    for i, day in enumerate(times):
        parts.append(f"{day}：最高{tmax[i] if i < len(tmax) else '未知'}℃，最低{tmin[i] if i < len(tmin) else '未知'}℃，降水{rain[i] if i < len(rain) else '未知'}mm，降水概率{rain_prob[i] if i < len(rain_prob) else '未知'}%，最大风速{wind[i] if i < len(wind) else '未知'}km/h")
    return "\n".join(parts)


STRICT_FACTS = """
只允许使用以下真实品牌信息：基诺浦（GINOBLE®）、2008 年成立、中国专业儿童机能鞋品牌、五阶段机能鞋体系、本体感鞋、成长鞋、稳健鞋、跃步鞋、健步鞋、幼儿园鞋、功能性皮鞋、夏季凉鞋、冬季棉鞋、运动跑鞋。
禁止输出任何型号编号、SKU 编号、虚构系列名、虚构参数、虚假销量、虚假认证或品牌没有明确出现的鞋类名称。
如果某个信息不在已给品牌资料中，必须直接忽略，不要猜测，不要补全，不要编造。
"""


def build_marketing_prompt(city_name: str, province: str, weather_text: str, mode: str = "base") -> list[dict]:
    system_prompt = (
        "你是基诺浦场景小助手。只做营销判断，不做天气科普；只用真实品牌信息，不编造型号、SKU、系列名或数据。"
        "输出要稳、准、可执行。"
    )
    if mode == "deep":
        user_prompt = f"""
请基于以下天气信息，补充输出深度分析。

【城市】{province} {city_name}
【天气信息】
{weather_text}

【要求】
1. 仅使用品牌资料中明确出现的鞋款名称。
2. 不写型号编号、SKU、虚构参数、虚假销量、虚假认证。
3. 每个小标题 100-200 字，合计内容不要太长。
4. 只输出以下 4 个模块：
【适用人群/场景】
【营销策略】
【内容/文案方向】
【下一步预判】
""".strip()
    else:
        user_prompt = f"""
请基于以下天气信息，输出基础分析。

【城市】{province} {city_name}
【天气信息】
{weather_text}

【要求】
1. 仅使用品牌资料中明确出现的鞋款名称。
2. 不写型号编号、SKU、虚构参数、虚假销量、虚假认证。
3. 每个小标题 100-200 字，内容要具体但不要啰嗦，尽量分点叙述，清晰简洁。
4. 在【主推鞋款】模块中，必须按“款式名称 + 一句话介绍”的方式逐条输出，每个款式用 1 句简短的话介绍一下适用天气、核心功能或场景。，这个模块可以小于100字
5. 只输出以下 4 个模块：
【天气判断】
【核心需求】
【主推鞋款】
【推荐理由】
""".strip()
    return [
        {"role": "system", "content": system_prompt + STRICT_FACTS},
        {"role": "user", "content": user_prompt + "\n\n品牌资料：\n" + load_ginoble_knowledge()},
    ]


def call_qwen(api_key: str, city_name: str, province: str, weather_text: str, mode: str = "base") -> str:
    brand = load_ginoble_knowledge()
    if not brand:
        raise RuntimeError("品牌文案未加载，请检查 ginoble_brand.txt")
    payload = {
        "model": "qwen-plus",
        "messages": build_marketing_prompt(city_name, province, weather_text, mode=mode),
        "temperature": 0.3,
    }
    resp = requests.post(DASHSCOPE_URL, json=payload, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_qwen_messages(api_key: str, messages: list[dict], temperature: float = 0.3, timeout: int = 120) -> str:
    payload = {
        "model": "qwen-plus",
        "messages": messages,
        "temperature": temperature,
    }
    resp = requests.post(
        DASHSCOPE_URL,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


@app.route("/")
def index():
    return send_from_directory(BASE_DIR / "static", "index.html")

@app.route("/data/<path:filename>")
def data_files(filename):
    return send_from_directory(BASE_DIR / "data", filename)

@app.route("/api/health")
def health():
    return jsonify({
        "ok": True,
        "has_api_key": bool(load_api_key()),
        "has_xhs_api_key": bool(load_xhs_api_key()),
        "has_tikhub_api_key": bool(load_tikhub_api_key()),
        "brand_loaded": bool(load_ginoble_knowledge()),
        "brand": "基诺浦 GINOBLE",
    })

@app.route("/api/weather")
def weather():
    try:
        lat = float(request.args.get("lat", ""))
        lon = float(request.args.get("lon", ""))
        days = int(request.args.get("days", 7))
    except (TypeError, ValueError):
        return jsonify({"error": "参数 lat、lon、days 无效"}), 400
    try:
        return jsonify(fetch_weather(lat, lon, days))
    except requests.RequestException as e:
        return jsonify({"error": f"天气服务请求失败: {e}"}), 502

@app.route("/api/analyze", methods=["POST"])
def analyze():
    api_key = load_api_key()
    if not api_key:
        return jsonify({"error": "未配置千问 API Key（请检查 key.env）"}), 500
    if not load_ginoble_knowledge():
        return jsonify({"error": "未加载品牌文案（请检查 ginoble_brand.txt）"}), 500
    body = request.get_json(silent=True) or {}
    city_name = body.get("city", "未知城市")
    province = body.get("province", "")
    weather_data = body.get("weather")
    deep = bool(body.get("deep", False))
    if not weather_data:
        return jsonify({"error": "缺少天气数据"}), 400
    weather_text = build_weather_summary(city_name, province, weather_data)
    try:
        analysis = call_qwen(api_key, city_name, province, weather_text, mode="deep" if deep else "base")
        # 保存天气分析报告
        saved = _wtr_save_report(analysis, {
            "city": city_name,
            "province": province,
            "analysis_type": "deep" if deep else "base",
            "weather_summary": weather_text,
        })
        report_id = saved.get("id") if saved else None
        return jsonify({"analysis": analysis, "weather_summary": weather_text, "report_id": report_id})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except requests.RequestException as e:
        return jsonify({"error": f"网络错误: {e}"}), 502


@app.route("/api/xhs/presets", methods=["GET"])
def xhs_presets_list():
    doc = xhs_service.load_presets_doc()
    return jsonify(doc)


@app.route("/api/xhs/presets", methods=["POST"])
def xhs_presets_create():
    body = request.get_json(silent=True) or {}
    if not (body.get("keyword") or "").strip() and not (body.get("name") or "").strip():
        return jsonify({"error": "请至少填写预设名称或关键词"}), 400
    try:
        preset = xhs_service.create_preset(body)
        return jsonify({"preset": preset})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/xhs/presets/<preset_id>", methods=["PUT"])
def xhs_presets_update(preset_id: str):
    body = request.get_json(silent=True) or {}
    try:
        preset = xhs_service.update_preset(preset_id, body)
        return jsonify({"preset": preset})
    except KeyError:
        return jsonify({"error": "预设不存在"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/xhs/presets/<preset_id>", methods=["DELETE"])
def xhs_presets_delete(preset_id: str):
    try:
        xhs_service.delete_preset(preset_id)
        return jsonify({"ok": True})
    except KeyError:
        return jsonify({"error": "预设不存在"}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/xhs/last-selection", methods=["PUT"])
def xhs_last_selection():
    body = request.get_json(silent=True) or {}
    try:
        last = xhs_service.update_last_selection(body)
        return jsonify({"last_selection": last})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/xhs/analyze", methods=["POST"])
def xhs_analyze():
    """启动后台分析任务，立即返回 job_id；前端轮询进度。关闭弹窗不会中断。"""
    qwen_key = load_api_key()
    xhs_key = load_xhs_api_key()
    brand = load_ginoble_knowledge()
    if not qwen_key:
        return jsonify({"error": "未配置千问 API Key（请检查 key.env）"}), 500
    if not xhs_key:
        return jsonify({"error": "未配置小红书 API Key（请在 key.env 写入 XHS_API_KEY）"}), 500
    if not brand:
        return jsonify({"error": "未加载品牌文案（请检查 ginoble_brand.txt）"}), 500

    body = request.get_json(silent=True) or {}
    fields = xhs_service.selection_fields(body)
    if not fields["keyword"]:
        return jsonify({"error": "请填写分析关键词"}), 400

    try:
        xhs_service.update_last_selection(fields)
    except Exception:
        pass

    weather_text = ""
    if fields["use_weather"]:
        weather_text = (body.get("weather_summary") or "").strip()
        if not weather_text:
            weather_data = body.get("weather")
            city_name = body.get("city") or fields.get("weather_city") or "当前城市"
            province = body.get("province") or fields.get("weather_province") or ""
            if weather_data:
                weather_text = build_weather_summary(city_name, province, weather_data)

    job_id = uuid.uuid4().hex[:12]
    with _xhs_jobs_lock:
        _xhs_jobs[job_id] = {
            "status": "running",
            "percent": 2,
            "message": "任务已创建，准备搜索…",
            "result": None,
            "error": None,
        }

    def _set_progress(percent: int, message: str):
        with _xhs_jobs_lock:
            job = _xhs_jobs.get(job_id)
            if not job or job.get("status") != "running":
                return
            job["percent"] = max(0, min(99, int(percent)))
            job["message"] = message

    def _run_job():
        try:
            _set_progress(8, f"正在搜索「{fields['keyword']}」…")
            notes = xhs_service.search_notes(
                xhs_key,
                keyword=fields["keyword"],
                fetch_count=fields["fetch_count"],
                sort_type=fields["sort_type"],
                note_time=fields["note_time"],
            )
            if not notes:
                raise RuntimeError("未搜索到相关笔记，请更换关键词或时间范围后重试")

            total = len(notes)
            _set_progress(18, f"已找到 {total} 条，开始拉取详情…")

            def on_progress(done, all_count, title):
                # 详情阶段：18% → 72%
                pct = 18 + int(54 * done / max(all_count, 1))
                short = (title or "")[:18]
                tip = f"拉取详情 {done}/{all_count}" + (f"：{short}" if short else "")
                _set_progress(pct, tip)

            enriched = xhs_service.enrich_notes(
                xhs_key,
                notes,
                fetch_comments=fields["fetch_comments"],
                on_progress=on_progress,
            )
            notes_text = xhs_service.notes_to_prompt_text(enriched)
            _, type_name = xhs_service.resolve_analysis_type(fields["analysis_type"])
            messages = xhs_service.build_xhs_analysis_messages(
                analysis_type=fields["analysis_type"],
                keyword=fields["keyword"],
                notes_text=notes_text,
                brand_text=brand + "\n" + STRICT_FACTS,
                extra_prompt=fields["extra_prompt"],
                weather_text=weather_text,
                sample_count=len(enriched),
                note_time=fields["note_time"],
            )
            _set_progress(78, "详情完成，通义千问分析中（较慢，请稍候）…")
            report_md = call_qwen_messages(qwen_key, messages, temperature=0.35, timeout=180)
            _set_progress(92, "分析完成，正在保存报告…")
            filename = xhs_service.safe_filename(fields["keyword"], fields["analysis_type"]) + ".md"
            meta = {
                "keyword": fields["keyword"],
                "analysis_type": fields["analysis_type"],
                "analysis_type_name": type_name,
                "sample_count": len(enriched),
                "note_time": fields["note_time"],
                "sort_type": fields["sort_type"],
                "fetch_comments": fields["fetch_comments"],
                "use_weather": bool(weather_text),
                "weather_city": fields.get("weather_city") or "",
                "filename": filename,
            }
            try:
                saved = xhs_service.save_report(report_md, meta)
                meta = {**meta, **saved}
            except Exception as e:
                print(f"[xhs] save report failed: {e}")

            payload = {
                "report_md": report_md,
                "meta": meta,
                "notes": [
                    {
                        "note_id": n.get("note_id"),
                        "title": n.get("title"),
                        "liked": n.get("liked", 0),
                        "collected": n.get("collected", 0),
                        "commented": n.get("commented", 0),
                        "author": n.get("author"),
                    }
                    for n in enriched
                ],
            }
            with _xhs_jobs_lock:
                _xhs_jobs[job_id] = {
                    "status": "done",
                    "percent": 100,
                    "message": "分析完成",
                    "result": payload,
                    "error": None,
                }
        except Exception as e:
            with _xhs_jobs_lock:
                _xhs_jobs[job_id] = {
                    "status": "error",
                    "percent": 100,
                    "message": "分析失败",
                    "result": None,
                    "error": str(e),
                }

    threading.Thread(target=_run_job, daemon=True).start()
    return jsonify({"job_id": job_id, "status": "running"})


@app.route("/api/xhs/analyze/status/<job_id>", methods=["GET"])
def xhs_analyze_status(job_id: str):
    with _xhs_jobs_lock:
        job = _xhs_jobs.get(job_id)
        if not job:
            return jsonify({"error": "任务不存在或已过期"}), 404
        # 返回副本，避免并发改写
        data = {
            "job_id": job_id,
            "status": job.get("status"),
            "percent": job.get("percent", 0),
            "message": job.get("message") or "",
            "error": job.get("error"),
        }
        if job.get("status") == "done":
            data["result"] = job.get("result")
    return jsonify(data)


@app.route("/api/xhs/reports", methods=["GET"])
def xhs_reports_list():
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    return jsonify({"reports": xhs_service.list_reports(limit=limit)})


@app.route("/api/xhs/reports/<report_id>", methods=["GET"])
def xhs_reports_get(report_id: str):
    try:
        data = xhs_service.get_report(report_id)
        return jsonify(data)
    except KeyError:
        return jsonify({"error": "报告不存在"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/xhs/reports/<report_id>", methods=["DELETE"])
def xhs_reports_delete(report_id: str):
    try:
        xhs_service.delete_report(report_id)
        return jsonify({"ok": True})
    except KeyError:
        return jsonify({"error": "报告不存在"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===========================================================================
# 抖音内容抓取分析 API
# ===========================================================================

@app.route("/api/dy/presets", methods=["GET"])
def dy_presets_list():
    doc = dy_service.load_presets_doc()
    return jsonify(doc)


@app.route("/api/dy/presets", methods=["POST"])
def dy_presets_create():
    body = request.get_json(silent=True) or {}
    if not (body.get("keyword") or "").strip() and not (body.get("name") or "").strip():
        return jsonify({"error": "请至少填写预设名称或关键词"}), 400
    try:
        preset = dy_service.create_preset(body)
        return jsonify({"preset": preset})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dy/presets/<preset_id>", methods=["PUT"])
def dy_presets_update(preset_id: str):
    body = request.get_json(silent=True) or {}
    try:
        preset = dy_service.update_preset(preset_id, body)
        return jsonify({"preset": preset})
    except KeyError:
        return jsonify({"error": "预设不存在"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dy/presets/<preset_id>", methods=["DELETE"])
def dy_presets_delete(preset_id: str):
    try:
        dy_service.delete_preset(preset_id)
        return jsonify({"ok": True})
    except KeyError:
        return jsonify({"error": "预设不存在"}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dy/last-selection", methods=["PUT"])
def dy_last_selection():
    body = request.get_json(silent=True) or {}
    try:
        last = dy_service.update_last_selection(body)
        return jsonify({"last_selection": last})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dy/analyze", methods=["POST"])
def dy_analyze():
    """启动抖音后台分析任务，立即返回 job_id；前端轮询进度。"""
    qwen_key = load_api_key()
    tikhub_key = load_tikhub_api_key()
    brand = load_ginoble_knowledge()
    if not qwen_key:
        return jsonify({"error": "未配置千问 API Key（请检查 key.env）"}), 500
    if not tikhub_key:
        return jsonify({"error": "未配置 TikHub API Key（请在 key.env 写入 TIKHUB_API_KEY）"}), 500
    if not brand:
        return jsonify({"error": "未加载品牌文案（请检查 ginoble_brand.txt）"}), 500

    body = request.get_json(silent=True) or {}
    fields = dy_service.selection_fields(body)
    if not fields["keyword"]:
        return jsonify({"error": "请填写分析关键词"}), 400

    try:
        dy_service.update_last_selection(fields)
    except Exception:
        pass

    job_id = uuid.uuid4().hex[:12]
    with _dy_jobs_lock:
        _dy_jobs[job_id] = {
            "status": "running",
            "percent": 2,
            "message": "任务已创建，准备搜索…",
            "result": None,
            "error": None,
        }

    def _set_progress(percent: int, message: str):
        with _dy_jobs_lock:
            job = _dy_jobs.get(job_id)
            if not job or job.get("status") != "running":
                return
            job["percent"] = max(0, min(99, int(percent)))
            job["message"] = message

    def _run_job():
        try:
            _set_progress(8, f"正在搜索「{fields['keyword']}」…")
            videos = dy_service.search_videos(
                tikhub_key,
                keyword=fields["keyword"],
                fetch_count=fields["fetch_count"],
                sort_type=fields["sort_type"],
                note_time=fields["note_time"],
            )
            if not videos:
                raise RuntimeError("未搜索到相关视频，请更换关键词或时间范围后重试")

            total = len(videos)
            _set_progress(18, f"已找到 {total} 条，开始拉取详情…")

            def on_progress(done, all_count, title):
                pct = 18 + int(54 * done / max(all_count, 1))
                short = (title or "")[:18]
                tip = f"拉取详情 {done}/{all_count}" + (f"：{short}" if short else "")
                _set_progress(pct, tip)

            enriched = dy_service.enrich_videos(
                tikhub_key,
                videos,
                fetch_comments=fields["fetch_comments"],
                on_progress=on_progress,
            )
            videos_text = dy_service.videos_to_prompt_text(enriched)
            _, type_name = dy_service.resolve_analysis_type(fields["analysis_type"])
            messages = dy_service.build_dy_analysis_messages(
                analysis_type=fields["analysis_type"],
                keyword=fields["keyword"],
                videos_text=videos_text,
                brand_text=brand + "\n" + STRICT_FACTS,
                extra_prompt=fields["extra_prompt"],
                sample_count=len(enriched),
                note_time=fields["note_time"],
            )
            _set_progress(78, "详情完成，通义千问分析中（较慢，请稍候）…")
            report_md = call_qwen_messages(qwen_key, messages, temperature=0.35, timeout=180)
            _set_progress(92, "分析完成，正在保存报告…")
            filename = dy_service.safe_filename(fields["keyword"], fields["analysis_type"]) + ".md"
            meta = {
                "keyword": fields["keyword"],
                "analysis_type": fields["analysis_type"],
                "analysis_type_name": type_name,
                "sample_count": len(enriched),
                "note_time": fields["note_time"],
                "sort_type": fields["sort_type"],
                "fetch_comments": fields["fetch_comments"],
                "filename": filename,
            }
            try:
                saved = dy_service.save_report(report_md, meta)
                meta = {**meta, **saved}
            except Exception as e:
                print(f"[dy] save report failed: {e}")

            payload = {
                "report_md": report_md,
                "meta": meta,
                "notes": [
                    {
                        "aweme_id": n.get("aweme_id"),
                        "title": n.get("title"),
                        "liked": n.get("liked", 0),
                        "commented": n.get("commented", 0),
                        "author": n.get("author"),
                    }
                    for n in enriched
                ],
            }
            with _dy_jobs_lock:
                _dy_jobs[job_id] = {
                    "status": "done",
                    "percent": 100,
                    "message": "分析完成",
                    "result": payload,
                    "error": None,
                }
        except Exception as e:
            with _dy_jobs_lock:
                _dy_jobs[job_id] = {
                    "status": "error",
                    "percent": 100,
                    "message": "分析失败",
                    "result": None,
                    "error": str(e),
                }

    threading.Thread(target=_run_job, daemon=True).start()
    return jsonify({"job_id": job_id, "status": "running"})


@app.route("/api/dy/analyze/status/<job_id>", methods=["GET"])
def dy_analyze_status(job_id: str):
    with _dy_jobs_lock:
        job = _dy_jobs.get(job_id)
        if not job:
            return jsonify({"error": "任务不存在或已过期"}), 404
        data = {
            "job_id": job_id,
            "status": job.get("status"),
            "percent": job.get("percent", 0),
            "message": job.get("message") or "",
            "error": job.get("error"),
        }
        if job.get("status") == "done":
            data["result"] = job.get("result")
    return jsonify(data)


@app.route("/api/dy/reports", methods=["GET"])
def dy_reports_list():
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    return jsonify({"reports": dy_service.list_reports(limit=limit)})


@app.route("/api/dy/reports/<report_id>", methods=["GET"])
def dy_reports_get(report_id: str):
    try:
        data = dy_service.get_report(report_id)
        return jsonify(data)
    except KeyError:
        return jsonify({"error": "报告不存在"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dy/reports/<report_id>", methods=["DELETE"])
def dy_reports_delete(report_id: str):
    try:
        dy_service.delete_report(report_id)
        return jsonify({"ok": True})
    except KeyError:
        return jsonify({"error": "报告不存在"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dy/hot", methods=["GET"])
def dy_hot_list():
    """获取童装童鞋垂直热榜（多关键词搜索聚合）。"""
    tikhub_key = load_tikhub_api_key()
    if not tikhub_key:
        return jsonify({"error": "未配置 TikHub API Key"}), 500
    top_n = int(request.args.get("top_n", 20))
    top_n = max(1, min(top_n, 50))
    try:
        items = dy_service.fetch_kids_hot_list(
            api_key=tikhub_key,
            top_n=top_n,
        )
        result = []
        for i, v in enumerate(items, 1):
            result.append({
                "rank": i,
                "aweme_id": v.get("aweme_id"),
                "title": v.get("title"),
                "author": v.get("author"),
                "liked": v.get("liked", 0),
                "commented": v.get("commented", 0),
                "hot_score": v.get("hot_score", 0),
                "source_keyword": v.get("source_keyword"),
            })
        return jsonify({"items": result, "count": len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/xhs/hot", methods=["GET"])
def xhs_hot_list():
    """获取童装童鞋小红书垂直热榜（多关键词搜索聚合）。"""
    xhs_key = load_xhs_api_key()
    if not xhs_key:
        return jsonify({"error": "未配置小红书 API Key"}), 500
    top_n = int(request.args.get("top_n", 20))
    top_n = max(1, min(top_n, 50))
    try:
        items = xhs_service.fetch_kids_hot_list(
            api_key=xhs_key,
            top_n=top_n,
        )
        result = []
        for i, n in enumerate(items, 1):
            result.append({
                "rank": i,
                "note_id": n.get("note_id"),
                "xsec_token": n.get("xsec_token", ""),
                "title": n.get("title"),
                "author": n.get("author"),
                "liked": n.get("liked", 0),
                "collected": n.get("collected", 0),
                "commented": n.get("commented", 0),
                "hot_score": n.get("hot_score", 0),
                "source_keyword": n.get("source_keyword"),
            })
        return jsonify({"items": result, "count": len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# 热搜日历 + 缓存系统
# ---------------------------------------------------------------------------

import json as _json_module
import datetime as _dt


def _hot_cache_path(date_str: str) -> Path:
    return HOT_CACHE_DIR / f"{date_str}.json"


def _hot_today_str() -> str:
    return _dt.date.today().strftime("%Y-%m-%d")


def _hot_save_cache(dy_items: list, xhs_items: list) -> str:
    HOT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    date_str = _hot_today_str()
    cache = {
        "date": date_str,
        "created_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dy": dy_items,
        "xhs": xhs_items,
    }
    _hot_cache_path(date_str).write_text(
        _json_module.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return date_str


def _hot_load_cache(date_str: str) -> dict | None:
    p = _hot_cache_path(date_str)
    if not p.is_file():
        return None
    try:
        return _json_module.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


@app.route("/api/hot/today", methods=["GET"])
def hot_today():
    """获取今日热榜（有缓存则直接返回，避免重复拉取）。

    ?force=1 时强制重新拉取。
    """
    force = request.args.get("force", "0") == "1"
    date_str = _hot_today_str()

    if not force:
        cached = _hot_load_cache(date_str)
        if cached:
            return jsonify({"cached": True, **cached})

    # 需要拉取
    tikhub_key = load_tikhub_api_key()
    xhs_key = load_xhs_api_key()
    errors = []
    dy_items = []
    xhs_items = []

    if tikhub_key:
        try:
            raw = dy_service.fetch_kids_hot_list(api_key=tikhub_key, top_n=20)
            dy_items = [{
                "rank": i + 1,
                "aweme_id": v.get("aweme_id"),
                "title": v.get("title"),
                "author": v.get("author"),
                "liked": v.get("liked", 0),
                "commented": v.get("commented", 0),
                "hot_score": v.get("hot_score", 0),
                "source_keyword": v.get("source_keyword"),
            } for i, v in enumerate(raw)]
        except Exception as e:
            errors.append(f"抖音: {e}")

    if xhs_key:
        try:
            raw = xhs_service.fetch_kids_hot_list(api_key=xhs_key, top_n=20)
            xhs_items = [{
                "rank": i + 1,
                "note_id": n.get("note_id"),
                "xsec_token": n.get("xsec_token", ""),
                "title": n.get("title"),
                "author": n.get("author"),
                "liked": n.get("liked", 0),
                "collected": n.get("collected", 0),
                "commented": n.get("commented", 0),
                "hot_score": n.get("hot_score", 0),
                "source_keyword": n.get("source_keyword"),
            } for i, n in enumerate(raw)]
        except Exception as e:
            errors.append(f"小红书: {e}")

    _hot_save_cache(dy_items, xhs_items)
    return jsonify({
        "cached": False,
        "date": date_str,
        "created_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dy": dy_items,
        "xhs": xhs_items,
        "errors": errors if errors else None,
    })


@app.route("/api/hot/calendar", methods=["GET"])
def hot_calendar():
    """返回有缓存数据的日期列表。"""
    HOT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dates = []
    for p in HOT_CACHE_DIR.glob("*.json"):
        date_str = p.stem
        try:
            _dt.date.fromisoformat(date_str)
            dates.append(date_str)
        except ValueError:
            continue
    dates.sort(reverse=True)
    return jsonify({"dates": dates})


@app.route("/api/hot/date", methods=["GET"])
def hot_by_date():
    """获取指定日期的缓存热榜。"""
    date_str = request.args.get("date", "")
    if not date_str:
        return jsonify({"error": "缺少 date 参数"}), 400
    cached = _hot_load_cache(date_str)
    if not cached:
        return jsonify({"error": "该日期无缓存数据"}), 404
    return jsonify(cached)


# ---------------------------------------------------------------------------
# 报告日历 API（小红书 + 抖音）
# ---------------------------------------------------------------------------

@app.route("/api/xhs/reports/calendar", methods=["GET"])
def xhs_reports_calendar():
    """返回小红书报告存在的日期列表。"""
    try:
        limit = int(request.args.get("limit", 500))
    except (TypeError, ValueError):
        limit = 500
    reports = xhs_service.list_reports(limit=limit)
    dates = set()
    for r in reports:
        created = r.get("created_at", "")
        if created and len(created) >= 10:
            dates.add(created[:10])
    return jsonify({"dates": sorted(dates, reverse=True)})


@app.route("/api/dy/reports/calendar", methods=["GET"])
def dy_reports_calendar():
    """返回抖音报告存在的日期列表。"""
    try:
        limit = int(request.args.get("limit", 500))
    except (TypeError, ValueError):
        limit = 500
    reports = dy_service.list_reports(limit=limit)
    dates = set()
    for r in reports:
        created = r.get("created_at", "")
        if created and len(created) >= 10:
            dates.add(created[:10])
    return jsonify({"dates": sorted(dates, reverse=True)})


# ---------------------------------------------------------------------------
# 天气分析报告 API
# ---------------------------------------------------------------------------

def _wtr_ensure_dir() -> Path:
    WEATHER_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    keep = WEATHER_REPORTS_DIR / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")
    return WEATHER_REPORTS_DIR


def _wtr_save_report(report_md: str, meta: dict) -> dict:
    """保存天气分析报告到 weather-reports/ 目录。"""
    _wtr_ensure_dir()
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_id = f"wtr_{stamp}_{uuid.uuid4().hex[:6]}"
    title = f"{meta.get('city', '未知城市')} · {'深度' if meta.get('analysis_type') == 'deep' else '基础'}分析"
    record = {
        **meta,
        "id": report_id,
        "title": title,
        "created_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "filename_md": f"{report_id}.md",
        "filename_meta": f"{report_id}.json",
    }
    try:
        md_path = WEATHER_REPORTS_DIR / f"{report_id}.md"
        meta_path = WEATHER_REPORTS_DIR / f"{report_id}.json"
        md_path.write_text(report_md or "", encoding="utf-8")
        meta_path.write_text(_json_module.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[wtr] save report failed: {e}")
        return None
    return record


def _wtr_list_reports(limit: int = 100, date_filter: str = "") -> list:
    _wtr_ensure_dir()
    items = []
    for meta_path in WEATHER_REPORTS_DIR.glob("*.json"):
        try:
            data = _json_module.loads(meta_path.read_text(encoding="utf-8"))
            if date_filter:
                created = data.get("created_at", "")
                if not created.startswith(date_filter):
                    continue
            items.append(data)
        except Exception:
            continue
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items[:limit]


def _wtr_get_report(report_id: str) -> dict:
    safe_id = report_id.replace("/", "").replace("\\", "").replace("..", "")
    meta_path = WEATHER_REPORTS_DIR / f"{safe_id}.json"
    md_path = WEATHER_REPORTS_DIR / f"{safe_id}.md"
    if not meta_path.exists():
        return None
    data = _json_module.loads(meta_path.read_text(encoding="utf-8"))
    data["report_md"] = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    return data


@app.route("/api/weather/reports", methods=["GET"])
def weather_reports_list():
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    date_filter = request.args.get("date", "")
    reports = _wtr_list_reports(limit=limit, date_filter=date_filter)
    # 不返回完整报告正文，只返回元数据
    for r in reports:
        r.pop("report_md", None)
    return jsonify({"reports": reports})


@app.route("/api/weather/reports/<report_id>", methods=["GET"])
def weather_reports_get(report_id: str):
    data = _wtr_get_report(report_id)
    if not data:
        return jsonify({"error": "报告不存在"}), 404
    return jsonify(data)


@app.route("/api/weather/reports/<report_id>", methods=["DELETE"])
def weather_reports_delete(report_id: str):
    safe_id = report_id.replace("/", "").replace("\\", "").replace("..", "")
    meta_path = WEATHER_REPORTS_DIR / f"{safe_id}.json"
    md_path = WEATHER_REPORTS_DIR / f"{safe_id}.md"
    deleted = False
    if meta_path.exists():
        meta_path.unlink()
        deleted = True
    if md_path.exists():
        md_path.unlink()
        deleted = True
    if not deleted:
        return jsonify({"error": "报告不存在"}), 404
    return jsonify({"ok": True})


@app.route("/api/weather/reports/calendar", methods=["GET"])
def weather_reports_calendar():
    """返回天气报告存在的日期列表。"""
    reports = _wtr_list_reports(limit=500)
    dates = set()
    for r in reports:
        created = r.get("created_at", "")
        if created and len(created) >= 10:
            dates.add(created[:10])
    return jsonify({"dates": sorted(dates, reverse=True)})


if __name__ == "__main__":
    SERVER_PORT = int(os.environ.get("PORT", SERVER_PORT))
    print("基诺浦场景小助手")
    print(f"浏览器打开: http://127.0.0.1:{SERVER_PORT}")
    print("服务启动中，请稍候...")
    _free_server_port(SERVER_PORT)
    load_api_key()
    load_xhs_api_key()
    load_ginoble_knowledge()
    xhs_service._ensure_presets_file()
    xhs_service._ensure_reports_dir()
    try:
        xhs_service._pg_init()
    except Exception as e:
        print(f"[startup] xhs pg init warning: {e}")
    dy_service._ensure_presets_file()
    dy_service._ensure_reports_dir()
    try:
        dy_service._pg_init()
    except Exception as e:
        print(f"[startup] dy pg init warning: {e}")
    load_tikhub_api_key()
    _wtr_ensure_dir()
    host = os.environ.get("HOST", "127.0.0.1")
    if host != "127.0.0.1":
        _open_browser_once(f"http://0.0.0.0:{SERVER_PORT}")
    else:
        _open_browser_once(f"http://127.0.0.1:{SERVER_PORT}")
    app.run(host=host, port=SERVER_PORT, debug=False, use_reloader=False)
else:
    # gunicorn / WSGI 入口：初始化必要目录 + 数据库表
    try:
        xhs_service._ensure_presets_file()
        xhs_service._ensure_reports_dir()
        xhs_service._pg_init()
    except Exception as e:
        print(f"[startup] xhs init warning: {e}")
    try:
        dy_service._ensure_presets_file()
        dy_service._ensure_reports_dir()
        dy_service._pg_init()
    except Exception as e:
        print(f"[startup] dy init warning: {e}")
    try:
        _wtr_ensure_dir()
    except Exception as e:
        print(f"[startup] weather reports dir warning: {e}")
