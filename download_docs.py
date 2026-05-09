#!/usr/bin/env python3
"""
Download TIBCO product documentation PDFs from docs.tibco.com
and place them into data/knowledge/<product>/ for ingestion.
"""

import io
import os
import zipfile
import requests

BASE_DIR = os.path.join(os.path.dirname(__file__), "data", "knowledge")

# "Download All Docs" ZIP bundles from docs.tibco.com
# Each entry: (product_folder, zip_url)
DOC_ZIPS = [
    # Flogo 2.26.3
    ("flogo", "https://docs.tibco.com/pub/flogo/2.26.3/tibco-flogo-2-26-3_documentation.zip"),
    # ActiveMatrix BusinessWorks 6.12.0
    ("bw", "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/tibco-activematrix-businessworks-6-12-0_documentation.zip"),
    # BWCE 2.10.0
    ("bw", "https://docs.tibco.com/pub/bwce/2.10.0/tibco-businessworks-container-edition-2-10-0_documentation.zip"),
    # EMS 10.5.0
    ("ems", "https://docs.tibco.com/pub/ems/10.5.0/tibco-enterprise-message-service-10-5-0_documentation.zip"),
    # FTL 7.2.0
    ("ftl", "https://docs.tibco.com/pub/ftl/7.2.0/tibco-ftl-enterprise-edition-7-2-0_documentation.zip"),
    # eFTL 7.2.0
    ("eftl", "https://docs.tibco.com/pub/eftl/7.2.0/tibco-eftl-enterprise-edition-7-2-0_documentation.zip"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; tibco-ai-agent/1.0)"}


def download_and_extract(product: str, url: str) -> int:
    """Download a ZIP, extract PDFs into data/knowledge/<product>/. Returns PDF count."""
    dest = os.path.join(BASE_DIR, product)
    os.makedirs(dest, exist_ok=True)

    print(f"\n[{product}] Downloading {url} ...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=120, stream=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [FAIL] {e}")
        return 0

    content_type = resp.headers.get("Content-Type", "")
    data = resp.content

    # Check if it's a ZIP
    if zipfile.is_zipfile(io.BytesIO(data)):
        count = 0
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".pdf"):
                    basename = os.path.basename(name)
                    if not basename or basename.startswith("."):
                        continue
                    out_path = os.path.join(dest, basename)
                    if os.path.exists(out_path):
                        print(f"  [SKIP] {basename} (already exists)")
                        continue
                    with open(out_path, "wb") as f:
                        f.write(zf.read(name))
                    size_kb = os.path.getsize(out_path) / 1024
                    print(f"  [OK] {basename} ({size_kb:.0f} KB)")
                    count += 1
        return count
    elif url.lower().endswith(".pdf"):
        # Direct PDF download
        basename = url.split("/")[-1]
        out_path = os.path.join(dest, basename)
        with open(out_path, "wb") as f:
            f.write(data)
        size_kb = len(data) / 1024
        print(f"  [OK] {basename} ({size_kb:.0f} KB)")
        return 1
    else:
        print(f"  [SKIP] Not a ZIP or PDF (Content-Type: {content_type})")
        return 0


def main():
    total = 0
    for product, url in DOC_ZIPS:
        count = download_and_extract(product, url)
        total += count
        print(f"  => {count} PDF(s) extracted for {product}")

    print(f"\n{'='*50}")
    print(f"Total: {total} PDFs downloaded to {BASE_DIR}")
    print(f"Run 'python ingest.py' to build the knowledge base.")


if __name__ == "__main__":
    main()
