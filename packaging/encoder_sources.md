# OrcaView animation encoder sources

The desktop application sends uncompressed frames to FFmpeg for GIF or H.264/MP4 export. This archive contains the imageio-ffmpeg Python wrapper, the FFmpeg and x264 source revisions used on each platform, and the Linux and wheel packaging recipes. The original upstream archives retain their license files. The Python wrapper uses BSD-2-Clause. Each distributed FFmpeg build enables GPL code and links x264.

| Platform | FFmpeg source | x264 source | Binary distributor |
| --- | --- | --- | --- |
| macOS arm64 | 9.0 | `7ed753b` | OSXExperts |
| Windows x64 | 9.0.2 | `0480cb0` | Gyan, essentials build |
| Linux x86-64 | `2a571b6068`, 17 commits after 9.0.2 | `0480cb0` | BtbN, GPL 9.0 build of 30 September 2026 |

`manifest.json` lists the source archive URLs, SHA-256 hashes, upstream binary distributions, wheel and executable hashes, and the configuration string embedded in each encoder. The executable hashes identify the files supplied by the wheels before desktop signing. The platform records cover the three bundled binaries and their additional enabled codecs and libraries.

- `imageio_ffmpeg-0.8.1.tar.gz` contains the Python package distributed on PyPI. The companion imageio Git archive includes the wheel preparation scripts and `tools/ffmpeg-sources.json`, which identifies each upstream binary package and executable digest. [Wrapper and wheel sources](https://github.com/imageio/imageio-ffmpeg/tree/v0.8.1)
- The two FFmpeg release tarballs and the Linux commit snapshot contain the source for the respective versions in the table. The Windows distributor identifies the release commit `946fcce07b`. [FFmpeg releases](https://ffmpeg.org/releases/) · [Windows release record](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2)
- The x264 archives match the revisions identified by the macOS and Windows encoder build strings and the Linux `scripts.d/50-x264.sh` recipe. [x264 upstream](https://code.videolan.org/videolan/x264) · [x264 source mirror](https://github.com/mirror/x264)
- The BtbN archive includes the platform build scripts, patches, Dockerfiles and component source references. The macOS and Windows distributors provide their own build documentation and component lists. Additional libraries enabled by those distributors are identified in the build records. [BtbN recipes](https://github.com/BtbN/FFmpeg-Builds/tree/autobuild-2026-09-30-13-08) · [macOS build notes](https://www.osxexperts.net/) · [Windows build and library list](https://www.gyan.dev/ffmpeg/builds/#libraries)

The desktop packages and this source archive include the binary distribution notices in `THIRD_PARTY_NOTICES.md`.
