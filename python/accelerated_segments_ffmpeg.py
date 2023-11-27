from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from random import randint
from pathlib import Path
import subprocess

@dataclass
class VideoTimestamp:
    """Handles video timestamps and provides manipulation methods."""
    timestamp: str = None
    type: Literal["+", "-", "|"] = None
    hour: int = None
    minute: int = None
    second: int = None
    orientation: Literal["negative", "positive"] = "positive"

    def __post_init__(self):
        time_atts = [self.hour, self.minute, self.second, self.type]
        if all([attr is not None for attr in time_atts]):
            leading_char = self.type if self.type != "|" else ""
            self.timestamp = (
                f"{leading_char}{self.hour:02d}:{self.minute:02d}:{self.second:02d}"
            )
            return
        try:
            type = self.timestamp[0]
            if type != "+" and type != "-" and type != "|":
                type = "|"
            self.type = type
            self.timestamp = self.timestamp.replace(type, "")
            split_timestamp = self.timestamp.split(":")
            self.hour = int(split_timestamp[0])
            self.minute = int(split_timestamp[1])
            self.second = int(split_timestamp[2])
        except (KeyError, ValueError):
            raise ValueError("invalid timestamp format. Accepted format: [type]hh:mm:ss")

    @classmethod
    def from_seconds(cls, seconds: int):
        if seconds < 0:
            seconds = abs(seconds)
            orientation = "negative"
        else:
            orientation = "positive"
        return cls(
            None,
            "|",
            seconds // 3600,
            (seconds % 3600) // 60,
            seconds % 60,
            orientation,
        )

    def plus(self, vt: VideoTimestamp):
        return VideoTimestamp.from_seconds(self.total_seconds + vt.total_seconds)

    def minus_seconds(self, seconds: int):
        return self.plus_seconds(-seconds)

    def plus_seconds(self, seconds: int):
        total_seconds = self.total_seconds + seconds
        return VideoTimestamp.from_seconds(total_seconds)

    def minus(self, vt: VideoTimestamp):
        total_seconds = self.total_seconds - vt.total_seconds
        return VideoTimestamp.from_seconds(total_seconds)

    @property
    def total_seconds(self) -> int:
        return self.hour * 3600 + self.minute * 60 + self.second

    def __add__(self, other: VideoTimestamp):
        if isinstance(other, int):
            return self.plus_seconds(other)
        return self.plus(other)

    def __sub__(self, other: VideoTimestamp):
        if isinstance(other, int):
            return self.minus_seconds(other)
        return self.minus(other)

    def __lt__(self, other: VideoTimestamp) -> bool:
        return self.total_seconds < other.total_seconds

    def __gt__(self, other: VideoTimestamp) -> bool:
        return self.total_seconds > other.total_seconds

    def __eq__(self, other: VideoTimestamp) -> bool:
        return self.total_seconds == other.total_seconds

    def __ge__(self, other: VideoTimestamp) -> bool:
        return self > other or self == other

    def __le__(self, other: VideoTimestamp) -> bool:
        return self < other or self == other

    def __floordiv__(self, other: VideoTimestamp) -> int:
        return self.total_seconds // other.total_seconds

    def __truediv__(self, other: VideoTimestamp) -> float:
        return self.total_seconds / other.total_seconds


def ffmpeg_cmd(
    input: str,
    output: str,
    start: str = "",
    to: str = "",
    velocity: int = 1,
    other_args: list[str] = [],
) -> list[str]:
    """Generates an FFmpeg command to process video segments."""
    pts = round(1 / velocity, 2)
    velocity = float(velocity)
    return [
        "ffmpeg",
        "-ss",
        start,
        "-to",
        to,
        "-i",
        input,
        "-filter_complex",
        f"[0:v]setpts={pts}*PTS[v];[0:a]atempo={velocity}[a]",
        "-map",
        "[v]",
        "-map",
        "[a]",
        output,
    ]


def parse_timestamps(file_path: str) -> list[str]:
    """Reads and parses timestamps from a file."""
    with open(file_path, "r") as f:
        txt = f.read()
    split = txt.split("\n")
    return [line.strip() for line in split if line != ""]


def get_vel(
    vt1: VideoTimestamp,
    vt2: VideoTimestamp,
    min_speed_duration="00:00:10",
    max_speed_duration="00:00:30",
) -> int:
    """Used to get a random acceleration with different segments"""
    if (vt1 - vt2).total_seconds < 0:
        raise ValueError("vt1 must be greater than vt2")
    min_speed_duration = VideoTimestamp(min_speed_duration)
    if vt2 - vt1 <= min_speed_duration:
        return 1
    max_speed_duration = VideoTimestamp(max_speed_duration)
    random_duration = VideoTimestamp(
        None,
        type="|",
        hour=randint(min_speed_duration.hour, max_speed_duration.hour),
        minute=randint(min_speed_duration.minute, max_speed_duration.minute),
        second=randint(min_speed_duration.second, max_speed_duration.second),
    )
    return int((vt2 - vt1) / random_duration)


def process_video(
    timestamps: list[str], rest_time: str, input_file="", out_folder=""
) -> (list[int], VideoTimestamp):
    offset = VideoTimestamp("00:00:00")
    input_file = Path(input_file)
    out_folder = Path(out_folder)
    rest_time = VideoTimestamp(rest_time)
    for i in range(len(timestamps) - 1):
        out_file_vel = out_folder / f"{input_file.stem}_{i}_2{input_file.suffix}"
        out_file_rest = out_folder / f"{input_file.stem}_{i}_1{input_file.suffix}"

        vt1 = VideoTimestamp(timestamps[i]) - offset
        vt2 = VideoTimestamp(timestamps[i + 1]) - offset

        print(f"vt1: {vt1.timestamp}")
        print(f"vt2: {vt2.timestamp}")
        print(f"rest time: {rest_time.timestamp}")

        vel = min(get_vel((vt1+rest_time), vt2), 70)

        if((vt2 - vt1).total_seconds < 25):
            rest_to_ts = vt2.timestamp
            vel = 1
        else:
            rest_to_ts = (vt1+rest_time).timestamp

        cmd_rest_seg = ffmpeg_cmd(
            str(input_file),
            str(out_file_rest),
            start=vt1.timestamp,
            to=rest_to_ts,
            velocity=1,
        )

        if((vt2 - vt1).total_seconds > 25):
            cmd_vel_seg = ffmpeg_cmd(
                str(input_file),
                str(out_file_vel),
                start=(vt1+rest_time).timestamp,
                to=vt2.timestamp,
                velocity=vel,
            )
            if(not out_file_vel.exists()):
                subprocess.check_output(cmd_vel_seg)

        print("cmd_rest_seg: ", cmd_rest_seg)


        if(not out_file_rest.exists()):
            subprocess.check_output(cmd_rest_seg)