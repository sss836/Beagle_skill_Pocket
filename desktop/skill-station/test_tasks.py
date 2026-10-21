import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from task_runner import TaskManager


class FakeRpc:
    instances = []

    def __init__(self, event, request, cwd):
        self.event, self.request, self.cwd = event, request, cwd
        self.calls, self.replies, self.stopped = [], [], False
        self.proc = self
        self.instances.append(self)

    def call(self, method, params, **_):
        self.calls.append((method, params))
        if method == 'account/read':
            return {'account': {'type': 'chatgpt'}}
        if method == 'thread/start':
            return {'thread': {'id': 'thread-test'}}
        if method == 'turn/start':
            self.event('turn/started', {'turn': {'id': 'turn-test'}})
            return {'turn': {'id': 'turn-test'}}
        if method == 'model/list':
            return {'data': [{'id':'sample','model':'sample-model','displayName':'Sample','description':'Test model',
                'defaultReasoningEffort':'medium','supportedReasoningEfforts':[], 'isDefault':True,'hidden':False,'availabilityNux':{'message':'Welcome'}}]}
        return {}

    def send(self, value):
        self.calls.append(('notification', value))

    def reply(self, request_id, result):
        self.replies.append((request_id, result))

    def poll(self):
        return 0 if self.stopped else None

    def close(self):
        self.stopped = True


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root/'work'
        self.workspace.mkdir()
        FakeRpc.instances = []
        self.manager = TaskManager(self.root/'tasks', [self.workspace], FakeRpc)
        self.addCleanup(self.stop_all)

    def stop_all(self):
        for job in self.manager.list():
            if job['status'] not in ('completed', 'failed', 'interrupted', 'cancelled'):
                self.manager.cancel(job['id'])
        self.manager.queue.join()

    def wait(self, condition):
        end = time.monotonic()+3
        while not condition():
            if time.monotonic() > end:
                self.fail('timed out waiting for task state')
            time.sleep(.01)

    def running(self):
        job = self.manager.submit('创建一份测试成果')
        self.wait(lambda: self.manager.get(job['id'])['status'] == 'running')
        return job, FakeRpc.instances[-1]

    def test_actual_turn_completion_is_required_and_result_survives_reload(self):
        job, rpc = self.running()
        rpc.event('item/completed', {'item': {'id': 'answer', 'type': 'agentMessage', 'phase': 'final_answer', 'text': '成果已生成'}})
        self.assertEqual(self.manager.get(job['id'])['status'], 'running')
        rpc.event('turn/completed', {'turn': {'status': 'completed'}})
        self.manager.queue.join()
        self.assertEqual(self.manager.get(job['id'])['result'], '成果已生成')
        loaded = TaskManager(self.root/'tasks', [self.workspace], FakeRpc)
        self.assertEqual(loaded.get(job['id'])['status'], 'completed')

    def test_failure_is_not_marked_success(self):
        job, rpc = self.running()
        rpc.event('turn/completed', {'turn': {'status': 'failed', 'error': {'message': 'quota exhausted'}}})
        self.manager.queue.join()
        self.assertEqual(self.manager.get(job['id'])['status'], 'failed')
        self.assertEqual(self.manager.get(job['id'])['error'], 'quota exhausted')

    def test_model_is_forwarded_only_when_selected(self):
        job = self.manager.submit('模型测试', model='sample-model')
        self.wait(lambda: self.manager.get(job['id'])['status']=='running')
        rpc = FakeRpc.instances[-1]
        self.assertEqual(next(p for m,p in rpc.calls if m=='thread/start')['model'],'sample-model')
        self.assertEqual(next(p for m,p in rpc.calls if m=='turn/start')['effort'],'medium')
        self.manager.cancel(job['id'])
        self.manager.queue.join()
        default, rpc = self.running()
        self.assertNotIn('model',next(p for m,p in rpc.calls if m=='thread/start'))
        self.assertNotIn('effort',next(p for m,p in rpc.calls if m=='turn/start'))
        with self.assertRaises(ValueError):
            self.manager.submit('模型测试',model='not-an-available-model')

    def test_approval_waits_for_human_and_grants_only_one_decision(self):
        job, rpc = self.running()
        rpc.request({'id': 'approve-1', 'method': 'item/commandExecution/requestApproval', 'params': {'command': 'example'}})
        self.assertEqual(self.manager.get(job['id'])['status'], 'waiting')
        self.assertEqual(rpc.replies, [])
        self.manager.respond(job['id'], 'approve-1', 'accept')
        self.assertEqual(rpc.replies, [('approve-1', {'decision': 'accept'})])
        self.assertEqual(self.manager.get(job['id'])['status'], 'running')
        with self.assertRaises(ValueError):
            self.manager.respond(job['id'], 'approve-1', 'accept')

    def test_question_answers_use_the_documented_shape(self):
        job, rpc = self.running()
        rpc.request({'id': 44, 'method': 'item/tool/requestUserInput', 'params': {'questions': [{'id': 'format', 'question': '用什么格式？'}]}})
        with self.assertRaises(ValueError):
            self.manager.respond(job['id'], 44, answers={})
        self.manager.respond(job['id'], 44, answers={'format': 'PPTX'})
        self.assertEqual(rpc.replies[-1][1], {'answers': {'format': {'answers': ['PPTX']}}})

    def test_tasks_run_serially_and_cancel_releases_queue(self):
        first, rpc = self.running()
        second = self.manager.submit('第二项任务')
        self.assertEqual(self.manager.get(second['id'])['status'], 'queued')
        self.manager.cancel(first['id'])
        self.wait(lambda: self.manager.get(second['id'])['status'] == 'running')
        self.assertTrue(rpc.stopped)
        self.assertEqual(self.manager.get(first['id'])['status'], 'cancelled')

    def test_workspace_escape_and_invalid_attachments_are_rejected(self):
        alias = self.workspace/'outside'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.manager.submit('任务', str(alias))
        with self.assertRaises(ValueError):
            self.manager.submit('任务', files=[str(self.root/'missing.pdf')])

    def test_new_results_are_collected_within_workspace(self):
        job, rpc = self.running()
        output = Path(job['output_dir'])
        output.mkdir(parents=True)
        result = output/'result.txt'
        result.write_text('done')
        rpc.event('turn/completed', {'turn': {'status': 'completed'}})
        self.manager.queue.join()
        self.assertEqual(self.manager.get(job['id'])['artifacts'], [str(result)])

    def test_restarted_incomplete_task_is_interrupted(self):
        state = {'id': 'stored', 'status': 'running', 'created_at': time.time(), 'task': 'old task',
                 'skill_title': '自动选择', 'workspace': str(self.workspace), 'pending': []}
        (self.root/'tasks/stored.json').write_text(json.dumps(state))
        loaded = TaskManager(self.root/'tasks', [self.workspace], FakeRpc)
        self.assertEqual(loaded.get('stored')['status'], 'interrupted')


if __name__ == '__main__':
    unittest.main()
