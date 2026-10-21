"""Build plugins and release archives from public, explicitly selected sources."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT/'desktop/skill-station'
VERSION = (ROOT/'VERSION').read_text().strip()
RUNTIME = ['app.py','launch.py','pet_support.py','task_runner.py','task_client.py','static','assets']


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True, ignore_dangling_symlinks=True,
                        ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    else:
        shutil.copy2(source, target)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')


def zip_paths(target, entries):
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for source, relative in entries:
            files = sorted(source.rglob('*')) if source.is_dir() else [source]
            for file in files:
                if file.is_file() and '__pycache__' not in file.parts:
                    name = relative/file.relative_to(source) if source.is_dir() else relative
                    archive.write(file, name)


def main():
    dist = ROOT/'dist'
    dist.mkdir(exist_ok=True)
    for name in ('beagle-skills','beagle-desktop'):
        folder = ROOT/'plugins'/name
        if folder.exists():
            assert (folder/'plugin.json').is_file()
            shutil.rmtree(folder)
        desktop = name == 'beagle-desktop'
        interface = {'displayName': '比格直接开工' if desktop else '比格技能口袋',
                     'shortDescription': '提交任务、查看进度、接收成果' if desktop else '技能导航与多 Agent 分工',
                     'brandColor': '#d9a568','composerIcon': './assets/beagle.png','logo': './assets/beagle.png'}
        extension = {'interface': interface}
        if desktop:
            extension['requires_local_executor'] = True
        write_json(folder/'plugin.json', {'$schema':'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json',
                   'name':name,'version':VERSION,'description':interface['shortDescription'],
                   'extensions':{'com.openai':extension}})
        copy(APP/'assets/beagle.png', folder/'assets/beagle.png')
        copy(ROOT/'docs/INSTALL.md', folder/'README.md')
        if desktop:
            copy(APP/'mcp_server.py', folder/'server/mcp_server.py')
            for item in RUNTIME:
                copy(APP/item, folder/'runtime'/item)
            copy(APP/'plugin-skills/beagle-tasks', folder/'skills/beagle-tasks')
            write_json(folder/'mcp.json', {'$schema':'https://agent-plugins.org/schemas/1.0.0/mcp.schema.json',
                'mcpServers':{'beagle_tasks':{'type':'stdio','command':'python3',
                'args':['${PLUGIN_ROOT}/server/mcp_server.py'],'cwd':'${PLUGIN_ROOT}'}}})
        else:
            for skill in ('agent-team','skill-hub'):
                copy(ROOT/'desktop/agent-skills'/skill, folder/'skills'/skill)
        zip_paths(dist/f'{name}-{VERSION}.zip', [(folder,Path('.'))])
    write_json(ROOT/'.agents/plugins/marketplace.json', {'name':'beagle-local',
        'interface':{'displayName':'比格的技能口袋'},'plugins':[
            {'name':name,'source':{'source':'local','path':'./plugins/'+name},
             'policy':{'installation':'AVAILABLE','authentication':'ON_INSTALL'},'category':'Productivity'}
            for name in ('beagle-skills','beagle-desktop')]})
    zip_paths(dist/f'beagle-linux-desktop-{VERSION}.zip', [
        (APP/part,Path('skill-station')/part)
        for part in RUNTIME+['pet.py','pet_tasks.py','install.py','vendor']]+[
        (ROOT/'desktop/agent-skills',Path('agent-skills')),(ROOT/'docs/INSTALL.md',Path('README.md'))])
    zip_paths(dist/f'beagle-one-click-{VERSION}.zip', [
        (ROOT/'Install-Beagle.desktop',Path('Install-Beagle.desktop')),
        (ROOT/'install.sh',Path('install.sh')),(ROOT/'README.md',Path('README.md'))])
    artifacts = sorted(dist.glob(f'*-{VERSION}.zip'))
    (dist/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in artifacts))
    print(json.dumps({'version':VERSION,'artifacts':[p.name for p in artifacts]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
