import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml",
    ".ini", ".cfg", ".sh", ".example", ".html", ".css", ".js",
}

SECRET_PATTERNS = {
    "BotFather-style token": re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"),
    "credentialed MongoDB URI": re.compile(
        r"mongodb(?:\+srv)?://[^/\s:@]+:[^@\s]+@",
        re.IGNORECASE,
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def _tracked_files():
    try:
        output = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            stderr=subprocess.DEVNULL,
        )
        return [
            ROOT / item.decode("utf-8")
            for item in output.split(b"\0")
            if item
        ]
    except Exception:
        ignored_dirs = {".git", "venv", ".venv", "env", "__pycache__"}
        files = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in ignored_dirs for part in path.parts):
                continue
            if path.name in {".env", "config.env", "start.sh"}:
                continue
            files.append(path)
        return files


class RepositoryHygieneTests(unittest.TestCase):
    def test_no_runtime_session_files_are_tracked(self):
        bad = []
        for path in _tracked_files():
            name = path.name
            if ".session" in name or name.endswith((".sqlite", ".sqlite3", ".db")):
                bad.append(str(path.relative_to(ROOT)))
        self.assertEqual([], bad, f"Runtime/session databases are tracked: {bad}")

    def test_no_obvious_secrets_are_tracked(self):
        findings = []
        for path in _tracked_files():
            if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
                ".gitignore", ".env.example", "Dockerfile", "Procfile"
            }:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    findings.append(f"{path.relative_to(ROOT)}: {label}")

        self.assertEqual([], findings, "Possible committed secrets found:\n" + "\n".join(findings))


if __name__ == "__main__":
    unittest.main()
