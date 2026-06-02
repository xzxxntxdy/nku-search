import unittest

from nku_search.config import SAMPLE_DOCUMENTS_PATH
from nku_search.index import load_pages
from nku_search.query import SearchQuery
from nku_search.search_pipeline import SearchPipeline


class SearchPipelineTest(unittest.TestCase):
    def test_pipeline_runs_components(self):
        pages = load_pages(SAMPLE_DOCUMENTS_PATH)
        context = SearchPipeline().run(SearchQuery(q=" 信息检索 "), pages)
        self.assertGreater(context.total, 0)
        self.assertIn("query_normalizer", context.metadata)
        self.assertIn("bm25f_retriever", context.metadata)
        self.assertTrue(context.suggestions)

    def test_pipeline_describe(self):
        description = SearchPipeline().describe()
        self.assertIn("bm25f_retriever", description["components"])


if __name__ == "__main__":
    unittest.main()
