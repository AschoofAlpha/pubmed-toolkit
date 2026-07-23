#!/usr/bin/env python3
"""
Command-line entry point.

Subcommands
-----------
  profile      What the publication record says about being this PI's student
  fetch        Search PubMed, filter by author identity, download OA PDFs
  download     Retry PDF downloads from a previously exported papers_*.json
  analyze      Authorship matrix, activity gantt and topic charts
  verify       Check a bibliography against CrossRef and PubMed
  clean-cache  Drop stale failure records from the SQLite cache

Run without a subcommand to get `fetch` (kept for backwards compatibility).
"""

import argparse
import logging
import os
import sys
from datetime import datetime

from pubmed_toolkit.config import DEFAULT_CONFIG, load_config


def setup_logging(output_dir: str, level: str = "INFO"):
    """配置日志：同时输出到控制台和文件"""
    os.makedirs(output_dir, exist_ok=True)
    log_file = os.path.join(output_dir, f"download_{datetime.now():%Y%m%d_%H%M%S}.log")

    root = logging.getLogger("pubmed_toolkit")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    # 控制台
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    root.addHandler(console)

    # 文件（DEBUG 级别，记录所有细节）
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    ))
    root.addHandler(file_handler)

    return log_file


def parse_fetch_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run.py [fetch]",
        description="PubMed 论文检索与 PDF 下载（默认子命令；可省略 'fetch'）",
    )
    parser.add_argument("--config", help="JSON 配置文件路径（默认自动读取 config.json）")
    parser.add_argument("--author", dest="author_name", help="目标作者名")
    parser.add_argument("--affiliation", help="目标机构名")
    parser.add_argument("--years-back", type=int, help="向前检索年数")
    parser.add_argument("--email", help="Unpaywall 邮箱")
    parser.add_argument("--api-key", help="PubMed API key")
    parser.add_argument("--output-dir", help="输出目录")
    parser.add_argument("--pdf-dir", help="PDF 输出目录")
    parser.add_argument("--cache-db", help="SQLite 缓存路径")
    parser.add_argument("--max-workers", type=int, help="论文级并发下载线程数")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="日志级别")
    parser.add_argument("--no-download", action="store_true", help="只检索与导出清单，不下载 PDF")
    return parser.parse_args(argv)


def parse_clean_cache_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run.py clean-cache",
        description="清理 SQLite 缓存里的过期失败记录（下载成功的记录不动）",
    )
    parser.add_argument("--config", help="JSON 配置文件路径（用于读取 cache_db）")
    parser.add_argument("--cache-db", help="SQLite 缓存路径（覆盖 config）")
    parser.add_argument("--output-dir", help="输出目录（用于推断默认 cache 路径）")
    parser.add_argument("--max-age-days", type=int, default=90,
                        help="清理 N 天之前的失败记录（默认 90）")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    return parser.parse_args(argv)


def parse_download_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run.py download",
        description="只跑 PDF 下载阶段：从已有 papers_*.json 读论文清单，跳过 PubMed efetch",
    )
    parser.add_argument("--config", help="JSON 配置文件路径（默认自动读取 config.json）")
    parser.add_argument("--input", help="papers_*.json 路径（默认取 output-dir 下最新一份）")
    parser.add_argument("--output-dir", help="输出目录（默认 pubmed_results）")
    parser.add_argument("--pdf-dir", help="PDF 输出目录（默认 output-dir/pdfs）")
    parser.add_argument("--cache-db", help="SQLite 缓存路径")
    parser.add_argument("--max-workers", type=int, help="论文级并发下载线程数")
    parser.add_argument("--email", help="Unpaywall 邮箱")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    return parser.parse_args(argv)


def parse_analyze_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run.py analyze",
        description="基于已有 papers_*.xlsx + pdfs/ 跑作者矩阵 / 甘特 / 主题图",
    )
    parser.add_argument("--config", help="JSON 配置文件路径（用于读取 author_name 作为 PI 名）")
    parser.add_argument("--output-dir", help="分析输出目录（默认与 fetch 相同：pubmed_results）")
    parser.add_argument("--input-excel", help="papers_*.xlsx 路径（默认取 output-dir 下最新一份）")
    parser.add_argument("--pdf-dir", help="PDF 目录（默认 output-dir/pdfs）")
    parser.add_argument("--papers-json", help="papers_*.json 路径（默认取 output-dir 下最新一份）")
    parser.add_argument("--pi-name", help="实验室 PI 名（用于甘特图标题与排除）")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    return parser.parse_args(argv)


