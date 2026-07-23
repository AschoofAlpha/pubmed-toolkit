"""Reusable analysis pipeline for downloader outputs."""

from __future__ import annotations

import csv
import glob
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

EXCEL_COLUMNS = {
    "PMID": "pmid",
    "标题": "title",
    "作者": "authors_str",
    "角色": "role",
    "期刊": "journal",
    "发表日期": "pub_date",
    "卷": "volume",
    "期": "issue",
    "页码": "pages",
    "DOI": "doi",
    "PMC ID": "pmc_id",
    "PDF状态": "pdf_status",
    "摘要": "abstract",
}

BUCKET_NAMES = {
    "A": "A 经典通路机制\n(signaling/泛素化/cell-death)",
    "B": "B 非编码 RNA / 表观遗传",
    "C": "C 纳米医学与递送",
    "D": "D 免疫治疗 / TME / cGAS-STING",
    "E": "E 临床研究 (cohort/RCT)",
    "F": "F 其他 (生信/文献为主)",
}

BUCKET_COLOR = {
    "A": "#1f77b4",
    "B": "#9467bd",
    "C": "#2ca02c",
    "D": "#d62728",
    "E": "#bcbd22",
    "F": "#7f7f7f",
}


def find_latest_excel(output_dir: str) -> str:
    files = glob.glob(os.path.join(output_dir, "papers_*.xlsx"))
    if not files:
        raise FileNotFoundError(f"No papers_*.xlsx found in {output_dir}")
    return max(files, key=os.path.getmtime)


def find_latest_json(output_dir: str) -> str | None:
    files = glob.glob(os.path.join(output_dir, "papers_*.json"))
    return max(files, key=os.path.getmtime) if files else None


def read_papers_from_excel(excel_path: str) -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(v).strip() if v is not None else "" for v in rows[0]]
    papers = []
    for row in rows[1:]:
        rec = {}
        for idx, value in enumerate(row):
            header = headers[idx] if idx < len(headers) else ""
            key = EXCEL_COLUMNS.get(header)
            if key:
                rec[key] = "" if value is None else str(value)
        if rec.get("pmid"):
            papers.append(rec)
    wb.close()
    return papers


def load_papers_json(path: str | None) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def find_pdf(pdf_dir: str, pmid: str) -> str | None:
    cands = [
        path for path in glob.glob(os.path.join(pdf_dir, f"{pmid}_*.pdf"))
        if f"{os.sep}suspect{os.sep}" not in path
    ]
    return cands[0] if cands else None


def extract_full_text(path: str) -> str:
    try:
        import fitz  # type: ignore
    except ImportError:
        return "__ERROR__:PyMuPDF unavailable"

    try:
        doc = fitz.open(path)
        try:
            pages = [page.get_text("text") for page in doc]
        finally:
            doc.close()
        return "\n".join(pages)
    except Exception as e:
        return f"__ERROR__:{type(e).__name__}: {e}"


