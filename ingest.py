#!/usr/bin/env python3
"""
CLI entry point — builds the ChromaDB knowledge base.

Usage:
    python ingest.py                   # local knowledge files only
    python ingest.py --web             # also fetch TIBCO web documentation
    python ingest.py --no-reset        # append to existing collection
"""

import argparse
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tibco_agent.config import settings
from tibco_agent.ingest.pipeline import IngestionPipeline
from tibco_agent.ingest.sources.file_source import FileSource
from tibco_agent.ingest.sources.web_source import WebSource

# TIBCO documentation pages — extend this list as you find useful pages
TIBCO_WEB_SOURCES = {
    "flogo": [
        "https://docs.tibco.com/pub/flogo/latest/doc/html/GUID-3B0E7C1A.html",
        "https://docs.tibco.com/pub/flogo/latest/doc/html/GUID-9C2E9540.html",
    ],
    "bw": [
        "https://docs.tibco.com/pub/activematrix_businessworks/6.10.0/doc/html/GUID-6D8A5A69.html",
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the TIBCO AI Agent knowledge base")
    parser.add_argument("--web", action="store_true", help="Also fetch TIBCO web documentation")
    parser.add_argument("--no-reset", action="store_true", help="Append instead of wiping collection")
    parser.add_argument("--knowledge-path", default=settings.knowledge_path,
                        help="Path to local knowledge directory")
    args = parser.parse_args()

    settings.validate()
    pipeline = IngestionPipeline()
    pipeline.add_source(
        FileSource(args.knowledge_path, glob_pattern="**/*", name="local-knowledge")
    )

    if args.web:
        print("Web ingestion enabled — fetching TIBCO documentation...")
        for product, urls in TIBCO_WEB_SOURCES.items():
            pipeline.add_source(
                WebSource(urls=urls, name=f"tibco-docs-{product}", product_tag=product)
            )

    total = pipeline.run(reset=not args.no_reset)
    print(f"\nIngestion complete — {total} chunks ready.")
    sys.exit(0 if total > 0 else 1)


if __name__ == "__main__":
    main()
