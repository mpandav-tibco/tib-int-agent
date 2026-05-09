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

# TIBCO documentation pages — Integration + Messaging categories
# Source: https://docs.tibco.com/product/categories#name=Integration
#         https://docs.tibco.com/product/categories#name=Messaging
TIBCO_WEB_SOURCES = {
    # ── Flogo ──────────────────────────────────────────────────────────
    "flogo": [
        # Designing apps in VS Code
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all/designing-flogo-applications-in-vsc.htm",
        # Creating flows and triggers
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all-vsc/creating-flows-and-triggers.htm",
        # Data mappings
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all-vsc/data-mappings.htm",
        # General triggers, activities, connections
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all-vsc/general.htm",
        # REST trigger
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all-vsc/rest.htm",
        # Developing APIs
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all-vsc/developing-apis.htm",
        # App properties, schemas, specs
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all-vsc/using-app-properties3.htm",
        # Using connectors
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all/using-connectors-ug.htm",
        # Supported Flogo connectors
        "https://docs.tibco.com/pub/flogo/latest/doc/html/connectors/connectors-shared/supported-flogo-connectors.htm",
        # File category trigger and activities
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all/files/FileCategory.htm",
        # Unit testing
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all-vsc/Unit-Testing.htm",
        # Validating app flows
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all-vsc/validating-your-app-flow.htm",
        # Running Flogo apps locally
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all-vsc/Running-Apps-Locally.htm",
        # Deploying apps from VS Code
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all-vsc/deploymentandconfiguration.htm",
        # Using extensions
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all-vsc/uploading-extensions2.htm",
        # Lambda development
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-all/aws-lambda/developing-for-lambd.htm",
        # Flogo Design Assistant (AI)
        "https://docs.tibco.com/pub/flogo/latest/doc/html/flogo-design-assistant/flogo-design-assistant.htm",
    ],
    # ── BusinessWorks 6 (Container Edition merged) ─────────────────────
    "bw": [
        # App development overview
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/studio-app-dev-overview.htm",
        # App design considerations
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/application-design-c.htm",
        # Process design considerations
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/process-design-consi.htm",
        # Developing a basic process
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/developing-a-basic-p2.htm",
        # Creating an application
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/creating-an-applicat3.htm",
        # Working with application properties
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/working-with-applica.htm",
        # Designing and testing RESTful services
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/designing-and-testin.htm",
        # Developing a SOAP service
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/developing-a-soap-se2.htm",
        # Best practices
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/best-practices.htm",
        # HTTP security
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/http-security.htm",
        # Docker base image
        "https://docs.tibco.com/pub/bwce/2.10.0/doc/html/app-dev-guide/creating-the-bwce-ba2.htm",
        # Docker environment variables
        "https://docs.tibco.com/pub/bwce/2.10.0/doc/html/app-dev-guide/environment-variable.htm",
        # Generating deployment artifacts
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/generating-deploymen2.htm",
        # Health check endpoints
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/http-endpoint-for-he.htm",
        # OpenTelemetry
        "https://docs.tibco.com/pub/bwce/2.10.0/doc/html/bwce-app-monitoring/opentelemetry.htm",
        # Troubleshooting
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/doc/bwce-html/app-dev-guide/troubleshooting.htm",
        # New features
        "https://docs.tibco.com/pub/activematrix_businessworks/6.12.0/relnotes/bw-ent-relnotes/new-features.htm",
    ],
    # ── TIBCO Enterprise Message Service (EMS) ─────────────────────────
    "ems": [
        # EMS user guide (web help root)
        "https://docs.tibco.com/pub/ems/10.5.0/doc/html/Default.htm",
        # EMS product page (overview + links)
        "https://docs.tibco.com/products/tibco-enterprise-message-service",
    ],
    # ── TIBCO FTL ──────────────────────────────────────────────────────
    "ftl": [
        # FTL user guide (web help root)
        "https://docs.tibco.com/pub/ftl/7.2.0/doc/html/index.html",
        # FTL product page
        "https://docs.tibco.com/products/tibco-ftl-enterprise-edition",
    ],
    # ── TIBCO eFTL ─────────────────────────────────────────────────────
    "eftl": [
        # eFTL user guide (web help root)
        "https://docs.tibco.com/pub/eftl/7.2.0/doc/html/index.html",
        # eFTL product page
        "https://docs.tibco.com/products/tibco-eftl-enterprise-edition",
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
