"""SynGen CLI: python -m syngen <generate|validate> ..."""
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


def cmd_new(args):
    from syngen.llm.client import LLMClient, load_llm_config
    from syngen.pipeline import ConsoleIO, run_new_story

    llm_cfg = load_llm_config(args.llm_config)
    story = args.story
    if not story and Path(args.story_file).exists():
        story = Path(args.story_file).read_text(encoding="utf-8")
    if not story:
        print("Paste your business story (end with an empty line):")
        story = "\n".join(iter(input, ""))

    client = LLMClient(llm_cfg)
    io = ConsoleIO() if not args.batch else _BatchIO()
    result = run_new_story(client, story, io, slug=args.slug)
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

    args = parser.parse_args(argv)
    if args.command == "generate":
        return cmd_generate(args)
    if args.command == "validate":
        return cmd_validate(args)
    if args.command == "new":
        return cmd_new(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
