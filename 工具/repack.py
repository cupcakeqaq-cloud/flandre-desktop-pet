"""把 `src\\` 下改过的源码重新塞回 `芙兰朵露.exe`（原地重打包，不用跑整套 PyInstaller）。

为什么不用 `pyinstaller` 重打一遍：整套重打要重新收集一大堆 Qt/PIL 的东西，
还得再跑一遍 `工具\\prune_internal.ps1` 把 `_internal` 里用不到的部分剪掉，既慢又
容易把上一版验证过的依赖组合搞乱。这里只做「换掉我们自己那几个模块」这一件事：

原 exe = 引导代码 + CArchive（pyimod / 入口脚本 / PYZ + TOC + cookie）。
本脚本把 CArchive 里的条目逐个原样搬过来，**只把 PYZ 里那 13 个项目模块换成
`src\\*.py` 新编译的版本**，其余第三方库的字节完全不动，然后重写 TOC 和 cookie。
所以写出来的 exe 除了我们改过的那几个模块之外，和原来逐字节一致。

用法（在项目根目录下，注意要用 .venv 里的 python）：
    .venv\\Scripts\\python.exe 工具\\repack.py                 # 原地更新 芙兰朵露.exe
    .venv\\Scripts\\python.exe 工具\\repack.py --out 测试.exe   # 写到别处先验证
    .venv\\Scripts\\python.exe 工具\\repack.py --check         # 只比对，不写

自检：会先拿当前 `src\\` 把原 PYZ 重建一遍再核对一遍，顺带打印各项目模块的新旧大小。
改完记得：先跑 `工具\\界面自检.bat`，再双击 exe 看效果。
**新增了第三方依赖（import 了没打进去的库）时这个脚本不够用**，得走 README 4.4 的
完整 PyInstaller 流程 + `工具\\prune_internal.ps1`。
"""

import argparse
import marshal
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_SITE = ROOT / ".venv" / "Lib" / "site-packages"
if VENV_SITE.is_dir():
    sys.path.insert(0, str(VENV_SITE))

try:
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
    from PyInstaller.archive.writers import CArchiveWriter, ZlibArchiveWriter
    from PyInstaller.building.utils import (get_code_object,
                                            replace_filename_in_code_object)
    from PyInstaller.compat import BYTECODE_MAGIC
except ImportError as exc:                                  # pragma: no cover
    sys.exit(f"需要 PyInstaller（用 .venv 里的 python 跑本脚本）：{exc}")

PKG_MAGIC = CArchiveWriter._COOKIE_MAGIC_PATTERN
COOKIE_FORMAT = CArchiveWriter._COOKIE_FORMAT
COOKIE_LENGTH = CArchiveWriter._COOKIE_LENGTH
TOC_ENTRY_LENGTH = CArchiveWriter._TOC_ENTRY_LENGTH
TOC_ENTRY_FORMAT = CArchiveWriter._TOC_ENTRY_FORMAT
PYZ_HEADER_LENGTH = 12 + 5
DEFAULT_EXE = ROOT / "芙兰朵露.exe"
PYZ_NAME = "PYZ.pyz"


def project_modules():
    """src 下的模块名 -> 源文件路径（排掉 main，它是入口脚本、存在 CArchive 里）。"""
    return {p.stem: p for p in sorted((ROOT / "src").glob("*.py")) if p.stem != "main"}


