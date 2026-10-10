"""Use isolated scratch data and no real credentials for automated checks."""
import os
import tempfile

_test_data = tempfile.mkdtemp(prefix="aibaa-tests-")
os.environ["AIBAA_DATA_DIR"] = _test_data
os.environ["DATABASE_URL"] = "sqlite:///" + _test_data + "/aibaa.db"
os.environ["AIBAA_API_BOOTSTRAP_TOKEN"] = "dev-local-token"
os.environ["AIBAA_JWT_SECRET"] = "aibaa-test-secret-at-least-32-characters"
os.environ["AIBAA_ENV"] = "development"
os.environ["AIBAA_DEV_AUTH_ENABLED"] = "true"
os.environ["GEMINI_API_KEY"] = ""
os.environ["NVIDIA_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = "auto"
os.environ["SERPAPI_API_KEY"] = ""
os.environ["AIBAA_RESEARCH_MODE"] = "live"
