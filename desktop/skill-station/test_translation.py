import tempfile
import threading
import unittest
from pathlib import Path

from skill_translation import SkillPage, SkillTranslations, needs_translation


ENGLISH='Use this skill to inspect CSV files, find missing values, and explain the columns. Never upload the data.'


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory=Path(self.temporary.name)
        self.skill={'id':'local-test','title':'csv-reader','summary':'Inspect CSV files'}

    def test_language_detection_ignores_code_and_preserves_chinese(self):
        self.assertTrue(needs_translation(ENGLISH))
        self.assertTrue(needs_translation('Read files.'))
        self.assertTrue(needs_translation('Читать файлы и объяснять столбцы.'))
        self.assertFalse(needs_translation('处理 CSV 文件，检查缺失值，不上传文件。\n```bash\n'+ENGLISH+'\n```'))

    def test_only_visible_documentation_is_extracted_and_code_is_preserved(self):
        parser=SkillPage()
        parser.feed('<main><nav>Not documentation</nav><div class="prose"><h1>Read CSV</h1><p>Read<br/>files</p><pre><code>python3 inspect.py input.csv</code></pre><script>untrusted()</script></div></main>')
        text=parser.documents[0]
        self.assertIn('# Read CSV',text)
        self.assertIn('Read\nfiles',text)
        self.assertIn('```\npython3 inspect.py input.csv\n```',text)
        self.assertNotIn('untrusted()',text)
        self.assertNotIn('Not documentation',text)

    def test_background_requests_are_deduplicated_and_cache_survives_restart(self):
        entered,release=threading.Event(),threading.Event()
        calls=[]
        def translate(title,body):
            calls.append(body);entered.set();release.wait(2)
            return {'title':'CSV 阅读器','summary':'检查缺失值，不上传数据。','content':'检查 CSV 文件、缺失值和列含义，不上传数据。'}
        manager=SkillTranslations(self.directory,translate)
        first=manager.start(skill=self.skill,original=ENGLISH)
        self.assertTrue(entered.wait(1))
        second=manager.start(skill=self.skill,original=ENGLISH)
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(second['status'],'translating')
        release.set();manager.queue.join()
        result=manager.get(first['id'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['original'],ENGLISH)
        self.assertTrue(result['translated'])
        restarted=SkillTranslations(self.directory,lambda *_:self.fail('cached text must not trigger another translation'))
        repeated=restarted.start(skill=self.skill,original=ENGLISH);restarted.queue.join()
        self.assertEqual(restarted.get(repeated['id'])['content'],result['content'])
        self.assertEqual(len(calls),1)

    def test_failed_translation_retains_original_and_can_be_retried(self):
        manager=SkillTranslations(self.directory,lambda *_:(_ for _ in ()).throw(RuntimeError('offline')))
        first=manager.start(skill=self.skill,original=ENGLISH);manager.queue.join()
        failed=manager.get(first['id'])
        self.assertEqual(failed['status'],'error');self.assertEqual(failed['original'],ENGLISH)
        manager.translator=lambda *_:{'title':'CSV 阅读器','summary':'检查 CSV。','content':'检查 CSV，保持数据不变。'}
        retried=manager.start(skill=self.skill,original=ENGLISH,retry=True);manager.queue.join()
        self.assertEqual(manager.get(retried['id'])['status'],'completed')

    def test_invalid_remote_locations_never_reach_the_loader(self):
        manager=SkillTranslations(self.directory,remote_loader=lambda *_:self.fail('invalid source fetched'))
        for source,slug in [('https://127.0.0.1','x'),('../private/repo','x'),('owner/repo','../secret')]:
            with self.assertRaises(ValueError):manager.start(source=source,slug=slug)

    def test_already_chinese_does_not_consume_translation_and_changed_source_invalidates_cache(self):
        calls=[]
        manager=SkillTranslations(self.directory,lambda _,body:(calls.append(body) or {'title':'阅读器','summary':'查看说明。','content':'原文对应的中文说明。'}))
        chinese=manager.start(skill=self.skill,original='读取表格，保持原始数据不变。');manager.queue.join()
        self.assertFalse(manager.get(chinese['id'])['translated'])
        first=manager.start(skill=self.skill,original=ENGLISH);manager.queue.join()
        second=manager.start(skill=self.skill,original=ENGLISH+' Requires Python.');manager.queue.join()
        self.assertNotEqual(first['id'],second['id']);self.assertEqual(len(calls),2)


if __name__=='__main__':
    unittest.main()
