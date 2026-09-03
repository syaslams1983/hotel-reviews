from pathlib import Path
import subprocess

SOURCE = Path("/kaggle/working/hotel-reviews/input/stock_media/14558416.mp4")
OUTDIR = Path("/kaggle/working/hotel-reviews/stock_label_test")
OUTPUT = OUTDIR / "001.mp4"

# Find a stock video automatically if the exact test file is not present.
if not SOURCE.exists():
    candidates = list(
        Path("/kaggle/working/hotel-reviews").rglob("*.mp4")
    )
    if not candidates:
        raise FileNotFoundError("No MP4 stock video found in the project.")
    SOURCE = candidates[0]

OUTDIR.mkdir(parents=True, exist_ok=True)

vf = (
    "scale=1920:1080:force_original_aspect_ratio=increase,"
    "crop=1920:1080,setsar=1,"
    "drawbox=x=1575:y=954:w=310:h=66:color=black@0.92:t=fill,"
    "drawtext="
    "text='STOCK VIDEO':"
    "fontcolor=yellow:"
    "fontsize=38:"
    "font='Arial':"
    "x=1595:"
    "y=970"
)

cmd = [
    "ffmpeg", "-y",
    "-i", str(SOURCE),
    "-t", "5",
    "-vf", vf,
    "-an",
    "-c:v", "h264_nvenc",
    "-preset", "p4",
    "-cq", "19",
    "-pix_fmt", "yuv420p",
    "-r", "30",
    str(OUTPUT),
]

print("SOURCE:", SOURCE)
print("OUTPUT:", OUTPUT)
subprocess.run(cmd, check=True)
print("TEST COMPLETE")
print("Open this file and confirm the visible STOCK VIDEO label:")
print(OUTPUT)