def split_by_section(full_text: str) -> dict[str, str]:
    if full_text.startswith("__ERROR__"):
        return {"_error": full_text}
    headings = [
        "abstract", "introduction", "background", "results", "methods",
        "materials and methods", "methodology", "discussion", "conclusion",
        "conclusions", "references", "acknowledgements", "acknowledgments",
    ]
    pattern = re.compile(
        r"(?im)^\s*(" + "|".join(re.escape(h) for h in headings) + r")\s*\.?\s*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(full_text))
    sections = {}
    for idx, match in enumerate(matches):
        name = match.group(1).strip().lower()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
        sections.setdefault(name, full_text[start:end].strip())
    return sections


def _first_paragraph(text: str, max_chars: int = 1500) -> str:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return paras[0][:max_chars] if paras else ""


def _last_paragraph(text: str, max_chars: int = 1500) -> str:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return paras[-1][:max_chars] if paras else ""


def build_corpus(papers: list[dict], output_dir: str, pdf_dir: str) -> str:
    corpus = []
    for paper in papers:
        pmid = str(paper.get("pmid", ""))
        rec = {
            "pmid": pmid,
            "title": paper.get("title", ""),
            "pub_date": paper.get("pub_date", ""),
            "journal": paper.get("journal", ""),
            "abstract": paper.get("abstract", ""),
            "pdf_path": find_pdf(pdf_dir, pmid),
            "pdf_status": "missing",
            "intro_last": "",
            "disc_first": "",
            "extraction_note": "",
        }
        if rec["pdf_path"]:
            full = extract_full_text(rec["pdf_path"])
            if full.startswith("__ERROR__"):
                rec["pdf_status"] = "error"
                rec["extraction_note"] = full
            else:
                rec["pdf_status"] = "ok"
                rec["pdf_chars"] = len(full)
                sections = split_by_section(full)
                intro = sections.get("introduction") or sections.get("background") or ""
                discussion = sections.get("discussion") or ""
                rec["intro_last"] = _last_paragraph(intro)
                rec["disc_first"] = _first_paragraph(discussion)
                rec["sections_found"] = list(sections.keys())
                if not intro and not discussion:
                    rec["extraction_note"] = "no Introduction/Discussion headers parsed; abstract-only"
        else:
            rec["extraction_note"] = "no PDF available; abstract-only"
        corpus.append(rec)

    out = os.path.join(output_dir, "_paper_corpus.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
    return out


def _date_iso(value: str) -> str:
    value = str(value or "").strip()
    match = re.search(r"(\d{4})", value)
    year = int(match.group(1)) if match else 1900
    month = 1
    day = 1
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    month_match = re.search(r"\b([A-Za-z]{3})[A-Za-z]*\b", value)
    if month_match:
        month = month_map.get(month_match.group(1).lower(), 1)
    nums = [int(n) for n in re.findall(r"\b\d{1,2}\b", value)]
    if nums:
        day = max(1, min(nums[-1], 31))
    return f"{year:04d}-{month:02d}-{day:02d}"


def _split_author_names(authors_str: str) -> list[str]:
    return [part.strip() for part in str(authors_str or "").split(",") if part.strip()]


def build_author_records(papers: list[dict], json_papers: list[dict], output_dir: str) -> str:
    detailed_by_pmid = {str(p.get("pmid", "")): p for p in json_papers if p.get("authors")}
    records = []
    for paper in papers:
        pmid = str(paper.get("pmid", ""))
        detailed = detailed_by_pmid.get(pmid, {})
        authors = detailed.get("authors") or [
            {"name": name, "equal_contrib": False, "is_corresponding": False}
            for name in _split_author_names(paper.get("authors_str", ""))
        ]
        parsed_authors = []
        for idx, author in enumerate(authors):
            name = author.get("name", "")
            if not name:
                continue
            parsed_authors.append({
                "name": name,
                "index": idx + 1,
                "is_first": idx == 0,
                "is_last": idx == len(authors) - 1,
                "equal_contrib": bool(author.get("equal_contrib")),
                "is_corresponding": bool(author.get("is_corresponding")),
                "affiliation": author.get("affiliation", ""),
            })
        records.append({
            "pmid": pmid,
            "title": paper.get("title", ""),
            "pubdate": _date_iso(paper.get("pub_date", "")),
            "authors": parsed_authors,
        })

    out = os.path.join(output_dir, "_authors_parsed.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    return out


def _author_role_label(author: dict) -> str:
    labels = []
    if author.get("is_first"):
        labels.append("F")
    if author.get("equal_contrib"):
        labels.append("cF")
    if author.get("is_last"):
        labels.append("L")
    if author.get("is_corresponding"):
        labels.append("C")
    if not labels:
        labels.append(f"#{author.get('index', '')}")
    return " / ".join(labels)


def write_author_matrix(author_records_path: str, output_dir: str) -> str:
    with open(author_records_path, encoding="utf-8") as f:
        records = json.load(f)
    records.sort(key=lambda r: r.get("pubdate", ""))

    authors = sorted({
        author["name"]
        for rec in records
        for author in rec.get("authors", [])
        if author.get("name")
    })
    columns = [f"{rec['pmid']} ({rec.get('pubdate', '')})" for rec in records]
    role_map = defaultdict(dict)
    # strict=True asserts the invariant that `columns` was built from `records`.
    for rec, col in zip(records, columns, strict=True):
        for author in rec.get("authors", []):
            role_map[author["name"]][col] = _author_role_label(author)

    out = os.path.join(output_dir, "_author_paper_matrix.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["author"] + columns)
        for author in authors:
            writer.writerow([author] + [role_map[author].get(col, "") for col in columns])
    return out


def render_gantt(
    author_records_path: str,
    output_dir: str,
    pi_name: str = "",
    exclude_names: set[str] | None = None,
) -> str | None:
    """
    Draw the activity timeline.

    `exclude_names` drops co-authors who would otherwise crowd the chart — a
    co-PI, a department head, a standing collaborator. It is a parameter rather
    than a constant because the previous version hardcoded the names of six real
    people from one specific lab, which then shipped in a public repository.
    Configure it per run via `advisor.exclude_names`; see
    profile.roles.default_gantt_exclude_names.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    with open(author_records_path, encoding="utf-8") as f:
        records = json.load(f)
    records.sort(key=lambda r: r.get("pubdate", ""))

    exclude = {pi_name, ""} | set(exclude_names or ())
    appearances = defaultdict(list)
    for rec in records:
        date = datetime.strptime(rec["pubdate"], "%Y-%m-%d")
        for author in rec.get("authors", []):
            name = author.get("name", "")
            if name in exclude:
                continue
            appearances[name].append({
                "date": date,
                "pmid": rec["pmid"],
                "first": bool(author.get("is_first")),
                "cofirst": bool(author.get("equal_contrib")),
            })
    if not appearances:
        return None

    students = sorted(appearances.keys(), key=lambda n: (appearances[n][0]["date"], -len(appearances[n])))
    fig, ax = plt.subplots(figsize=(13, max(5, 0.5 * len(students))))
    colors = {"first": "#d62728", "cofirst": "#ff7f0e", "mid": "#1f77b4"}
    for idx, student in enumerate(students):
        apps = sorted(appearances[student], key=lambda item: item["date"])
        d0, d1 = apps[0]["date"], apps[-1]["date"]
        if d0 != d1:
            ax.hlines(idx, d0, d1, color="#bbbbbb", lw=2, zorder=1)
        for app in apps:
            if app["first"]:
                color, marker, size = colors["first"], "*", 240
            elif app["cofirst"]:
                color, marker, size = colors["cofirst"], "D", 90
            else:
                color, marker, size = colors["mid"], "o", 60
            ax.scatter(app["date"], idx, color=color, marker=marker, s=size, zorder=3, edgecolor="white", linewidth=0.6)

    ax.set_yticks(range(len(students)))
    ax.set_yticklabels([f"{s} (n={len(appearances[s])})" for s in students])
    ax.invert_yaxis()
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.grid(True, axis="x", alpha=0.25, ls="--")
    ax.set_xlabel("Publication date")
    ax.set_title(f"{pi_name or 'PI'} lab — student activity span")
    ax.legend(handles=[
        Line2D([0], [0], marker="*", color="w", markerfacecolor=colors["first"], markersize=14, label="first author"),
        Line2D([0], [0], marker="D", color="w", markerfacecolor=colors["cofirst"], markersize=9, label="co-first"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=colors["mid"], markersize=8, label="middle / other"),
        Line2D([0], [0], color="#bbbbbb", lw=2, label="active span"),
    ], loc="lower right", framealpha=0.95)
    plt.tight_layout()
    out = os.path.join(output_dir, "student_activity_gantt.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    return out


def _load_topic_records(output_dir: str) -> list[dict]:
    json_path = os.path.join(output_dir, "_topic_extraction.json")
    csv_path = os.path.join(output_dir, "_topic_extraction.csv")
    if os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as f:
            return json.load(f)
    if os.path.exists(csv_path):
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    return []


def render_topic_charts(output_dir: str) -> list[str]:
    recs = _load_topic_records(output_dir)
    if not recs:
        return []

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans SC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    prim = Counter(r.get("primary_bucket", "") for r in recs)
    labels, sizes, colors = [], [], []
    for bucket in ["A", "B", "C", "D", "E", "F"]:
        if prim[bucket] > 0:
            labels.append(f"{BUCKET_NAMES[bucket]}\n({prim[bucket]} 篇)")
            sizes.append(prim[bucket])
            colors.append(BUCKET_COLOR[bucket])

    outputs = []
    if sizes:
        fig, ax = plt.subplots(figsize=(9, 7))
        _, _, autotexts = ax.pie(
            sizes, labels=labels, colors=colors, autopct="%1.0f%%",
            startangle=90, pctdistance=0.78,
            wedgeprops={"edgecolor": "white", "linewidth": 2},
            textprops={"fontsize": 10},
        )
        for text in autotexts:
            text.set_color("white")
            text.set_fontweight("bold")
        ax.set_title("主要研究主题分布\n（每篇按 primary bucket 计 1 票）", fontsize=13, pad=20)
        plt.tight_layout()
        out = os.path.join(output_dir, "topic_pie.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        plt.close()
        outputs.append(out)

    years = sorted({int(r["year"]) for r in recs if str(r.get("year", "")).isdigit()})
    if years:
        buckets = ["A", "B", "C", "D", "E", "F"]
        mat = np.zeros((len(buckets), len(years)), dtype=int)
        for rec in recs:
            year_text = str(rec.get("year", ""))
            if not year_text.isdigit():
                continue
            yi = years.index(int(year_text))
            for bucket in [rec.get("primary_bucket", ""), rec.get("secondary_bucket", "")]:
                if bucket in buckets:
                    mat[buckets.index(bucket), yi] += 1
        fig, ax = plt.subplots(figsize=(8, 5))
        im = ax.imshow(mat, cmap="YlOrRd", aspect="auto", vmin=0, vmax=max(1, int(mat.max())))
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels(years)
        ax.set_yticks(range(len(buckets)))
        ax.set_yticklabels([BUCKET_NAMES[b].split("\n")[0] for b in buckets])
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                value = mat[i, j]
                color = "white" if value >= max(1, int(mat.max())) * 0.6 else "black"
                ax.text(j, i, str(value), ha="center", va="center", color=color, fontsize=12, fontweight="bold")
        cbar = plt.colorbar(im, ax=ax, fraction=0.04, pad=0.04)
        cbar.set_label("该年涉及该主题的论文数（含 secondary）")
        ax.set_title("主题 × 年份热图", fontsize=12)
        ax.set_xlabel("Publication year")
        plt.tight_layout()
        out = os.path.join(output_dir, "topic_year_heatmap.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        plt.close()
        outputs.append(out)

    return outputs


def run_analysis(
    output_dir: str = "pubmed_results",
    input_excel: str | None = None,
    pdf_dir: str | None = None,
    papers_json: str | None = None,
    pi_name: str = "",
    exclude_names: set[str] | None = None,
) -> dict[str, Any]:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    excel_path = input_excel or find_latest_excel(output_dir)
    pdf_dir = pdf_dir or os.path.join(output_dir, "pdfs")
    json_path = papers_json or find_latest_json(output_dir)

    papers = read_papers_from_excel(excel_path)
    detailed_papers = load_papers_json(json_path)
    results: dict[str, Any] = {
        "excel": excel_path,
        "papers_json": json_path,
        "papers": len(papers),
    }

    results["paper_corpus"] = build_corpus(papers, output_dir, pdf_dir)
    author_records = build_author_records(papers, detailed_papers, output_dir)
    results["authors_parsed"] = author_records
    results["author_matrix"] = write_author_matrix(author_records, output_dir)
    results["gantt"] = render_gantt(author_records, output_dir, pi_name, exclude_names)
    results["topic_charts"] = render_topic_charts(output_dir)
    if not results["topic_charts"]:
        results["topic_note"] = "No _topic_extraction.json/csv found; topic charts skipped."
    return results
