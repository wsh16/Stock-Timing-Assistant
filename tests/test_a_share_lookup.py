from __future__ import annotations

from timing_assistant.a_share_lookup import lookup_a_share_match


class DummyResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.encoding = "gbk"

    def raise_for_status(self) -> None:
        return None


def test_lookup_a_share_match(monkeypatch):
    def fake_get(url, headers, timeout):  # noqa: ANN001
        assert url.endswith("sh600519")
        return DummyResponse('var hq_str_sh600519="贵州茅台,1467.450,1467.500,1462.840";')

    monkeypatch.setattr("timing_assistant.a_share_lookup.requests.get", fake_get)
    lookup_a_share_match.cache_clear()

    match = lookup_a_share_match("600519")

    assert match is not None
    assert match.normalized_symbol == "sh600519"
    assert match.display_name == "贵州茅台"
