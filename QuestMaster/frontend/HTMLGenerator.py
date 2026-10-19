import json
from pathlib import Path

TEMPLATE = (Path(__file__).parent / "quest_template.html").read_text(encoding="utf-8")


def generate_html(metadata: dict, narrative: str) -> str:
    """Render the quest page by embedding metadata and narrative as JSON into the static template."""
    # Escape every "<" so the data can never close the <script> tag ("</script>", "<!--").
    data = json.dumps({"meta": metadata, "narrative": narrative}).replace("<", "\\u003c")
    return TEMPLATE.replace("__QUEST_DATA__", data)


if __name__ == "__main__":
    page = generate_html({"quest_data": {}}, "</script><script>alert(1)</script>")
    assert "<script>alert" not in page
    assert page.count("</script>") == TEMPLATE.count("</script>")
    print("ok")
