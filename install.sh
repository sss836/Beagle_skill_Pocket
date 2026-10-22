#!/usr/bin/env bash
# User-level installer. No sudo, credential copying, or API key is required here.
set -euo pipefail
BEAGLE_VERSION=0.3.4
BEAGLE_REPO=sss836/Beagle_skill_Pocket
beagle_mode=all
beagle_start=1
beagle_check=0
beagle_workspace=
while (($#)); do
  case "$1" in
    --all) beagle_mode=all ;;
    --plugins-only) beagle_mode=plugins ;;
    --skills-only) beagle_mode=skills ;;
    --desktop-only) beagle_mode=desktop ;;
    --no-start) beagle_start=0 ;;
    --check) beagle_check=1 ;;
    --workspace) shift; beagle_workspace=${1:?请提供工作文件夹} ;;
    -h|--help)
      echo '比格安装：bash install.sh [--all|--plugins-only|--skills-only|--desktop-only] [--workspace 文件夹] [--no-start] [--check]'
      exit 0 ;;
    *) echo "未知选项：$1" >&2; exit 2 ;;
  esac
  shift
done
if [[ "$beagle_mode" != skills && "$(uname -s)" != Linux ]]; then
  echo '桌宠和本机连接层当前支持 Linux。只安装技能可使用 --skills-only。' >&2
  exit 1
fi
beagle_codex=$(command -v codex || true)
if [[ -z "$beagle_codex" && -x /usr/lib/chatgpt/resources/codex ]]; then
  beagle_codex=/usr/lib/chatgpt/resources/codex
fi
if [[ -z "$beagle_codex" ]]; then
  echo '请先安装 Codex 并使用自己的账号登录，再重新运行安装程序。' >&2
  echo 'https://developers.openai.com/codex/cli/' >&2
  exit 1
fi
beagle_python=/usr/bin/python3
[[ -x "$beagle_python" ]] || beagle_python=$(command -v python3)
"$beagle_python" -c 'import sys; assert sys.version_info >= (3,11), "需要 Python 3.11 或更高版本"'
if [[ "$beagle_mode" == all || "$beagle_mode" == desktop ]]; then
  if ! "$beagle_python" -c 'import gi, cairo; gi.require_version("Gtk","3.0"); from gi.repository import Gtk' 2>/dev/null; then
    echo '缺少桌宠依赖。Ubuntu / Debian 请先运行以下命令，再重新安装：' >&2
    echo 'sudo apt install python3-gi python3-cairo python3-gi-cairo gir1.2-gtk-3.0' >&2
    exit 1
  fi
fi
if [[ -n "$beagle_workspace" && ! -d "$beagle_workspace" ]]; then
  echo "工作文件夹不存在：$beagle_workspace" >&2; exit 1
fi
if ((beagle_check)); then
  echo "依赖检查通过（$beagle_mode）。"; exit 0
fi
beagle_source=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ! -f "$beagle_source/.agents/plugins/marketplace.json" ]]; then
  # Standalone downloaded entry: retain the source so a local marketplace keeps working.
  beagle_source=$("$beagle_python" - "$BEAGLE_REPO" "$BEAGLE_VERSION" <<'PY'
import io, os, shutil, sys, tempfile, urllib.request, zipfile
from pathlib import Path
repo, version = sys.argv[1:]
url = f'https://github.com/{repo}/archive/refs/tags/v{version}.zip'
print(f'正在下载比格 {version}…', file=sys.stderr)
with urllib.request.urlopen(url, timeout=45) as response:
    data = response.read()
destination = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'beagle-skill-pocket'/f'source-{version}'
with tempfile.TemporaryDirectory(prefix='beagle-install-') as temporary:
    root = Path(temporary)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            path = root/member.filename
            if not path.resolve().is_relative_to(root.resolve()) or (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise SystemExit('安装包包含不支持的路径。')
        archive.extractall(root)
    sources = list(root.glob('*/.agents/plugins/marketplace.json'))
    if len(sources) != 1:
        raise SystemExit('安装包目录不完整。')
    source = sources[0].parents[2]
    if destination.exists() and not (destination/'VERSION').is_file():
        raise SystemExit(f'目录已存在且不属于本安装程序：{destination}')
    shutil.copytree(source, destination, dirs_exist_ok=True)
print(destination)
PY
)
fi
if [[ "$beagle_mode" == all || "$beagle_mode" == desktop ]]; then
  beagle_args=()
  if [[ -n "$beagle_workspace" ]]; then beagle_args+=(--workspace "$beagle_workspace"); fi
  "$beagle_python" "$beagle_source/desktop/skill-station/install.py" "${beagle_args[@]}"
fi
if [[ "$beagle_mode" != desktop ]]; then
  "$beagle_codex" plugin marketplace add "$beagle_source"
  "$beagle_codex" plugin add beagle-skills@beagle-local
  if [[ "$beagle_mode" != skills ]]; then
    "$beagle_codex" plugin add beagle-desktop@beagle-local
  fi
fi
if [[ "$beagle_mode" == all || "$beagle_mode" == desktop ]]; then
  if ((beagle_start)) && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    mkdir -p "$HOME/.cache/beagle-skill-pocket"
    nohup "$beagle_python" "$HOME/.local/share/skill-station/pet.py" >"$HOME/.cache/beagle-skill-pocket/pet.log" 2>&1 </dev/null &
  fi
fi
echo '比格已安装。桌宠可从桌面或应用菜单启动；重新打开 Codex 会话后使用插件。'
echo '执行任务前，请用自己的 Codex 账号登录，并选择工作文件夹。'
