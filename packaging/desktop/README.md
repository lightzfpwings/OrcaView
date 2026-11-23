# Linux 和 Windows 便携版

使用 CPython 3.13 在仓库根目录运行以下命令。构建脚本校验依赖锁定文件中的 SHA-256，使用目标平台的 CPython、PySide6 Essentials、Shiboken 和 Open Babel 二进制，并将 OrcaView 源码编译成对应版本的 Python 字节码。

```sh
python3.13 packaging/desktop/build.py both
```

可将 `both` 换成 `linux` 或 `windows`。默认下载缓存在构建完成后释放。重复构建时可指定 `--cache <目录>` 复用经过校验的下载。成品分别写入 `dist/linux/<版本>/` 和 `dist/windows/<版本>/`。解压后可见主启动器、随程序运行的 `python` 目录和可直接打开的「示例」。四个语言包、Qt 标准控件译文和许可证随运行库提供。发行页的独立第三方源码附件包含对应的 Open Babel 源码。

- **Linux x86-64**。解开 `.tar.gz`，在图形桌面运行解压目录里的 `./OrcaView`。Qt 6.8.3 的 Linux 原生库要求 glibc 2.28 或更新版本，并使用系统图形栈、字体和键盘库。在没有安装完整桌面环境的 Debian/Ubuntu 系统中，X11 插件还需要系统的 `libxcb-cursor0`、`libxkbcommon-x11-0` 等桌面库。可用 `./OrcaView --version` 验证命令入口。
- **Windows x64**。完整解压 ZIP，双击 `OrcaView.exe`，在命令行使用 `.\python\OrcaView-cli.exe --version`。两个 EXE 均从自身目录查找随包提供的 Python，移动应用时请移动整个解压目录。当前本地 ORCA 作业执行器使用 POSIX 进程组，Windows 支持界面、结构处理、输入生成和已有结果导入。
