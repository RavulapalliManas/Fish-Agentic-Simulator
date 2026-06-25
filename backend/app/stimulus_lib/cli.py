"""CLI for the stimulus platform.

    python -m app.stimulus_lib.cli render  path/to/spec.json [--out DIR]
    python -m app.stimulus_lib.cli list-tasks
    python -m app.stimulus_lib.cli make-task omr --param temporal_freq_hz=4 --param duration_s=6 [--out DIR]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .render import render_experiment
from .spec import ExperimentSpec, load_spec


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

    ramp_parser = sub.add_parser("calibration-ramp", help="Print the luminance levels to display for measurement")
    ramp_parser.add_argument("--n", type=int, default=17, help="Number of ramp levels")

    cal_parser = sub.add_parser("calibrate", help="Build a measured-luminance calibration LUT from a CSV of level,luminance")
    cal_parser.add_argument("csv", help="CSV with two columns: pixel level in [0,1], measured luminance")
    cal_parser.add_argument("--out", default="calibration.json", help="Output calibration JSON path")
    cal_parser.add_argument("--display-id", default="unspecified-display")
    cal_parser.add_argument("--instrument", default="unspecified")

    qa_parser = sub.add_parser("qa", help="Build an HTML QA report for a render directory")
    qa_parser.add_argument("render_dir")

    timing_parser = sub.add_parser("decode-timing", help="Decode the baked sync marker and report frame timing")
    timing_parser.add_argument("render_dir")

    verify_parser = sub.add_parser("verify", help="Write or check a golden-frame fingerprint for a render")
    verify_parser.add_argument("render_dir")
    verify_parser.add_argument("--golden", help="Golden JSON to verify the render against")
    verify_parser.add_argument("--write-golden", help="Write a golden JSON for this render")

    repro_parser = sub.add_parser("reproduce", help="Re-render from a manifest and verify config + frame hashes")
    repro_parser.add_argument("manifest")
    repro_parser.add_argument("--out", required=True)

    events_parser = sub.add_parser("export-events", help="Write a BIDS-style events.tsv for a spec")
    events_parser.add_argument("spec")
    events_parser.add_argument("--out", default="events.tsv")

    sub.add_parser("smoke-test", help="Render a tiny known stimulus and validate the whole pipeline end-to-end")

    batch_parser = sub.add_parser("batch", help="Render a sweep (JSON: base, axes, presentation_seed) with job management")
    batch_parser.add_argument("sweep", help="Sweep JSON: {base:<spec>, axes:[{path,values}], presentation_seed}")
    batch_parser.add_argument("--out", required=True, help="Output root directory")
    batch_parser.add_argument("--force", action="store_true", help="Re-render even if a matching render exists")
    batch_parser.add_argument("--dry-run", action="store_true", help="Report condition count + cost estimate, render nothing")
    batch_parser.add_argument("--workers", type=int, default=None)

    index_parser = sub.add_parser("index", help="Build a JSON index over a rendered set")
    index_parser.add_argument("out_root")

    table_parser = sub.add_parser("table", help="Condition table (csv/md) for a rendered set")
    table_parser.add_argument("out_root")
    table_parser.add_argument("--fmt", default="csv", choices=["csv", "md"])

    playlist_parser = sub.add_parser("playlist", help="Export a presentation playlist for a rendered set")
    playlist_parser.add_argument("out_root")
    playlist_parser.add_argument("--fmt", default="csv", choices=["csv", "psychopy", "bonsai", "stytra"])

    sheet_parser = sub.add_parser("contact-sheet", help="Thumbnail strip (PNG) for one render")
    sheet_parser.add_argument("render_dir")
    sheet_parser.add_argument("--out", required=True)
    sheet_parser.add_argument("--n", type=int, default=6)

    gallery_parser = sub.add_parser("gallery", help="Contact-sheet grid (PNG) across a rendered set")
    gallery_parser.add_argument("out_root")
    gallery_parser.add_argument("--out", required=True)

    diff_parser = sub.add_parser("diff", help="Difference image (PNG) between two renders")
    diff_parser.add_argument("dir_a")
    diff_parser.add_argument("dir_b")
    diff_parser.add_argument("--out", required=True)
    diff_parser.add_argument("--frame", type=int, default=0)

    qab_parser = sub.add_parser("qa-batch", help="Aggregate QA over a rendered set into one HTML report")
    qab_parser.add_argument("out_root")

    session_parser = sub.add_parser("session", help="Build a session (JSON: items, iti_s, repeats, randomize, seed) -> manifest + events")
    session_parser.add_argument("session")
    session_parser.add_argument("--out", default="session")

    args = parser.parse_args(argv)

    if args.command == "render":
        spec = load_spec(args.spec)
        _print_render(render_experiment(spec, args.out or f"output/stimuli/{spec.name}"))
        return

    if args.command == "list-tasks":
        from .tasks import list_tasks

        print(json.dumps(list_tasks(), indent=2))
        return

    if args.command == "calibration-ramp":
        from .calibration import luminance_ramp_levels

        print(json.dumps({"levels": luminance_ramp_levels(args.n)}, indent=2))
        return

    if args.command == "calibrate":
        import csv as _csv

        from .calibration import Calibration

        levels, luminances = [], []
        with open(args.csv, newline="", encoding="utf-8") as handle:
            for row in _csv.reader(handle):
                if len(row) < 2:
                    continue
                try:
                    levels.append(float(row[0]))
                    luminances.append(float(row[1]))
                except ValueError:
                    continue  # skip a header row
        calibration = Calibration.from_measurements(
            levels, luminances, display_id=args.display_id, instrument=args.instrument
        )
        calibration.save(args.out)
        print(json.dumps({
            "saved": args.out,
            "n_levels": len(levels),
            "max_luminance": calibration.max_luminance,
            "calibration_hash": calibration.identity_hash(),
        }, indent=2))
        return

    if args.command == "qa":
        from .qa_report import build_qa_report

        print(json.dumps({"qa_report": build_qa_report(args.render_dir)}, indent=2))
        return

    if args.command == "decode-timing":
        from .sync_decode import analyze_timing, decode_sequence

        decoded = decode_sequence(Path(args.render_dir) / "frames")
        print(json.dumps(analyze_timing(decoded), indent=2))
        return

    if args.command == "verify":
        from .regression import verify_against_golden, write_golden

        if args.write_golden:
            print(json.dumps(write_golden(args.render_dir, args.write_golden), indent=2))
        elif args.golden:
            print(json.dumps(verify_against_golden(args.render_dir, args.golden), indent=2))
        else:
            raise SystemExit("verify requires --golden or --write-golden")
        return

    if args.command == "reproduce":
        from .regression import reproduce

        print(json.dumps(reproduce(args.manifest, args.out), indent=2))
        return

    if args.command == "export-events":
        from .events import spec_events, write_events_tsv

        rows = spec_events(load_spec(args.spec))
        path = write_events_tsv(rows, args.out)
        print(json.dumps({"events": path, "n_rows": len(rows)}, indent=2))
        return

    if args.command == "smoke-test":
        import tempfile

        from .qa_report import build_qa_report
        from .regression import reproduce
        from .sync_decode import analyze_timing, decode_sequence
        from .tasks import build_task

        work = Path(tempfile.mkdtemp())
        spec = build_task("omr", duration_s=0.3)
        spec.geometry = {"screen_w_px": 320, "screen_h_px": 200}
        spec.render = {**spec.render, "sync_marker": True}
        result = render_experiment(spec, work / "smoke")
        decoded = decode_sequence(work / "smoke" / "frames")
        rep = reproduce(work / "smoke" / f"{spec.name}.manifest.json", work / "repro")
        checks = {
            "rendered": result["n_frames"] > 0,
            "lossless": bool(result["manifest"]["qa"]["lossless_verified"]),
            "timing_round_trip": decoded == list(range(result["n_frames"])),
            "timing_ok": analyze_timing(decoded, expected_n=result["n_frames"])["ok"],
            "qa_report": Path(build_qa_report(work / "smoke")).exists(),
            "reproducible": rep["config_hash_match"] and rep["frames_hash_match"],
        }
        ok = all(checks.values())
        print(json.dumps({"smoke_test": "PASS" if ok else "FAIL", "checks": checks}, indent=2))
        if not ok:
            raise SystemExit(1)
        return

    if args.command == "batch":
        from .batch import estimate_cost, render_batch
        from .sweep import expand_sweep

        cfg = json.loads(Path(args.sweep).read_text(encoding="utf-8"))
        base_cfg = cfg.get("base", {})
        base = ExperimentSpec(
            name=base_cfg.get("name", "sweep"), seed=int(base_cfg.get("seed", 0)),
            geometry=base_cfg.get("geometry", {}), render=base_cfg.get("render", {}), scene=base_cfg.get("scene", []),
        )
        design = expand_sweep(base, cfg.get("axes", []), presentation_seed=int(cfg.get("presentation_seed", 0)))
        if args.dry_run:
            print(json.dumps(estimate_cost(design), indent=2))
            return
        print(json.dumps(render_batch(design, args.out, force=args.force, max_workers=args.workers)["summary"], indent=2))
        return

    if args.command == "index":
        from .index import build_index

        print(json.dumps(build_index(args.out_root), indent=2))
        return

    if args.command == "table":
        from .index import build_index, condition_table

        print(condition_table(build_index(args.out_root), fmt=args.fmt))
        return

    if args.command == "playlist":
        from .index import build_index, export_playlist

        print(export_playlist(build_index(args.out_root), fmt=args.fmt))
        return

    if args.command == "contact-sheet":
        from .preview import contact_sheet, save_image

        print(json.dumps({"saved": save_image(contact_sheet(args.render_dir, n=args.n), args.out)}, indent=2))
        return

    if args.command == "gallery":
        from .preview import gallery, save_image

        print(json.dumps({"saved": save_image(gallery(args.out_root), args.out)}, indent=2))
        return

    if args.command == "diff":
        from .preview import diff_image, save_image

        print(json.dumps({"saved": save_image(diff_image(args.dir_a, args.dir_b, frame_index=args.frame), args.out)}, indent=2))
        return

    if args.command == "qa-batch":
        from .qa_checks import batch_qa_report

        result = batch_qa_report(args.out_root)
        print(json.dumps({"html": result["html_path"], "summary": result["summary"]}, indent=2))
        return

    if args.command == "session":
        from .events import write_events_tsv
        from .session import build_session, session_to_events

        cfg = json.loads(Path(args.session).read_text(encoding="utf-8"))
        sess = build_session(
            cfg.get("items", []), iti_s=cfg.get("iti_s", 1.0), repeats=cfg.get("repeats", 1),
            randomize=cfg.get("randomize", True), seed=cfg.get("seed", 0),
        )
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "session.json").write_text(json.dumps(sess, indent=2), encoding="utf-8")
        write_events_tsv(session_to_events(sess), out_dir / "events.tsv")
        print(json.dumps({"out": str(out_dir), "n_trials": sess["n_trials"], "total_duration_s": sess["total_duration_s"]}, indent=2))
        return

    if args.command == "make-task":
        from .tasks import build_task

        spec = build_task(args.name, **_parse_overrides(args.param))
        _print_render(render_experiment(spec, args.out or f"output/stimuli/{spec.name}"))
        return


if __name__ == "__main__":
    main()
