"""Session folders: one project, self-contained, replayable (contracts section 8)."""
import re
from datetime import date
from pathlib import Path


class Session:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create(cls, base_dir="sessions", slug=None):
        slug = slug or "story"
        slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")[:40] or "story"
        stamp = date.today().strftime("%Y-%m-%d")
        existing = 0
        candidate = Path(base_dir) / f"{stamp}_{slug}"
        while candidate.exists():
            existing += 1
            candidate = Path(base_dir) / f"{stamp}_{slug}_{existing + 1}"
        session = cls(candidate)
        session.log(f"# Session {candidate.name}")
        return session

    def log(self, text):
        with open(self.root / "session_log.md", "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n\n")

    def write_artifact(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.log(f"Artifact written: {name} ({len(content)} chars)")
        return path

    def read_artifact(self, name):
        return (self.root / name).read_text(encoding="utf-8")

    def llm_logger(self):
        def log_fn(text):
            self.log(text)
        return log_fn