def parse_profile_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run.py profile",
        description="从已有 papers_*.json 生成导师画像：发表记录反映出的「当这位 PI 的学生是什么样」",
        epilog="报告不打分、不排名，也没有可调的样本量下限——抑制阈值是规范的一部分，不作为参数暴露。",
    )
    parser.add_argument("--config", help="JSON 配置文件路径（提供 author_identity 与 advisor 配置）")
    parser.add_argument("--output-dir", help="报告输出目录（默认与 fetch 相同：pubmed_results）")
    parser.add_argument("--papers-json", help="papers_*.json 路径（默认取 output-dir 下最新一份）")
    parser.add_argument("--pi-name", help="目标 PI 名（默认取 config 的 author_name）")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    return parser.parse_args(argv)


def apply_cli_overrides(cfg: dict, args: argparse.Namespace) -> dict:
    output_overridden = args.output_dir is not None
    for key in ["author_name", "affiliation", "email", "output_dir", "pdf_dir", "cache_db", "max_workers", "log_level"]:
        value = getattr(args, key, None)
        if value is not None:
            cfg[key] = value
    if output_overridden and args.pdf_dir is None and cfg.get("pdf_dir") == DEFAULT_CONFIG["pdf_dir"]:
        cfg["pdf_dir"] = os.path.join(cfg["output_dir"], "pdfs")
    if output_overridden and args.cache_db is None and cfg.get("cache_db") == DEFAULT_CONFIG["cache_db"]:
        cfg["cache_db"] = os.path.join(cfg["output_dir"], "paper_cache.db")
    if args.years_back is not None:
        cfg["years_back"] = args.years_back
    if args.api_key is not None:
        cfg["api_key"] = args.api_key
    if args.no_download:
        cfg["download_pdfs"] = False
    return cfg


SUBCOMMANDS = {"fetch", "analyze", "profile", "download", "verify", "clean-cache"}


def _split_subcommand(argv: list[str] | None) -> tuple[str, list[str]]:
    """Pop a leading subcommand if present; default to 'fetch' for backward compat."""
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in SUBCOMMANDS:
        return argv[0], argv[1:]
    return "fetch", list(argv)


def main(argv: list[str] | None = None):
    cmd, rest = _split_subcommand(argv)
    if cmd == "analyze":
        return cmd_analyze(rest)
    if cmd == "profile":
        return cmd_profile(rest)
    if cmd == "download":
        return cmd_download(rest)
    if cmd == "clean-cache":
        return cmd_clean_cache(rest)
    if cmd == "verify":
        return cmd_verify(rest)
    return cmd_fetch(rest)


def cmd_clean_cache(argv: list[str]):
    args = parse_clean_cache_args(argv)
    cfg = load_config(args.config)
    output_dir = args.output_dir or cfg.get("output_dir", "pubmed_results")
    cache_db = args.cache_db or cfg.get("cache_db") or os.path.join(output_dir, "paper_cache.db")

    setup_logging(output_dir, args.log_level)
    logger = logging.getLogger("pubmed_toolkit.clean_cache")

    if not os.path.exists(cache_db):
        logger.error("缓存文件不存在: %s", cache_db)
        return 1

    from pubmed_toolkit.cache import PaperCache
    cache = PaperCache(cache_db)
    try:
        before = cache.stats()
        logger.info("清理前: total=%d | downloaded=%d | failed=%d",
                    before["total"], before["downloaded"], before["failed"])
        deleted = cache.cleanup_expired(args.max_age_days)
        after = cache.stats()
        logger.info("清理后: total=%d | downloaded=%d | failed=%d",
                    after["total"], after["downloaded"], after["failed"])
        logger.info("已删除 %d 条 (>%d 天的失败记录) — %s",
                    deleted, args.max_age_days, cache_db)
    finally:
        cache.close()
    return 0


