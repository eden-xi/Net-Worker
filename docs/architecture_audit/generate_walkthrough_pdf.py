"""Turn a walkthrough Markdown file into a PDF saved in docs/architecture_audit/.

Usage (from the repo root):
    python docs/architecture_audit/generate_walkthrough_pdf.py docs/login_wall_walkthrough.md

Handles the Markdown our walkthroughs use: #/##/### headings, paragraphs, - and 1. lists,
| tables |, ``` code blocks ```, ![images](path), > quotes, **bold**, `code` and [links](url).
Requires: fpdf2.
"""
import re
import sys
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace
from PIL import Image

OUT_DIR = Path(__file__).resolve().parent
SWAPS = {"—": "-", "–": "-", "→": "->", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "..."}


def clean(text):
    for a, b in SWAPS.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


def inline(text):
    """Strip `code` ticks and [link](targets). Return (text, use_markdown).
    fpdf2 reads __ and -- as styling, so markdown is switched off for those lines."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)        # [label](url) -> label
    text = clean(text.replace("`", ""))
    return text, "**" in text and "__" not in text and "--" not in text


class Walkthrough(FPDF):
    def __init__(self, title):
        super().__init__(format="A4")
        self.doc_title = title
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(True, 16)

    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8); self.set_text_color(120)
            self.cell(0, 6, self.doc_title, align="R", new_x="LMARGIN", new_y="NEXT"); self.set_text_color(0)

    def footer(self):
        self.set_y(-12); self.set_font("Helvetica", "", 8); self.set_text_color(120)
        self.cell(0, 6, f"Page {self.page_no()}/{{nb}}", align="C")

    def heading(self, level, text):
        size = {1: 20, 2: 14, 3: 11.5}[level]
        self.ln(4 if level > 1 else 0)
        self.set_font("Helvetica", "B", size); self.set_text_color(30, 60, 110)
        self.multi_cell(0, size * 0.5, inline(text)[0], new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0); self.ln(1.5)

    def paragraph(self, text, indent=0, bullet=""):
        body, md = inline(text)
        self.set_font("Helvetica", "", 10)
        if bullet:
            self.set_x(self.l_margin + indent); self.cell(6, 5.2, bullet)
        self.multi_cell(0, 5.2, body, markdown=md, new_x="LMARGIN", new_y="NEXT")
        self.ln(0.6 if bullet else 2)

    def table_block(self, rows):
        cells = [[inline(c.strip())[0].replace("**", "") for c in r.strip().strip("|").split("|")] for r in rows]
        cells = [r for r in cells if not all(set(c) <= set("-: ") for c in r)]    # drop the |---| line
        widest = [min(max(len(r[i]) for r in cells) + 4, 70) for i in range(len(cells[0]))]
        widest = [max(width, 9) for width in widest]                       # no column too thin to print
        widths = [w / sum(widest) * self.epw for w in widest]
        self.set_font("Helvetica", "", 8.5)
        with self.table(col_widths=widths, text_align="LEFT", line_height=4.6, padding=1.4,
                        headings_style=FontFace(emphasis="BOLD", fill_color=(220, 228, 242))) as table:
            for row in cells:
                line = table.row()
                for cell in row:
                    line.cell(cell)
        self.ln(3)

    def code_block(self, lines):
        self.set_font("Courier", "", 8.5); self.set_fill_color(242, 242, 246)
        self.multi_cell(0, 4.6, clean("\n".join(lines)), fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def picture(self, path):
        if not path.exists():
            return self.paragraph(f"[missing image: {path.name}]")
        with Image.open(path) as picture_file:                          # keep the real shape
            pixel_width, pixel_height = picture_file.size
        width = self.epw
        height = width * pixel_height / pixel_width
        if height > 200:                                               # very tall images: shrink to fit a page
            width, height = width * 200 / height, 200
        if self.get_y() + height > self.page_break_trigger:
            self.add_page()
        self.image(str(path), x=self.l_margin + (self.epw - width) / 2, w=width); self.ln(3)

    def quote(self, text):
        body, md = inline(text)
        self.set_font("Helvetica", "I", 9.5); self.set_fill_color(245, 240, 252)
        self.multi_cell(0, 5, body, markdown=md, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)


def render(md_path):
    lines = md_path.read_text(encoding="utf-8").splitlines()
    title = next((l[2:] for l in lines if l.startswith("# ")), md_path.stem)
    pdf = Walkthrough(clean(title)); pdf.add_page()
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            end = next(j for j in range(i + 1, len(lines)) if lines[j].startswith("```"))
            pdf.code_block(lines[i + 1:end]); i = end + 1; continue
        if line.startswith("|"):
            end = i
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            pdf.table_block(lines[i:end]); i = end; continue
        heading = re.match(r"^(#{1,3}) (.*)", line)
        image = re.match(r"^!\[[^\]]*\]\(([^)]+)\)", line)
        item = re.match(r"^(\s*)(- |\d+\. )(.*)", line)
        if heading:
            pdf.heading(len(heading.group(1)), heading.group(2))
        elif image:
            pdf.picture((md_path.parent / image.group(1)).resolve())
        elif line.startswith("> "):
            pdf.quote(line[2:])
        elif line.strip() == "---":
            pdf.ln(2)
        elif item:
            indent = len(item.group(1)) * 2
            pdf.paragraph(item.group(3), indent=indent, bullet="-" if item.group(2) == "- " else item.group(2).strip())
        elif line.strip():
            pdf.paragraph(line)
        i += 1

    out = OUT_DIR / f"{md_path.stem}.pdf"
    pdf.output(str(out))
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python docs/architecture_audit/generate_walkthrough_pdf.py <walkthrough.md>")
    print(f"wrote {render(Path(sys.argv[1]).resolve())}")
