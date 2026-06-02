import io
import unittest
import warnings
import zipfile

from nku_search.text import clean_document_text, extract_document_text, extract_links, normalize_document_title


class TextUtilityTest(unittest.TestCase):
    def test_extract_links_skips_malformed_href(self):
        html = '<a href="https://bad.example.com\uff1a443/path">bad</a><a href="/ok.html">ok</a><a href="javascript:void(0)">skip</a>'
        links = extract_links(html, "https://news.nankai.edu.cn/base/index.html")
        self.assertEqual(links, ["https://news.nankai.edu.cn/ok.html"])

    def test_extract_links_reads_embedded_spa_data_and_filters_assets(self):
        html = """
        <link href="/_next/static/chunks/app.js" rel="preload">
        <img src="/openlist/d/resource/anime/a424242/banner.avif">
        <div data-url="/2025/0522/c17471a596037/page.htm"></div>
        <script>self.__next_f.push(['{\"dbId\":\"a542203\"}'])</script>
        """
        links = extract_links(html, "http://12club.nankai.edu.cn/anime")
        self.assertIn("http://12club.nankai.edu.cn/anime/a424242", links)
        self.assertIn("http://12club.nankai.edu.cn/anime/a542203", links)
        self.assertIn("http://12club.nankai.edu.cn/2025/0522/c17471a596037/page.htm", links)
        self.assertFalse(any(link.endswith(".js") or link.endswith(".avif") for link in links))

    def test_extract_links_parses_sitemap_xml_without_html_warning(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset><url><loc>https://news.nankai.edu.cn/test/page.htm</loc></url></urlset>
        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            links = extract_links(xml, "https://news.nankai.edu.cn/sitemap.xml")
        self.assertIn("https://news.nankai.edu.cn/test/page.htm", links)
        self.assertFalse(any(item.category.__name__ == "XMLParsedAsHTMLWarning" for item in caught))

    def test_normalize_document_title_decodes_percent_encoded_chinese_name(self):
        title = normalize_document_title(
            "https://xb.nankai.edu.cn/upload/20250701102209/%E5%8D%97%E5%BC%80%E5%A4%A7%E5%AD%A62025%E5%B9%B4%E6%9A%91%E5%81%87%E5%80%BC%E7%8F%AD%E8%A1%A8.pdf",
            "pdf",
        )
        self.assertEqual(title, "\u5357\u5f00\u5927\u5b662025\u5e74\u6691\u5047\u503c\u73ed\u8868")

    def test_normalize_document_title_uses_text_for_opaque_uuid_name(self):
        title = normalize_document_title(
            "https://economics.nankai.edu.cn/_upload/article/files/3b/ca/9ee963e44cd688dfff0462ac3737/4f7acb2b-aed1-40d4-8b9b-72a7a6c14506.pdf",
            "pdf",
            text="\u5357\u5f00\u5927\u5b66\u7ecf\u6d4e\u5b66\u9662\u7855\u58eb\u7814\u7a76\u751f\u62db\u751f\u590d\u8bd5\u5b89\u6392 \u6b63\u6587\u5185\u5bb9",
        )
        self.assertEqual(title, "\u5357\u5f00\u5927\u5b66\u7ecf\u6d4e\u5b66\u9662\u7855\u58eb\u7814\u7a76\u751f\u62db\u751f\u590d\u8bd5\u5b89\u6392 \u6b63\u6587\u5185\u5bb9")

    def test_pptx_text_is_extracted_from_office_xml(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "docProps/core.xml",
                """<?xml version="1.0" encoding="UTF-8"?>
                <cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                  xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>\u5357\u5f00\u56fe\u4e66\u9986\u57f9\u8bad\u8bfe\u4ef6</dc:title></cp:coreProperties>""",
            )
            archive.writestr(
                "ppt/slides/slide1.xml",
                """<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
                  <a:t>\u4fe1\u606f\u68c0\u7d22\u8bfe\u7a0b</a:t><a:t>\u6570\u636e\u5e93\u4f7f\u7528\u65b9\u6cd5</a:t></p:sld>""",
            )
        content = payload.getvalue()
        text = extract_document_text(content, "pptx")
        self.assertIn("\u4fe1\u606f\u68c0\u7d22\u8bfe\u7a0b", text)
        self.assertEqual(
            normalize_document_title(
                "https://lib.nankai.edu.cn/_upload/article/files/demo/uuid.pptx",
                "pptx",
                text=text,
                fallback_title="PK\x03\x04[Content_Types].xml",
            ),
            "\u4fe1\u606f\u68c0\u7d22\u8bfe\u7a0b \u6570\u636e\u5e93\u4f7f\u7528\u65b9\u6cd5",
        )

    def test_binary_ppt_title_falls_back_to_document_label(self):
        title = normalize_document_title(
            "https://lib.nankai.edu.cn/_upload/article/files/demo/48f68bbc-9a60-49ae-9feb-376b70f4be71.ppt",
            "ppt",
            text="\x11\u0871\x1a\x00\x00\x00> JFIF \x00\x00",
            fallback_title="\x11\u0871\x1a\x00\x00",
        )
        self.assertEqual(title, "PPT document")
        self.assertEqual(clean_document_text("PK\x03\x04[Content_Types].xml\x00\x00", "pptx"), "")


if __name__ == "__main__":
    unittest.main()
