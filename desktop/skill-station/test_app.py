import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import app


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def skill(self, relative, name='demo', description='A useful demo.'):
        path = self.home / relative / 'SKILL.md'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(f'---\nname: {name}\ndescription: {description}\n---\nInstructions\n')
        return path

    def test_latest_plugin_version_and_personal_skills(self):
        self.skill('.codex/skills/demo')
        self.skill('.codex/skills/.system/builtin','builtin')
        self.skill('.codex/plugins/cache/vendor/sample/1.9/skills/old','old')
        self.skill('.codex/plugins/cache/vendor/sample/1.10/skills/new','new')
        with patch.dict(app.os.environ,{},clear=True):
            rows=app.catalog(self.home)
        self.assertEqual({r['name'] for r in rows},{'demo','builtin','new'})
        self.assertEqual(next(r for r in rows if r['name']=='new')['origin'],'插件缓存')

    def test_disabled_folder_and_broken_skill_do_not_hide_catalog(self):
        path=self.skill('.codex/skills/demo')
        self.skill('.codex/skills/good','good')
        broken=self.home/'.codex/skills/broken/SKILL.md';broken.parent.mkdir();broken.write_text('---\ninvalid: [\n---\n')
        (self.home/'.codex/config.toml').write_text(f'[[skills.config]]\npath = "{path.parent}"\nenabled = false\n')
        with patch.dict(app.os.environ,{},clear=True):
            rows=app.catalog(self.home)
        self.assertEqual(len(rows),2)
        self.assertFalse(next(r for r in rows if r['name']=='demo')['enabled'])

    def test_multiline_description(self):
        path=self.skill('.codex/skills/demo',description='>\n  First line\n  second line')
        self.assertEqual(app.read_yaml(path)['description'].strip(),'First line second line')

    def test_plugin_invocation_preserves_namespace_and_display_name(self):
        self.skill('.codex/plugins/cache/vendor/presentations/1.0/skills/presentations','Presentations')
        with patch.dict(app.os.environ,{},clear=True):
            row=app.catalog(self.home)[0]
        self.assertEqual(row['invocation'],'presentations:Presentations')
        self.assertEqual(row['title'],'演示文稿')
        self.assertEqual(row['category'],'文档与办公')
        self.assertIn('$presentations:Presentations',row['prompt'])

    def test_chinese_query_preserves_explicit_technology(self):
        terms=app.expand_query('React 性能排查')
        self.assertIn('react',terms)
        self.assertIn('performance',terms)
        self.assertLessEqual(len(terms),4)

    def test_online_results_deduplicate_and_reject_invalid_sources(self):
        payload={'skills':[{'id':'pdf','name':'PDF','source':'anthropics/skills','installs':5000},
                           {'id':'bad','name':'Bad','source':'../../etc','installs':100000}]}
        with patch.object(app,'fetch_json',return_value=payload):
            result=app.search_online('PDF 文档')
        self.assertEqual(len(result['skills']),1)
        row=result['skills'][0]
        self.assertEqual(row['url'],'https://skills.sh/anthropics/skills/pdf')
        self.assertFalse(row['verified'])
        self.assertTrue(row['known_publisher'])

    def test_network_failure_is_not_no_such_skill(self):
        with patch.object(app,'fetch_json',side_effect=urllib.error.URLError('offline')):
            result=app.search_online('pdf')
        self.assertTrue(result['error'])
        self.assertTrue(result['partial'])

    def test_explicit_technology_outranks_unrelated_install_count(self):
        payload={'skills':[{'id':'golang-performance','name':'golang-performance','source':'sample/golang','installs':9999999},
                           {'id':'react-performance','name':'react-performance','source':'sample/react','installs':100}]}
        with patch.object(app,'fetch_json',return_value=payload):
            result=app.search_online('React 性能排查')
        self.assertEqual(result['skills'][0]['name'],'react-performance')


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.server=app.SkillServer(('127.0.0.1',0),Path(cls.tmp.name),[])
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.tmp.cleanup()

    def test_health_and_static_page(self):
        with urllib.request.urlopen(self.url+'/api/health') as r:
            self.assertEqual(json.load(r)['service'],app.SERVICE)
        with urllib.request.urlopen(self.url+'/') as r:
            self.assertIn('技能小站',r.read().decode())
            self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])

    def test_rejects_foreign_host_and_path_traversal(self):
        request=urllib.request.Request(self.url+'/api/skills',headers={'Host':'foreign.example'})
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(request)
        self.assertEqual(exc.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(self.url+'/../../etc/passwd')
        self.assertEqual(exc.exception.code,404)

    def test_beagle_stickers_are_served_without_exposing_other_assets(self):
        for filename in ('beagle-work.png','beagle-please.png','beagle-service.png'):
            with urllib.request.urlopen(self.url+'/media/'+filename) as response:
                self.assertEqual(response.headers['Content-Type'],'image/png')
                self.assertEqual(response.read(8),b'\x89PNG\r\n\x1a\n')
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(self.url+'/media/../../pet.py')
        self.assertEqual(exc.exception.code,404)

    def test_empty_query_does_not_search(self):
        with patch.object(app,'search_online') as search:
            with self.assertRaises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(self.url+'/api/search?q=')
            self.assertEqual(exc.exception.code,400)
            search.assert_not_called()

    def test_task_submission_requires_local_origin_and_nonce(self):
        with urllib.request.urlopen(self.url+'/api/runner') as response:
            token=json.load(response)['token']
        for headers in ({}, {'X-Beagle-Token': token, 'Origin': 'https://unrelated.example'}):
            request=urllib.request.Request(self.url+'/api/jobs',data=b'{"task":"test"}',
                headers={'Content-Type':'application/json',**headers})
            with self.assertRaises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(request)
            self.assertEqual(exc.exception.code,403)
        with patch.object(self.server.tasks,'submit',return_value={'id':'accepted'}) as submit:
            request=urllib.request.Request(self.url+'/api/jobs',data=b'{"task":"test"}',
                headers={'Content-Type':'application/json','X-Beagle-Token':token,'Origin':self.url})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status,201)
            submit.assert_called_once()


if __name__=='__main__':
    unittest.main()
