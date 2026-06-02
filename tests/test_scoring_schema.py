import unittest

from nku_search.schema import DEFAULT_SCHEMA
from nku_search.scoring import BM25FModel, TermStats


class ScoringSchemaTest(unittest.TestCase):
    def test_default_schema_has_weighted_text_fields(self):
        boosts = {field.name: field.boost for field in DEFAULT_SCHEMA.scorable_text_fields()}
        self.assertGreater(boosts["title"], boosts["text"])
        self.assertGreater(boosts["anchors"], boosts["text"])

    def test_bm25f_model_scores_term_frequency_and_boost(self):
        model = BM25FModel()
        low = model.score(TermStats(10, 2, 1, 20, 20, 1.0))
        high = model.score(TermStats(10, 2, 3, 20, 20, 3.0))
        self.assertGreater(high, low)


if __name__ == "__main__":
    unittest.main()

