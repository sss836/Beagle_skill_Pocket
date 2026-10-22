"""Local task queue backed by the installed Codex app-server JSON-RPC protocol."""
from __future__ import annotations

import copy
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}
STATUS = {'queued': '排队中', 'starting': '正在接单', 'running': '正在干活',
          'waiting': '等你确认', 'completed': '已完成', 'failed': '执行失败',
          'cancelled': '已取消', 'interrupted': '运行已中断'}


def conversation_title(task):
    return '比格 · ' + ' '.join(task.split())[:48]


def codex_executable():
    return shutil.which('codex') or next((str(p) for p in (
        Path('/usr/lib/chatgpt/resources/codex'), Path('/opt/Codex/resources/codex'),
        Path('/Applications/Codex.app/Contents/Resources/codex')) if p.is_file()), None)


class RpcClient:
    def __init__(self, on_event, on_request, cwd, command=None):
        executable = codex_executable()
        if not command and not executable:
            raise RuntimeError('未找到 Codex。请先安装并登录 Codex，再回来开工。')
        self.on_event, self.on_request = on_event, on_request
        self.lock, self.pending_lock = threading.Lock(), threading.Lock()
        self.pending, self.sequence = {}, 0
        self.closed = False
        self.proc = subprocess.Popen(command or [executable, 'app-server', '--listen', 'stdio://'],
            cwd=cwd, env={**os.environ, 'BEAGLE_WORKER': '1'}, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()
        # Drain stderr so verbose subprocess diagnostics cannot block JSON-RPC.
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self):
        for _ in self.proc.stderr:
            pass

    def send(self, message):
        with self.lock:
            if self.closed or self.proc.poll() is not None:
                raise RuntimeError('Codex 连接已关闭')
            self.proc.stdin.write(json.dumps(message, ensure_ascii=False)+'\n')
            self.proc.stdin.flush()

    def call(self, method, params, timeout=45):
        with self.pending_lock:
            self.sequence += 1
            request_id = self.sequence
            answer = queue.Queue(maxsize=1)
            self.pending[request_id] = answer
        try:
            self.send({'id': request_id, 'method': method, 'params': params})
            try:
                result = answer.get(timeout=timeout)
            except queue.Empty:
                raise RuntimeError(f'Codex 连接超时（{method}），请检查登录和网络。') from None
            if 'error' in result:
                raise RuntimeError(result['error'].get('message', 'Codex 请求失败'))
            return result.get('result', {})
        finally:
            with self.pending_lock:
                self.pending.pop(request_id, None)

    def reply(self, request_id, result):
        self.send({'id': request_id, 'result': result})

    def _read(self):
        try:
            for line in self.proc.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if 'method' in message:
                    if 'id' in message:
                        self.on_request(message)
                    else:
                        self.on_event(message['method'], message.get('params', {}))
                else:
                    with self.pending_lock:
                        waiter = self.pending.get(message.get('id'))
                    if waiter:
                        waiter.put_nowait(message)
        except (OSError, ValueError, RuntimeError):
            pass
        finally:
            with self.pending_lock:
                for waiter in self.pending.values():
                    if waiter.empty():
                        waiter.put_nowait({'error': {'message': 'Codex 连接意外结束'}})

    def close(self):
        self.closed = True
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            stream.close()


