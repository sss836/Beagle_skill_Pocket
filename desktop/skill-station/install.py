#!/usr/bin/env python3
"""Install the reviewed local app, two personal skills, and desktop launchers."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def identical_tree(source, target):
    expected = sorted(p.relative_to(source) for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    existing = sorted(p.relative_to(target) for p in target.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    return expected == existing and all((source/p).read_bytes() == (target/p).read_bytes() for p in expected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--desktop', type=Path)
    parser.add_argument('--workspace', type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    skills = source.parent / 'agent-skills'
    destination = args.home / '.local/share/skill-station'
    app_files = ['app.py', 'launch.py', 'pet.py', 'pet_support.py', 'pet_tasks.py', 'task_runner.py', 'task_client.py', 'static', 'assets', 'vendor']
    for name in app_files:
        if not (source/name).exists():
            raise SystemExit(f'缺少文件：{name}')
    if destination.exists() and not (destination/'INSTALLATION.json').is_file():
        raise SystemExit(f'目标目录已存在且不属于本安装程序：{destination}')
    for name in ('agent-team', 'skill-hub'):
        target = args.home / '.codex/skills' / name
        if target.exists() and not identical_tree(skills/name, target):
            raise SystemExit(f'已有同名技能，未覆盖：{target}')
    desktop = args.desktop
    if desktop is None and args.home == Path.home():
        try:
            desktop = Path(subprocess.check_output(['xdg-user-dir','DESKTOP'],text=True).strip())
        except (OSError, subprocess.SubprocessError):
            desktop = args.home / 'Desktop'
    desktop = desktop or args.home / 'Desktop'
    launchers = [args.home / '.local/share/applications/skill-station.desktop', desktop / '技能小站.desktop']
    for path in launchers:
        if path.exists() and 'X-SkillStation-Managed=true' not in path.read_text():
            raise SystemExit(f'已有同名桌面文件，未覆盖：{path}')
    destination.mkdir(parents=True,exist_ok=True)
    for name in app_files:
        if (source/name).is_dir():
            shutil.copytree(source/name,destination/name,dirs_exist_ok=True,ignore_dangling_symlinks=True)
        else:
            shutil.copy2(source/name,destination/name)
    settings_path = destination/'settings.json'
    # Upgrades preserve folders and any settings introduced by newer versions.
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {'workspaces': []}
    if args.workspace:
        workspace = args.workspace.expanduser().resolve()
        if not workspace.is_dir():
            raise SystemExit(f'工作文件夹不存在：{workspace}')
        settings['workspaces'] = list(dict.fromkeys(settings.get('workspaces', []) + [str(workspace)]))
    settings_path.write_text(json.dumps(settings,ensure_ascii=False,indent=2)+'\n')
    (destination/'INSTALLATION.json').write_text(json.dumps({'application':'skill-station','version':3,'interface':'beagle-tasks'},indent=2)+'\n')
    installed = []
    for name in ('agent-team','skill-hub'):
        target = args.home / '.codex/skills' / name
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(skills/name,target)
        installed.append(str(target))
    executable = str(Path(sys.executable).resolve())
    def exec_quote(value):
        value = str(value).replace('%', '%%')
        for char in ('\\', '"', '`', '$'):
            value = value.replace(char, '\\' + char)
        return '"' + value + '"'
    entry = '\n'.join(['[Desktop Entry]','Type=Application','Version=1.0','Name=比格技能口袋','Name[en]=Beagle Skill Pocket',
        'Comment=桌面比格，鼠标移近打开技能口袋',f'Exec={exec_quote(executable)} {exec_quote(destination / "pet.py")}',
        f'Icon={destination}/assets/beagle.png','Terminal=false','Categories=Utility;',
        'StartupNotify=false','StartupWMClass=skill-station-pet','X-SkillStation-Managed=true',''])
    for path in launchers:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(entry)
        path.chmod(0o755)
    trusted = False
    if args.home == Path.home() and shutil.which('gio'):
        trusted = subprocess.run(['gio','set',str(launchers[1]),'metadata::trusted','true'],capture_output=True).returncode == 0
    if args.home == Path.home() and shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database',str(launchers[0].parent)],capture_output=True)
    print(json.dumps({'app':str(destination),'desktop':str(launchers[1]),'desktop_trusted':trusted,'skills':installed},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
