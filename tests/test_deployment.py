import tomllib
import unittest
from pathlib import Path

from vietlott_mega645.storage import DEFAULT_DATASET_PATH, load_records


ROOT = Path(__file__).resolve().parents[1]


class DeploymentConfigTests(unittest.TestCase):
    def test_streamlit_entrypoint_is_at_repo_root(self):
        self.assertTrue((ROOT / "streamlit_app.py").exists())

    def test_requirements_pins_streamlit(self):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("streamlit==1.57.0", text)
        self.assertIn("pandas>=2.2", text)

    def test_community_cloud_config_toml(self):
        config_path = ROOT / ".streamlit" / "config.toml"
        self.assertTrue(config_path.exists())
        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
        self.assertTrue(parsed["server"]["headless"])
        self.assertFalse(parsed["browser"]["gatherUsageStats"])
        self.assertNotIn("port", parsed.get("server", {}))

    def test_official_jsonl_is_shipped(self):
        records = load_records(DEFAULT_DATASET_PATH)
        self.assertGreaterEqual(len(records), 1000)
        self.assertEqual(records[-1].id, "01561")

    def test_dockerfile_follows_official_streamlit_healthcheck(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM python:3.12-slim", dockerfile)
        self.assertIn("/_stcore/health", dockerfile)
        self.assertIn("streamlit_app.py", dockerfile)
        self.assertIn("--server.address=0.0.0.0", dockerfile)

    def test_gitignore_keeps_firecrawl_and_secrets_out_of_git(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".firecrawl/", ignore)
        self.assertIn("!.streamlit/config.toml", ignore)


if __name__ == "__main__":
    unittest.main()
