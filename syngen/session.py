"""Session folders: one project, self-contained, replayable (contracts section 8).

M3 rules:
- history/ is append-only: every convergence iteration archives its exact
  simulator.json + validation_report.json; current files reflect latest state.
- story text is versioned: story.v1.md, story.v2.md, ... story.md stays as a
  convenience pointer (copy) to the latest version.
"""
import json
import re
from datetime import date
from pathlib import Path


class SessionError(ValueError):
    pass


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

    @classmethod
    def open(cls, path):
        root = Path(path)
        if not root.is_dir():
            raise SessionError(f"no such session folder: {root}")
        if not (root / "session_log.md").exists():
            raise SessionError(f"not a SynGen session (missing session_log.md): {root}")
        session = cls(root)
        session.log(f"--- session reopened ---")
        return session

    # -- logging -----------------------------------------------------------

    def log(self, text):
        with open(self.root / "session_log.md", "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n\n")

    def llm_logger(self):
        def log_fn(text):
            self.log(text)
        return log_fn

    # -- artifacts ---------------------------------------------------------

    def write_artifact(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.log(f"Artifact written: {name} ({len(content)} chars)")
        return path

    def read_artifact(self, name):
        return (self.root / name).read_text(encoding="utf-8")

    # -- history (append-only) ----------------------------------------------

    def archive_iteration(self, iteration, simulator_json_text, report_json_text):
        hist = self.root / "history"
        hist.mkdir(exist_ok=True)
        n = f"{iteration:02d}"
        (hist / f"iter{n}_simulator.json").write_text(
            simulator_json_text, encoding="utf-8")
        (hist / f"iter{n}_validation_report.json").write_text(
            report_json_text, encoding="utf-8")

    # -- story versioning ---------------------------------------------------

    def story_versions(self):
        return sorted(self.root.glob("story.v*.md"))

    def save_story(self, text):
        """Append a new story version. Returns the new version number."""
        n = len(self.story_versions()) + 1
        path = self.root / f"story.v{n}.md"
        path.write_text(text, encoding="utf-8")
        (self.root / "story.md").write_text(text, encoding="utf-8")
        self.log(f"Story saved as story.v{n}.md ({len(text)} chars)")
        return n

    def latest_story(self):
        versions = self.story_versions()
        if not versions:
            legacy = self.root / "story.md"
            if legacy.exists():
                return legacy.read_text(encoding="utf-8")
            raise SessionError(f"no story found in {self.root}")
        return versions[-1].read_text(encoding="utf-8")

    # -- misc ----------------------------------------------------------------

    @staticmethod
    def list_all(base_dir="sessions"):
        base = Path(base_dir)
        if not base.exists():
            return []
        return sorted(p for p in base.iterdir() if p.is_dir() and
                      (p / "session_log.md").exists())
