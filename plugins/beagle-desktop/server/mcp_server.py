#!/usr/bin/env python3
"""Dependency-free stdio MCP adapter for the local beagle task service."""
import json
import os
import sys
from pathlib import Path

installed = Path.home()/'.local/share/skill-station'
runtime = Path(__file__).resolve().parent.parent/'runtime'
source = installed if (installed/'task_client.py').is_file() else runtime
if not source.is_dir():
    source = Path(__file__).resolve().parent
sys.path.insert(0, str(source))
from task_client import TaskClient

client = TaskClient()


def schema(properties=None, required=None):
    return {'type': 'object', 'properties': properties or {}, 'required': required or [], 'additionalProperties': False}


STRING = {'type': 'string'}
TOOLS = [
    {'name': 'beagle_list_models', 'description': '读取本机 Codex 实际模型列表。只在用户要求选择模型时使用；未指定模型的任务默认沿用当前 Codex 设置。', 'inputSchema': schema(), 'annotations': {'readOnlyHint': True}},
    {'name': 'beagle_status', 'description': '查看本机比格执行连接和已配置工作文件夹；不提交任务。', 'inputSchema': schema(), 'annotations': {'readOnlyHint': True}},
    {'name': 'beagle_list_skills', 'description': '列出或按关键词筛选本机技能元数据。缓存中存在不代表所需外部连接可用。', 'inputSchema': schema({'query': STRING}), 'annotations': {'readOnlyHint': True}},
    {'name': 'beagle_list_tasks', 'description': '查看最近任务及其真实状态；不创建新任务。', 'inputSchema': schema(), 'annotations': {'readOnlyHint': True}},
    {'name': 'beagle_get_task', 'description': '读取指定任务的真实进度、最终答复、成果路径和等待用户处理的请求。', 'inputSchema': schema({'id': STRING}, ['id']), 'annotations': {'readOnlyHint': True}},
    {'name': 'beagle_submit_task', 'description': '将用户明确要求执行的任务提交给本机 Codex。可在所选工作文件夹内创建或修改文件；需使用对方自己的 Codex 登录。返回任务 ID，之后用 beagle_get_task 查看进度。仅询问方法或状态时不要调用。',
     'inputSchema': schema({'task': STRING, 'workspace': STRING, 'skill_id': STRING, 'files': {'type': 'array', 'items': STRING}, 'model': STRING}, ['task']),
     'annotations': {'readOnlyHint': False, 'destructiveHint': True, 'idempotentHint': False, 'openWorldHint': True}},
    {'name': 'beagle_cancel_task', 'description': '停止用户指定的比格任务。已经写入的文件不会自动撤销。', 'inputSchema': schema({'id': STRING}, ['id']), 'annotations': {'readOnlyHint': False, 'idempotentHint': True}},
    {'name': 'beagle_configure_workspace', 'description': '添加用户明确指定的本机工作文件夹。只在用户提供并选择了该文件夹时调用。', 'inputSchema': schema({'path': STRING}, ['path']), 'annotations': {'readOnlyHint': False, 'idempotentHint': True}}
]


def call_tool(name, arguments):
    definition = next((tool for tool in TOOLS if tool['name'] == name), None)
    if not definition:
        raise ValueError('未知工具')
    if not isinstance(arguments, dict) or any(key not in definition['inputSchema']['properties'] for key in arguments):
        raise ValueError('工具参数不正确')
    for key in definition['inputSchema']['required']:
        if key not in arguments:
            raise ValueError('缺少参数：'+key)
    if name == 'beagle_status':
        result = client.connect()
        return {key: value for key, value in result.items() if key != 'token'}
    if name == 'beagle_list_models':
        return client.request('GET', '/api/models')
    if name == 'beagle_list_skills':
        from pet_support import rank_skills
        rows = client.request('GET', '/api/skills')['skills']
        return {'skills': [{key: row[key] for key in ('id', 'name', 'title', 'summary', 'category', 'enabled', 'connection')}
                           for row in rank_skills(rows, arguments.get('query', ''))[:60]]}
    if name == 'beagle_list_tasks':
        return client.request('GET', '/api/jobs')
    if name == 'beagle_get_task':
        result = client.job(arguments['id'])
        result.pop('skill', None)
        result['task_url'] = client.url+'/?job='+result['id']
        return result
    if name == 'beagle_submit_task':
        if os.environ.get('BEAGLE_WORKER') == '1':
            raise ValueError('正在执行任务的 Agent 应直接完成工作，不能递归提交比格任务。')
        job = client.request('POST', '/api/jobs', arguments)
        return {key: job[key] for key in ('id', 'status', 'status_label', 'workspace', 'output_dir')}
    if name == 'beagle_cancel_task':
        result = client.request('POST', '/api/job/cancel', arguments)
        return {'id': result['id'], 'status': result['status'], 'status_label': result['status_label']}
    if name == 'beagle_configure_workspace':
        return client.request('POST', '/api/workspaces', arguments)


def handle(request):
    method, params = request.get('method'), request.get('params') or {}
    if 'id' not in request:
        return None
    answer = {'jsonrpc': '2.0', 'id': request['id']}
    if method == 'initialize':
        supported = ('2024-11-05', '2025-03-26', '2025-06-18')
        version = params.get('protocolVersion')
        answer['result'] = {'protocolVersion': version if version in supported else supported[-1],
            'capabilities': {'tools': {}}, 'serverInfo': {'name': 'beagle-desktop', 'version': '0.3.4'}}
    elif method == 'ping':
        answer['result'] = {}
    elif method == 'tools/list':
        answer['result'] = {'tools': TOOLS}
    elif method == 'tools/call':
        try:
            result = call_tool(params.get('name'), params.get('arguments') or {})
            answer['result'] = {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}], 'structuredContent': result, 'isError': False}
        except Exception as error:
            answer['result'] = {'content': [{'type': 'text', 'text': str(error)}], 'isError': True}
    else:
        answer['error'] = {'code': -32601, 'message': 'Method not found'}
    return answer


def main():
    for line in sys.stdin:
        try:
            request = json.loads(line)
            answer = handle(request)
        except (ValueError, TypeError, AttributeError):
            answer = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
        if answer is not None:
            print(json.dumps(answer, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
