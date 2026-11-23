# Linux 和 Windows 便携版

使用 CPython 3.13 在仓库根目录运行以下命令。构建 Windows 包还需要将 Go 1.23 或更高版本的 `go` 加入 PATH。0.1.0a43 发行包使用 Go 1.27.4。构建机可使用 macOS、Linux 或 Windows。脚本使用 Go 标准库交叉编译 Windows x64 启动器，并校验锁定的 CPython、PySide6 Essentials、Shiboken 和 Open Babel 依赖。

```sh
python3.13 packaging/desktop/build.py both
```

可将 `both` 换成 `linux` 或 `windows`。重复构建时可指定 `--cache <目录>` 复用经过校验的下载。成品分别写入 `dist/linux/<版本>/` 和 `dist/windows/<版本>/`。四个语言包、Qt 标准控件译文和许可证随运行库提供。发行页的独立第三方源码附件包含对应的 Open Babel 源码。

- **Linux x86-64**。解开 `.tar.gz`，在图形桌面运行解压目录里的 `./OrcaView`。Qt 6.8.3 的 Linux 原生库要求 glibc 2.28 或更新版本，并使用系统图形栈、字体和键盘库。在没有安装完整桌面环境的 Debian/Ubuntu 系统中，X11 插件还需要系统的 `libxcb-cursor0`、`libxkbcommon-x11-0` 等桌面库。可用 `./OrcaView --version` 验证命令入口。
- **Windows x64**。将 `-Windows-x64-portable.zip` 解压到独立目录，里面有 `OrcaView.exe`、`LICENSE` 和 `Examples`。双击 EXE 启动界面，命令行可运行 `.\OrcaView.exe --version`。EXE 内嵌一个标准 ZIP，每次启动会将运行库展开至当前用户的临时目录，常规退出后清除。Windows 支持界面、结构处理、输入生成和已有结果导入。
