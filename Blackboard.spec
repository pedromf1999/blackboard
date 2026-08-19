# -*- mode: python ; coding: utf-8 -*-

import os
from os.path import join
import sys

from beeref import constants


block_cipher = None
# Executable name, from the application name
appname = f'Blackboard-{constants.VERSION}'


def write_version_resource():
    """Write the version info Windows shows in a file's properties.

    Without this, right-clicking the executable and looking at Details
    shows nothing at all, which makes it impossible to tell two builds
    apart outside the application. Windows wants four numbers, so the
    version is padded out with zeroes.
    """

    numbers = [int(part) for part in constants.VERSION.split('.')]
    numbers = (numbers + [0, 0, 0, 0])[:4]
    path = join('build', 'file_version_info.txt')
    os.makedirs('build', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tuple(numbers)},
    prodvers={tuple(numbers)},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('FileDescription', '{constants.APPNAME_FULL}'),
        StringStruct('FileVersion', '{constants.VERSION}'),
        StringStruct('InternalName', '{constants.APPNAME}'),
        StringStruct('OriginalFilename', '{appname}.exe'),
        StringStruct('ProductName', '{constants.APPNAME}'),
        StringStruct('ProductVersion', '{constants.VERSION}'),
        StringStruct('LegalCopyright', '{constants.COPYRIGHT}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""")
    return path


version_resource = write_version_resource() if sys.platform.startswith(
    'win') else None

if sys.platform.startswith('win'):
    icon = 'logo.ico'
else:
    icon = 'logo.icns'  # For OSX; param gets ignored on Linux


a = Analysis(
    [join('beeref', '__main__.py')],
    pathex=[os.getcwd()],
    binaries=[],
    datas=[
        (join('beeref', 'documentation'), join('beeref', 'documentation')),
        (join('beeref', 'assets', '*.png'), join('beeref', 'assets')),
        # The colour palette the pickers offer
        (join('beeref', 'assets', '*.hex'), join('beeref', 'assets')),
        (join('beeref', 'assets', 'fonts'), join('beeref', 'assets',
                                                 'fonts')),
        (join('beeref', 'assets', 'icons'), join('beeref', 'assets',
                                                 'icons'))],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=appname,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None ,
    version=version_resource,
    icon=join('beeref', 'assets', icon))

if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='Blackboard.app',
        icon=join('beeref', 'assets', icon),
        bundle_identifier='org.bvref.app',
        version=f'{constants.VERSION}',
        info_plist={
            'CFBundleDocumentTypes': [
                {
                    'CFBundleTypeExtensions': [ 'blk', 'bee' ],
                    'CFBundleTypeRole': 'Viewer'
                }
            ]
        })