def cmd_download(argv: list[str]):
    args = parse_download_args(argv)
    cfg = load_config(args.config)

    # 命令行覆盖
    for key in ("output_dir", "pdf_dir", "cache_db", "email"):
        value = getattr(args, key, None)
        if value is not None:
            cfg[key] = value
    if args.max_workers is not None:
        cfg["max_workers"] = args.max_workers

    output_dir = cfg["output_dir"]
    pdf_dir = cfg.get("pdf_dir") or os.path.join(output_dir, "pdfs")
    cache_db = cfg.get("cache_db") or os.path.join(output_dir, "paper_cache.db")

    log_file = setup_logging(output_dir, args.log_level)
    logger = logging.getLogger("pubmed_toolkit.download")

    # 定位输入 JSON
    json_path = args.input
    if not json_path:
        from pubmed_toolkit.analysis import find_latest_json
        json_path = find_latest_json(output_dir)
    if not json_path or not os.path.exists(json_path):
        logger.error("没找到 papers_*.json — 先跑 fetch，或用 --input 指定路径")
        return 1

    import json as _json
    with open(json_path, encoding="utf-8") as f:
        papers = _json.load(f)
    if not isinstance(papers, list) or not papers:
        logger.error("输入 JSON 不是论文列表或为空: %s", json_path)
        return 1

    logger.info("=" * 60)
    logger.info("仅下载阶段：跳过 PubMed efetch")
    logger.info("输入: %s (%d 篇)", json_path, len(papers))
    logger.info("PDF 目录: %s | 缓存: %s | 并发: %d 线程",
                pdf_dir, cache_db, cfg.get("max_workers", 4))
    logger.info("日志: %s", log_file)
    logger.info("=" * 60)

    from pubmed_toolkit.engine import DownloadEngine
    engine = DownloadEngine(
        email=cfg.get("email", ""),
        max_workers=cfg.get("max_workers", 4),
        proxy_list=cfg.get("proxy_list"),
        cache_db=cache_db,
    )
    try:
        engine.download_batch(papers, pdf_dir)
        logger.info("缓存统计: %s", engine.cache.stats())
    finally:
        engine.close()

    # 写新版 Excel / JSON / 校验报告（不覆盖输入）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    from pubmed_toolkit.export import save_to_csv, save_to_excel, save_to_json
    from pubmed_toolkit.reports import write_pdf_validation_report

    try:
        import openpyxl  # noqa: F401
        excel_path = os.path.join(output_dir, f"papers_{timestamp}.xlsx")
        save_to_excel(papers, excel_path)
        logger.info("Excel 清单: %s", excel_path)
    except ImportError:
        csv_path = os.path.join(output_dir, f"papers_{timestamp}.csv")
        save_to_csv(papers, csv_path)
        logger.warning(
            "openpyxl 不可用，已降级导出 CSV 而非 Excel: %s（执行 `pip install openpyxl` 可恢复）",
            csv_path,
        )

    out_json = os.path.join(output_dir, f"papers_{timestamp}.json")
    save_to_json(papers, out_json)
    logger.debug("Papers JSON: %s", out_json)

    report_path = os.path.join(output_dir, f"pdf_validation_report_{timestamp}.csv")
    write_pdf_validation_report(papers, report_path, pdf_dir=pdf_dir)
    logger.info("PDF 校验报告: %s", report_path)
    return 0


def cmd_analyze(argv: list[str]):
    args = parse_analyze_args(argv)
    cfg = load_config(args.config)
    output_dir = args.output_dir or cfg.get("output_dir", "pubmed_results")
    pdf_dir = args.pdf_dir or os.path.join(output_dir, "pdfs")
    pi_name = args.pi_name or cfg.get("author_name", "")

    setup_logging(output_dir, args.log_level)
    logger = logging.getLogger("pubmed_toolkit.analyze")

    from pubmed_toolkit.analysis import run_analysis

    logger.info("=" * 60)
    logger.info("分析层：作者矩阵 / 甘特 / 主题图")
    logger.info("output_dir=%s | pdf_dir=%s | PI=%s", output_dir, pdf_dir, pi_name or "(未指定)")
    logger.info("=" * 60)

    try:
        results = run_analysis(
            output_dir=output_dir,
            input_excel=args.input_excel,
            pdf_dir=pdf_dir,
            papers_json=args.papers_json,
            pi_name=pi_name,
        )
    except FileNotFoundError as e:
        logger.error("找不到输入：%s", e)
        return 1

    logger.info("Excel 输入: %s (%d 篇)", results["excel"], results["papers"])
    if results.get("papers_json"):
        logger.info("Authors JSON: %s", results["papers_json"])
    logger.info("语料: %s", results["paper_corpus"])
    logger.info("作者矩阵: %s", results["author_matrix"])
    if results.get("gantt"):
        logger.info("甘特图: %s", results["gantt"])
    if results.get("topic_charts"):
        for path in results["topic_charts"]:
            logger.info("主题图: %s", path)
    if results.get("topic_note"):
        logger.warning(results["topic_note"])
    return 0


