from pathlib import Path
import csv
import json
import subprocess

from config import VOICE_FILE, ORIGINAL_IMAGES_DIR
from src.timeline_builder import TimelineBuilder
from src.renderer import Renderer

TEST_DURATION = 30.0
TEST_AUDIO = Path("filmora_test_30s_audio.mp3")
AUDIO_COPY = Path("filmora_test_export") / "voice_30s.mp3"
EXPORT_DIR = Path("filmora_test_export")
CLIPS_DIR = EXPORT_DIR / "clips"
MANIFEST_JSON = EXPORT_DIR / "timeline_manifest.json"
MANIFEST_CSV = EXPORT_DIR / "timeline_manifest.csv"


def make_test_audio():
    """Create a real 30-second audio input so TimelineBuilder never builds the full video."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(VOICE_FILE),
            "-t", str(TEST_DURATION),
            "-vn",
            "-acodec", "libmp3lame",
            "-b:a", "192k",
            str(TEST_AUDIO),
        ],
        check=True,
    )


def render_video(source, duration, output):
    """Create a self-contained trimmed video clip for Filmora testing."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(source),
            "-t", f"{duration:.6f}",
            "-vf",
            (
                "scale=1920:1080:"
                "force_original_aspect_ratio=increase,"
                "crop=1920:1080:"
                "(in_w-1920)/2:(in_h-1080)/2,"
                "setsar=1"
            ),
            "-an",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            str(output),
        ],
        check=True,
    )


def render_image_simple(source, duration, output):
    """Use FFmpeg for a clean, self-contained image->video test clip."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(source),
            "-t", f"{duration:.6f}",
            "-vf",
            (
                "scale=1920:1080:"
                "force_original_aspect_ratio=increase,"
                "crop=1920:1080:"
                "(in_w-1920)/2:(in_h-1080)/2,"
                "setsar=1"
            ),
            "-an",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            str(output),
        ],
        check=True,
    )


def main():
    print("========================================")
    print("FILMORA 30-SECOND TEST")
    print("========================================")

    EXPORT_DIR.mkdir(exist_ok=True)
    CLIPS_DIR.mkdir(exist_ok=True)

    # IMPORTANT: build only from a 30-second audio file.
    make_test_audio()
    AUDIO_COPY.parent.mkdir(exist_ok=True)
    AUDIO_COPY.write_bytes(TEST_AUDIO.read_bytes())

    builder = TimelineBuilder(
        audio_file=TEST_AUDIO,
        images_dir=ORIGINAL_IMAGES_DIR,
    )

    timeline = builder.build()

    # Hard cap the resulting timeline too, in case transcription produces a
    # final segment slightly beyond the audio boundary.
    selected = []
    for item in timeline:
        start = float(item["start"])
        end = min(TEST_DURATION, float(item["end"]))
        if start >= TEST_DURATION or end <= start:
            continue

        item = dict(item)
        item["start"] = start
        item["end"] = end
        item["duration"] = end - start
        selected.append(item)

    manifest = []

    for export_index, item in enumerate(selected):
        start = float(item["start"])
        end = float(item["end"])
        duration = end - start

        source = Path(item["media"])
        if not source.exists():
            print(f"[SKIP] Missing media: {source}")
            continue

        out_file = CLIPS_DIR / (
            f"{export_index:03d}_{start:09.3f}_{end:09.3f}.mp4"
        )

        print(
            f"[{export_index:03d}] {start:.3f} -> {end:.3f} | "
            f"{item['source_type']} | {source.name}"
        )

        if item["media_type"] == "image":
            render_image_simple(source, duration, out_file)
        else:
            render_video(source, duration, out_file)

        manifest.append(
            {
                "export_index": export_index,
                "start": start,
                "end": end,
                "duration": duration,
                "source_type": item["source_type"],
                "media_type": item["media_type"],
                "source_file": str(source),
                "export_file": str(out_file),
                "query": item.get("query", ""),
                "sentence_index": item.get("sentence_index"),
                "visual_piece": item.get("visual_piece"),
                "visual_pieces_total": item.get("visual_pieces_total"),
            }
        )

    MANIFEST_JSON.write_text(
        json.dumps(
            {
                "test_duration": TEST_DURATION,
                "clip_count": len(manifest),
                "clips": manifest,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with MANIFEST_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        fields = [
            "export_index", "start", "end", "duration",
            "source_type", "media_type", "source_file",
            "export_file", "query", "sentence_index",
            "visual_piece", "visual_pieces_total",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)

    print("========================================")
    print(f"TEST CLIPS : {len(manifest)}")
    print(f"FOLDER     : {CLIPS_DIR.resolve()}")
    print(f"MANIFEST   : {MANIFEST_JSON.resolve()}")
    print(f"AUDIO      : {AUDIO_COPY.resolve()}")
    print("========================================")


if __name__ == "__main__":
    main()
