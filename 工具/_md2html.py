# 把 README.md 转成带样式的 HTML（给 Edge 无头打印成 PDF 用）
# 用法: python _md2html.py README.md _readme_print.html
import html
import re
import sys
from pathlib import Path

# ---------- 行内格式 ----------
def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", s)
    s = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    # 链接与自动链接
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"&lt;(https?://[^&]+?)&gt;", r'<a href="\1">\1</a>', s)
    return s


def convert(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    para: list[str] = []
    in_code = False
    code: list[str] = []
    list_stack: list[str] = []  # "ul" / "ol"
    table: list[list[str]] = []
    quote: list[str] = []

    def flush_para():
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    def close_lists():
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    def flush_table():
        if not table:
            return
        head, *body = table
        out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>")
        for row in body:
            out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
        out.append("</tbody></table>")
        table.clear()

    def flush_quote():
        if quote:
            out.append("<blockquote>" + "".join(f"<p>{inline(q)}</p>" for q in quote) + "</blockquote>")
            quote.clear()

    def flush_all():
        flush_para()
        flush_table()
        flush_quote()
        close_lists()

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()

        if in_code:
            if line.startswith("```"):
                out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
                code.clear()
                in_code = False
            else:
                code.append(line)
            i += 1
            continue

        if line.startswith("```"):
            flush_all()
            in_code = True
            i += 1
            continue

        # 表格
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            flush_para(); flush_quote(); close_lists()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            table.extend([rows[0]] + rows[2:])
            flush_table()
            continue

        if not line.strip():
            flush_para(); flush_quote(); close_lists()
            i += 1
            continue

        if line.startswith("> "):
            flush_para(); flush_table(); close_lists()
            quote.append(line[2:].strip())
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_all()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        if re.match(r"^[-*]\s+", line):
            flush_para(); flush_table(); flush_quote()
            if not list_stack or list_stack[-1] != "ul":
                close_lists(); out.append("<ul>"); list_stack.append("ul")
            out.append("<li>" + inline(re.sub(r"^[-*]\s+", "", line)) + "</li>")
            i += 1
            continue

        m = re.match(r"^\d+\.\s+(.*)$", line)
        if m:
            flush_para(); flush_table(); flush_quote()
            if not list_stack or list_stack[-1] != "ol":
                close_lists(); out.append("<ol>"); list_stack.append("ol")
            out.append("<li>" + inline(m.group(1)) + "</li>")
            i += 1
            continue

        if line.strip() == "---":
            flush_all()
            out.append("<hr>")
            i += 1
            continue

        if line.startswith("   ") or line.startswith("\t"):
            # 列表项的续行
            if out and out[-1].startswith("<li>"):
                out[-1] = out[-1][:-5] + " " + inline(line.strip()) + "</li>"
                i += 1
                continue

        flush_table(); flush_quote()
        para.append(line.strip())
        i += 1

    flush_all()
    return "\n".join(out)


def page(body: str, title: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
  @page {{ size: A4; margin: 16mm 14mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Microsoft YaHei", "Noto Sans SC", "SimHei", sans-serif;
         font-size: 10.5pt; line-height: 1.75; color: #1c1c1c; margin: 0; }}
  h1 {{ font-size: 20pt; border-bottom: 3px solid #c0392b; padding-bottom: 6px; }}
  h2 {{ font-size: 15pt; margin-top: 1.4em; border-bottom: 1px solid #ddd; padding-bottom: 4px; color: #a8322a; }}
  h3 {{ font-size: 12.5pt; margin-top: 1.2em; color: #333; }}
  h4 {{ font-size: 11pt; margin-top: 1em; }}
  h1, h2, h3, h4 {{ page-break-after: avoid; break-after: avoid; }}
  p, li {{ orphans: 3; widows: 3; }}
  table {{ border-collapse: collapse; width: 100%; margin: 0.6em 0; font-size: 9.5pt; page-break-inside: auto; }}
  th, td {{ border: 1px solid #bbb; padding: 4px 7px; text-align: left; vertical-align: top; }}
  th {{ background: #f2f2f2; }}
  tr {{ page-break-inside: avoid; break-inside: avoid; }}
  code {{ font-family: Consolas, monospace; background: #f5f5f5; padding: 1px 4px; border-radius: 3px; font-size: 9.5pt; }}
  pre {{ background: #f7f7f7; border: 1px solid #e0e0e0; border-left: 4px solid #c0392b;
        padding: 8px 10px; overflow-wrap: anywhere; white-space: pre-wrap; page-break-inside: avoid; }}
  pre code {{ background: none; padding: 0; }}
  blockquote {{ margin: 0.6em 0; padding: 6px 12px; background: #faf7e8; border-left: 4px solid #e2c65a; }}
  blockquote p {{ margin: 0.3em 0; }}
  hr {{ border: none; border-top: 1px dashed #ccc; margin: 1.2em 0; }}
  del {{ color: #888; }}
  a {{ color: #1a5fb4; word-break: break-all; }}
  ul, ol {{ padding-left: 1.4em; }}
</style></head><body>
{body}
</body></html>"""


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    md = src.read_text(encoding="utf-8")
    title = next((l for l in md.splitlines() if l.startswith("# ")), src.stem).lstrip("# ").strip()
    dst.write_text(page(convert(md), title), encoding="utf-8")
    print(f"wrote {dst} ({dst.stat().st_size} bytes)")