def _profile_corpus(papers: list[dict], cfg: dict) -> dict:
    """
    Wrap a legacy papers_*.json list in the Section 4 corpus contract.

    That file records nothing about the search that produced it, so nothing is
    invented here: unknown fields stay unset and render as "?" in the provenance
    block rather than as a confident value.
    """
    identity = cfg.get("author_identity") or {}
    return {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        # cmd_fetch keeps only first/last/corresponding-author papers, so on this
        # corpus the PI's byline position is decided by that filter rather than by
        # the data. Section 7.7 suppresses the metric on the strength of this flag.
        "position_filtered": True,
        "query": {
            "years_back": cfg.get("years_back", "?"),
            # Truncation is unknowable from a legacy file: it records neither the
            # esearch hit count nor how many PMIDs came back, so gate G1 cannot run.
            "truncated": "unknown",
        },
        "identity": {
            "author_name": cfg.get("author_name", ""),
            "orcid": (identity.get("orcid") or "").strip(),
            "affiliation_keywords": list(identity.get("affiliation_keywords") or []),
            "email_domains": list(identity.get("email_domains") or []),
            # Spec P5: is_first_or_corresponding defaults this to True when the key
            # is absent from the identity dict it is handed, while DEFAULT_CONFIG
            # sets False. The default here must match the function, not the config.
            "require_affiliation_effective": bool(identity.get("require_affiliation", True)),
        },
        "counts": {},
        # cmd_fetch stamps every paper "待确认" when nothing passed verification and
        # it kept the whole result set. That stamp is the only surviving trace of
        # the condition gate G2 refuses on.
        "fallback_fired": bool(papers) and all(p.get("role") == "待确认" for p in papers),
        "papers": papers,
    }


def _render_timeline(papers: list[dict], output_dir: str, cfg: dict, logger: logging.Logger) -> str | None:
    """Draw the activity timeline with the existing renderer, or say why there is none."""
    from pubmed_toolkit.analysis import build_author_records, render_gantt
    from pubmed_toolkit.profile import default_gantt_exclude_names

    # `papers` goes in twice: build_author_records reads title and pub_date from
    # the first argument and the structured author list from the second, and here
    # both come from the same records.
    records_path = build_author_records(papers, papers, output_dir)
    try:
        pi_name = cfg.get("author_name", "")
        return render_gantt(
            records_path, output_dir, pi_name,
            exclude_names=default_gantt_exclude_names(pi_name, cfg.get("advisor")),
        )
    except ImportError:
        logger.warning(
            "matplotlib 不可用，活跃期甘特图已跳过，报告其余部分照常生成"
            "（执行 `pip install -e \".[analysis]\"` 可恢复）。"
        )
        return None


def _build_profile_report(json_path: str, cfg: dict, output_dir: str, logger: logging.Logger) -> dict | None:
    """Turn the input file into a report dict. None means the input is unusable."""
    from pubmed_toolkit.profile import (
        build_report,
        build_report_from_path,
        check_corpus_gates,
        check_source_path,
    )

    # The spreadsheet refusal is decided on the extension alone so the file is
    # never opened; build_report_from_path is the entry point that does that.
    if check_source_path(json_path):
        return build_report_from_path(json_path, cfg)

    import json as _json
    with open(json_path, encoding="utf-8") as f:
        data = _json.load(f)

    if isinstance(data, dict):
        corpus = data  # already written in the Section 4 corpus shape
    elif isinstance(data, list) and data:
        logger.warning(
            "papers_*.json 不记录检索式与命中数，provenance 的 query 块按当前 config 重建，"
            "截断门禁 G1 因此无法判定。"
        )
        corpus = _profile_corpus(data, cfg)
    else:
        logger.error("输入 JSON 既不是论文列表也不是语料对象，或者是空的: %s", json_path)
        return None

    # Gates first: a refused report must not leave behind a timeline PNG that
    # nothing references.
    gantt_path = None
    if check_corpus_gates(corpus) is None:
        gantt_path = _render_timeline(corpus["papers"], output_dir, cfg, logger)
    return build_report(corpus, cfg, gantt_path)


