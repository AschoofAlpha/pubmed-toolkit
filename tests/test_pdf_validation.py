#!/usr/bin/env python3
"""
PDF identity validation tests.

These tests stub text extraction so they do not need real PDFs or PyMuPDF.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pubmed_toolkit import pdf_utils


def _with_temp_file(fn):
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        return fn(path)
    finally:
        if os.path.exists(path):
            os.remove(path)


def run_tests():
    original = pdf_utils.extract_pdf_text
    passed = 0
    failed = 0

    cases = [
        {
            "name": "DOI match accepts",
            "paper": {
                "doi": "10.1038/s41388-024-03001-1",
                "title": "NAT10 Phase Separation Regulates YTHDF1 Splicing to Promote Gastric Cancer Progression.",
            },
            "text": "Published article DOI: 10.1038/s41388-024-03001-1. unrelated title words " * 20,
            "expected": True,
        },
        {
            "name": "Title overlap accepts",
            "paper": {
                "doi": "",
                "title": "USP10-mediated Ku70/80 stabilization inhibits PANoptosis and promotes chemoresistance in colorectal cancer.",
            },
            "text": "USP10 mediated Ku70 80 stabilization inhibits PANoptosis and promotes chemoresistance in colorectal cancer " * 20,
            "expected": True,
        },
        {
            "name": "Wrong title rejects",
            "paper": {
                "doi": "",
                "title": "YY1-mediated transcriptional regulation of LINC01615 inhibits WNT2 mRNA degradation to promote gastric cancer progression.",
            },
            "text": "MUC5AC CD44 axis promotes lung tumor invasion with macrophage signaling and extracellular matrix remodeling " * 30,
            "expected": False,
        },
    ]

    try:
        for case in cases:
            pdf_utils.extract_pdf_text = lambda _path, text=case["text"]: (text, "stubbed")

            def _run(path, paper=case["paper"]):
                return pdf_utils.validate_pdf_matches_paper(path, paper)

            ok, reason = _with_temp_file(_run)
            status = "[PASS]" if ok == case["expected"] else "[FAIL]"
            if ok == case["expected"]:
                passed += 1
            else:
                failed += 1
            print(f"{case['name']}: expected={case['expected']} actual={ok} reason={reason} {status}")
    finally:
        pdf_utils.extract_pdf_text = original

    print(f"\n总结: {passed} 通过 / {failed} 失败 / {len(cases)} 总计")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
