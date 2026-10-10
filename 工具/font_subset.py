"""把 font\\NotoSansSC-VF.ttf 裁成「项目会显示的字 + GB2312 全部 6763 字」。

为什么裁：原字是 Noto Sans SC 可变字重的**全字库**，16.95 MB，而界面实际会显示的字
只有一千多个。裁完约 3.6 MB，视觉零变化（同一份字形，只是去掉了用不到的）。

什么时候要重跑：**改了台词 / 加了界面文案、出现新字之后**。双击同目录的
`字体子集化.bat` 即可 —— 字体是 exe 同级的外部文件，不用重新打包。
跑完顺手再跑一次 `界面自检.bat` 确认对话框还正常。

原字会备份到 `.tmp\\font_orig_NotoSansSC-VF.ttf`（只备份一次，不会覆盖）。
"""

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
FONT = ROOT / "font" / "NotoSansSC-VF.ttf"
BACKUP = ROOT / ".tmp" / "font_orig_NotoSansSC-VF.ttf"

# 项目用字之外再兜底保留的码位区间：基本拉丁/拉丁补充、常用标点、货币、字母式符号、
# 箭头、圈号、几何图形、杂项符号、CJK 标点、兼容形式、全角形式。
# （待办内容和昵称是用户自由输入的，别只按现有文案裁）
EXTRA_RANGES = [
    (0x0020, 0x00FF), (0x2000, 0x206F), (0x20A0, 0x20BF), (0x2100, 0x214F),
    (0x2190, 0x21FF), (0x2460, 0x24FF), (0x25A0, 0x25FF), (0x2600, 0x26FF),
    (0x3000, 0x303F), (0xFE30, 0xFE4F), (0xFF00, 0xFFEF),
]


def gb2312_chars():
    """GB2312 能编码的全部汉字与全角符号（6763 个汉字）。"""
    out = set()
    for lo, hi in ((0x4E00, 0xA000), (0x3000, 0x3100)):
        for cp in range(lo, hi):
            ch = chr(cp)
            try:
                ch.encode("gb2312")
            except UnicodeEncodeError:
                continue
            out.add(ch)
    return out


def project_chars():
    """项目会显示的字：台词 json 的全部字符串 + src 下所有源码里的非 ASCII 字符。"""
    out = set()

    def walk(o):
        if isinstance(o, str):
            out.update(o)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    data = ROOT / "data" / "dialogue.json"
    if data.exists():
        walk(json.loads(data.read_text(encoding="utf-8")))
    for f in SRC.glob("*.py"):
        out.update(c for c in f.read_text(encoding="utf-8") if ord(c) > 0x7F)
    return out


def main():
    if not FONT.exists():
        print(f"找不到字体：{FONT}")
        return 1

    before = FONT.stat().st_size
    chars = project_chars()
    mine = len(chars)
    chars |= gb2312_chars()
    for lo, hi in EXTRA_RANGES:
        chars.update(chr(c) for c in range(lo, hi + 1))
    chars -= {"\n", "\r", "\t", "\0"}
    text = "".join(sorted(chars))
    print(f"项目直接用到 {mine} 个字，连兜底合计 {len(text)} 个码位")

    from fontTools import subset

    opts = subset.Options()
    opts.layout_features = ["*"]      # 连字/定位特性全留，排版行为不变
    opts.name_IDs = ["*"]             # 家族名等 name 表全留（Qt 靠它认字体）
    opts.name_legacy = True
    opts.notdef_outline = True
    opts.recalc_bounds = True
    opts.recalc_timestamp = False     # 输出可复现

    font = subset.load_font(str(FONT), opts)
    subsetter = subset.Subsetter(options=opts)
    subsetter.populate(text=text)
    subsetter.subset(font)

    tmp = BACKUP.parent / "font_subset_new.ttf"   # 先写到 .tmp，别往 font\ 里扔中间产物
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    subset.save_font(font, str(tmp), opts)

    # 1. 可变字重轴必须还在，否则 DemiBold(600) 会退化成 Regular
    from fontTools.ttLib import TTFont

    chk = TTFont(str(tmp), lazy=True)
    assert "fvar" in chk, "可变字重轴（fvar）丢了，DemiBold 会失效"
    axes = [(a.axisTag, a.minValue, a.defaultValue, a.maxValue)
            for a in chk["fvar"].axes]
    assert "glyf" in chk and "gvar" in chk, "轮廓表没了"
    chk.close()  # lazy=True 会一直占着文件句柄，不关掉后面就替换不了

    # 2. Qt 得能装上，且关键字符都有字形（含用户自由输入会用到的数字/标点）
    #    ⚠️ Qt 一旦 addApplicationFont 过某个文件，那个文件在本进程内就被锁住替换不了，
    #    所以验的是 .tmp 里的副本，不是待替换的那一份。
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QFont, QFontDatabase, QRawFont
    from PySide6.QtWidgets import QApplication

    probe_copy = BACKUP.parent / "font_check.ttf"
    shutil.copy2(tmp, probe_copy)
    app = QApplication([])
    fid = QFontDatabase.addApplicationFont(str(probe_copy))
    assert fid >= 0, "Qt 打不开裁完的字体"
    families = QFontDatabase.applicationFontFamilies(fid)
    assert families, "裁完的字体没有家族名"
    raw = QRawFont.fromFont(QFont(families[0], 10))
    probe = "芙兰朵露休息番茄钟倒计时待办主人0123456789ABCabc，。！？：；【】（）×·—…/-"
    missing = [c for c in probe if not raw.supportsCharacter(ord(c))]
    assert not missing, f"裁完缺字：{missing}"
    del app

    # 3. 两项检查都过了才动真格的字体文件（原字先备份一份）
    #    ⚠️ 这里只能「覆盖写」，不能用 os.replace / Move-Item：font\ 下的文件带
    #    Low 完整性 + No-Write-Up 标签，重命名替换会被拒（WinError 5 拒绝访问），
    #    但直接往文件里写内容是允许的。
    if not BACKUP.exists():
        shutil.copy2(FONT, BACKUP)
        print(f"原字已备份到 {BACKUP.relative_to(ROOT)}")
    FONT.write_bytes(tmp.read_bytes())
    for p in (tmp, probe_copy):
        try:
            p.unlink()
        except OSError:
            pass  # Qt 还锁着 probe_copy 时删不掉，下次跑会自动覆盖

    after = FONT.stat().st_size
    print(f"字体家族：{families[0]}    字重轴：{axes}")
    print(f"{before/1048576:.2f} MB → {after/1048576:.2f} MB"
          f"（省 {(before-after)/1048576:.2f} MB，{after/before*100:.1f}%）")
    print("OK: 字体子集化完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
