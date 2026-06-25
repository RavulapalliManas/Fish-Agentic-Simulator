"""CLI for the stimulus platform.

    python -m app.stimulus_lib.cli render  path/to/spec.json [--out DIR]
    python -m app.stimulus_lib.cli list-tasks
    python -m app.stimulus_lib.cli make-task omr --param temporal_freq_hz=4 --param duration_s=6 [--out DIR]
"""

from __future__ import annotations

import argparse
import json

from .render import render_experiment
from .spec import load_spec


def _print_render(result: dict) -> None:
    manifest = result["manifest"]
    print(
        json.dumps(
            {
                "out_dir": result["out_dir"],
                "n_frames": result["n_frames"],
                "config_hash": manifest["config_hash"],
                "git_commit": manifest["git_commit"],
                "qa": manifest["qa"],
                "validation_warnings": manifest["validation_warnings"],
            },
            indent=2,
        )
    )


def _parse_overrides(pairs: list[str]) -> dict:
    overrides = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"--param expects key=value, got {pair!r}")
        key, value = pair.split("=", 1)
        overrides[key.strip()] = value.strip()
    return overrides


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="stimulus_lib", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    render_parser = sub.add_parser("render", help="Render a spec file to a frame sequence + manifest")
    render_parser.add_argument("spec", help="Path to a .json or .yaml experiment spec")
    render_parser.add_argument("--out", default=None, help="Output directory (default: output/stimuli/<name>)")

    sub.add_parser("list-tasks", help="List the paradigm catalog and tunable parameters")

    task_parser = sub.add_parser("make-task", help="Generate and render a named paradigm")
    task_parser.add_argument("name", help="Task name (see list-tasks)")
    task_parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE", help="Override a task parameter (repeatable)")
    task_parser.add_argument("--out", default=None, help="Output directory (default: output/stimuli/<name>)")

    args = parser.parse_args(argv)

    if args.command == "render":
        spec = load_spec(args.spec)
        _print_render(render_experiment(spec, args.out or f"output/stimuli/{spec.name}"))
        return

    if args.command == "list-tasks":
        from .tasks import list_tasks

        print(json.dumps(list_tasks(), indent=2))
        return

    if args.command == "make-task":
        from .tasks import build_task

        spec = build_task(args.name, **_parse_overrides(args.param))
        _print_render(render_experiment(spec, args.out or f"output/stimuli/{spec.name}"))
        return


if __name__ == "__main__":
    main()
