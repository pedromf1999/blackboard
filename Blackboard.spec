# -*- mode: python ; coding: utf-8 -*-

import os
from os.path import join
import sys

from beeref import constants


block_cipher = None
# Executable name, from the application name
appname = f'Blackboard-{constants.VERSION}'

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
                    'CFBundleTypeExtensions': [ 'bee' ],
                    'CFBundleTypeRole': 'Viewer'
                }
            ]
        })
