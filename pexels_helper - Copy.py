import os
import webbrowser
import subprocess
import ctypes
from ctypes import wintypes
from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES, COPY
    DND_AVAILABLE = True
except Exception:
    TkinterDnD = None
    DND_FILES = None
    COPY = 1
    DND_AVAILABLE = False

import requests
from PIL import Image, ImageTk

PROJECT_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = PROJECT_DIR / "_media"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

API_KEY = ""
try:
    import config
    API_KEY = getattr(config, "PEXELS_API_KEY", "") or ""
except Exception:
    pass
API_KEY = API_KEY or os.environ.get("PEXELS_API_KEY", "").strip()

VIDEO_URL = "https://api.pexels.com/videos/search"
PHOTO_URL = "https://api.pexels.com/v1/search"

class PexelsHelper(TkinterDnD.Tk if DND_AVAILABLE else tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Pexels Helper")
        self.geometry("1220x860")
        self.minsize(900, 650)
        self.query = tk.StringVar()
        self.kind = tk.StringVar(value="videos")
        self.status = tk.StringVar(value="Ready")

        self.results = []
        self.current_page = 0
        self.thumb_refs = []
        self.next_download_number = 1
        self.download_cards = []
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_label = tk.StringVar(value="")
        self.progress_bar = None
        self._ui()
        self.after(150, self._apply_native_titlebar)

    def _ui(self):
        top = ttk.Frame(self, padding=(14, 12, 14, 8))
        top.pack(fill="x")

        row = ttk.Frame(top)
        row.pack(fill="x", pady=(6, 0))

        self.search_entry = ttk.Entry(
            row,
            textvariable=self.query,
            font=("Segoe UI", 13),
        )
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.search_entry.bind("<Return>", lambda _e: self.search())

        self.kind_combo = ttk.Combobox(
            row,
            textvariable=self.kind,
            values=("videos", "photos"),
            state="readonly",
            width=12,
            font=("Segoe UI", 11),
        )
        self.kind_combo.pack(side="left", padx=10, ipady=4)

        self.search_button = tk.Button(
            row,
            text="🔎  Search Pexels",
            command=self.search,
            bg="#4a90e2",
            fg="white",
            activebackground="#357abd",
            activeforeground="white",
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            bd=0,
            padx=18,
            pady=9,
            cursor="hand2",
        )
        self.search_button.pack(side="left")
        ttk.Label(
            top,
            text="Search stock video or photo • 12 results per page • See more for additional results",
            foreground="#666666",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(5, 0))
        ttk.Label(top, textvariable=self.status, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 0))

        progress_row = ttk.Frame(top)
        progress_row.pack(fill="x", pady=(6, 0))
        self.progress_bar = ttk.Progressbar(
            progress_row,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        )
        self.progress_bar.pack(side="left", fill="x", expand=True)
        ttk.Label(
            progress_row,
            textvariable=self.progress_label,
            width=22,
        ).pack(side="left", padx=(8, 0))

        self.downloaded_frame = ttk.LabelFrame(
            self,
            text="Downloaded — drag files directly to your editor",
            padding=8,
        )
        self.downloaded_frame.pack(fill="x", padx=14, pady=(0, 8))
        self.downloaded_frame.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 12))

        self.results_frame = ttk.Frame(self.canvas)
        self.canvas.bind_all("<MouseWheel>", self._on_global_mousewheel, add="+")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.results_frame, anchor="nw")
        self.results_frame.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self._render_downloads()
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width),
        )


    def _apply_native_titlebar(self):
        try:
            self.update_idletasks()
            hwnd = wintypes.HWND(self.winfo_id())
            dwmapi = ctypes.windll.dwmapi
            caption = ctypes.c_int(0x00FFEACF)  # light blue #CFEAFF
            text = ctypes.c_int(0x00473012)     # dark blue #123047
            dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))
            dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text), ctypes.sizeof(text))
        except Exception:
            pass

    def _bind_mousewheel(self, widget):
        def on_mousewheel(event):
            delta = -1 * int(event.delta / 120) if event.delta else 0
            if delta:
                self.canvas.yview_scroll(delta, "units")

        widget.bind("<MouseWheel>", on_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_mousewheel(child)


    def _on_mousewheel(self, event):
        if not hasattr(self, "canvas"):
            return
        # Smaller step feels much smoother than the default Tk unit jump.
        if event.delta:
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _on_global_mousewheel(self, event):
        try:
            x = self.winfo_pointerx()
            y = self.winfo_pointery()
            left = self.canvas.winfo_rootx()
            top = self.canvas.winfo_rooty()
            right = left + self.canvas.winfo_width()
            bottom = top + self.canvas.winfo_height()
            if left <= x <= right and top <= y <= bottom:
                return self._on_mousewheel(event)
        except Exception:
            pass

    def _bind_wheel_recursive(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_wheel_recursive(child)

    def _clear(self):
        for c in self.results_frame.winfo_children():
            c.destroy()
        self.thumb_refs.clear()

    def _clear_download_list(self):
        self.download_cards.clear()
        self._render_downloads()
        self.status.set("Downloaded list cleared (files are kept on disk).")

    def _remove_download_card(self, index):
        if 0 <= index < len(self.download_cards):
            removed = self.download_cards.pop(index)
            self._render_downloads()
            self.status.set(
                f"Removed {removed['name']} from the list. File kept on disk."
            )

    def _clear_download_list(self):
        self.download_cards.clear()
        self._render_downloads()
        self.status.set("Downloaded list cleared (files are kept on disk).")

    def _render_downloads(self):
        for child in self.downloaded_frame.winfo_children():
            child.destroy()

        if not self.download_cards:
            ttk.Label(
                self.downloaded_frame,
                text="No downloaded files yet. Download a result and it will appear here.",
                foreground="#666666",
            ).grid(row=0, column=0, sticky="w")
            return

        ttk.Label(
            self.downloaded_frame,
            text="Drag the filename directly into Filmora.",
            foreground="#555555",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        ttk.Button(
            self.downloaded_frame,
            text="Clear list",
            command=self._clear_download_list,
        ).grid(row=0, column=1, sticky="e", pady=(0, 4))

        for i, item in enumerate(self.download_cards, start=1):
            row = ttk.Frame(
                self.downloaded_frame,
                padding=(8, 5),
                relief="solid",
                borderwidth=1,
            )
            row.grid(row=i, column=0, columnspan=2, sticky="ew", pady=2)
            row.columnconfigure(1, weight=1)

            drag_label = ttk.Label(
                row,
                text=item["name"],
                font=("Segoe UI", 10, "bold"),
                foreground="#1f4e79",
                cursor="hand2",
            )
            drag_label.grid(row=0, column=0, sticky="w", padx=(0, 14))

            if DND_AVAILABLE:
                try:
                    drag_label.drag_source_register(1, DND_FILES)

                    def start_drag(_event, path=item["path"]):
                        return (COPY, DND_FILES, (str(path),))

                    drag_label.dnd_bind("<<DragInitCmd>>", start_drag)
                except Exception:
                    pass

            ttk.Label(
                row,
                text=(
                    f"Pexels ID: {item.get('pexels_id', 'n/a')}  •  "
                    f"{item['type']}  •  {item.get('duration_text', '')}"
                ),
            ).grid(row=0, column=1, sticky="w")

            ttk.Button(
                row,
                text="Open",
                command=lambda path=item["path"]: os.startfile(path),
            ).grid(row=0, column=2, padx=3)

            ttk.Button(
                row,
                text="Copy path",
                command=lambda path=item["path"]: (
                    self.clipboard_clear(),
                    self.clipboard_append(str(path)),
                ),
            ).grid(row=0, column=3, padx=3)

            ttk.Button(
                row,
                text="✕",
                command=lambda idx=i - 1: self._remove_download_card(idx),
            ).grid(row=0, column=4, padx=(6, 0))

    def _render(self):
        self._clear()

        per_page = 12
        start = self.current_page * per_page
        end = min(start + per_page, len(self.results))
        page_results = self.results[start:end]

        for i, item in enumerate(page_results):
            r, c = divmod(i, 4)
            card = ttk.Frame(self.results_frame, padding=8, relief="solid", borderwidth=1)
            card.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            self.results_frame.grid_columnconfigure(c, weight=1)

            img_label = ttk.Label(card, text="Loading…")
            img_label.pack()
            if item["thumb"]:
                try:
                    data = requests.get(item["thumb"], timeout=20).content
                    im = Image.open(BytesIO(data)).convert("RGB")
                    im.thumbnail((220, 124))
                    ph = ImageTk.PhotoImage(im)
                    img_label.configure(image=ph, text="")
                    self.thumb_refs.append(ph)
                except Exception:
                    pass

            ttk.Label(
                card,
                text=f"Pexels ID: {item['id']}",
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w")
            if item["type"] == "video":
                duration = item.get("duration")
                duration_text = (
                    f"Duration: {float(duration):.1f} sec"
                    if duration is not None else "Duration: n/a"
                )
                ttk.Label(card, text=duration_text).pack(anchor="w")
            ttk.Label(
                card,
                text=f"{item.get('width','?')} × {item.get('height','?')}"
            ).pack(anchor="w")

            btns = ttk.Frame(card)
            btns.pack(fill="x", pady=(8, 0))
            tk.Button(
                btns,
                text="▶ Preview",
                command=lambda x=item: self.preview(x),
                bg="#27ae60",
                fg="white",
                activebackground="#1e8449",
                activeforeground="white",
                relief="flat",
                bd=0,
                font=("Segoe UI", 9, "bold"),
                padx=16,
                pady=6,
                cursor="hand2",
            ).pack(side="left", padx=(0, 6))

            tk.Button(
                btns,
                text="⬇ Download",
                command=lambda x=item: self.download(x),
                bg="#e67e22",
                fg="white",
                activebackground="#ca6f1e",
                activeforeground="white",
                relief="flat",
                bd=0,
                font=("Segoe UI", 9, "bold"),
                padx=16,
                pady=6,
                cursor="hand2",
            ).pack(side="right")

        self._bind_wheel_recursive(self.results_frame)

        # Navigation row: first page shows first 12, See More reveals 12 more.
        nav = ttk.Frame(self.results_frame, padding=10)
        nav.grid(row=(len(page_results) + 3) // 4, column=0, columnspan=4, sticky="ew")

        total_pages = max(1, (len(self.results) + per_page - 1) // per_page)

        self._bind_mousewheel(self.results_frame)

        if self.current_page > 0:
            ttk.Button(
                nav,
                text="‹ Previous",
                command=self.previous_page,
            ).pack(side="left")

        ttk.Label(
            nav,
            text=f"Results {start + 1}-{end} of {len(self.results)}   •   Page {self.current_page + 1}/{total_pages}",
        ).pack(side="left", padx=12)

        if end < len(self.results):
            ttk.Button(
                nav,
                text="See more",
                command=self.next_page,
            ).pack(side="right")

    def next_page(self):
        if (self.current_page + 1) * 12 < len(self.results):
            self.current_page += 1
            self._render()
            self.status.set(
                f"Showing results {self.current_page * 12 + 1}-"
                f"{min((self.current_page + 1) * 12, len(self.results))} "
                f"of {len(self.results)}"
            )

    def previous_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render()

    def preview(self, item):
        url = item.get("url")
        if not url:
            messagebox.showwarning("Preview", "No preview URL available.")
            return

        # Try local media players first. These can stream the remote MP4 without
        # saving it to disk.
        for player in (
            ["ffplay", "-autoexit", "-window_title", f"Pexels {item.get('id')}", url],
            ["mpv", "--force-window=yes", "--title", f"Pexels {item.get('id')}", url],
        ):
            try:
                subprocess.Popen(player, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.status.set(f"Streaming preview: Pexels {item.get('id')}")
                return
            except FileNotFoundError:
                continue
            except Exception:
                break

        # Last resort: open the direct URL in the browser. Some browsers may
        # download CDN video URLs instead of playing them, so this is only a fallback.
        try:
            webbrowser.open(url)
            self.status.set("Opened Pexels preview URL in browser.")
        except Exception as exc:
            messagebox.showerror("Preview failed", str(exc))

    def _ask_duration(self, original_duration, pexels_id):
        """Ask for output duration and provide a one-click Original duration fill."""
        original = float(original_duration)
        result = {"value": None}

        dlg = tk.Toplevel(self)
        dlg.title("Video duration")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        body = ttk.Frame(dlg, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(
            body,
            text=f"Pexels ID: {pexels_id}",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(
            body,
            text="Original duration:",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        original_var = tk.StringVar(value=f"{original:.1f} sec")
        ttk.Label(
            body,
            textvariable=original_var,
        ).grid(row=1, column=1, sticky="w", pady=(8, 0))

        entry_var = tk.StringVar(value=f"{min(original, 5.0):.1f}")

        entry = ttk.Entry(
            body,
            textvariable=entry_var,
            width=15,
            font=("Segoe UI", 11),
        )
        entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 8))

        def use_original():
            entry_var.set(f"{original:.1f}")
            entry.focus_set()
            entry.selection_range(0, tk.END)

        ttk.Button(
            body,
            text="Use original",
            command=use_original,
        ).grid(row=2, column=2, padx=(8, 0), pady=(12, 8), sticky="e")

        ttk.Label(
            body,
            text=f"Enter 0.1–{original:.1f} seconds, or use the original duration.",
            foreground="#666666",
        ).grid(row=3, column=0, columnspan=3, sticky="w")

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=3, sticky="e", pady=(14, 0))

        def ok():
            try:
                value = float(entry_var.get().strip())
            except ValueError:
                messagebox.showwarning(
                    "Video duration",
                    "Please enter a valid number of seconds.",
                    parent=dlg,
                )
                return

            if value < 0.1 or value > original:
                messagebox.showwarning(
                    "Video duration",
                    f"Duration must be between 0.1 and {original:.1f} seconds.",
                    parent=dlg,
                )
                return

            result["value"] = value
            dlg.destroy()

        ttk.Button(
            buttons,
            text="Cancel",
            command=dlg.destroy,
        ).pack(side="right", padx=(8, 0))

        ttk.Button(
            buttons,
            text="OK",
            command=ok,
        ).pack(side="right")

        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.bind("<Return>", lambda _e: ok())
        dlg.bind("<Escape>", lambda _e: dlg.destroy())

        entry.focus_set()
        entry.selection_range(0, tk.END)

        self.wait_window(dlg)
        return result["value"]

    def download(self, item):
        if not item.get("url"):
            messagebox.showwarning("Download", "No downloadable URL.")
            return

        # Ask the user how much of the Pexels video/image to use.
        requested_duration = None
        source_duration = item.get("duration")

        if item["type"] == "video" and source_duration is not None:
            requested_duration = self._ask_duration(source_duration, item.get("id"))
            if requested_duration is None:
                return
        else:
            requested_duration = None

        ext = ".mp4" if item["type"] == "video" else ".jpg"
        target = self._next_name(ext)

        # Temp file is only used while downloading; final file keeps the simple
        # 001.mp4 / 002.mp4 naming requested by the user.
        temp = target.with_name(f".{target.stem}_source{ext}")

        try:
            self.status.set(f"Downloading Pexels {item.get('id')}…")
            self.progress_var.set(0)
            self.progress_label.set("Starting…")
            self.update_idletasks()

            r = requests.get(item["url"], stream=True, timeout=120)
            r.raise_for_status()

            total = int(r.headers.get("content-length", 0))
            done = 0

            with temp.open("wb") as f:
                for chunk in r.iter_content(512 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = (done / total) * 100
                        self.progress_var.set(pct)
                        self.progress_label.set(
                            f"{done / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB"
                        )
                    else:
                        self.progress_label.set(f"{done / 1024 / 1024:.1f} MB")
                    self.update_idletasks()

            if item["type"] == "video" and requested_duration is not None:
                self.status.set(f"Trimming to {requested_duration:.1f} sec…")
                self.progress_label.set("Trimming…")
                self.update_idletasks()
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", str(temp),
                        "-t", f"{requested_duration:.6f}",
                        "-c", "copy",
                        str(target),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                temp.unlink(missing_ok=True)
                final_duration_text = f"{requested_duration:.1f} sec"
            else:
                temp.replace(target)
                final_duration_text = (
                    f"{float(source_duration):.1f} sec"
                    if source_duration is not None else ""
                )

            self.download_cards.append({
                "name": target.name,
                "path": target,
                "type": item["type"],
                "duration_text": final_duration_text,
                "pexels_id": item.get("id"),
            })
            self._render_downloads()

            self.progress_var.set(100)
            self.progress_label.set("Complete")
            self.status.set(
                f"Downloaded: {target.name} • Pexels ID {item.get('id')}"
            )

        except (requests.RequestException, subprocess.CalledProcessError, OSError) as exc:
            for path in (temp, target):
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
            self.progress_var.set(0)
            self.progress_label.set("")
            messagebox.showerror("Download failed", str(exc))
            self.status.set("Download failed")


    def search(self):
        q = self.query.get().strip()
        if not q:
            messagebox.showwarning("Search", "Enter a search query.")
            return
        if not API_KEY:
            messagebox.showerror("Pexels API", "PEXELS_API_KEY not found in config.py or environment.")
            return

        self.status.set(f"Searching: {q}")
        self.update_idletasks()
        try:
            url = VIDEO_URL if self.kind.get() == "videos" else PHOTO_URL
            r = requests.get(
                url,
                headers={"Authorization": API_KEY},
                params={"query": q, "per_page": 80, "orientation": "landscape"},
                timeout=30,
            )
            r.raise_for_status()
            raw = r.json().get("videos" if self.kind.get() == "videos" else "photos", [])
            self.results = [self._video(x) for x in raw] if self.kind.get() == "videos" else [self._photo(x) for x in raw]
            self.current_page = 0
        except requests.RequestException as exc:
            messagebox.showerror("Search failed", str(exc))
            self.status.set("Search failed")
            return

        self._render()
        self.status.set(f"{len(self.results)} results for: {q}")


    def _video(self, x):
        files = [f for f in x.get("video_files", []) if f.get("link") and f.get("file_type") == "video/mp4"]
        files.sort(key=lambda f: (f.get("width") or 0) * (f.get("height") or 0), reverse=True)
        pics = x.get("video_pictures") or []
        return {
            "id": x.get("id"),
            "type": "video",
            "thumb": pics[0].get("picture") if pics else None,
            "url": files[0]["link"] if files else None,
            "width": files[0].get("width") if files else None,
            "height": files[0].get("height") if files else None,
            "duration": x.get("duration"),
        }


    def _photo(self, x):
        src = x.get("src") or {}
        return {
            "id": x.get("id"),
            "type": "photo",
            "thumb": src.get("medium") or src.get("large"),
            "url": src.get("original") or src.get("large2x") or src.get("large"),
            "width": x.get("width"),
            "height": x.get("height"),
        }


    def _render_downloads(self):
        for child in self.downloaded_frame.winfo_children():
            child.destroy()

        if not self.download_cards:
            ttk.Label(
                self.downloaded_frame,
                text="No downloaded files yet. Downloaded files will appear here."
            ).grid(row=0, column=0, sticky="w")
            return

        for i, item in enumerate(self.download_cards):
            row = ttk.Frame(self.downloaded_frame, padding=6, relief="solid", borderwidth=1)
            row.grid(row=i + 1, column=0, columnspan=2, sticky="ew", pady=3)
            row.columnconfigure(1, weight=1)

            drag_label = ttk.Label(
                row,
                text=item["name"],
                font=("Segoe UI", 10, "bold"),
                cursor="hand2",
            )
            drag_label.grid(row=0, column=0, sticky="w", padx=(0, 12))

            if DND_AVAILABLE:
                try:
                    # Register this widget as a Windows drag source. Holding and
                    # dragging the filename sends the local file path, allowing
                    # direct drop into Filmora's Media panel/timeline.
                    drag_label.drag_source_register(1, DND_FILES)

                    def start_drag(_event, path=item["path"]):
                        # tkinterdnd2 expects (action, type, data).
                        return (COPY, DND_FILES, (str(path),))

                    drag_label.dnd_bind("<<DragInitCmd>>", start_drag)
                except Exception:
                    pass

            ttk.Label(
                row,
                text=f"Pexels ID: {item.get('pexels_id', 'n/a')}  •  {item['type']}  •  {item.get('duration_text', '')}",
            ).grid(row=0, column=1, sticky="w")

            def open_file(path=item["path"]):
                try:
                    os.startfile(path)
                except Exception as exc:
                    messagebox.showerror("Open file", str(exc))

            ttk.Button(
                row,
                text="Open",
                command=open_file,
            ).grid(row=0, column=2, padx=4)

            ttk.Button(
                row,
                text="Copy path",
                command=lambda path=item["path"]: self.clipboard_append(str(path)),
            ).grid(row=0, column=3, padx=4)

    def _next_name(self, ext):
        # Simple 001.mp4 / 002.mp4 naming, exactly as requested.
        while True:
            name = f"{self.next_download_number:03d}{ext}"
            candidate = DOWNLOAD_DIR / name
            self.next_download_number += 1
            if not candidate.exists():
                return candidate

    def search(self):
        q = self.query.get().strip()
        if not q:
            messagebox.showwarning("Search", "Enter a search query.")
            return
        if not API_KEY:
            messagebox.showerror("Pexels API", "PEXELS_API_KEY not found in config.py or environment.")
            return

        self.status.set(f"Searching: {q}")
        self.update_idletasks()
        try:
            url = VIDEO_URL if self.kind.get() == "videos" else PHOTO_URL
            r = requests.get(
                url,
                headers={"Authorization": API_KEY},
                params={"query": q, "per_page": 80, "orientation": "landscape"},
                timeout=30,
            )
            r.raise_for_status()
            raw = r.json().get("videos" if self.kind.get() == "videos" else "photos", [])
            self.results = [self._video(x) for x in raw] if self.kind.get() == "videos" else [self._photo(x) for x in raw]
            self.current_page = 0
        except requests.RequestException as exc:
            messagebox.showerror("Search failed", str(exc))
            self.status.set("Search failed")
            return

        self._render()
        self.status.set(f"{len(self.results)} results for: {q}")

    def _video(self, x):
        files = [f for f in x.get("video_files", []) if f.get("link") and f.get("file_type") == "video/mp4"]
        files.sort(key=lambda f: (f.get("width") or 0) * (f.get("height") or 0), reverse=True)
        pics = x.get("video_pictures") or []
        return {
            "id": x.get("id"),
            "type": "video",
            "thumb": pics[0].get("picture") if pics else None,
            "url": files[0]["link"] if files else None,
            "width": files[0].get("width") if files else None,
            "height": files[0].get("height") if files else None,
            "duration": x.get("duration"),
        }

    def _photo(self, x):
        src = x.get("src") or {}
        return {
            "id": x.get("id"),
            "type": "photo",
            "thumb": src.get("medium") or src.get("large"),
            "url": src.get("original") or src.get("large2x") or src.get("large"),
            "width": x.get("width"),
            "height": x.get("height"),
        }

    def _render(self):
        self._clear()

        per_page = 12
        start = self.current_page * per_page
        end = min(start + per_page, len(self.results))
        page_results = self.results[start:end]

        for i, item in enumerate(page_results):
            r, c = divmod(i, 4)
            card = ttk.Frame(self.results_frame, padding=8, relief="solid", borderwidth=1)
            card.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            self.results_frame.grid_columnconfigure(c, weight=1)

            img_label = ttk.Label(card, text="Loading…")
            img_label.pack()
            if item["thumb"]:
                try:
                    data = requests.get(item["thumb"], timeout=20).content
                    im = Image.open(BytesIO(data)).convert("RGB")
                    im.thumbnail((220, 124))
                    ph = ImageTk.PhotoImage(im)
                    img_label.configure(image=ph, text="")
                    self.thumb_refs.append(ph)
                except Exception:
                    pass

            ttk.Label(
                card,
                text=f"Pexels ID: {item['id']}",
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w")
            if item["type"] == "video":
                duration = item.get("duration")
                duration_text = (
                    f"Duration: {float(duration):.1f} sec"
                    if duration is not None else "Duration: n/a"
                )
                ttk.Label(card, text=duration_text).pack(anchor="w")
            ttk.Label(
                card,
                text=f"{item.get('width','?')} × {item.get('height','?')}"
            ).pack(anchor="w")

            btns = ttk.Frame(card)
            btns.pack(fill="x", pady=(8, 0))
            tk.Button(
                btns,
                text="▶ Preview",
                command=lambda x=item: self.preview(x),
                bg="#2fb865",
                fg="white",
                activebackground="#269650",
                activeforeground="white",
                relief="flat",
                bd=0,
                font=("Segoe UI", 9, "bold"),
                padx=14,
                pady=6,
                cursor="hand2",
            ).pack(side="left", padx=(0, 8))

            tk.Button(
                btns,
                text="⬇ Download",
                command=lambda x=item: self.download(x),
                bg="#ee8b2c",
                fg="white",
                activebackground="#d57418",
                activeforeground="white",
                relief="flat",
                bd=0,
                font=("Segoe UI", 9, "bold"),
                padx=14,
                pady=6,
                cursor="hand2",
            ).pack(side="right")

        # Navigation row: first page shows first 12, See More reveals 12 more.
        nav = ttk.Frame(self.results_frame, padding=10)
        nav.grid(row=(len(page_results) + 3) // 4, column=0, columnspan=4, sticky="ew")

        total_pages = max(1, (len(self.results) + per_page - 1) // per_page)

        self._bind_mousewheel(self.results_frame)

        if self.current_page > 0:
            ttk.Button(
                nav,
                text="‹ Previous",
                command=self.previous_page,
            ).pack(side="left")

        ttk.Label(
            nav,
            text=f"Results {start + 1}-{end} of {len(self.results)}   •   Page {self.current_page + 1}/{total_pages}",
        ).pack(side="left", padx=12)

        if end < len(self.results):
            ttk.Button(
                nav,
                text="See more",
                command=self.next_page,
            ).pack(side="right")

    def next_page(self):
        if (self.current_page + 1) * 12 < len(self.results):
            self.current_page += 1
            self._render()
            self.status.set(
                f"Showing results {self.current_page * 12 + 1}-"
                f"{min((self.current_page + 1) * 12, len(self.results))} "
                f"of {len(self.results)}"
            )

    def previous_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render()


    def preview(self, item):
        url = item.get("url")
        if not url:
            messagebox.showwarning("Preview", "No preview URL available.")
            return

        # Try local media players first. These can stream the remote MP4 without
        # saving it to disk.
        for player in (
            ["ffplay", "-autoexit", "-window_title", f"Pexels {item.get('id')}", url],
            ["mpv", "--force-window=yes", "--title", f"Pexels {item.get('id')}", url],
        ):
            try:
                subprocess.Popen(player, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.status.set(f"Streaming preview: Pexels {item.get('id')}")
                return
            except FileNotFoundError:
                continue
            except Exception:
                break

        # Last resort: open the direct URL in the browser. Some browsers may
        # download CDN video URLs instead of playing them, so this is only a fallback.
        try:
            webbrowser.open(url)
            self.status.set("Opened Pexels preview URL in browser.")
        except Exception as exc:
            messagebox.showerror("Preview failed", str(exc))


    def download(self, item):
        if not item.get("url"):
            messagebox.showwarning("Download", "No downloadable URL.")
            return

        # Ask the user how much of the Pexels video/image to use.
        requested_duration = None
        source_duration = item.get("duration")

        if item["type"] == "video" and source_duration is not None:
            requested_duration = self._ask_duration(source_duration, item.get("id"))
            if requested_duration is None:
                return
        else:
            requested_duration = None

        ext = ".mp4" if item["type"] == "video" else ".jpg"
        target = self._next_name(ext)

        # Temp file is only used while downloading; final file keeps the simple
        # 001.mp4 / 002.mp4 naming requested by the user.
        temp = target.with_name(f".{target.stem}_source{ext}")

        try:
            self.status.set(f"Downloading Pexels {item.get('id')}…")
            self.progress_var.set(0)
            self.progress_label.set("Starting…")
            self.update_idletasks()

            r = requests.get(item["url"], stream=True, timeout=120)
            r.raise_for_status()

            total = int(r.headers.get("content-length", 0))
            done = 0

            with temp.open("wb") as f:
                for chunk in r.iter_content(512 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = (done / total) * 100
                        self.progress_var.set(pct)
                        self.progress_label.set(
                            f"{done / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB"
                        )
                    else:
                        self.progress_label.set(f"{done / 1024 / 1024:.1f} MB")
                    self.update_idletasks()

            if item["type"] == "video" and requested_duration is not None:
                self.status.set(f"Trimming to {requested_duration:.1f} sec…")
                self.progress_label.set("Trimming…")
                self.update_idletasks()
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", str(temp),
                        "-t", f"{requested_duration:.6f}",
                        "-c", "copy",
                        str(target),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                temp.unlink(missing_ok=True)
                final_duration_text = f"{requested_duration:.1f} sec"
            else:
                temp.replace(target)
                final_duration_text = (
                    f"{float(source_duration):.1f} sec"
                    if source_duration is not None else ""
                )

            self.download_cards.append({
                "name": target.name,
                "path": target,
                "type": item["type"],
                "duration_text": final_duration_text,
                "pexels_id": item.get("id"),
            })
            self._render_downloads()

            self.progress_var.set(100)
            self.progress_label.set("Complete")
            self.status.set(
                f"Downloaded: {target.name} • Pexels ID {item.get('id')}"
            )

        except (requests.RequestException, subprocess.CalledProcessError, OSError) as exc:
            for path in (temp, target):
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
            self.progress_var.set(0)
            self.progress_label.set("")
            messagebox.showerror("Download failed", str(exc))
            self.status.set("Download failed")

if __name__ == "__main__":
    if not DND_AVAILABLE:
        print("NOTE: Native drag-out is unavailable until tkinterdnd2 is installed.")
    PexelsHelper().mainloop()

if __name__ == "__main__":
    PexelsHelper().mainloop()
