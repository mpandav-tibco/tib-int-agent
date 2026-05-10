from __future__ import annotations

import re
import time

from .base import KnowledgeSource, RawDocument


class WebSource(KnowledgeSource):
    """
    Fetches web pages and converts their main content to plain text for ingestion.
    Respects a polite crawl delay between requests.

    Add URLs:
        WebSource(
            urls=["https://docs.tibco.com/..."],
            name="tibco-flogo-docs",
            product_tag="flogo",
        )
    """

    def __init__(
        self,
        urls: list[str],
        name: str = "",
        product_tag: str = "general",
        delay: float = 1.5,
        timeout: float = 20.0,
    ) -> None:
        self.urls = urls
        self.name = name or f"web:{urls[0] if urls else 'empty'}"
        self.product_tag = product_tag
        self.delay = delay
        self.timeout = timeout

    def load(self) -> list[RawDocument]:
        try:
            import requests
        except ImportError:
            print("  [WARN] 'requests' or 'beautifulsoup4' not installed. Skipping web source.")
            return []

        docs = []
        headers = {"User-Agent": "Mozilla/5.0 (compatible; tibco-ai-agent/1.0; research-tool)"}

        for url in self.urls:
            try:
                resp = requests.get(url, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                content = self._extract(resp.text)
                if len(content.strip()) > 200:
                    docs.append(RawDocument(
                        content=content,
                        source=url,
                        metadata={"source_type": "web", "url": url, "product": self.product_tag},
                    ))
                    print(f"  [OK] {url} ({len(content):,} chars)")
                else:
                    print(f"  [SKIP] {url} — too little content extracted")
                time.sleep(self.delay)
            except Exception as e:
                print(f"  [WARN] {url}: {e}")

        return docs

    def _extract(self, html: str) -> str:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "form"]):
            tag.decompose()

        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find(id="content")
            # MadCap Flare pages (TIBCO docs)
            or soup.find(attrs={"class": "page-content"})
            or soup.find(attrs={"class": re.compile(r"(main|topic|article|content)[-_]?(content|body|text)?", re.I)})
            or soup.body
        )

        if main is None:
            return ""

        text = main.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
