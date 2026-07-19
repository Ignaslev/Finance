from django.test import SimpleTestCase
from .markdown import render_markdown


class MarkdownRendererTests(SimpleTestCase):
    def test_renders_safe_internal_and_https_links(self):
        html = str(render_markdown("[Vidinis](/straipsniai/) ir [šaltinis](https://www.lb.lt/lt/asmeniniai-finansai)"))
        self.assertIn('href="/straipsniai/"', html)
        self.assertIn('href="https://www.lb.lt/lt/asmeniniai-finansai"', html)

    def test_escapes_untrusted_html(self):
        self.assertNotIn("<script>", str(render_markdown("<script>alert(1)</script>")))
