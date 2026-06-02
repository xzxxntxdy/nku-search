from pathlib import Path
import tempfile
import unittest

from nku_search.auth import AuthService
from nku_search.recommend import update_suggestions_from_query
from nku_search.storage import Storage


class StorageTest(unittest.TestCase):
    def test_user_session_history_and_suggestions(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            storage = Storage(Path(tmpdir) / "search.db")
            auth = AuthService(storage)
            ok, message = auth.register("alice", "pass1234", "信息检索")
            self.assertTrue(ok, message)
            ok, _, token = auth.login("alice", "pass1234")
            self.assertTrue(ok)
            user = storage.get_user_by_session(token)
            self.assertIsNotNone(user)
            storage.log_query("信息检索", "normal", 3, user_id=user["id"])
            storage.upsert_suggestion("信息检索", 2.0, "query")
            self.assertEqual(storage.query_history(user["id"])[0]["query"], "信息检索")
            self.assertIn("信息检索", storage.suggestions("信", user_id=user["id"]))



    def test_user_interest_terms_feed_personalization(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            storage = Storage(Path(tmpdir) / "search.db")
            auth = AuthService(storage)
            ok, message = auth.register("bob", "pass1234", "artificial intelligence retrieval")
            self.assertTrue(ok, message)
            ok, _, token = auth.login("bob", "pass1234")
            self.assertTrue(ok)
            user = storage.get_user_by_session(token)
            terms = storage.user_query_terms(user["id"])
            self.assertIn("artificial intelligence retrieval", terms)

    def test_logged_in_query_suggestions_stay_personal(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            storage = Storage(Path(tmpdir) / "search.db")
            auth = AuthService(storage)
            ok, message = auth.register("carol", "pass1234", "")
            self.assertTrue(ok, message)
            ok, _, token = auth.login("carol", "pass1234")
            self.assertTrue(ok)
            user = storage.get_user_by_session(token)

            storage.log_query("private_personal_term", "normal", 0, user_id=user["id"])
            update_suggestions_from_query(storage, "private_personal_term", user_id=user["id"])
            self.assertIn("private_personal_term", storage.suggestions("private", user_id=user["id"]))
            self.assertNotIn("private_personal_term", storage.suggestions("private"))

            update_suggestions_from_query(storage, "public_global_term", user_id=None)
            self.assertIn("public_global_term", storage.suggestions("public"))

if __name__ == "__main__":
    unittest.main()

