#!/usr/bin/env python3
"""Local skill browser. Only metadata and explicit search terms leave the UI."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import threading
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
SERVICE = "skill-station-v1"
CATEGORIES = ["全部技能", "协作与导航", "论文与研究", "图表与设计", "文档与办公", "网站与开发", "工具与连接", "模板与其他"]
LABELS = {
    "agent-team": ("多 Agent 指挥官", "让主 agent 协调调查、实施与独立验收，最后整合交付。", "协作与导航", "🐾"),
    "skill-hub": ("技能总入口", "说出目标，帮你选择技能、组合流程，或寻找新技能。", "协作与导航", "🧭"),
    "find-skills": ("寻找新技能", "按需求寻找社区技能，核查来源和适用范围。", "协作与导航", "🔎"),
    "supervisor": ("质量监督员", "组织严格检查与独立评审，核验重要成果。", "协作与导航", "🛡️"),
    "handoff": ("工作交接", "为其他 agent 或后续会话整理清晰的接续材料。", "协作与导航", "🤝"),
    "nature-writing": ("论文写作", "把研究结果和笔记组织成论文段落与投稿材料。", "论文与研究", "✍️"),
    "nature-polishing": ("学术润色", "润色、翻译和压缩已有学术文字，保留事实边界。", "论文与研究", "🪶"),
    "nature-citation": ("论文配引用", "为论文主张寻找支持文献并整理引用。", "论文与研究", "📎"),
    "nature-academic-search": ("文献检索", "查文献、核对引文、整理引用指标和参考文献。", "论文与研究", "📚"),
    "nature-reviewer": ("模拟审稿", "从审稿人视角检查论文的贡献、证据与问题。", "论文与研究", "🧐"),
    "nature-response": ("审稿回复", "准备逐条回复、修回信和修改材料。", "论文与研究", "💌"),
    "nature-paper2ppt": ("论文变 PPT", "把论文制作成中文组会汇报，保留图证和讲稿。", "论文与研究", "🎓"),
    "deep-research": ("深入研究", "围绕问题做多来源研究与反证核查。", "论文与研究", "🔬"),
    "research": ("资料研究", "查阅可信原始资料并保存研究结论。", "论文与研究", "🔭"),
    "nature-figure": ("科研绘图", "根据论证目标制作适合论文的高质量科研图。", "图表与设计", "📊"),
    "scipilot-figure-skill": ("数据图表顾问", "先检查数据，再选择图型与配色并检查成图。", "图表与设计", "📈"),
    "drawio-diagram-builder": ("可编辑结构图", "创建流程图、技术架构图和科研方法图。", "图表与设计", "🧩"),
    "imagegen": ("图片创作", "生成或编辑插画、图片和透明背景素材。", "图表与设计", "🎨"),
    "visualize": ("交互可视化", "用可交互的小工具讲清楚关系、对比与变化。", "图表与设计", "✨"),
    "documents": ("Word 文档", "制作、编辑与检查 Word 文档的实际版面。", "文档与办公", "📝"),
    "pdf": ("PDF 工具", "读取、生成、渲染和检查 PDF。", "文档与办公", "📄"),
    "spreadsheets": ("表格与数据", "处理 Excel、CSV、公式、图表与表格分析。", "文档与办公", "🧮"),
    "presentations": ("演示文稿", "创建或编辑 PowerPoint 与 Google Slides。", "文档与办公", "🖼️"),
    "skill-creator": ("制作新技能", "把可复用的方法封装成自己的 skill。", "协作与导航", "🪄"),
    "skill-installer": ("安装技能", "安装经过选择的技能或指定仓库中的技能。", "工具与连接", "📦"),
    "openai-docs": ("Codex 使用帮助", "核实 Codex、OpenAI 产品和 API 的当前用法。", "工具与连接", "💡"),
    "grilling": ("方案压力测试", "用连续追问澄清想法、风险和决策。", "协作与导航", "🌶️"),
    "grill-me": ("追问与澄清", "通过提问梳理计划与关键假设。", "协作与导航", "🌶️"),
}
SEARCH_HINTS = [
    (("论文", "文献", "学术", "科研", "研究"), ["research", "academic"]),
    (("润色", "翻译", "写作", "写文"), ["writing", "editing"]),
    (("ppt", "幻灯", "汇报", "演示"), ["slides", "presentation"]),
    (("图表", "绘图", "可视化", "画图"), ["data-visualization", "charts"]),
    (("审稿", "评审", "review"), ["review"]),
    (("网页", "网站", "前端", "界面", "设计"), ["frontend-design", "web-design"]),
    (("性能", "优化", "卡顿"), ["performance"]),
    (("react",), ["react"]), (("测试", "bug", "调试", "排查"), ["testing", "debugging"]),
    (("表格", "excel", "csv"), ["spreadsheet"]), (("pdf",), ["pdf"]),
    (("word", "文档", "报告"), ["docx", "documents"]),
    (("agent", "代理", "协作", "分工"), ["multi-agent", "workflow"]),
    (("视频", "动画"), ["video", "animation"]), (("图片", "插画"), ["image"]),
]


def read_yaml(path: Path) -> dict:
    """Read metadata without executing skill contents; PyYAML is optional."""
    try:
        text = path.read_text(encoding="utf-8-sig")
        if path.name.lower() == "skill.md":
            match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---(?:\s*\r?\n|$)", text, re.S)
            if not match:
                return {}
            text = match.group(1)
        try:
            import yaml
            result = yaml.safe_load(text)
            return result if isinstance(result, dict) else {}
        except ImportError:
            result = {}
            lines = text.splitlines()
            for i, line in enumerate(lines):
                match = re.match(r"^\s*(name|description|display_name|short_description|default_prompt):\s*(.*)$", line)
                if not match:
                    continue
                key, value = match.groups()
                if value in (">", "|", ">-", "|-"):
                    rest = []
                    for following in lines[i + 1:]:
                        if following and not following[0].isspace():
                            break
                        rest.append(following.strip())
                    value = " ".join(rest)
                result[key] = value.strip("\"'")
            return result
    except Exception:
        # A broken skill should not hide every other installed skill.
        return {}


def version_key(path: Path):
    return tuple(int(x) for x in re.findall(r"\d+", path.name))


def skill_paths(home: Path, workspaces: list[Path]):
    codex = Path(os.environ.get("CODEX_HOME", str(home / ".codex")))
    roots = [(codex / "skills", "个人技能", True), (codex / "skills/.system", "内置技能", True),
             (home / ".agents/skills", "个人技能", True)]
    for workspace in workspaces:
        roots.extend((workspace / sub, "项目技能", True) for sub in (".agents/skills", ".codex/skills"))
    config = {}
    try:
        config = tomllib.loads((codex / "config.toml").read_text())
    except (OSError, ValueError):
        pass
    disabled_paths = {str(Path(item.get("path", "")).resolve()) for item in config.get("skills", {}).get("config", []) if item.get("enabled") is False}
    for root, origin, enabled in roots:
        if root.is_dir():
            for folder in sorted(root.iterdir()):
                file = folder / "SKILL.md"
                if file.is_file():
                    allowed = str(file.resolve()) not in disabled_paths and str(folder.resolve()) not in disabled_paths
                    yield file, origin, enabled and allowed, ""
    plugins = config.get("plugins", {})
    cache = codex / "plugins/cache"
    if not cache.is_dir():
        return
    for marketplace in sorted(cache.iterdir()):
        if not marketplace.is_dir():
            continue
        for plugin in sorted(marketplace.iterdir()):
            if not plugin.is_dir():
                continue
            versions = sorted((p for p in plugin.iterdir() if p.is_dir()), key=version_key, reverse=True)
            if not versions:
                continue
            key = f"{plugin.name}@{marketplace.name}"
            known = key in plugins
            enabled = plugins.get(key, {}).get("enabled", True) is not False
            for file in sorted((versions[0] / "skills").glob("*/SKILL.md")):
                yield file, "插件技能" if known else "插件缓存", enabled, plugin.name


def describe(name: str, raw: str, display: str, plugin: str):
    if name.lower() in LABELS:
        return LABELS[name.lower()]
    if name.startswith("google-"):
        return display or name, "连接 Google Drive、Docs、Sheets 或 Slides 后处理在线文件。", "文档与办公", "☁️"
    if name.startswith("artifact-template") or plugin == "template-creator":
        return display or name, "复用内容或版式模板，制作对应类型的材料。", "模板与其他", "🗂️"
    if plugin == "pages":
        return display or name, "管理、编写或维护 ChatGPT Pages 与 Space。", "文档与办公", "📒"
    if plugin == "work-pets":
        return display or name, "创建或管理 ChatGPT Work 中的动画宠物。", "图表与设计", "🐣"
    if name == "sites":
        return "网站与小工具", "制作、编辑或发布网站与交互工具。", "网站与开发", "🌐"
    if "plugin" in name:
        return "插件管理", "查找、连接或管理插件能力。", "工具与连接", "🔌"
    if name == "excel-live-control":
        return "操作当前 Excel", "通过已连接的 Excel 会话操作打开的工作簿。", "文档与办公", "🟩"
    from skill_translation import needs_translation
    summary = '打开中文说明，了解这个技能的用途和适用范围。' if needs_translation(raw) else raw[:160]
    return display or name, summary, "模板与其他", "🌱"


def catalog(home: Path | None = None, workspaces: list[Path] | None = None) -> list[dict]:
    home = home or Path.home()
    try:
        translated_labels=json.loads((home/'.local/share/skill-station/translations/labels.json').read_text())
        if not isinstance(translated_labels,dict):translated_labels={}
    except (OSError,ValueError):translated_labels={}
    records = {}
    for file, origin, enabled, plugin in skill_paths(home, workspaces or []):
        meta = read_yaml(file)
        name = meta.get("name")
        raw = meta.get("description", "")
        if not isinstance(name, str) or not name or not isinstance(raw, str):
            continue
        if name == "nature-shared":
            continue  # Internal support for other skills, not an invocation entrypoint.
        resolved = str(file.resolve())
        if resolved in records:
            continue
        ui = read_yaml(file.parent / "agents/openai.yaml")
        ui = ui.get("interface", ui)
        if not isinstance(ui, dict):
            ui = {}
        title, summary, category, icon = describe(name, raw, str(ui.get("display_name", "")), plugin)
        invocable = meta.get("disable-model-invocation") is not True
        invocation = f"{plugin}:{name}" if plugin else name
        prompt = str(ui.get("default_prompt") or f"使用 ${invocation}，帮我完成以下任务：")
        if plugin and f"${plugin}:" not in prompt:
            prompt = prompt.replace(f"${name}", f"${invocation}")
        if not prompt.startswith(("使用", "Use", "$")) or f"${invocation}" not in prompt:
            prompt = f"使用 ${invocation}，帮我完成以下任务："
        skill_id=hashlib.sha256(resolved.encode()).hexdigest()[:16]
        try: stamp=file.stat()
        except OSError: continue
        signature=f'{stamp.st_mtime_ns}:{stamp.st_size}'
        localized=translated_labels.get(skill_id,{})
        if isinstance(localized,dict) and localized.get('signature')==signature:
            if isinstance(localized.get('title'),str):title=localized['title'][:100] or title
            if isinstance(localized.get('summary'),str):summary=localized['summary'][:240] or summary
        records[resolved] = {
            "id": skill_id, "name": name,"translation_signature":signature,
            "title": title, "summary": summary, "description": raw, "category": category,
            "icon": icon, "origin": origin, "plugin": plugin, "enabled": enabled,
            "invocable": invocable, "invocation": invocation, "path": resolved, "prompt": prompt,
            "connection": origin == "插件缓存" or plugin in {"google-drive", "pages", "work-pets"},
        }
    return sorted(records.values(), key=lambda x: (not x["enabled"], CATEGORIES.index(x["category"]), x["name"]))


def expand_query(query: str) -> list[str]:
    lower = query.casefold()
    hints = []
    for words, values in SEARCH_HINTS:
        if any(word in lower for word in words):
            hints.extend(values)
    english = re.findall(r"[a-z][a-z0-9.+-]{1,40}", lower)
    result = list(dict.fromkeys(english + hints))
    return result[:4] or [query]


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "SkillStation/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=14) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("响应过大，请缩小检索范围")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("搜索服务返回了无法识别的数据")
    return value


def search_online(query: str) -> dict:
    terms = expand_query(query)
    candidates, errors = {}, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_json, "https://skills.sh/api/search?" + urllib.parse.urlencode({"q": term, "limit": 15})): term for term in terms}
        for future in as_completed(futures):
            term = futures[future]
            try:
                payload = future.result()
                skills = payload.get("skills")
                if not isinstance(skills, list):
                    raise ValueError("搜索服务数据格式变化")
                for item in skills:
                    if not isinstance(item, dict):
                        continue
                    source, slug = str(item.get("source", "")), str(item.get("id", "")).split("/")[-1]
                    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source) or ".." in source:
                        continue
                    if not re.fullmatch(r"[A-Za-z0-9_.-]+", slug) or slug in {".", ".."}:
                        continue
                    key = f"{source}/{slug}"
                    installs = item.get("installs")
                    installs = max(0, installs) if isinstance(installs, int) else 0
                    if key not in candidates:
                        owner = source.split("/")[0].lower()
                        candidates[key] = {"id": key, "name": str(item.get("name", slug))[:160], "source": source,
                            "slug": slug, "installs": installs, "matched": [],
                            "url": "https://skills.sh/" + key, "repo": "https://github.com/" + source,
                            "known_publisher": owner in {"vercel-labs", "anthropics", "openai", "microsoft", "google", "supabase", "remotion-dev"},
                            "verified": False}
                    candidates[key]["matched"].append(term)
            except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
                errors.append(str(exc)[:160])
    focus = re.findall(r"[a-z][a-z0-9.+-]{1,40}", query.casefold())
    def relevance(item):
        name = item["name"].casefold()
        return 12 * sum(term in name for term in focus) + 4 * sum(term in name for term in terms) + len(item["matched"])
    rows = sorted(candidates.values(), key=lambda x: (-relevance(x), -x["installs"], x["id"]))[:24]
    return {"query": query, "terms": terms, "skills": rows, "partial": bool(errors),
            "error": "暂时无法连接技能目录。可以重试，或把需求复制给 Codex 继续查找。" if errors and not rows else "",
            "notice": "按技能名称匹配、关键词覆盖与社区安装量排序；来源代码和实际适用性仍需评估。"}


class SkillServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, home=None, workspaces=None):
        self.home, self.workspaces = home, workspaces or []
        self.search_cache, self.cache_lock = {}, threading.Lock()
        self.csrf_token = secrets.token_urlsafe(32)
        self._tasks = None
        self._translations = None
        super().__init__(address, Handler)

    @property
    def tasks(self):
        from task_runner import TaskManager
        with self.cache_lock:
            if self._tasks is None:
                data = Path(self.home)/'.local/share/skill-station/tasks' if self.home else BASE/'tasks'
                self._tasks = TaskManager(data, self.workspaces)
            return self._tasks

    @property
    def translations(self):
        from skill_translation import SkillTranslations
        with self.cache_lock:
            if self._translations is None:
                data = Path(self.home)/'.local/share/skill-station/translations' if self.home else BASE/'translations'
                self._translations = SkillTranslations(data)
            return self._translations


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status: int, data: bytes, kind="application/json; charset=utf-8", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json(self, value, status=200):
        self.respond(status, json.dumps(value, ensure_ascii=False).encode())

    def local_request(self):
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get('Host') not in allowed:
            self.json({'error': '仅允许本机访问'}, 403)
            return False
        return True

    def do_POST(self):
        if not self.local_request():
            return
        origins = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
        if self.headers.get('Origin') not in origins | {None} or not secrets.compare_digest(
                self.headers.get('X-Beagle-Token', ''), self.server.csrf_token):
            self.json({'error': '请从比格小站重新提交'}, 403)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 100000 or 'application/json' not in self.headers.get('Content-Type', ''):
                raise ValueError('请求格式不正确')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('请求格式不正确')
            path = urllib.parse.urlsplit(self.path).path
            if path == '/api/translate':
                if data.get('id'):
                    skill = next((s for s in catalog(self.server.home,self.server.workspaces) if s['id']==data['id']),None)
                    if not skill: raise ValueError('该技能已变化，请刷新列表')
                    result=self.server.translations.start(skill=skill,original=Path(skill['path']).read_text()[:160000],retry=data.get('retry') is True)
                else:
                    result=self.server.translations.start(source=data.get('source'),slug=data.get('slug'),retry=data.get('retry') is True)
                self.json(result,202)
            elif path == '/api/jobs':
                skill = None
                if data.get('skill_id'):
                    skill = next((s for s in catalog(self.server.home, self.server.workspaces) if s['id'] == data['skill_id']), None)
                    if not skill:
                        raise ValueError('该技能已变化，请刷新列表')
                self.json(self.server.tasks.submit(data.get('task'), data.get('workspace', ''), skill, data.get('files'), data.get('model')), 201)
            elif path == '/api/job/cancel':
                self.json(self.server.tasks.cancel(data.get('id')))
            elif path == '/api/job/respond':
                self.json(self.server.tasks.respond(data.get('id'), data.get('request_id'), data.get('decision'), data.get('answers')))
            elif path == '/api/workspaces':
                directory = Path(data.get('path', '')).expanduser().resolve()
                if not data.get('path') or not directory.is_dir():
                    raise ValueError('请选择存在的工作文件夹')
                value = str(directory)
                if value not in self.server.workspaces:
                    self.server.workspaces.append(value)
                settings_path = BASE/'settings.json'
                try:
                    settings = json.loads(settings_path.read_text())
                except (OSError, ValueError):
                    settings = {}
                settings['workspaces'] = [str(p) for p in self.server.workspaces]
                settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2)+'\n')
                self.server.tasks.workspaces = [Path(p).resolve() for p in self.server.workspaces]
                self.json(self.server.tasks.info())
            else:
                self.json({'error': '接口不存在'}, 404)
        except (ValueError, TypeError, OSError) as error:
            self.json({'error': str(error)}, 400)

    def do_GET(self):
        if not self.local_request():
            return
        parsed = urllib.parse.urlsplit(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/health":
            self.json({"service": SERVICE})
        elif parsed.path == '/api/translation':
            try:
                self.json(self.server.translations.get(params.get('id',[''])[0]))
            except ValueError as error:
                self.json({'error':str(error)},404)
        elif parsed.path == '/api/runner':
            self.json({**self.server.tasks.info(), 'token': self.server.csrf_token})
        elif parsed.path == '/api/jobs':
            self.json({'jobs': self.server.tasks.list()})
        elif parsed.path == '/api/models':
            try:
                self.json({'models': self.server.tasks.models()})
            except (ValueError, RuntimeError, OSError) as error:
                self.json({'error': str(error)}, 503)
        elif parsed.path in ('/api/job', '/api/artifact'):
            try:
                job = self.server.tasks.get(params.get('id', [''])[0])
                if parsed.path == '/api/job':
                    self.json(job)
                else:
                    file = Path(params.get('path', [''])[0]).resolve()
                    if str(file) not in job['artifacts'] or Path(job['workspace']) not in file.parents or not file.is_file():
                        raise ValueError('没有找到这项任务的成果文件')
                    if file.stat().st_size > 100 * 1024 * 1024:
                        raise ValueError('文件较大，请从工作文件夹打开')
                    self.respond(200, file.read_bytes(), 'application/octet-stream', {
                        'Content-Disposition': "attachment; filename*=UTF-8''"+urllib.parse.quote(file.name)})
            except (ValueError, OSError) as error:
                self.json({'error': str(error)}, 404)
        elif parsed.path == "/api/skills":
            self.json({"skills": catalog(self.server.home, self.server.workspaces), "categories": CATEGORIES})
        elif parsed.path == "/api/skill":
            found = next((r for r in catalog(self.server.home, self.server.workspaces) if r["id"] == params.get("id", [""])[0]), None)
            if not found:
                self.json({"error": "没有找到该技能，请刷新列表"}, 404)
            else:
                try:
                    self.json({"skill": found, "content": Path(found["path"]).read_text()[:160000]})
                except OSError:
                    self.json({"error": "该技能文件暂时无法读取"}, 404)
        elif parsed.path == "/api/search":
            query = params.get("q", [""])[0].strip()
            if not query or len(query) > 240:
                self.json({"error": "请用 1–240 个字描述需求"}, 400)
                return
            with self.server.cache_lock:
                cached = self.server.search_cache.get(query)
            if cached and time.monotonic() - cached[0] < 300:
                self.json(cached[1])
                return
            result = search_online(query)
            if not result["error"]:
                with self.server.cache_lock:
                    self.server.search_cache[query] = (time.monotonic(), result)
            self.json(result)
        else:
            media = {"/media/beagle-work.png": "beagle.png", "/media/beagle-please.png": "beagle-please.png",
                     "/media/beagle-service.png": "beagle-service.png"}
            if parsed.path in media:
                self.respond(200, (BASE / "assets" / media[parsed.path]).read_bytes(), "image/png")
                return
            static = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8"), "/icon.svg": ("icon.svg", "image/svg+xml"),
                      '/tasks.js': ('tasks.js', 'text/javascript; charset=utf-8'), '/tasks.css': ('tasks.css', 'text/css; charset=utf-8')}
            if parsed.path not in static:
                self.json({"error": "页面不存在"}, 404)
                return
            name, kind = static[parsed.path]
            self.respond(200, (BASE / "static" / name).read_bytes(), kind)


def runtime_dir() -> Path:
    root = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / f"skill-station-{os.getuid()}"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_uid != os.getuid() or root.is_symlink():
        raise RuntimeError("运行目录所有者不匹配")
    root.chmod(0o700)
    return root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--home", type=Path)
    parser.add_argument("--workspace", action="append", type=Path)
    args = parser.parse_args()
    settings = {}
    try:
        settings = json.loads((BASE / "settings.json").read_text())
    except (OSError, ValueError):
        pass
    workspaces = args.workspace or [Path(p) for p in settings.get("workspaces", [])]
    server = SkillServer(("127.0.0.1", args.port), args.home, workspaces)
    state = runtime_dir() / "state.json"
    state.write_text(json.dumps({"url": f"http://127.0.0.1:{server.server_port}", "pid": os.getpid(), "app": str(BASE)}))
    state.chmod(0o600)
    print(f"http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
