import unittest

from nku_search.analytics import analyze_pages
from nku_search.config import SAMPLE_DOCUMENTS_PATH


class AnalyticsTest(unittest.TestCase):
    def test_analyzes_sample_documents(self):
        report = analyze_pages(SAMPLE_DOCUMENTS_PATH)
        self.assertGreaterEqual(report["document_count"], 5)
        self.assertIn("filetypes", report)
        self.assertIn("top_terms", report)
        self.assertIn("top_pagerank", report)


if __name__ == "__main__":
    unittest.main()