def cmd_profile(argv: list[str]):
    args = parse_profile_args(argv)
    cfg = load_config(args.config)
    output_dir = args.output_dir or cfg.get("output_dir", "pubmed_results")
    # Written back into cfg because the report reads the target name from there
    # when the corpus does not carry one.
    cfg["author_name"] = args.pi_name or cfg.get("author_name", "")

    setup_logging(output_dir, args.log_level)
    logger = logging.getLogger("pubmed_toolkit.profile")

    from pubmed_toolkit.analysis import find_latest_json
    from pubmed_toolkit.profile import write_report

    json_path = args.papers_json or find_latest_json(output_dir)
    if not json_path or not os.path.exists(json_path):
        logger.error("没找到 papers_*.json — 先跑 fetch，或用 --papers-json 指定路径")
        return 1

    logger.info("=" * 60)
    logger.info("导师画像：发表记录反映出的「当这位 PI 的学生是什么样」")
    logger.info("output_dir=%s | 输入=%s | PI=%s",
                output_dir, json_path, cfg["author_name"] or "(未指定)")
    logger.info("=" * 60)

    report = _build_profile_report(json_path, cfg, output_dir, logger)
    if report is None:
        return 1

    paths = write_report(report, output_dir)
    if report["refused"]:
        gate = report["gate"]
        logger.error("门禁 %s (%s) 拒绝出报告：%s", gate["id"], gate["name"], gate["message"])
    else:
        prov = report["provenance"]
        logger.info("语料 %d 篇 / 人员 %d 位（严格键 %d、宽松键 %d，两者之差即人员计数的误差范围）",
                    prov["corpus_size"], prov["n_people"], prov["n_strict"], prov["n_loose"])
        if report["gantt_path"]:
            logger.info("活跃期甘特图: %s", report["gantt_path"])
    logger.info("画像报告: %s | %s", paths["markdown"], paths["json"])
    return report["exit_code"]


