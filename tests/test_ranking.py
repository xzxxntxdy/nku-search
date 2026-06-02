import unittest

from nku_search.models import CrawledPage
from nku_search.query import QueryMode, SearchQuery
from nku_search.ranking import LocalRankDocument, compute_pagerank, infer_interest_score, rank_documents
from nku_search.search_engine import LocalSearchBackend


class RankingTest(unittest.TestCase):
    def test_pagerank_rewards_linked_page(self):
        ranks = compute_pagerank({"a": ["b"], "b": ["c"], "c": ["b"]}, iterations=50)
        self.assertGreater(ranks["b"], ranks["a"])

    def test_rank_documents_prefers_title_match(self):
        docs = [
            LocalRankDocument("1", "普通校园通知", "信息检索课程安排", []),
            LocalRankDocument("2", "信息检索学术论坛", "普通新闻内容", []),
        ]
        ranked = rank_documents("信息检索", docs)
        self.assertEqual(ranked[0][0].doc_id, "2")

    def test_personal_interest_score_uses_history(self):
        score = infer_interest_score(["人工智能", "信息检索"], "人工智能论坛", "南开新闻")
        self.assertGreater(score, 0.0)


class LocalSearchBackendTest(unittest.TestCase):
    def setUp(self):
        self.backend = LocalSearchBackend(
            [
                CrawledPage(
                    url="https://news.nankai.edu.cn/a.html",
                    title="南开大学人工智能论坛",
                    text="论坛讨论信息检索和搜索引擎。",
                    anchors=["学术新闻"],
                ),
                CrawledPage(
                    url="https://jwc.nankai.edu.cn/course.pdf",
                    title="课程安排",
                    text="计算机网络和数据库课程。",
                    filetype="pdf",
                ),
            ]
        )

    def test_phrase_search(self):
        hits, total = self.backend.search(SearchQuery(q='"信息检索"', mode=QueryMode.PHRASE))
        self.assertEqual(total, 1)
        self.assertIn("人工智能论坛", hits[0].title)

    def test_wildcard_and_document_search(self):
        hits, total = self.backend.search(SearchQuery(q="计?", mode=QueryMode.WILDCARD, filetype="pdf"))
        self.assertEqual(total, 1)
        self.assertEqual(hits[0].filetype, "pdf")

    def test_advanced_query_filters_and_explain(self):
        hits, total = self.backend.search(SearchQuery(q='site:https://news.nankai.edu.cn/ title:人工智能 信息检索'))
        self.assertEqual(total, 1)
        self.assertIn("bm25", hits[0].explanation)
        self.assertTrue(self.backend.index.last_diagnostics.facets)


if __name__ == "__main__":
    unittest.main()
