"""SynGen CLI: python -m syngen <generate|validate|new|resume|sessions> ..."""
import argparse
import json
import sys
from pathlib import Path

from syngen.config import ConfigError
from syngen.generator.engine import generate_to_workbook
from syngen.validator.report import render_table, run_validation, to_report_dict


def cmd_generate(args):
    try:
        frames, path = generate_to_workbook(args.config)
    except ConfigError as e:
        print(f"CONFIG ERROR: {e}")
        return 2
    print(f"Wrote {path}")
    print(frames["quarterly_summary"].to_string(index=False))
    return 0


def cmd_validate(args):
    if not Path(args.workbook).exists():
        print(f"NOT FOUND: {args.workbook}")
        return 2
    results, all_pass = run_validation(args.workbook, args.criteria)
    print(render_table(results, all_pass))
    if args.report:
        report = to_report_dict(results, all_pass, args.workbook)
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report written to {args.report}")
    return 0 if all_pass else 1


def _read_story_arg(args):
    if args.story:
        return args.story
    if args.story_file and Path(args.story_file).exists():
        return Path(args.story_file).read_text(encoding="utf-8")
    return None


def cmd_new(args):
    from syngen.llm.client import LLMClient, load_llm_config
    from syngen.pipeline import ConsoleIO, run_new_story

    llm_cfg = load_llm_config(args.llm_config)
    story = _read_story_arg(args)
    if not story:
        print("Paste your business story (end with an empty line):")
        story = "\n".join(iter(input, ""))

    client = LLMClient(llm_cfg)
    io = ConsoleIO() if not args.batch else _BatchIO()
    result = run_new_story(client, story, io, slug=args.slug,
                           use_personas=args.personas)
    return _finish(result)


def cmd_resume(args):
    from syngen.llm.client import LLMClient, load_llm_config
    from syngen.pipeline import ConsoleIO, run_resume

    llm_cfg = load_llm_config(args.llm_config)
    client = LLMClient(llm_cfg)
    io = ConsoleIO() if not args.batch else _BatchIO()
    result = run_resume(args.session, client, io,
                        new_story=_read_story_arg(args))
    return _finish(result)


def cmd_sessions(args):
    from syngen.session import Session

    sessions = Session.list_all(args.dir)
    if not sessions:
        print(f"no sessions found in {args.dir}")
        return 0
    for s in sessions:
        has_criteria = (s / "criteria.json").exists()
        has_sim = (s / "simulator.json").exists()
        state = "ready" if (has_criteria and has_sim) else "incomplete"
        n_versions = len(list(s.glob("story.v*.md")))
        print(f"{s.name}  [{state}]  story_versions={n_versions}")
    return 0


def _finish(result):
    print(f"\nResult: {result['status']}")
    return 0 if result["status"] in ("converged", "delivered_unaccepted") else 1


class _BatchIO:
    """Non-interactive defaults for scripted runs."""

    def inform(self, text):
        from syngen.pipeline import ConsoleIO
        ConsoleIO._safe_print(text)

    def confirm(self, prompt, default=True):
        return default

    def ask(self, prompt, default=""):
        return default

    def free_text(self, prompt):
        return ""


def main(argv=None):
    parser = argparse.ArgumentParser(prog="syngen", description="Story-driven synthetic datasets")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="generate workbook from simulator.json")
    g.add_argument("config", help="path to simulator.json")

    v = sub.add_parser("validate", help="validate a workbook against criteria.json")
    v.add_argument("workbook", help="path to dataset .xlsx")
    v.add_argument("criteria", nargs="?", default="criteria.json",
                   help="path to criteria.json (default: ./criteria.json)")
    v.add_argument("--report", default=None, help="optional path for validation_report.json")

    n = sub.add_parser("new", help="start a new story session (Phase 1-4)")
    n.add_argument("--story", default="", help="story text inline")
    n.add_argument("--story-file", default="", help="path to a .md/.txt story")
    n.add_argument("--slug", default="", help="session folder name hint")
    n.add_argument("--llm-config", default=None, help="path to llm.config.json")
    n.add_argument("--batch", action="store_true",
                   help="accept all defaults without interaction")
    n.add_argument("--personas", action="store_true",
                   help="enable the persona-critique pass (off by default; "
                        "M4 A/B found no quality benefit at ~35s cost)")

    r = sub.add_parser("resume", help="return to an existing session: "
                                      "regenerate or apply a story tweak")
    r.add_argument("session", help="path to the session folder")
    r.add_argument("--story", default="",
                   help="new story text (omit to regenerate as-is)")
    r.add_argument("--story-file", default="",
                   help="path to the revised .md/.txt story")
    r.add_argument("--llm-config", default=None, help="path to llm.config.json")
    r.add_argument("--batch", action="store_true",
                   help="accept all defaults without interaction")

    s = sub.add_parser("sessions", help="list session folders and their state")
    s.add_argument("--dir", default="sessions",
                   help="sessions directory (default: ./sessions)")

    args = parser.parse_args(argv)
    if args.command == "generate":
        return cmd_generate(args)
    if args.command == "validate":
        return cmd_validate(args)
    if args.command == "new":
        return cmd_new(args)
    if args.command == "resume":
        return cmd_resume(args)
    if args.command == "sessions":
        return cmd_sessions(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