def cmd_fetch(argv: list[str]):
    args = parse_fetch_args(argv)
    cfg = apply_cli_overrides(load_config(args.config), args)

    # 设置日志
    log_file = setup_logging(cfg["output_dir"], cfg["log_level"])
    logger = logging.getLogger("pubmed_toolkit.main")

    logger.info("=" * 60)
    logger.info("PubMed 论文检索与下载工具 (v2.1)")
    logger.info("作者: %s | 机构: %s | 近 %d 年", cfg["author_name"], cfg["affiliation"], cfg["years_back"])
    logger.info("并发: %d 线程 | 日志: %s", cfg["max_workers"], log_file)
    logger.info("PDF下载: %s", "启用" if cfg.get("download_pdfs") else "关闭")
    logger.info("=" * 60)
    if not cfg.get("api_key"):
        logger.warning("未配置 PubMed API key，将按 NCBI 匿名限速请求。")
    if cfg.get("download_pdfs") and not cfg.get("email"):
        logger.warning("未配置 Unpaywall 邮箱，Unpaywall 源会自动跳过。")

    # 导入模块
    from pubmed_toolkit.engine import DownloadEngine
    from pubmed_toolkit.pubmed_api import (
        AUTHOR_IDENTITY,
        fetch_details,
        is_first_or_corresponding,
        search_pubmed,
    )

    # 用 CONFIG 中的 author_identity 覆盖默认配置
    identity_cfg = cfg.get("author_identity")
    if identity_cfg:
        AUTHOR_IDENTITY.update(identity_cfg)
        logger.info("身份验证: 严格模式=%s | 机构关键词=%d个 | 邮箱域=%d个",
                     identity_cfg.get("require_affiliation", True),
                     len(identity_cfg.get("affiliation_keywords", [])),
                     len(identity_cfg.get("email_domains", [])))

    # Step 1: 搜索。把身份配置一并传入 —— ORCID 可直接作为检索项，
    # 机构关键词在结果超出 retmax 时用于服务端收窄。
    pmids = search_pubmed(
        cfg["author_name"], cfg["years_back"], cfg["api_key"],
        retmax=cfg.get("retmax", 500), identity=identity_cfg,
    )
    if not pmids:
        logger.warning("未找到任何论文，请检查作者名拼写。")
        return

    # Step 2: 获取详情
    logger.info("正在获取 %d 篇论文的详细信息...", len(pmids))
    all_papers = fetch_details(pmids, cfg["api_key"], cfg["delay_seconds"])
    logger.info("成功解析 %d 篇", len(all_papers))

    # Step 3: 过滤（带机构深度验证 + [Keep]/[Skip] 日志）
    logger.info("筛选第一/通讯作者 + 机构身份验证...")
    matched_papers = []
    skipped_papers = []
    for p in all_papers:
        is_match, role = is_first_or_corresponding(
            p, cfg["author_name"], cfg["affiliation"], identity=identity_cfg
        )
        if is_match:
            p["role"] = role
            matched_papers.append(p)
        else:
            skipped_papers.append(p)

    logger.info("身份验证结果: %d 篇通过 / %d 篇拒绝 / %d 篇总计",
                len(matched_papers), len(skipped_papers), len(all_papers))

    if not matched_papers:
        logger.warning("未找到以第一/通讯作者发表的论文，将保存全部结果供参考。")
        for p in all_papers:
            p["role"] = "待确认"
        matched_papers = all_papers

    matched_papers.sort(key=lambda x: x.get("pub_year", "0"), reverse=True)

    # Step 4: 并发下载 PDF
    if cfg["download_pdfs"]:
        logger.info("开始并发下载 PDF（%d 线程）...", cfg["max_workers"])
        engine = DownloadEngine(
            email=cfg["email"],
            max_workers=cfg["max_workers"],
            proxy_list=cfg.get("proxy_list"),
            cache_db=cfg["cache_db"],
        )
        try:
            stats = engine.download_batch(matched_papers, cfg["pdf_dir"])
            logger.info(
                "下载结果: 成功 %d / 缓存命中 %d / 失败 %d / 共 %d 篇",
                stats["downloaded"], stats["cached"], stats["failed"], stats["total"],
            )
            logger.info("缓存统计: %s", engine.cache.stats())
        finally:
            engine.close()
    else:
        for p in matched_papers:
            p["pdf_status"] = "未下载"

    # Step 5: 保存清单
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    from pubmed_toolkit.export import save_to_csv, save_to_excel, save_to_json
    try:
        import openpyxl  # noqa: F401  ensure dependency present
        excel_path = os.path.join(cfg["output_dir"], f"papers_{timestamp}.xlsx")
        save_to_excel(matched_papers, excel_path)
        logger.info("Excel 清单: %s", excel_path)
    except ImportError:
        csv_path = os.path.join(cfg["output_dir"], f"papers_{timestamp}.csv")
        save_to_csv(matched_papers, csv_path)
        logger.warning(
            "openpyxl 不可用，已降级导出 CSV 而非 Excel: %s（执行 `pip install openpyxl` 可恢复）",
            csv_path,
        )

    # 同步导出 JSON（供 analyze / download 子命令复用作者完整信息）
    json_path = os.path.join(cfg["output_dir"], f"papers_{timestamp}.json")
    save_to_json(matched_papers, json_path)
    logger.debug("Papers JSON: %s", json_path)

    # PDF 下载结果与身份校验汇总报告
    from pubmed_toolkit.reports import write_pdf_validation_report
    report_path = os.path.join(cfg["output_dir"], f"pdf_validation_report_{timestamp}.csv")
    write_pdf_validation_report(matched_papers, report_path, pdf_dir=cfg["pdf_dir"])
    logger.info("PDF 校验报告: %s", report_path)

    # 打印论文列表
    logger.info("=" * 60)
    logger.info("检索完成！符合条件: %d 篇", len(matched_papers))
    for i, p in enumerate(matched_papers, 1):
        logger.info(
            "%d. [%s] %s | %s (%s) | PDF: %s",
            i, p.get("role", ""), p["title"][:60],
            p["journal"], p["pub_date"], p.get("pdf_status", ""),
        )