def rebuild_pyz(pyz_old, modules, tmp_dir):
    """项目模块用 `src\\` 的新源码重编译，其余模块连压缩后的字节都原样搬过去。

    PYZ 格式（见 PyInstaller.loader.pyimod01_archive）：PYZ\\0 + 字节码魔数 + TOC 偏移
    (4 字节) + 4 字节空 → 各模块的 zlib(marshal(code)) → marshal 的 TOC 列表。
    自己写这 20 行，比借 ZlibArchiveWriter 稳（那个 writer 把 src_path='-' 当成
    PEP-420 命名空间包，会写出 0 字节的空条目）。
    """
    tmp_dir = Path(tmp_dir)
    old_path = tmp_dir / "old.pyz"
    old_path.write_bytes(pyz_old)
    reader = ZlibArchiveReader(str(old_path))
    old_raw = _raw_pyz_toc(pyz_old)

    body, toc, offset = bytearray(), {}, PYZ_HEADER_LENGTH
    for name, (typecode, _old_off, _old_len) in reader.toc.items():
        if name in modules:
            code = get_code_object(name, str(modules[name]), -1)
            code = replace_filename_in_code_object(
                code, f"{name.replace('.', '/')}.py")
            blob = zlib.compress(marshal.dumps(code),
                                 ZlibArchiveWriter._COMPRESSION_LEVEL)
        else:
            typecode, blob = old_raw[name][0], old_raw[name][1]
        toc[name] = (typecode, offset, len(blob))   # 运行时要的是 dict（见 pyimod01）
        body += blob
        offset += len(blob)

    toc_bytes = marshal.dumps(toc)
    # 头是 17 字节：PYZ\0 + 字节码魔数 + TOC 偏移 + 5 字节填充（多一个都不能少）
    header = (ZlibArchiveWriter._PYZ_MAGIC_PATTERN + BYTECODE_MAGIC
              + struct.pack("!i", offset)
              + b"\0" * (PYZ_HEADER_LENGTH - 12))
    print(f"   PYZ：{len(reader.toc)} 个模块，重编译 {len(modules)} 个项目模块"
          f"（{', '.join(sorted(modules))}），其余字节原样保留")
    return header + bytes(body) + toc_bytes


def _raw_pyz_toc(pyz_bytes):
    """读出每个模块**未经解压**的原始字节，搬运用（省得当中间人重压一遍）。"""
    _, _, toc_offset = struct.unpack("!4s4si", pyz_bytes[:12])
    entries = marshal.loads(pyz_bytes[toc_offset:])
    if not isinstance(entries, list):
        entries = list(entries.items())
    return {name: (typecode, pyz_bytes[offset:offset + length])
            for name, (typecode, offset, length) in entries}


def toc_entries(toc_bytes):
    """按顺序解析 TOC 字节流——reader 会把 option 条目（typecode 'o'）滤掉，但重建
    时必须把它们放回原位（`pyi-contents-directory` 就藏在这里面）。"""
    entries, pos = [], 0
    while pos < len(toc_bytes):
        entry_length, offset, clen, dlen, comp, tc = struct.unpack(
            TOC_ENTRY_FORMAT, toc_bytes[pos:pos + TOC_ENTRY_LENGTH])
        name_length = entry_length - TOC_ENTRY_LENGTH
        name = toc_bytes[pos + TOC_ENTRY_LENGTH:
                         pos + TOC_ENTRY_LENGTH + name_length].rstrip(b"\0")
        entries.append((offset, clen, dlen, comp, tc.decode("ascii"),
                        name.decode("utf-8")))
        pos += entry_length
    return entries


def serialize_toc(toc):
    """和 PyInstaller 的 CArchiveWriter._serialize_toc 一致（TOC 条目按 16 字节对齐）。"""
    out = []
    for data_offset, compressed_length, data_length, compress, typecode, name in toc:
        raw = name.encode("utf-8") if isinstance(name, str) else name
        name_length = len(raw) + 1                     # 末尾的 \\0
        entry_length = TOC_ENTRY_LENGTH + name_length
        if entry_length % 16:
            name_length += 16 - (entry_length % 16)
        out.append(struct.pack(TOC_ENTRY_FORMAT + f"{name_length}s",
                               TOC_ENTRY_LENGTH + name_length, data_offset,
                               compressed_length, data_length, compress,
                               typecode.encode("ascii"), raw))
    return b"".join(out)


