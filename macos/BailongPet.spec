from pathlib import Path

root = Path(SPECPATH).resolve().parent
datas = [(str(root/'outputs'), 'outputs'),
         (str(root/'app/sounds'), 'app/sounds'),
         (str(root/'licenses'), 'licenses'),
         (str(root/'ASSETS.md'), '.'),
         (str(root/'MACOS.txt'), '.'),
         (str(root/'NOTICE.md'), '.'),
         (str(root/'THIRD_PARTY_NOTICES.md'), '.'),
         (str(root/'BUILD_INFO.json'), '.')]
a = Analysis([str(root/'app/pet.py')], pathex=[str(root/'app')],
             binaries=[], datas=datas,
             hiddenimports=['autostart', 'selftest', 'runtime_paths', 'version',
                            'animation_frames', 'desktop_visibility', 'chat_ui', 'chat_backend', 'quota'],
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['tkinter', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
                       'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets',
                       'PySide6.QtVirtualKeyboard', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets'],
             noarchive=False)

# Qt's general plugin discovery otherwise pulls PDF/QML/virtual-keyboard
# frameworks into this widget-only app. Pillow decodes the artwork; none of
# those modules or their input/PDF plugins is part of the pet's runtime.
def used_qt_resource(entry):
    destination = entry[0].replace('\\', '/')
    if any(name in destination for name in ('QtQml', 'QtQuick', 'QtVirtualKeyboard', 'QtPdf')):
        return False
    return not any(part in destination for part in
                   ('/plugins/platforminputcontexts/', '/plugins/generic/',
                    '/plugins/imageformats/libqpdf'))

a.binaries = [entry for entry in a.binaries if used_qt_resource(entry)]
a.datas = [entry for entry in a.datas if used_qt_resource(entry)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='BailongPet',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, target_arch='arm64', codesign_identity=None,
          entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='BailongPet')
app = BUNDLE(coll, name='BailongPet.app', icon=str(root/'macos/BailongPet.icns'),
             bundle_identifier='local.bailongpet.macos', version='0.4.1',
             info_plist={'CFBundleDisplayName': '白龙桌宠',
                         'CFBundleVersion': '3',
                         'LSUIElement': True,
                         'NSHighResolutionCapable': True,
                         'LSMinimumSystemVersion': '12.0'})