def parse_verify_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pubmed-toolkit verify",
        description="Verify a bibliography against CrossRef and PubMed.",
    )
    parser.add_argument("input", help="Path to a .bib or .json reference list")
    parser.add_argument("--config", help="JSON config file (used for email / api_key)")
    parser.add_argument("--email", help="Contact email for the CrossRef and NCBI polite pools")
    parser.add_argument("--ncbi-api-key", help="NCBI API key (raises the rate limit 3/s -> 10/s)")
    parser.add_argument("--output-dir", default="verify_results", help="Where reports are written")
    parser.add_argument("--max-workers", type=int, default=6,
                        help="Concurrent lookups. Throughput is bounded by NCBI's rate "
                             "limit (3/s, or 10/s with --ncbi-api-key), not by this value.")
    parser.add_argument("--timeout", type=float, default=12.0, help="Hard per-request timeout (s)")
    parser.add_argument("--no-pubmed", action="store_true",
                        help="Use CrossRef only; skips the bidirectional identifier check")
    parser.add_argument("--fail-on-mismatch", action="store_true",
                        help="Exit non-zero when any entry has an issue (for CI)")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    return parser.parse_args(argv)


def cmd_verify(argv: list[str]):
    from pubmed_toolkit.verify import (
        ReferenceVerifier,
        load_bibtex,
        load_json_refs,
        summarize,
        write_json_report,
        write_markdown_report,
    )

    args = parse_verify_args(argv)
    cfg = load_config(args.config) if args.config else {}

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(message)s",
                        stream=sys.stdout)
    logger = logging.getLogger("pubmed_toolkit.verify")

    src = args.input
    if not os.path.exists(src):
        logger.error("Input file not found: %s", src)
        return 2

    try:
        refs = load_json_refs(src) if src.lower().endswith(".json") else load_bibtex(src)
    except (ValueError, OSError) as e:
        logger.error("Could not read %s: %s: %s", src, type(e).__name__, e)
        return 2
    if not refs:
        logger.error("No references parsed from %s", src)
        return 2

    email = args.email or cfg.get("email", "") or os.environ.get("CROSSREF_EMAIL", "")
    api_key = (args.ncbi_api_key or cfg.get("api_key", "")
               or os.environ.get("PUBMED_API_KEY", ""))
    if not email:
        logger.warning(
            "No contact email set. CrossRef and NCBI both ask for one and may "
            "throttle anonymous traffic. Pass --email or set CROSSREF_EMAIL."
        )

    logger.info("=" * 60)
    logger.info("Verifying %d references from %s", len(refs), src)
    logger.info("PubMed cross-check: %s", "off" if args.no_pubmed else "on")
    logger.info("=" * 60)

    verifier = ReferenceVerifier(
        email=email, ncbi_api_key=api_key, timeout=args.timeout,
        max_workers=args.max_workers, use_pubmed=not args.no_pubmed,
    )
    results = verifier.verify_all(refs)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = write_json_report(results, os.path.join(args.output_dir, f"verify_{stamp}.json"))
    md_path = write_markdown_report(results, os.path.join(args.output_dir, f"verify_{stamp}.md"))

    s = summarize(results)
    logger.info("=" * 60)
    logger.info(
        "verified=%d  conflicts=%d  unregistered=%d  mismatch=%d  "
        "partial=%d  not_found=%d  error=%d  (total %d)",
        s["verified"], s["conflicts"], s["unresolvable_ids"], s["mismatch"],
        s["partial"], s["not_found"], s["error"], s["total"],
    )
    if s["incomplete"]:
        logger.warning(
            "%d entries had a lookup fail, so not every check ran on them. "
            "They are not counted as verified.", s["incomplete"],
        )
    logger.info("Reports: %s | %s", md_path, json_path)
    logger.info("=" * 60)

    if args.fail_on_mismatch and (
        s["mismatch"] or s["conflicts"] or s["unresolvable_ids"] or s["error"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    main()
