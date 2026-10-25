# Third-party notices — macOS build

These notices describe the Mac build, rather than the original Windows runtime. Each dependency retains its own copyright and license. The dependency licenses do not change ownership or licensing of the original desktop-pet code, character, artwork, or animations; see [NOTICE.md](NOTICE.md) and [ASSETS.md](ASSETS.md).

| Component | Version in this build | Notice and source |
| --- | --- | --- |
| CPython runtime | 3.12.14 | [Included Python license](licenses/Python/LICENSE.txt); [corresponding source](https://github.com/python/cpython/tree/v3.12.14) |
| PySide6 / Essentials / Addons / Shiboken6 | 6.9.2 | LGPL-3.0-only / GPL alternatives as declared by the installed distributions; [LGPL text](licenses/Qt/LGPL-3.0-only.txt), [GPL text](licenses/Qt/GPL-3.0-only.txt); [source](https://code.qt.io/cgit/pyside/pyside-setup.git/tree/?h=v6.9.2) |
| Qt runtime frameworks and plugins | 6.9.2 | Applicable Qt module licenses and third-party notices; [Qt source notices](licenses/Qt/source-notices/), [Qt source repositories](https://code.qt.io/cgit/qt/) |
| Pillow | 12.0.0 | [MIT-CMU and bundled native-library notices](licenses/Pillow/LICENSE); [source](https://github.com/python-pillow/Pillow/tree/12.0.0) |
| psutil | 7.0.0 | [BSD-3-Clause](licenses/psutil/LICENSE); [source](https://github.com/giampaolo/psutil/tree/release-7.0.0) |
| FFmpeg libraries distributed with Qt Multimedia | 7.1.1 | Bundled library reports LGPL version 2.1 or later; [LGPL text](licenses/FFmpeg/COPYING.LGPLv2.1); [corresponding source](https://github.com/FFmpeg/FFmpeg/tree/n7.1.1) |
| PyInstaller bootloader | 6.22.3 | [GPL and distribution exception](licenses/PyInstaller/COPYING.txt); [source](https://github.com/pyinstaller/pyinstaller/tree/v6.22.3) |

The current click sound is described by the upstream `app/sounds/来源.txt` as an original program-synthesized sound without external recording samples. The [Kenney CC0 notice](licenses/Kenney/LICENSE.txt) is retained from the original distribution as provenance; it is not used to infer a CC0 grant for the current WAV.

The Pillow wheel's complete license file also contains the notices for its bundled native image libraries, including FreeType, LittleCMS, WebP, AVIF, libjpeg, OpenJPEG, TIFF, XZ, Xau, XCB, and zlib/zlib-ng. Their reported versions are recorded in [the Mac component inventory](licenses/components.json).

Qt source notices are collected from the pinned `v6.9.2` official source tags, including license files referenced by `qt_attribution.json`. Their origin URLs and SHA-256 digests are recorded in the [notice manifest](licenses/Qt/source-notices/manifest.json). This source-notice collection covers more platform-specific source components than a single Mac binary necessarily uses; it is not a claim that every referenced component is shipped.

The exact native files in the prepared Mac application are listed in [native-libraries.json](licenses/native-libraries.json). The application uses separate dynamic-library files. No third-party library source was changed for this port; the packager may thin universal binaries to arm64, adjust their bundle layout and load paths, and apply local ad-hoc signatures.

The original Windows notices are preserved in [upstream-notices/licenses/](upstream-notices/licenses/) as provenance. They are not the Mac dependency inventory. Nothing in these notices is intended to restrict the rights granted by a third-party dependency's own license.
