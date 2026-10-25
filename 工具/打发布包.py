# -*- coding: utf-8 -*-
"""打发布包（解压即跑，不带 .venv / .tmp / .git）。

用法：& .venv\\Scripts\\python.exe -B 工具\\打发布包.py
产物：项目根目录下的 `芙兰朵露_发布包.zip`（桌面这个进程写不进去——目录是低完整性，
      见交接文档 §3.10，所以放项目根，用户双击 `复制发布包到桌面.bat` 拷过去）。
"""
import os
import zipfile

FL = r"C:\Users\CupCakeQAQ_\Desktop\芙兰"
OUT = os.path.join(FL, "芙兰朵露_发布包.zip")
ROOT = "芙兰朵露"
# 解压即能跑的最小集 + 源码/文档（用户要求「连源码一起打」）
ITEMS = ["芙兰朵露.exe", "_internal", "贴图", "font", "sound", "data", "model",
         "src", "工具",
         "README.md", "交接文档.md", ".gitignore",
         "LICENSE", "LICENSE-贴图",     # 2026-10-25 第三十一批：GPL-3.0 要求随程序给许可证，贴图另一套条款
         "关闭SmartScreen拦截(右键管理员运行).bat"]
# 运行时才长出来的东西别打进去（settings.json 记的是我这台机器的气泡偏移）
SKIP_DIRS = {".venv", ".pysite", ".tmp", "__pycache__", ".git",
             "收藏", "芙兰的收藏"}   # 2026-10-24 补充⑮：收藏夹改名了，两个名字都别进发布包
SKIP_FILES = {os.path.join("data", n) for n in
              ("settings.json", "gift.log", "chat_history.json", "debug.log",
               "_voice_tmp.wav",      # 语音的临时录音，认完字就该没了，别带给别人
               "_voice_log.txt", "_stt_probe.txt")}   # 语音排障日志，只有我本机才需要


def main():
    if os.path.exists(OUT):
        os.remove(OUT)
    total = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for it in ITEMS:
            p = os.path.join(FL, it)
            if not os.path.exists(p):
                print("跳过（不存在）：" + it)
                continue
            if os.path.isfile(p):
                z.write(p, ROOT + "/" + it)
                total += 1
                continue
            for r, dirs, fs in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for f in fs:
                    full = os.path.join(r, f)
                    rel = os.path.relpath(full, FL)
                    if rel in SKIP_FILES:
                        print("跳过（运行时文件）：" + rel)
                        continue
                    z.write(full, ROOT + "/" + rel.replace("\\", "/"))
                    total += 1
    size = os.path.getsize(OUT)
    print("打包完成：%s" % OUT)
    print("%d 个文件 / %.1f MB" % (total, size / 1048576.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
