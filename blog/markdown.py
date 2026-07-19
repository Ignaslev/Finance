import re

from django.utils.html import escape
from django.utils.safestring import mark_safe


def render_markdown(value):
    blocks = [item.strip() for item in value.strip().split("\n\n") if item.strip()]
    html = []
    for item in blocks:
        safe = str(escape(item))
        safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
        safe = re.sub(
            r"\[([^\]]+)\]\((https://[^\s)]+|/[^\s)]+)\)",
            r'<a href="\2">\1</a>',
            safe,
        )
        if safe.startswith("### "):
            html.append(f"<h3>{safe[4:]}</h3>")
        elif safe.startswith("## "):
            html.append(f"<h2>{safe[3:]}</h2>")
        elif all(line.startswith("- ") for line in safe.splitlines()):
            html.append("<ul>" + "".join(f"<li>{line[2:]}</li>" for line in safe.splitlines()) + "</ul>")
        else:
            html.append(f"<p>{' '.join(safe.splitlines())}</p>")
    return mark_safe("\n".join(html))
