# Build: python -m PyInstaller --noconfirm --clean EliteDangerousNeutronPlanner.spec
from pathlib import Path
project = Path(SPECPATH)
a = Analysis([str(project / 'src' / 'planner_app.py')], pathex=[str(project / 'src')],
             binaries=[], datas=[(str(project / 'LICENSE'), '.')],
             hiddenimports=['smoke_test'], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='EliteDangerousNeutronPlanner',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          manifest=str(project / "EliteDangerousNeutronPlanner.manifest"), disable_windowed_traceback=False)
