"""Incremental streaming utilities — framework-independent, safe to import in tests."""
from __future__ import annotations


class ThinkFilter:
    """O(n) incremental filter that strips <think>...</think> blocks from an LLM stream.

    deepseek-r1 reasoning models emit long `<think>` chains before the actual answer.
    Applying a regex over the growing accumulated buffer on every token is O(n²). This
    class processes each token in O(len(token)) by tracking parser state across calls.
    """

    _OPEN  = "<think>"
    _CLOSE = "</think>"

    def __init__(self) -> None:
        self._in_think = False
        self._buf = ""  # lookahead for partial tags that span token boundaries

    def feed(self, token: str) -> str:
        """Feed one token; return the clean output delta (empty while inside <think>)."""
        out: list[str] = []
        data = self._buf + token
        self._buf = ""
        while data:
            if self._in_think:
                end = data.lower().find(self._CLOSE)
                if end == -1:
                    keep = len(self._CLOSE) - 1
                    self._buf = data[-keep:] if len(data) >= keep else data
                    break
                data = data[end + len(self._CLOSE):]
                self._in_think = False
            else:
                start = data.lower().find(self._OPEN)
                if start == -1:
                    keep = len(self._OPEN) - 1
                    if len(data) >= keep:
                        out.append(data[:-keep])
                        self._buf = data[-keep:]
                    else:
                        self._buf = data
                    break
                out.append(data[:start])
                data = data[start + len(self._OPEN):]
                self._in_think = True
        return "".join(out)

    def finalize(self) -> str:
        """Flush any safe buffered content (partial open-tag lookahead) at stream end."""
        if self._in_think:
            return ""
        result = self._buf
        self._buf = ""
        return result
