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
    llm_cfg.update(_budget_config(args))
    story = _read_story_arg(args)
    if not story:
        print("Paste your business story (end with an empty line):")
        story = "\n".join(iter(input, ""))

    client = LLMClient(llm_cfg)
    io = ConsoleIO() if not args.batch else _BatchIO()
    stage = getattr(args, "stage", None)
    if stage is not None or getattr(args, "all_stages", False):
        from syngen.runner import create_session_and_run
        result = create_session_and_run(
            story, client, io, slug=args.slug, upto=stage,
            all=bool(getattr(args, "all_stages", False)),
            flags=_stage_flags(args) or None)
        return _finish_stage(result)
    result = run_new_story(client, story, io, slug=args.slug,
                           use_personas=args.personas,
                           stage23=getattr(args, "stage23", "classic"))
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


def _stage_flags(args):
    flags = {}
    for key in ("stage23", "rework_strategy"):
        val = getattr(args, key, None)
        if val:
            flags[key] = val
    if getattr(args, "use_capability", False):
        flags["use_capability"] = True
    return flags


def _budget_config(args):
    """P18: CLI overrides for the per-flight LLM budget."""
    out = {}
    for arg, key in (("max_calls", "max_calls"),
                     ("max_tokens", "max_total_tokens"),
                     ("max_usd", "max_usd"),
                     ("max_seconds", "max_seconds")):
        v = getattr(args, arg, None)
        if v is not None:
            out[key] = v
    if getattr(args, "allow_unbounded", False):
        out["allow_unbounded"] = True
    return out


def _finish_stage(result):
    print(f"\nResult: {result.get('status')}  "
          f"(next stage: {result.get('next_stage')})")
    if result.get("reason"):
        print(f"Reason: {result['reason']}")
    return 0 if result.get("status") in ("converged", "in_progress") else 1


def cmd_run(args):
    """Stage-based execution: resume, run a prefix, or rewind a session."""
    from syngen.llm.client import LLMClient, load_llm_config
    from syngen.pipeline import ConsoleIO
    from syngen.runner import run_stages
    from syngen.session import Session

    session = Session.open(args.session)
    llm_cfg = load_llm_config(args.llm_config)
    llm_cfg.update(_budget_config(args))
    client = LLMClient(llm_cfg)
    io = ConsoleIO() if not args.batch else _BatchIO()
    result = run_stages(session, client, io,
                        upto=args.stage, only=args.only,
                        from_stage=args.from_stage, all=args.all,
                        flags=_stage_flags(args) or None)
    return _finish_stage(result)


def cmd_status(args):
    from syngen.runner import status_rows
    from syngen.session import Session

    session = Session.open(args.session)
    print(f"Session: {session.root}")
    for n, name, st, mark in status_rows(session):
        print(f"  {n}  {name:<10} {st:<10} {mark}")
    return 0


def cmd_fly(args):
    """Solo-flight harness: full pipeline, zero interaction, telemetry."""
    from syngen.fly import run_fly
    from syngen.llm.client import LLMClient, load_llm_config

    story = _read_story_arg(args)
    if not story:
        print("fly needs --story or --story-file")
        return 2
    llm_cfg = load_llm_config(args.llm_config)
    llm_cfg.update(_budget_config(args))
    client = LLMClient(llm_cfg)
    report = run_fly(story, client, slug=args.slug,
                     stage23=getattr(args, "stage23", "classic"),
                     upto=getattr(args, "stage", None))
    print(json.dumps({k: v for k, v in report.items()
                      if k != "telemetry"}, indent=2, default=str))
    return 0 if report["status"] in ("converged", "in_progress") else 1


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


def _normalize_argv(argv):
    """Accept `--stage-3` as sugar for `--stage 3`."""
    import re
    out = []
    for a in (argv if argv is not None else sys.argv[1:]):
        m = re.fullmatch(r"--stage-(\d+)", a)
        if m:
            out.extend(["--stage", m.group(1)])
        else:
            out.append(a)
    return out


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
    n.add_argument("--stage23", default="classic",
                   choices=("classic", "split"),
                   help="stage 2/3 drafting: classic one-prompt or split "
                        "block-by-block (P11)")
    n.add_argument("--stage", type=int, default=None,
                   help="run the stage runner up to and including stage N")
    n.add_argument("--all-stages", action="store_true",
                   help="run every stage through the stage runner")
    n.add_argument("--use-capability", action="store_true",
                   help="enable the capability workbench (stage runner)")

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

    f = sub.add_parser("fly", help="solo flight: non-interactive end-to-end "
                                   "run with a fly_report.json telemetry file")
    f.add_argument("--story", default="", help="story text inline")
    f.add_argument("--story-file", default="", help="path to a .md/.txt story")
    f.add_argument("--slug", default="", help="session folder name hint")
    f.add_argument("--llm-config", default=None, help="path to llm.config.json")
    f.add_argument("--stage23", default="classic",
                   choices=("classic", "split"),
                   help="stage 2/3 drafting: classic one-prompt or split "
                        "block-by-block (P11)")
    f.add_argument("--stage", type=int, default=None,
                   help="run the stage runner up to and including stage N")

    rn = sub.add_parser("run", help="stage-based execution: resume, run a "
                                    "prefix, or rewind a session")
    rn.add_argument("session", help="path to the session folder")
    rn.add_argument("--all", action="store_true",
                    help="run all remaining stages")
    rn.add_argument("--stage", type=int, default=None,
                    help="run up to and including stage N (--stage-3)")
    rn.add_argument("--only", type=int, default=None,
                    help="run exactly stage N")
    rn.add_argument("--from", dest="from_stage", type=int, default=None,
                    help="rewind to stage N and run forward")
    rn.add_argument("--llm-config", default=None, help="path to llm.config.json")
    rn.add_argument("--batch", action="store_true",
                    help="accept all defaults without interaction")
    rn.add_argument("--stage23", default=None, choices=("classic", "split"))
    rn.add_argument("--use-capability", action="store_true")

    st = sub.add_parser("status", help="show stage progress for a session")
    st.add_argument("session", help="path to the session folder")

    # P18: per-flight budget flags on every run-producing command.
    for p in (n, rn, f):
        p.add_argument("--max-calls", type=int, default=None, dest="max_calls",
                       help="hard cap on LLM calls per flight (P18)")
        p.add_argument("--max-tokens", type=int, default=None,
                       dest="max_tokens",
                       help="hard cap on total tokens per flight (P18)")
        p.add_argument("--max-usd", type=float, default=None, dest="max_usd",
                       help="hard cap on estimated spend (needs prices) (P18)")
        p.add_argument("--max-seconds", type=int, default=None,
                       dest="max_seconds",
                       help="hard wall-clock cap per flight (P18)")
        p.add_argument("--allow-unbounded", action="store_true",
                       help="do NOT apply default hosted budget caps (P18)")

    args = parser.parse_args(_normalize_argv(argv))
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
    if args.command == "fly":
        return cmd_fly(args)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "status":
        return cmd_status(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
