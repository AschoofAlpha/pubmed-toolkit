"""
Configuration loading for the paper downloader.

Default settings are intentionally safe to commit. Secrets and local choices can
come from config.json, a custom JSON file, or environment variables.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "author_name": "",
    "affiliation": "",
    "api_key": "",
    "email": "",
    "years_back": 5,
    # esearch 单次最多取回多少条 PMID。命中数超过它会触发告警,
    # 并在配置了 affiliation_keywords 时自动加机构条件收窄。
    "retmax": 500,
    "output_dir": "pubmed_results",
    "pdf_dir": "pubmed_results/pdfs",
    "download_pdfs": True,
    "delay_seconds": 0.15,
    "max_workers": 4,
    "cache_db": "pubmed_results/paper_cache.db",
    "log_level": "INFO",
    "proxy_list": [],
    # Author disambiguation. Leave empty to accept every name match (not
    # recommended for common names). See config.example.json for a worked
    # example showing how to express institution name variants.
    "author_identity": {
        "affiliation_keywords": [],
        "email_domains": [],
        "orcid": "",
        "require_affiliation": False,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _list(value: str) -> list[str]:
    return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a JSON object: {path}")
    return data


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """
    Load configuration in this order:
    1. built-in safe defaults
    2. config.json or --config path
    3. environment variables
    """
    config = copy.deepcopy(DEFAULT_CONFIG)

    path: Path | None = None
    if config_path:
        path = Path(config_path)
    else:
        candidate = Path("config.json")
        if candidate.exists():
            path = candidate

    if path:
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        _deep_merge(config, _load_json(path))

    env_map = {
        "PUBMED_AUTHOR_NAME": ("author_name", str),
        "PUBMED_AFFILIATION": ("affiliation", str),
        "PUBMED_API_KEY": ("api_key", str),
        "UNPAYWALL_EMAIL": ("email", str),
        "PUBMED_YEARS_BACK": ("years_back", int),
        "PAPER_DOWNLOADER_OUTPUT_DIR": ("output_dir", str),
        "PAPER_DOWNLOADER_PDF_DIR": ("pdf_dir", str),
        "PAPER_DOWNLOADER_CACHE_DB": ("cache_db", str),
        "PAPER_DOWNLOADER_MAX_WORKERS": ("max_workers", int),
        "PAPER_DOWNLOADER_LOG_LEVEL": ("log_level", str),
        "PAPER_DOWNLOADER_DOWNLOAD_PDFS": ("download_pdfs", _bool),
    }
    for env_name, (config_key, caster) in env_map.items():
        if env_name in os.environ and os.environ[env_name].strip():
            config[config_key] = caster(os.environ[env_name])

    identity = config.setdefault("author_identity", {})
    nested_env = {
        "AUTHOR_ORCID": ("orcid", str),
        "AUTHOR_REQUIRE_AFFILIATION": ("require_affiliation", _bool),
        "AUTHOR_AFFILIATION_KEYWORDS": ("affiliation_keywords", _list),
        "AUTHOR_EMAIL_DOMAINS": ("email_domains", _list),
    }
    for env_name, (identity_key, caster) in nested_env.items():
        if env_name in os.environ and os.environ[env_name].strip():
            identity[identity_key] = caster(os.environ[env_name])

    if config.get("output_dir") != DEFAULT_CONFIG["output_dir"]:
        if config.get("pdf_dir") == DEFAULT_CONFIG["pdf_dir"]:
            config["pdf_dir"] = os.path.join(config["output_dir"], "pdfs")
        if config.get("cache_db") == DEFAULT_CONFIG["cache_db"]:
            config["cache_db"] = os.path.join(config["output_dir"], "paper_cache.db")

    return config