class TaskManager:
    def __init__(self, data_dir, workspaces, rpc_factory=RpcClient):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.workspaces = [Path(p).expanduser().resolve() for p in workspaces]
        self.rpc_factory = rpc_factory
        self.lock = threading.RLock()
        self.model_lock = threading.Lock()
        self.model_cache = None
        self.jobs, self.clients, self.done = {}, {}, {}
        self.queue = queue.Queue(maxsize=20)
        for path in sorted(self.data_dir.glob('*.json'), reverse=True)[:100]:
            try:
                job = json.loads(path.read_text())
                if job['status'] not in TERMINAL:
                    job.update(status='interrupted', pending=[], error='小站已重新启动；这项任务未继续执行。')
                self.jobs[job['id']] = job
            except (OSError, ValueError, KeyError):
                pass
        threading.Thread(target=self._worker, daemon=True).start()

    def info(self):
        return {'available': bool(codex_executable()), 'workspaces': [str(p) for p in self.workspaces],
                'connection': 'Codex 本机登录', 'active': sum(j['status'] not in TERMINAL for j in self.jobs.values())}

    def models(self):
        with self.model_lock:
            if self.model_cache and time.monotonic()-self.model_cache[0] < 300:
                return copy.deepcopy(self.model_cache[1])
            client = self.rpc_factory(lambda *_: None, lambda *_: None, str(self.workspaces[0] if self.workspaces else Path.home()))
            try:
                client.call('initialize', {'clientInfo': {'name': 'beagle_skill_station', 'version': '0.3.4'}})
                client.send({'method': 'initialized', 'params': {}})
                response = client.call('model/list', {'includeHidden': False, 'limit': 100}, timeout=20)
                rows = response.get('data', [])
                while response.get('nextCursor'):
                    response = client.call('model/list', {'includeHidden': False, 'limit': 100, 'cursor': response['nextCursor']}, timeout=20)
                    rows.extend(response.get('data', []))
                result = [{key: row.get(key) for key in ('id', 'model', 'displayName', 'description',
                    'isDefault', 'defaultReasoningEffort', 'supportedReasoningEfforts', 'availabilityNux')}
                    for row in rows if not row.get('hidden')]
                self.model_cache = (time.monotonic(), result)
                return copy.deepcopy(result)
            finally:
                client.close()

    def _save(self, job):
        job['updated_at'] = time.time()
        path = self.data_dir/(job['id']+'.json')
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(job, ensure_ascii=False))
        temp.chmod(0o600)
        temp.replace(path)

    def _event(self, job, message):
        job['events'].append({'time': time.time(), 'message': message})
        job['events'] = job['events'][-120:]

    def get(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise ValueError('没有找到这项任务')
            job = copy.deepcopy(self.jobs[job_id])
            job['status_label'] = STATUS[job['status']]
            job['thread_title'] = job.get('thread_title') or conversation_title(job['task'])
            thread_id = job.get('thread_id')
            job['thread_url'] = 'codex://threads/'+quote(thread_id, safe='') if thread_id else ''
            return job

    def list(self):
        with self.lock:
            keys = sorted(self.jobs, key=lambda k: self.jobs[k]['created_at'], reverse=True)[:50]
            return [{k: j[k] for k in ('id', 'task', 'skill_title', 'status', 'status_label', 'created_at', 'workspace')}
                    for j in (self.get(key) for key in keys)]

    def submit(self, task, workspace='', skill=None, files=None, model=None):
        if not isinstance(task, str) or not 1 <= len(task.strip()) <= 20000:
            raise ValueError('请填写 1–20000 字的任务')
        if not self.workspaces:
            raise ValueError('请先在设置中添加工作文件夹')
        selected = Path(workspace or self.workspaces[0]).expanduser().resolve()
        if not selected.is_dir() or not any(selected == root or root in selected.parents for root in self.workspaces):
            raise ValueError('请选择已配置的工作文件夹')
        if skill and (not skill.get('enabled', True) or not skill.get('invocable', True)):
            raise ValueError('这个技能当前不能调用')
        selected_model = None
        if model:
            selected_model = next((row for row in self.models() if row['model'] == model), None)
            if not selected_model:
                raise ValueError('这个模型当前不可选，请刷新模型列表')
        inputs = []
        if not isinstance(files or [], list) or len(files or []) > 20:
            raise ValueError('一次最多附上 20 个文件路径')
        for item in files or []:
            path = Path(item).expanduser().resolve()
            if not path.is_file():
                raise ValueError('找不到附件：'+str(path))
            inputs.append(str(path))
        now = time.time()
        job_id = time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
        job = {'id': job_id, 'task': task.strip(), 'workspace': str(selected), 'files': inputs,
               'skill': skill, 'skill_title': skill['title'] if skill else '自动选择技能',
               'status': 'queued', 'created_at': now, 'updated_at': now, 'events': [],
               'pending': [], 'messages': {}, 'result': '', 'error': '', 'artifacts': [],
               'thread_id': '', 'thread_title': conversation_title(task), 'turn_id': '',
               'output_dir': str(selected/'outputs/beagle-tasks'/job_id)}
        job['model'] = selected_model['model'] if selected_model else None
        job['model_label'] = selected_model['displayName'] if selected_model else '沿用当前 Codex 设置'
        job['effort'] = selected_model['defaultReasoningEffort'] if selected_model else None
        with self.lock:
            if self.queue.full():
                raise ValueError('待办已经排满，请稍后再提交')
            self.jobs[job_id] = job
            self.done[job_id] = threading.Event()
            self._event(job, '任务已接收，等待开工')
            self._save(job)
            self.queue.put_nowait(job_id)
        return self.get(job_id)

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                raise ValueError('没有找到这项任务')
            if job['status'] in TERMINAL:
                return self.get(job_id)
            job.update(status='cancelled', pending=[])
            self._event(job, '你已停止这项任务')
            self._save(job)
            client = self.clients.get(job_id)
        if client:
            if job['thread_id'] and job['turn_id']:
                try:
                    client.call('turn/interrupt', {'threadId': job['thread_id'], 'turnId': job['turn_id']}, timeout=3)
                except RuntimeError:
                    pass
            client.close()
        self.done[job_id].set()
        return self.get(job_id)

    def respond(self, job_id, request_id, decision=None, answers=None):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job['status'] in TERMINAL:
                raise ValueError('任务已结束，无法继续回答')
            request = next((p for p in job['pending'] if str(p['id']) == str(request_id)), None)
            client = self.clients.get(job_id)
            if not request or not client:
                raise ValueError('请求已经失效，请刷新任务')
            if request['kind'] == 'questions':
                if not isinstance(answers, dict):
                    raise ValueError('请填写问题的答案')
                cleaned = {}
                for question in request['params'].get('questions', []):
                    value = answers.get(question['id'])
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError('请回答：'+question.get('question', question['id']))
                    cleaned[question['id']] = {'answers': [value.strip()]}
                result = {'answers': cleaned}
            else:
                if decision not in ('accept', 'decline'):
                    raise ValueError('请选择允许这一次或拒绝')
                if request['method'] == 'item/permissions/requestApproval':
                    result = {'permissions': request['params'].get('permissions', {}) if decision == 'accept' else {}, 'scope': 'turn'}
                else:
                    available = request['params'].get('availableDecisions')
                    if available and decision not in available:
                        raise ValueError('这个请求不支持所选决定，请停止任务后在 Codex 中处理')
                    result = {'decision': decision}
            client.reply(request['id'], result)
            job['pending'].remove(request)
            job['status'] = 'waiting' if job['pending'] else 'running'
            self._event(job, '已收到你的答复，继续执行')
            self._save(job)
        return self.get(job_id)

    def _on_request(self, job_id, request):
        method, params = request['method'], request.get('params', {})
        supported = {'item/commandExecution/requestApproval', 'item/fileChange/requestApproval',
                     'item/permissions/requestApproval', 'item/tool/requestUserInput', 'tool/requestUserInput'}
        with self.lock:
            job = self.jobs[job_id]
            if method not in supported:
                self.clients[job_id].send({'id': request['id'], 'error': {'code': -32601,
                    'message': '比格暂不支持这个交互，请在 Codex 原生界面处理：'+method}})
                self._event(job, '遇到暂不支持的交互：'+method)
                self._save(job)
                return
            job['pending'].append({'id': request['id'], 'method': method, 'params': params,
                                   'kind': 'questions' if 'requestUserInput' in method else 'approval'})
            job['status'] = 'waiting'
            self._event(job, '需要你的答复，任务已暂停等待')
            self._save(job)

    def _on_event(self, job_id, method, params):
        with self.lock:
            job = self.jobs[job_id]
            if job['status'] in TERMINAL:
                return
            if method == 'turn/started':
                job['turn_id'] = params['turn']['id']
                job['status'] = 'running'
                self._event(job, 'Codex 已开始处理')
            elif method == 'item/agentMessage/delta':
                key = params.get('itemId', 'reply')
                previous = job['messages'].get(key, {'text': '', 'phase': 'commentary'})
                previous['text'] = (previous['text']+params.get('delta', ''))[-200000:]
                job['messages'][key] = previous
            elif method in ('item/started', 'item/completed'):
                item = params.get('item', {})
                kind = item.get('type')
                if kind == 'agentMessage':
                    job['messages'][item['id']] = {'text': item.get('text', ''), 'phase': item.get('phase') or 'commentary'}
                elif method == 'item/started':
                    labels = {'commandExecution': '正在执行任务步骤', 'fileChange': '正在更新文件',
                              'mcpToolCall': '正在调用工具', 'webSearch': '正在查找资料',
                              'collabToolCall': '正在协调子 Agent'}
                    if kind in labels:
                        self._event(job, labels[kind])
                if kind == 'fileChange' and method == 'item/completed':
                    for change in item.get('changes', []):
                        self._artifact(job, change.get('path', ''))
            elif method == 'turn/plan/updated':
                job['plan'] = params.get('plan', [])
                self._event(job, '已更新执行计划')
            elif method == 'error':
                job['error'] = params.get('error', {}).get('message', 'Codex 执行遇到问题')
                self._event(job, job['error'])
            elif method == 'serverRequest/resolved':
                job['pending'] = [p for p in job['pending'] if p['id'] != params.get('requestId')]
                if not job['pending']:
                    job['status'] = 'running'
            elif method == 'turn/completed':
                turn = params['turn']
                state = turn.get('status')
                job['status'] = state if state in ('completed', 'failed', 'interrupted') else 'failed'
                job['pending'] = []
                if turn.get('error'):
                    job['error'] = turn['error'].get('message', '任务失败')
                messages = list(job['messages'].values())
                final = [m['text'] for m in messages if m['phase'] == 'final_answer' and m['text']]
                job['result'] = '\n\n'.join(final or [m['text'] for m in messages if m['text']])
                output = Path(job['output_dir'])
                if output.is_dir():
                    for file in output.rglob('*'):
                        self._artifact(job, str(file))
                self._event(job, STATUS[job['status']])
                self.done[job_id].set()
            else:
                return
            self._save(job)

    def _artifact(self, job, value):
        if not value:
            return
        path = Path(value)
        path = (Path(job['workspace'])/path).resolve() if not path.is_absolute() else path.resolve()
        root = Path(job['workspace'])
        if path.is_file() and root in path.parents and str(path) not in job['artifacts']:
            job['artifacts'].append(str(path))

    def _worker(self):
        while True:
            job_id = self.queue.get()
            client = None
            try:
                with self.lock:
                    job = self.jobs[job_id]
                    if job['status'] == 'cancelled':
                        continue
                    job['status'] = 'starting'
                    self._event(job, '正在连接本机 Codex')
                    self._save(job)
                client = self.rpc_factory(lambda m,p: self._on_event(job_id,m,p),
                    lambda r: self._on_request(job_id,r), job['workspace'])
                with self.lock:
                    self.clients[job_id] = client
                    if job['status'] == 'cancelled':
                        continue
                client.call('initialize', {'clientInfo': {'name': 'beagle_skill_station',
                    'title': 'Beagle Skill Station', 'version': '0.3.4'}})
                client.send({'method': 'initialized', 'params': {}})
                account = client.call('account/read', {'refreshToken': False}, timeout=15)
                if not account.get('account'):
                    raise RuntimeError('请先在 Codex 登录你的账号，再回来提交任务。')
                # Persist a normal chat in the selected project root. Output files
                # have a separate folder and must never become the chat's cwd.
                thread_params = {'cwd': job['workspace'], 'ephemeral': False, 'sandbox': 'workspace-write',
                    'approvalPolicy': 'on-request', 'serviceName': 'beagle_skill_station',
                    'developerInstructions': '你正在执行用户从比格技能口袋提交的任务。直接使用可用技能和工具完成工作；不要通过 beagle_tasks MCP 再次提交本任务。只根据真实事件报告进度，最终说明成果路径和实际检查。默认将新增成果保存到用户给定的本次输出文件夹，用户指定其他位置时遵从用户。'}
                if job.get('model'):
                    thread_params['model'] = job['model']
                started = client.call('thread/start', thread_params)
                with self.lock:
                    job['thread_id'] = started['thread']['id']
                    job['actual_model'] = started.get('model', job.get('model'))
                    self._save(job)
                try:
                    client.call('thread/name/set', {'threadId': job['thread_id'],
                        'name': job['thread_title']}, timeout=10)
                except RuntimeError:
                    # Naming support varies by Codex version; execution can continue.
                    with self.lock:
                        self._event(job, '对话已建立，将使用 Codex 默认标题')
                        self._save(job)
                skill = job['skill']
                prompt = (f'使用 ${skill["invocation"]}，' if skill else '')+job['task']
                prompt += '\n\n本次输出文件夹：'+job['output_dir']
                if job['files']:
                    prompt += '\n用户提供的本机附件路径：\n'+'\n'.join(job['files'])
                inputs = [{'type': 'text', 'text': prompt}]
                if skill:
                    inputs.append({'type': 'skill', 'name': skill['name'], 'path': skill['path']})
                turn_params = {'threadId': job['thread_id'], 'cwd': job['workspace'], 'input': inputs}
                if job.get('effort'):
                    turn_params['effort'] = job['effort']
                turn = client.call('turn/start', turn_params)
                with self.lock:
                    job['turn_id'] = turn['turn']['id']
                    self._save(job)
                while not self.done[job_id].wait(1):
                    if client.proc.poll() is not None:
                        raise RuntimeError('Codex 连接在任务结束前中断')
                with self.lock:
                    output = Path(job['output_dir'])
                    if output.is_dir():
                        for file in output.rglob('*'):
                            self._artifact(job, str(file))
                    self._save(job)
            except Exception as error:
                with self.lock:
                    job = self.jobs[job_id]
                    if job['status'] not in TERMINAL:
                        job.update(status='failed', pending=[], error=str(error))
                        self._event(job, str(error))
                        self._save(job)
                    self.done[job_id].set()
            finally:
                if client:
                    client.close()
                with self.lock:
                    self.clients.pop(job_id, None)
                self.queue.task_done()
