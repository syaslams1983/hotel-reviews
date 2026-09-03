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
VOICE_OUT = EXPORT_DIR / "voice.mp3"
MANIFEST_JSON = EXPORT_DIR / "timeline_manifest.json"
MANIFEST_CSV = EXPORT_DIR / "timeline_manifest.csv"


def run(cmd):
    print("[CMD]", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def export_voice():
    VOICE_OUT.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y",
        "-i", str(VOICE_FILE),
        "-vn",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(VOICE_OUT),
    ])


def stock_label_filter():
    # Visible only on stock-video clips.
    # Use a simple white label with a dark box so it remains readable on any footage.
    return (
        "scale=1920:1080:"
        "force_original_aspect_ratio=increase,"
        "crop=1920:1080,"
        "setsar=1,"
        "drawbox=x=34:y=34:w=250:h=54:color=black@0.72:t=fill,"
        "drawtext=text='STOCK VIDEO':"
        "fontcolor=white:"
        "fontsize=28:"
        "x=52:y=45"
    )


def export_stock_video(source: Path, duration: float, output: Path):
    """Make an exact-duration standalone MP4 for Filmora with STOCK VIDEO label."""
    run([
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(source),
        "-t", f"{duration:.6f}",
        "-vf", stock_label_filter(),
        "-an",
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-cq", "19",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        str(output),
    ])


def export_stock_video_cpu(source: Path, duration: float, output: Path):
    """CPU fallback if NVENC is unavailable for a particular clip."""
    run([
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(source),
        "-t", f"{duration:.6f}",
        "-vf", stock_label_filter(),
        "-an",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        str(output),
    ])


def export_image_cpu(source: Path, duration: float, output: Path):
    """Reliable CPU fallback: image -> 1080p MP4 with subtle centered zoom."""
    frames = max(1, int(round(duration * 30)))
    vf = (
        "scale=1920:1080:force_original_aspect_ratio=increase,"
        "crop=1920:1080,"
        f"zoompan="
        f"z='min(zoom+0.0008,1.08)':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s=1920x1080:fps=30,"
        "setsar=1"
    )
    run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(source),
        "-frames:v", str(frames),
        "-vf", vf,
        "-an",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        str(output),
    ])


def copy_original(source: Path, destination_dir: Path, number: int):
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / f"{number:03d}{source.suffix.lower()}"
    if not target.exists():
        shutil.copy2(source, target)
    return target


def main():
    print("========================================")
    print("KAGGLE -> FILMORA MEDIA EXPORT")
    print("========================================")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    # Build exactly the same visual timeline the current project already uses.
    print("[1/4] Building timeline...")
    builder = TimelineBuilder(
        audio_file=VOICE_FILE,
        images_dir=ORIGINAL_IMAGES_DIR,
    )
    timeline = builder.build()

    if not timeline:
        raise RuntimeError("TimelineBuilder returned no visual clips.")

    print("[2/4] Exporting voice...")
    export_voice()

    print("[3/4] Exporting separate Filmora clips...")
    renderer = Renderer()
    manifest = []
    image_renderer_failures = 0
    video_encoder_fallbacks = 0

    for number, item in enumerate(timeline, start=1):
        source = Path(item["media"])
        if not source.exists():
            print(f"[SKIP] Missing source: {source}")
            continue

        start = float(item["start"])
        end = float(item["end"])
        duration = max(0.001, end - start)

        target = CLIPS_DIR / f"{number:03d}.mp4"

        print(
            f"\n[{number:03d}] "
            f"{start:.3f} -> {end:.3f} "
            f"({duration:.3f}s) | "
            f"{item['media_type']} | {source.name}"
        )

        if item["media_type"] == "image":
            # First try the project's own renderer (keeps its established
            # pan/zoom behavior and GPU path). Fall back to CPU only if it fails.
            try:
                renderer.render_image(
                    image_path=source,
                    duration=duration,
                    output=target,
                    index=number - 1,
                )
            except Exception as exc:
                image_renderer_failures += 1
                print(f"[WARN] Project image renderer failed: {exc}")
                print("[FALLBACK] CPU image pan/zoom render...")
                export_image_cpu(source, duration, target)
        else:
            # Prefer GPU encoding on Kaggle T4; fall back to CPU if necessary.
            try:
                export_stock_video(source, duration, target)
            except subprocess.CalledProcessError as exc:
                video_encoder_fallbacks += 1
                print(f"[WARN] NVENC failed: {exc}")
                print("[FALLBACK] CPU stock-video render...")
                export_stock_video_cpu(source, duration, target)

        original_ref = copy_original(source, EXPORT_DIR / "originals", number)

        manifest.append({
            "clip_number": number,
            "filename": target.name,
            "start": start,
            "end": end,
            "duration": duration,
            "media_type": item["media_type"],
            "source_type": item["source_type"],
            "source_file": str(source),
            "original_reference": str(original_ref),
            "query": item.get("query", ""),
            "sentence_index": item.get("sentence_index"),
            "visual_piece": item.get("visual_piece"),
            "visual_pieces_total": item.get("visual_pieces_total"),
        })

    print("[4/4] Writing manifest...")

    payload = {
        "clip_count": len(manifest),
        "voice": str(VOICE_OUT),
        "clips": manifest,
        "notes": {
            "filename_order": "001.mp4, 002.mp4, 003.mp4 ...",
            "stock_video_label": "STOCK VIDEO is burned into stock-video exports only.",
            "filmora_workflow": (
                "Import voice.mp3 and the clips folder. "
                "Sort media by Name -> Ascending in Filmora. "
                "Place clips in filename order. "
                "Use start/end from the manifest when checking sync."
            ),
            "image_renderer_failures": image_renderer_failures,
            "video_nvenc_fallbacks": video_encoder_fallbacks,
        },
    }

    MANIFEST_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fields = [
        "clip_number",
        "filename",
        "start",
        "end",
        "duration",
        "media_type",
        "source_type",
        "source_file",
        "original_reference",
        "query",
        "sentence_index",
        "visual_piece",
        "visual_pieces_total",
    ]

    with MANIFEST_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)

    print("========================================")
    print(f"CLIPS     : {len(manifest)}")
    print(f"FOLDER    : {CLIPS_DIR.resolve()}")
    print(f"VOICE     : {VOICE_OUT.resolve()}")
    print(f"MANIFEST  : {MANIFEST_JSON.resolve()}")
    print(f"IMG FALLBACKS : {image_renderer_failures}")
    print(f"NVENC FALLBACKS: {video_encoder_fallbacks}")
    print("========================================")


if __name__ == "__main__":
    main()
