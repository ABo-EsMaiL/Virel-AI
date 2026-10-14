"""Check relocated runtime paths from a different working directory."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class RuntimePathTests(unittest.TestCase):
    def test_relative_profile_and_session_stay_in_project_root(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PYTHONPATH=str(root), CHROME_PROFILE_DIR="runtime/path-fixture")
        code = "from virel import config as c; import json; print(json.dumps([c.CHROME_PROFILE_DIR, c.SESSION_DATA_PATH, c.TEMP_UPLOADS_DIR]))"
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True, check=True)
        paths = [Path(value) for value in json.loads(result.stdout)]
        self.assertEqual(paths, [root / "runtime/path-fixture", root / "runtime/session.json", root / "runtime/uploads"])
        self.assertTrue(all(path.is_absolute() for path in paths))
