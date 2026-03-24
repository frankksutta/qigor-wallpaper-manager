# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\Users\\my4nt\\OneDrive\\lucid24\\py_tools\\mp4_movie_and_image_tools\\qigor_wallpaper\\app', 'app'), ('C:\\Users\\my4nt\\OneDrive\\lucid24\\py_tools\\mp4_movie_and_image_tools\\qigor_wallpaper\\assets', 'assets')]
binaries = []
hiddenimports = []
tmp_ret = collect_all('tkinterdnd2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\Users\\my4nt\\OneDrive\\lucid24\\py_tools\\mp4_movie_and_image_tools\\qigor_wallpaper\\qigor_wallpaper_manager.pyw'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='QiGor_Wallpaper_Manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:\\Users\\my4nt\\OneDrive\\lucid24\\py_tools\\mp4_movie_and_image_tools\\qigor_wallpaper\\_version_info.txt',
    icon=['C:\\Users\\my4nt\\OneDrive\\lucid24\\py_tools\\mp4_movie_and_image_tools\\qigor_wallpaper\\qigor_wallpaper_manager.ico'],
)
