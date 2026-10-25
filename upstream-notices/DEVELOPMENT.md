# 开发者说明

普通用户请用windows-x64.zip。此仓库压缩包不含动画、Python及Qt运行环境。
开发者需安装64位Python，并将完整包的outputs文件夹复制到此目录。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app\prepare_assets.py
.venv\Scripts\python.exe app\pet.py
.venv\Scripts\python.exe app\test_pet.py
```

复刻EXE可安装PyInstaller 6.22.3，使用onedir/windowed模式，以app/pet.py作为入口，显式包含autostart、selftest、version模块。Windows包必须在Windows构建。
程序支持--autostart、--enable-autostart、--disable-autostart、--self-test。
所有播放路径相对发行目录。renderScale和renderOffset控制固定显示校准。
源码未指定开源许可证，美术许可见ASSETS.md。
