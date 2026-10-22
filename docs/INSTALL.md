# 比格技能口袋 0.3.4：安装与分享

本版本包含两个独立插件和一个 Linux 桌面小工具。自己的账号、连接和工作文件夹由每位使用者自行配置。分享包不包含登录凭据、个人任务记录或本机已安装的第三方技能。

## 文件怎么选

| 文件 | 内容 | 使用范围 |
| --- | --- | --- |
| `beagle-skills-0.3.4.zip` | 技能导航 `skill-hub`、多 Agent 分工 `agent-team` | 插件技能；能否执行具体工具取决于宿主实际能力 |
| `beagle-desktop-0.3.4.zip` | 本机任务 MCP、`beagle-tasks` 技能、连接服务 | 需要本机执行环境和已经登录的 Codex；已在本机 Linux 验证 |
| `beagle-linux-desktop-0.3.4.zip` | 比格桌宠、悬浮弹窗、完整网页和连接层 | 已验证的 Linux 桌面版本；不是 Windows EXE 或 Mac DMG |

仓库插件源包括 `.agents/plugins/marketplace.json`、`plugins/beagle-skills/` 和 `plugins/beagle-desktop/`。直接分享 GitHub 仓库链接即可按下面的方式安装。单独的插件 ZIP 用于插件导入或官方提交，不是聊天分享链接。

## 在 Codex 安装插件

前提：安装 Codex 并用使用者自己的账号登录；本机可运行 Python 3.11+，命令为 `python3`。目前连接层在 Linux 验证，其他系统需要另外验证本机启动与运行目录适配。

在包含本地插件源目录的位置执行：

```bash
codex plugin marketplace add sss836/Beagle_skill_Pocket --ref v0.3.4
codex plugin add beagle-skills@beagle-local
codex plugin add beagle-desktop@beagle-local
```

重新打开一个 Codex 会话，在已安装插件中选择“比格技能口袋”或“比格直接开工”。插件中提供：连接状态、模型列表、本机技能目录、提交任务、任务列表、读取结果、停止任务、添加用户指定的工作文件夹。

示例请求：

> 使用比格直接开工，在我指定的工作文件夹整理这份资料。提交后告诉我任务 ID，并查看真实进度。

没有工作文件夹时，先明确提供要使用的本机文件夹；不要默认把整台电脑作为工作目录。需要人工确认或补充内容时，在返回的任务看板链接中处理。

## 在 ChatGPT 分享

支持本地插件的桌面界面可使用上述本地目录，并在插件目录中选择本地来源；必要时重新启动桌面应用。完整本机执行插件需要本地执行环境，不能靠普通网页直接访问另一位用户电脑上的 `127.0.0.1` 服务。

面向普通网页用户公开分发时，可以先提交通用技能包。公开插件需按官方提交流程审核、发布，当前文件尚未提交或公开上架。带本机 MCP 的插件属于桌面范围，官方对本地 MCP 提交还有额外准入要求。若要让网页用户调用云端执行，需要单独部署带认证的远程 HTTPS MCP 服务；本版本没有把你的电脑暴露到公网。

官方文档：

- https://developers.openai.com/plugins/build/plugins
- https://developers.openai.com/plugins/deploy/submission
- https://developers.openai.com/plugins/deploy/desktop-only

## 安装 Linux 比格桌宠

解压 `beagle-linux-desktop-0.3.4.zip`。在 Ubuntu 的已验证环境中，需要 Python 3.12、GTK 3、PyGObject 和 Cairo。系统依赖可由使用者从系统包管理器安装，例如：

```bash
sudo apt install python3-gi python3-cairo python3-gi-cairo gir1.2-gtk-3.0
/usr/bin/python3.12 skill-station/install.py --workspace /你的工作文件夹
```

安装程序只写入使用者自己的应用目录、技能目录和桌面启动器。已有不同内容的同名技能不会被覆盖。包内私有 Cairo 桥接库来自 Ubuntu 官方包，面向原先验证的 Python 3.12 Linux 环境。

点击桌面比格，悬停后选择技能，填写要求和附件，可选择执行模型，再点“开工”。模型列表来自本机 Codex；默认沿用当前设置，主 Agent 使用选定模型，子 Agent 的单独选型取决于宿主支持。任务窗口与网页看板显示真实状态；新增成果默认保存在所选工作文件夹的 `outputs/beagle-tasks/任务ID/`。

关闭任务窗口会让任务继续在后台运行；点“停止任务”才会中断。停止不会撤销已经写入的文件。电脑或服务重新启动后，尚未结束的任务会标记为中断，不会自动重跑。

## 连接与数据

比格通过官方 `codex app-server` 与本机 Codex 通信，复用该使用者已有登录。连接层不提取或打包凭据。任务默认使用工作文件夹写入沙箱和按需批准；需要确认的请求会停下来等待用户处理。任务记录保存在本机应用的 `tasks/` 目录中，不加入分享包。

官方接口：https://learn.chatgpt.com/docs/app-server
