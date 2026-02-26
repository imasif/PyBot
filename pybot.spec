# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['bot.py'],
    pathex=[],
    binaries=[],
    datas=[('skills', 'skills'), ('services', 'services'), ('.env.example', '.env.example')],
    hiddenimports=['services.browser', 'services.calculation', 'services.cron', 'services.cron_nl', 'services.emails', 'services.identity', 'services.info_search', 'services.news', 'services.notes', 'services.shopping', 'services.timer', 'services.tracking', 'services.weather', 'skills.trello.service'],
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
    [],
    exclude_binaries=True,
    name='pybot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='pybot',
)