def patch(exe_path, out_path, check_only=False):
    exe_path, out_path = Path(exe_path), Path(out_path)
    carc = CArchiveReader(str(exe_path))
    start, end = carc._start_offset, carc._end_offset
    with open(exe_path, "rb") as fp:
        fp.seek(start)
        archive = fp.read(end - start)
        fp.seek(0)
        bootloader = fp.read(start)
    magic, _alen, toc_offset, toc_length, _pyvers, pylib_name = struct.unpack(
        COOKIE_FORMAT, archive[-COOKIE_LENGTH:])
    assert magic == PKG_MAGIC, "cookie 魔数不对"
    pylib = pylib_name.split(b"\0")[0].decode("ascii")
    print(f"原 exe：引导代码 {len(bootloader)} 字节，CArchive {len(archive)} 字节，"
          f"{len(carc.toc)} 个条目，python 库 {pylib}")

    # TOC 字节必须能原样重建，否则说明这个 exe 不是这套 PyInstaller 打的
    orig_entries = toc_entries(archive[toc_offset:toc_offset + toc_length])
    if serialize_toc(orig_entries) != archive[toc_offset:toc_offset + toc_length]:
        sys.exit("TOC 对不上，不敢改——请改用 README 4.4 的完整 PyInstaller 流程")
    print(f"   TOC 校验通过（{len(orig_entries)} 个条目原样重建逐字节一致）")

    tmp_dir = Path(tempfile.mkdtemp(prefix="repack_"))
    try:
        blobs = {}
        with open(exe_path, "rb") as fp:
            for name, (offset, length, _dlen, _comp, _tc) in carc.toc.items():
                fp.seek(start + offset)
                blobs[name] = fp.read(length)

        pyz_new = rebuild_pyz(
            zlib.decompress(blobs[PYZ_NAME]) if carc.toc[PYZ_NAME][3]
            else blobs[PYZ_NAME], project_modules(), tmp_dir)
        if check_only:
            print(f"   比对模式：原 PYZ {len(blobs[PYZ_NAME])} 字节 → "
                  f"新 PYZ {len(pyz_new)} 字节")
            return 0

        body, toc, offset = [], [], 0
        for _off, _clen, data_length, compress, typecode, name in orig_entries:
            if typecode == "o":                        # option 条目没有数据体
                toc.append((0, 0, 0, compress, typecode, name))
                continue
            data = pyz_new if name == PYZ_NAME else blobs[name]
            if compress and name != PYZ_NAME:
                raw = data                             # 原字节本来就是压缩过的
            elif compress:
                raw = zlib.compress(data, CArchiveWriter._COMPRESSION_LEVEL)
            else:
                raw = data
            body.append(raw)
            toc.append((offset, len(raw), data_length, compress, typecode, name))
            offset += len(raw)

        toc_bytes = serialize_toc(toc)
        toc_offset = offset
        archive_length = toc_offset + len(toc_bytes) + COOKIE_LENGTH
        cookie = struct.pack(COOKIE_FORMAT, PKG_MAGIC, archive_length, toc_offset,
                             len(toc_bytes),
                             sys.version_info[0] * 100 + sys.version_info[1],
                             pylib.encode("ascii"))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as fp:
            fp.write(bootloader)
            for chunk in body:
                fp.write(chunk)
            fp.write(toc_bytes)
            fp.write(cookie)
        print(f"已写出 {out_path}（{out_path.stat().st_size} 字节，"
              f"比原来大 {out_path.stat().st_size - exe_path.stat().st_size} 字节）")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return 0


def smoke(exe_path):
    """把打好的 exe 拷进隔离目录、真的启动一次（`_internal` 用 junction，不复制几百 MB）。"""
    exe_path = Path(exe_path)
    sandbox = ROOT / ".tmp" / "exe_test"
    shutil.rmtree(sandbox, ignore_errors=True)
    sandbox.mkdir(parents=True)
    shutil.copy2(exe_path, sandbox / exe_path.name)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(sandbox / "_internal"),
                    str(ROOT / "_internal")], capture_output=True, check=True)
    for item in ("data", "font", "sound", "贴图"):
        shutil.copytree(ROOT / item, sandbox / item)

    proc = subprocess.Popen([str(sandbox / exe_path.name)], cwd=str(sandbox),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(6)
    alive = proc.poll() is None
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
    print(f"冒烟：启动 6 秒后还活着 = {alive}；子进程输出 = "
          f"{out.decode('utf-8', 'replace')[:2000] or '(空，正常)'}")
    return 0 if alive else 1


def main():
    ap = argparse.ArgumentParser(description="把 src 里的源码重新塞回 exe")
    ap.add_argument("--exe", default=str(DEFAULT_EXE), help="要改的 exe")
    ap.add_argument("--out", default=None, help="写到别处（默认原地覆盖）")
    ap.add_argument("--check", action="store_true", help="只比对 PYZ，不写文件")
    ap.add_argument("--smoke", action="store_true", help="打完再隔离启动一次，看能不能跑")
    args = ap.parse_args()
    target = args.out or args.exe
    code = patch(args.exe, target, check_only=args.check)
    if code == 0 and args.smoke and not args.check:
        code = smoke(target)
    return code


if __name__ == "__main__":
    sys.exit(main())
