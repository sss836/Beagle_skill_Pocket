# 第三方组件

桌宠通过系统安装的 GTK 3、PyGObject 与 Cairo 运行。这些组件遵循各自的上游许可证。

Linux 包内的 `_gi_cairo.cpython-312-x86_64-linux-gnu.so` 是未修改的 Ubuntu `python3-gi-cairo` 3.48.2-1 桥接库，仅适用于对应的 Linux x86_64 / CPython 3.12 环境。其版权与许可证信息保留在：

- `desktop/skill-station/vendor/usr/share/doc/python3-gi-cairo/copyright`
- `desktop/skill-station/vendor/COPYING.LGPL-2.1`

上游 PyGObject：https://gitlab.gnome.org/GNOME/pygobject

对应 Ubuntu 源码包：https://launchpad.net/ubuntu/+source/pygobject/3.48.2-1

比格图像根据用户提供的角色参考制作，不将上游组件或角色参考的权利归为项目自有代码。仓库不打包用户安装的其他第三方技能。
