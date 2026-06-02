import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from nku_search.config import SAMPLE_DOCUMENTS_PATH
from nku_search.index import load_pages
from nku_search.web import app, topic_payload


class WebApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_stats_and_references(self):
        stats = self.client.get("/api/stats")
        self.assertEqual(stats.status_code, 200)
        self.assertIn("backend", stats.json())
        refs = self.client.get("/api/references")
        self.assertEqual(refs.status_code, 200)
        names = {item["name"] for item in refs.json()["references"]}
        self.assertIn("Ant Design Pro", names)
        self.assertIn("Elastic Search UI", names)
        pipeline = self.client.get("/api/pipeline")
        self.assertEqual(pipeline.status_code, 200)
        self.assertIn("components", pipeline.json())
        topics = self.client.get("/api/topics")
        self.assertEqual(topics.status_code, 200)
        self.assertGreaterEqual(topics.json()["target_pages"], 100000)
        self.assertTrue(topics.json()["sections"])

    def test_frontend_shell_and_snapshot_are_served_by_backend(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        sample_doc = load_pages(SAMPLE_DOCUMENTS_PATH)[0]
        snapshot = self.client.get(f"/snapshot/{sample_doc.doc_id}")
        self.assertEqual(snapshot.status_code, 200)
        self.assertIn("<", snapshot.text)

    def test_json_search_history_and_account_flow(self):
        search = self.client.get("/api/search", params={"q": "信息检索"})
        self.assertEqual(search.status_code, 200)
        self.assertGreaterEqual(search.json()["total"], 1)
        limited = self.client.get("/api/search", params={"q": "南开", "size": 2})
        self.assertEqual(limited.status_code, 200)
        self.assertLessEqual(len(limited.json()["results"]), 2)
        topic_search = self.client.get("/api/search", params={"q": "南开", "category": "新闻资讯"})
        self.assertEqual(topic_search.status_code, 200)
        self.assertGreaterEqual(topic_search.json()["total"], 1)
        self.assertEqual(topic_search.json()["results"][0]["category"], "新闻资讯")
        username = f"webapi_user_{uuid4().hex[:8]}"
        self.client.post("/api/register", json={"username": username, "password": "pass1234", "interests": "信息检索"})
        me = self.client.get("/api/me")
        self.assertEqual(me.status_code, 200)
        history = self.client.get("/api/history")
        self.assertEqual(history.status_code, 200)
        self.assertIn("rows", history.json())

    def test_account_rejects_bad_login_and_updates_interests(self):
        username = f"account_user_{uuid4().hex[:8]}"
        register = self.client.post(
            "/api/register",
            json={"username": username, "password": "pass1234", "interests": "人工智能"},
        )
        self.assertEqual(register.status_code, 200)

        self.client.post("/api/logout")
        bad_login = self.client.post("/api/login", json={"username": username, "password": "wrong"})
        self.assertEqual(bad_login.status_code, 401)
        self.assertFalse(bad_login.json()["ok"])

        login = self.client.post("/api/login", json={"username": username, "password": "pass1234"})
        self.assertEqual(login.status_code, 200)
        update = self.client.post("/api/profile", json={"interests": "信息检索 图书馆"})
        self.assertEqual(update.status_code, 200)
        me = self.client.get("/api/me")
        self.assertEqual(me.json()["user"]["interests"], "信息检索 图书馆")

    def test_topic_payload_uses_elasticsearch_aggregations(self):
        class FakeClient:
            def search(self, **kwargs):
                return {
                    "aggregations": {
                        "section": {"buckets": [{"key": "anime", "doc_count": 1516}]},
                        "category": {"buckets": [{"key": "动漫资源", "doc_count": 1516}]},
                    }
                }

        class FakeBackend:
            index_name = "nku_pages"
            client = FakeClient()

        payload = topic_payload(FakeBackend())
        sections = {item["key"]: item["indexed_count"] for item in payload["sections"]}
        self.assertEqual(sections["anime"], 1516)
        self.assertIn({"name": "动漫资源", "indexed_count": 1516}, payload["categories"])


if __name__ == "__main__":
    unittest.main()
