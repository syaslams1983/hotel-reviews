from pathlib import Path
import csv
import json
import shutil
import subprocess

from config import VOICE_FILE, ORIGINAL_IMAGES_DIR
from src.timeline_builder import TimelineBuilder
from src.renderer import Renderer

EXPORT_DIR = Path("filmora_export")
CLIPS_DIR = EXPORT_DIR / "clips"
ORIGINALS_DIR = EXPORT_DIR / "originals"
VOICE_OUT = EXPORT_DIR / "voice.mp3"
MANIFEST_JSON = EXPORT_DIR / "timeline_manifest.json"
MANIFEST_CSV = EXPORT_DIR / "timeline_manifest.csv"


def export_audio():
    VOICE_OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(VOICE_FILE),
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(VOICE_OUT),
        ],
        check=True,
    )


def render_video_segment(source, duration, output):
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


def render_image_segment(source, duration, output):
    # Use the project's Renderer so the existing image motion/zoom behavior is
    # preserved as much as possible for Filmora's exported visual clips.
    renderer = Renderer()

    if hasattr(renderer, "render_image"):
        renderer.render_image(
            image_path=source,
            duration=duration,
            output=output,
        )
        return

    # Fallback if the renderer API differs: produce a clean full-frame clip.
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


def copy_original_reference(source, index):
    ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    target = ORIGINALS_DIR / f"{index:03d}{suffix}"
    if not target.exists():
        shutil.copy2(source, target)
    return target


def main():
    print("========================================")
    print("FULL FILMORA EXPORT")
    print("========================================")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/3] Building timeline...")
    builder = TimelineBuilder(
        audio_file=VOICE_FILE,
        images_dir=ORIGINAL_IMAGES_DIR,
    )
    timeline = builder.build()

    if not timeline:
        raise RuntimeError("TimelineBuilder returned no visual items.")

    print("[2/3] Exporting voice...")
    export_audio()

    print("[3/3] Exporting separate Filmora clips...")
    manifest = []

    for idx, item in enumerate(timeline, start=1):
        start = float(item["start"])
        end = float(item["end"])
        duration = end - start

        if duration <= 0:
            continue

        source = Path(item["media"])
        if not source.exists():
            print(f"[SKIP] Missing media: {source}")
            continue

        target = CLIPS_DIR / f"{idx:03d}.mp4"
        original_ref = copy_original_reference(source, idx)

        print(
            f"{idx:03d} | {start:.3f} -> {end:.3f} | "
            f"{duration:.3f}s | {item['source_type']} | {source.name}"
        )

        if item["media_type"] == "image":
            render_image_segment(source, duration, target)
        else:
            render_video_segment(source, duration, target)

        manifest.append(
            {
                "clip_number": idx,
                "filename": target.name,
                "start": start,
                "end": end,
                "duration": duration,
                "media_type": item["media_type"],
                "source_type": item["source_type"],
                "original_source": str(source),
                "original_reference": str(original_ref),
                "query": item.get("query", ""),
                "sentence_index": item.get("sentence_index"),
                "visual_piece": item.get("visual_piece"),
                "visual_pieces_total": item.get("visual_pieces_total"),
            }
        )

    payload = {
        "voice": str(VOICE_OUT),
        "clip_count": len(manifest),
        "clips": manifest,
        "filmora_note": (
            "Import voice.mp3 and clips/001.mp4, 002.mp4, ... "
            "in ascending filename order. Each clip filename maps to the "
            "start/end timestamps in this manifest."
        ),
    }

    MANIFEST_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with MANIFEST_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        fields = [
            "clip_number",
            "filename",
            "start",
            "end",
            "duration",
            "media_type",
            "source_type",
            "original_source",
            "original_reference",
            "query",
            "sentence_index",
            "visual_piece",
            "visual_pieces_total",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)

    print("========================================")
    print(f"Clips    : {len(manifest)}")
    print(f"Folder   : {CLIPS_DIR.resolve()}")
    print(f"Voice    : {VOICE_OUT.resolve()}")
    print(f"Manifest : {MANIFEST_JSON.resolve()}")
    print("========================================")


if __name__ == "__main__":
    main()
