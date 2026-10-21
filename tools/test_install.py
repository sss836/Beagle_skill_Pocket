"""Install into a disposable home and verify upgrade and launcher behavior."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def test_upgrade_preserves_user_data_and_adds_workspace(self):
        with tempfile.TemporaryDirectory(prefix='beagle install ') as temporary:
            home = Path(temporary)/'home with spaces'
            first, second = Path(temporary)/'first folder', Path(temporary)/'second folder'
            first.mkdir(); second.mkdir()
            command = ['/usr/bin/python3',str(ROOT/'desktop/skill-station/install.py'),'--home',str(home)]
            subprocess.run(command+['--workspace',str(first)],check=True,capture_output=True)
            app = home/'.local/share/skill-station'
            settings = {'workspaces':[str(first)],'custom_preference':True}
            (app/'settings.json').write_text(json.dumps(settings))
            (app/'tasks').mkdir(); (app/'tasks/keep.json').write_text('{}')
            (app/'pet-state.json').write_text('{"x":123}')
            subprocess.run(command,check=True,capture_output=True)
            self.assertEqual(json.loads((app/'settings.json').read_text()),settings)
            subprocess.run(command+['--workspace',str(second)],check=True,capture_output=True)
            self.assertEqual(json.loads((app/'settings.json').read_text())['workspaces'],[str(first),str(second)])
            self.assertEqual((app/'pet-state.json').read_text(),'{"x":123}')
            self.assertTrue((app/'tasks/keep.json').exists())
            subprocess.run(['desktop-file-validate',str(home/'Desktop/技能小站.desktop')],check=True,capture_output=True)

    def test_plugin_install_commands_and_no_desktop_in_skills_mode(self):
        with tempfile.TemporaryDirectory(prefix='beagle-cli-') as temporary:
            directory = Path(temporary)
            fake = directory/'codex'
            fake.write_text('#!/usr/bin/python3\nimport json,os,sys\nwith open(os.environ["BEAGLE_TEST_LOG"],"a") as f:f.write(json.dumps(sys.argv[1:])+"\\n")\n')
            fake.chmod(0o755)
            log = directory/'commands.jsonl'
            home = directory/'empty-home'; home.mkdir()
            env = dict(os.environ,HOME=str(home),PATH=str(directory)+':'+os.environ['PATH'],BEAGLE_TEST_LOG=str(log))
            subprocess.run(['bash',str(ROOT/'install.sh'),'--skills-only','--no-start'],env=env,check=True,capture_output=True)
            commands = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(commands,[['plugin','marketplace','add',str(ROOT)],['plugin','add','beagle-skills@beagle-local']])
            self.assertFalse((home/'.local/share/skill-station').exists())
            log.unlink()
            subprocess.run(['bash',str(ROOT/'install.sh'),'--plugins-only','--no-start'],env=env,check=True,capture_output=True)
            commands = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(commands[-1],['plugin','add','beagle-desktop@beagle-local'])
            log.unlink()
            env['XDG_CONFIG_HOME'] = str(home/'.config')
            subprocess.run(['bash',str(ROOT/'install.sh'),'--all','--no-start','--workspace',str(home)],env=env,check=True,capture_output=True)
            installed = home/'.local/share/skill-station'
            self.assertTrue((installed/'pet.py').exists())
            self.assertEqual(json.loads((installed/'settings.json').read_text())['workspaces'],[str(home)])
            self.assertTrue((home/'.local/share/applications/skill-station.desktop').exists())


if __name__ == '__main__':
    unittest.main()
