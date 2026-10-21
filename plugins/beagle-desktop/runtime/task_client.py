"""The same local connection is used by the native pet and stdio MCP plugin."""
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class TaskClient:
    def __init__(self, url=None):
        self.url, self.token = url, None

    def connect(self):
        if not self.url:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve().parent/'launch.py'), '--no-open'],
                capture_output=True, text=True, timeout=15, check=True)
            self.url = result.stdout.strip().splitlines()[-1]
        if not self.url.startswith('http://127.0.0.1:'):
            raise ValueError('任务连接必须使用本机小站')
        info = self.request('GET', '/api/runner')
        self.token = info['token']
        return info

    def request(self, method, route, data=None):
        if not self.url:
            self.connect()
        if method == 'POST' and not self.token:
            self.connect()
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['X-Beagle-Token'] = self.token
        request = urllib.request.Request(self.url+route, method=method, headers=headers,
            data=json.dumps(data, ensure_ascii=False).encode() if data is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                message = json.loads(error.read()).get('error', str(error))
            except (ValueError, OSError):
                message = str(error)
            if error.code == 403 and method == 'POST':
                self.token = None
            raise RuntimeError(message) from None

    def job(self, job_id):
        return self.request('GET', '/api/job?'+urllib.parse.urlencode({'id': job_id}))
