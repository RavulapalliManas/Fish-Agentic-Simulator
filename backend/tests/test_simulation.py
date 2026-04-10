from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from renderer.video_exporter import ExportControl, VideoExporter  # noqa: E402
from simulation import StimulusEngine, build_preview_clip, sample_preview_state  # noqa: E402
from utils.config import StimulusConfig  # noqa: E402


class StimulusEngineTests(unittest.TestCase):
    def test_config_supports_three_minute_duration(self) -> None:
        config = StimulusConfig(video_duration=180.0, time_in_center=30.0, time_to_split=110.0)
        self.assertEqual(config.video_duration, 180.0)
        self.assertEqual(config.time_in_center, 30.0)
        self.assertEqual(config.time_to_split, 110.0)

    def test_config_requires_exact_split_counts(self) -> None:
        with self.assertRaises(ValueError):
            StimulusConfig(number_of_agents=10, left_count=4, right_count=5)

    def test_split_phase_uses_requested_left_and_right_counts(self) -> None:
        config = StimulusConfig(
            video_duration=8.0,
            fps=60,
            number_of_agents=31,
            left_count=11,
            right_count=20,
            time_to_split=4.0,
        )
        engine = StimulusEngine(config)
        target_frame = int(round((config.time_to_split + config.dt) * config.fps))
        for _ in range(target_frame):
            engine.step()

        self.assertEqual(engine.phase, "split")
        self.assertEqual(engine.metrics["left_count"], 11)
        self.assertEqual(engine.metrics["right_count"], 20)

    def test_post_split_clusters_remain_tight_near_their_attractors(self) -> None:
        config = StimulusConfig(
            video_duration=10.0,
            fps=60,
            number_of_agents=48,
            left_count=20,
            right_count=28,
        )
        engine = StimulusEngine(config)
        for _ in range(config.total_frames - 1):
            engine.step()

        left_distances: list[float] = []
        right_distances: list[float] = []
        for agent in engine.agents:
            if agent.group == "left":
                left_distances.append(float(np.linalg.norm(agent.position - config.left_attractor)))
            elif agent.group == "right":
                right_distances.append(float(np.linalg.norm(agent.position - config.right_attractor)))

        self.assertEqual(len(left_distances), config.left_count)
        self.assertEqual(len(right_distances), config.right_count)
        self.assertLess(max(left_distances), config.target_cluster_radius)
        self.assertLess(max(right_distances), config.target_cluster_radius)
        self.assertLess(float(engine.metrics["avg_speed"]), config.speed * 0.2)

        minimum_distance = min(
            float(np.linalg.norm(first.position - second.position))
            for index, first in enumerate(engine.agents)
            for second in engine.agents[index + 1 :]
        )
        self.assertGreaterEqual(minimum_distance, config.minimum_agent_spacing * 0.9)

    def test_preview_sampling_respects_requested_phase(self) -> None:
        config = StimulusConfig()
        preview = sample_preview_state(config, "stabilize")
        self.assertEqual(preview.phase, "stabilize")
        self.assertEqual(len(preview.agents), config.number_of_agents)

    def test_preview_clip_returns_multiple_frames_and_warnings(self) -> None:
        config = StimulusConfig(noise=0.36)
        preview = build_preview_clip(config, "split")
        self.assertEqual(preview.phase, "split")
        self.assertGreater(len(preview.frames), 12)
        self.assertGreaterEqual(preview.preview_agent_count, 20)
        self.assertTrue(any("Noise level" in warning for warning in preview.warnings))

    def test_exporter_stop_preserves_partial_video_and_metadata(self) -> None:
        config = StimulusConfig(
            video_duration=2.0,
            fps=12,
            output_width=160,
            output_height=120,
        )
        control = ExportControl()

        def progress_callback(completed: int, total: int, eta_seconds: float, phase: str) -> None:
            del total, eta_seconds, phase
            if completed >= 4:
                control.request_stop()

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "partial.mp4"
            result = VideoExporter(config, progress_callback=progress_callback, control=control).export(str(output_path))

            self.assertEqual(result.status, "stopped")
            self.assertTrue(output_path.exists())
            self.assertLess(result.frames_rendered, config.total_frames)
            self.assertTrue(output_path.with_suffix(".json").exists())

            metadata = json.loads(output_path.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "stopped")
            self.assertEqual(metadata["frames_rendered"], result.frames_rendered)
            self.assertIn(metadata["writer_backend"], {"opencv", "ffmpeg"})

    def test_exporter_cancel_removes_partial_output(self) -> None:
        config = StimulusConfig(
            video_duration=2.0,
            fps=12,
            output_width=160,
            output_height=120,
        )
        control = ExportControl()

        def progress_callback(completed: int, total: int, eta_seconds: float, phase: str) -> None:
            del total, eta_seconds, phase
            if completed >= 3:
                control.request_cancel()

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "cancelled.mp4"
            result = VideoExporter(config, progress_callback=progress_callback, control=control).export(str(output_path))

            self.assertEqual(result.status, "cancelled")
            self.assertFalse(output_path.exists())
            self.assertFalse(output_path.with_suffix(".json").exists())
            self.assertIsNone(result.metadata_path)
            self.assertIn(result.writer_backend, {"opencv", "ffmpeg"})


if __name__ == "__main__":
    unittest.main()
