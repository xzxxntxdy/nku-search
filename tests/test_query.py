import unittest

from nku_search.query import QueryMode, SearchQuery, build_es_query, clean_query, detect_mode, site_prefix_filters, wildcard_to_regex


class QueryParsingTest(unittest.TestCase):
    def test_detects_phrase_wildcard_and_regex(self):
        self.assertEqual(detect_mode('"南开大学"'), QueryMode.PHRASE)
        self.assertEqual(detect_mode("“南开大学”"), QueryMode.PHRASE)
        self.assertEqual(detect_mode("温*"), QueryMode.WILDCARD)
        self.assertEqual(detect_mode("/计.*/"), QueryMode.REGEX)
        self.assertEqual(detect_mode("信息检索"), QueryMode.NORMAL)

    def test_clean_query_unwraps_special_modes(self):
        self.assertEqual(clean_query('"南开大学"', QueryMode.PHRASE), "南开大学")
        self.assertEqual(clean_query("“南开大学”", QueryMode.PHRASE), "南开大学")
        self.assertEqual(clean_query("/计.*/", QueryMode.REGEX), "计.*")

    def test_wildcard_to_regex_matches_expected_terms(self):
        regex = wildcard_to_regex("计?")
        self.assertTrue(regex.search("计网"))
        self.assertTrue(regex.search("计算"))
        self.assertFalse(regex.search("信息检索"))

    def test_build_es_query_includes_site_and_filetype_filters(self):
        query = SearchQuery(q="信息检索", site="https://news.nankai.edu.cn/", filetype="pdf", section="news", category="新闻资讯")
        body = build_es_query(query, user_terms=["人工智能"])
        filters = body["query"]["function_score"]["query"]["bool"]["filter"]
        self.assertIn({"prefix": {"url": "https://news.nankai.edu.cn/"}}, filters)
        self.assertIn({"term": {"filetype": "pdf"}}, filters)
        self.assertIn({"term": {"section": "news"}}, filters)
        self.assertIn({"term": {"category": "新闻资讯"}}, filters)

    def test_site_query_accepts_domain_only_and_operator_only(self):
        prefixes = site_prefix_filters("news.nankai.edu.cn")
        self.assertIn({"prefix": {"url": "https://news.nankai.edu.cn/"}}, prefixes)
        self.assertIn({"prefix": {"url": "http://news.nankai.edu.cn/"}}, prefixes)

        body = build_es_query(SearchQuery(q="site:news.nankai.edu.cn"))
        query = body["query"]["function_score"]["query"]["bool"]
        self.assertEqual(query["must"], [{"match_all": {}}])
        self.assertIn(
            {
                "bool": {
                    "should": [
                        {"prefix": {"url": "https://news.nankai.edu.cn/"}},
                        {"prefix": {"url": "http://news.nankai.edu.cn/"}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            query["filter"],
        )

    def test_mode_detection_ignores_wildcards_inside_site_operator(self):
        self.assertEqual(detect_mode("site:https://example.com/search?q=* 南开"), QueryMode.NORMAL)

    def test_quoted_phrase_inside_normal_query_becomes_phrase_clause(self):
        body = build_es_query(SearchQuery(q='site:news.nankai.edu.cn “南开大学”'))
        query = body["query"]["function_score"]["query"]["bool"]
        phrase_clauses = [
            clause
            for clause in query["must"]
            if clause.get("multi_match", {}).get("type") == "phrase"
        ]
        self.assertEqual(len(phrase_clauses), 1)
        self.assertEqual(phrase_clauses[0]["multi_match"]["query"], "南开大学")



    def test_build_es_query_has_operational_guards_and_facets(self):
        body = build_es_query(SearchQuery(q="CARSI"))
        self.assertEqual(body["_source"], {"excludes": ["text", "anchors", "outgoing_links"]})
        self.assertEqual(body["highlight"]["max_analyzed_offset"], 100000)
        self.assertIn("filetype", body["aggs"])
        self.assertIn("category", body["aggs"])
        self.assertIn("section", body["aggs"])

if __name__ == "__main__":
    unittest.main()

