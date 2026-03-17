from __future__ import annotations

import logging
import subprocess
from datetime import date
from pathlib import Path
from typing import Iterable, Tuple

logger = logging.getLogger(__name__)


class Encoder:
    def __init__(
        self,
        indexed_dir: Path,
        renders_dir: Path,
        reports_dir: Path,
        fps: int,
        codec: str,
        crf: int,
        preset: str,
        pixel_format: str,
        output_extension: str,
    ) -> None:
        self.indexed_dir = indexed_dir
        self.renders_dir = renders_dir
        self.reports_dir = reports_dir
        self.fps = fps
        self.codec = codec
        self.crf = crf
        self.preset = preset
        self.pixel_format = pixel_format
        self.output_extension = output_extension

    def get_frame_paths(self, capture_date: str) -> list[Path]:
        day_dir = self.indexed_dir / capture_date
        return sorted([p for p in day_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}])

    def render_day(self, capture_date: str) -> Tuple[Path, int]:
        frames = self.get_frame_paths(capture_date)
        if not frames:
            raise FileNotFoundError(f"No frames found for {capture_date}")

        self.renders_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        list_file = self.reports_dir / f"{capture_date}_ffmpeg_input.txt"
        with list_file.open("w", encoding="utf-8") as f:
            for frame in frames:
                f.write(f"file '{frame.resolve()}'\n")

        output_video = self.renders_dir / f"{capture_date}.{self.output_extension}"
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-framerate",
            str(self.fps),
            "-vsync",
            "cfr",
            "-c:v",
            self.codec,
            "-preset",
            self.preset,
            "-crf",
            str(self.crf),
            "-pix_fmt",
            self.pixel_format,
            str(output_video),
        ]
        logger.info("Running ffmpeg for %s", capture_date)
        subprocess.run(cmd, check=True)
        self.write_report(capture_date, frames, output_video)
        return output_video, len(frames)

    def write_report(self, capture_date: str, frames: list[Path], output_video: Path) -> Path:
        report_file = self.reports_dir / f"{capture_date}.txt"
        first = frames[0].name if frames else "N/A"
        last = frames[-1].name if frames else "N/A"
        duration_seconds = len(frames) / self.fps if self.fps else 0
        with report_file.open("w", encoding="utf-8") as f:
            f.write(f"Capture date: {capture_date}\n")
            f.write(f"Frame count: {len(frames)}\n")
            f.write(f"First frame: {first}\n")
            f.write(f"Last frame: {last}\n")
            f.write(f"Output video: {output_video}\n")
            f.write(f"Render FPS: {self.fps}\n")
            f.write(f"Estimated duration seconds: {duration_seconds:.2f}\n")
        return report_file
