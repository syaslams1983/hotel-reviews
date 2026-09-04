import os
import webbrowser
import subprocess
import threading
from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

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
DOWNLOAD_DIR = PROJECT_DIR / "kdenlive_media"
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
        self.geometry("1180x820")
        self.minsize(900, 650)
        self.query = tk.StringVar()
        self.kind = tk.StringVar(value="videos")
        self.status = tk.StringVar(value="Ready")

        self.downloaded_frame = None
        self.results = []
        self.visible_count = 12
        self.thumb_refs = []
        self.next_download_number = 1
        self.download_cards = []
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_label = tk.StringVar(value="")
        self.add_stock_label = tk.BooleanVar(value=True)
        self._ui()

    def _ui(self):
        top = ttk.Frame(self, padding=(14, 12, 14, 8))
        top.pack(fill="x")

        banner = tk.Frame(top, bg="#cfeaff")
        banner.pack(fill="x", pady=(0, 10))
        tk.Label(
            banner,
            text="Pexels Helper",
            bg="#cfeaff",
            fg="#123047",
            font=("Segoe UI", 21, "bold"),
            anchor="w",
            padx=14,
            pady=9,
        ).pack(fill="x")

        # Premium search bar + media-type selector.
        row = tk.Frame(top, bg="#ffffff")
        row.pack(fill="x", pady=(0, 2))

        search_shell = tk.Frame(
            row,
            bg="#ffffff",
            highlightthickness=2,
            highlightbackground="#b9cde2",
            highlightcolor="#4a90e2",
        )
        search_shell.pack(side="left", fill="x", expand=True)

        tk.Label(
            search_shell,
            text="⌕",
            bg="#ffffff",
            fg="#6d8499",
            font=("Segoe UI Symbol", 18),
        ).pack(side="left", padx=(11, 3))

        entry = tk.Entry(
            search_shell,
            textvariable=self.query,
            font=("Segoe UI", 14),
            bd=0,
            relief="flat",
            bg="#ffffff",
            fg="#17324d",
            insertbackground="#17324d",
        )
        entry.pack(side="left", fill="x", expand=True, ipady=11, padx=(0, 10))
        self._search_entry = entry
        entry.bind("<Return>", lambda _e: self.search())

        type_box = tk.Frame(
            row,
            bg="#e8eef5",
            highlightthickness=1,
            highlightbackground="#c9d5e1",
        )
        type_box.pack(side="left", padx=10, ipadx=3, ipady=3)

        def set_kind(kind):
            self.kind.set(kind)
            refresh_kind_buttons()

        video_btn = tk.Button(
            type_box,
            text="🎬 Videos",
            command=lambda: set_kind("videos"),
            relief="flat",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=7,
            cursor="hand2",
        )
        video_btn.pack(side="left")

        both_btn = tk.Button(
            type_box,
            text="◫ Both",
            command=lambda: set_kind("both"),
            relief="flat",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=7,
            cursor="hand2",
        )
        both_btn.pack(side="left")

        photo_btn = tk.Button(
            type_box,
            text="🖼 Photos",
            command=lambda: set_kind("photos"),
            relief="flat",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=7,
            cursor="hand2",
        )
        photo_btn.pack(side="left")

        def refresh_kind_buttons():
            selected = self.kind.get()
            for btn, kind in (
                (video_btn, "videos"),
                (both_btn, "both"),
                (photo_btn, "photos"),
            ):
                if selected == kind:
                    btn.configure(
                        bg="#f39c12", fg="white",
                        activebackground="#f39c12",
                        activeforeground="white",
                    )
                else:
                    btn.configure(
                        bg="#e8eef5", fg="#35536d",
                        activebackground="#dbe5ef",
                        activeforeground="#17324d",
                    )

        refresh_kind_buttons()

        tk.Button(
            row,
            text="🔎  Search Pexels",
            command=self.search,
            bg="#4a90e2",
            fg="white",
            activebackground="#357abd",
            activeforeground="white",
            relief="flat",
            bd=0,
            font=("Segoe UI", 11, "bold"),
            padx=20,
            pady=10,
            cursor="hand2",
        ).pack(side="left")

        ttk.Label(
            top,
            text="80 results loaded • 12 shown at a time • See more adds the next 12 here",
            foreground="#666666",
        ).pack(anchor="w", pady=(5, 0))

        ttk.Label(
            top,
            textvariable=self.status,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(5, 0))

        progress_row = ttk.Frame(top)
        progress_row.pack(fill="x", pady=(5, 0))

        ttk.Progressbar(
            progress_row,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        ).pack(side="left", fill="x", expand=True)

        ttk.Label(
            progress_row,
            textvariable=self.progress_label,
            width=24,
        ).pack(side="left", padx=(8, 0))

        # Premium orange stock-label toggle.
        stock_toggle = tk.Frame(
            top,
            bg="#ffffff",
            cursor="hand2",
            highlightthickness=1,
            highlightbackground="#e6e6e6",
            highlightcolor="#f39c12",
        )
        stock_toggle.pack(anchor="w", pady=(7, 6), padx=1, ipadx=6, ipady=4)

        stock_box = tk.Canvas(
            stock_toggle,
            width=22,
            height=22,
            bg="#ffffff",
            highlightthickness=0,
            bd=0,
        )
        stock_box.pack(side="left", padx=(2, 8))

        stock_text = tk.Label(
            stock_toggle,
            text="Add stock label to downloaded media  (STOCK VIDEO / STOCK IMAGE)",
            bg="#ffffff",
            fg="#16324f",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
            cursor="hand2",
        )
        stock_text.pack(side="left", padx=(0, 6))

        def redraw_stock_toggle(*_):
            stock_box.delete("all")
            if self.add_stock_label.get():
                stock_box.create_rectangle(
                    1, 1, 21, 21,
                    fill="#f39c12",
                    outline="#e67e22",
                    width=1,
                )
                stock_box.create_line(
                    5, 11, 9, 15, 17, 6,
                    fill="white",
                    width=2.5,
                    capstyle="round",
                    joinstyle="round",
                )
            else:
                stock_box.create_rectangle(
                    1, 1, 21, 21,
                    fill="#ffffff",
                    outline="#b8b8b8",
                    width=1.5,
                )

        def toggle_stock(*_):
            self.add_stock_label.set(not self.add_stock_label.get())
            redraw_stock_toggle()

        for widget in (stock_toggle, stock_box, stock_text):
            widget.bind("<Button-1>", toggle_stock)

        redraw_stock_toggle()

        self.downloaded_frame = tk.Frame(
            self,
            bg="#eaf5ff",
            bd=1,
            relief="solid",
        )
        self.downloaded_frame.pack(fill="x", padx=14, pady=(0, 8))
        self.downloaded_frame.columnconfigure(0, weight=1)

        results_wrap = ttk.Frame(self)
        results_wrap.pack(
            fill="both",
            expand=True,
            padx=(14, 0),
            pady=(0, 12),
        )

        self.canvas = tk.Canvas(
            results_wrap,
            highlightthickness=0,
            borderwidth=0,
        )
        self.scroll = ttk.Scrollbar(
            results_wrap,
            orient="vertical",
            command=self.canvas.yview,
        )
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.results_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.results_frame,
            anchor="nw",
        )

        self.results_frame.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all"),
            ),
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(
                self.canvas_window,
                width=e.width,
            ),
        )

        self.canvas.bind("<MouseWheel>", self._on_mousewheel, add="+")
        self.results_frame.bind("<MouseWheel>", self._on_mousewheel, add="+")
        self.bind_all("<MouseWheel>", self._on_mousewheel_global, add="+")

        self._render_downloads()

    def _on_mousewheel(self, event):
        if getattr(event, "delta", 0):
            self.canvas.yview_scroll(
                -1 if event.delta > 0 else 1,
                "units",
            )
        return "break"

    def _on_mousewheel_global(self, event):
        try:
            x, y = self.winfo_pointerx(), self.winfo_pointery()
            left, top = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
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

    def _delete_download(self, index):
        if not (0 <= index < len(self.download_cards)):
            return
        item = self.download_cards[index]
        try:
            Path(item["path"]).unlink(missing_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "Delete failed",
                f"Could not delete {item['name']}.\n\n{exc}",
            )
            return
        self.download_cards.pop(index)
        self._render_downloads()
        self.status.set(f"Deleted: {item['name']}")

    def _clear_download_list(self):
        self.download_cards.clear()
        self._render_downloads()
        self.status.set("Downloaded list cleared. Files remain on disk.")

    def _open_download_folder(self):
        try:
            os.startfile(str(DOWNLOAD_DIR))
            self.status.set(f"Opened folder: {DOWNLOAD_DIR}")
        except OSError as exc:
            messagebox.showerror("Open folder failed", str(exc))

    def _render_downloads(self):
        for child in self.downloaded_frame.winfo_children():
            child.destroy()

        header = tk.Frame(self.downloaded_frame, bg="#d7edff")
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="Downloaded  •  drag files directly into Filmora",
            bg="#d7edff",
            fg="#123b5d",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            padx=10,
            pady=6,
        ).grid(row=0, column=0, sticky="w")

        tk.Button(
            header,
            text="📁 Open folder",
            command=self._open_download_folder,
            bg="#0b5cab",
            fg="white",
            activebackground="#084780",
            relief="flat",
            bd=0,
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
            cursor="hand2",
        ).grid(row=0, column=1, padx=5, pady=4)

        tk.Button(
            header,
            text="Clear list",
            command=self._clear_download_list,
            bg="#7f8c8d",
            fg="white",
            activebackground="#667071",
            relief="flat",
            bd=0,
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
            cursor="hand2",
        ).grid(row=0, column=2, padx=(0, 6), pady=4)

        if not self.download_cards:
            tk.Label(
                self.downloaded_frame,
                text="No downloaded files yet.",
                bg="#eaf5ff",
                fg="#6b7c8c",
                font=("Segoe UI", 9),
                padx=10,
                pady=7,
            ).grid(row=1, column=0, columnspan=3, sticky="ew")
            return

        for i, item in enumerate(self.download_cards, start=1):
            row = tk.Frame(
                self.downloaded_frame,
                bg="#f7fbff",
                bd=1,
                relief="solid",
            )
            row.grid(row=i, column=0, columnspan=3, sticky="ew", padx=4, pady=2)
            row.grid_columnconfigure(1, weight=1)

            drag_label = tk.Label(
                row,
                text=item["name"],
                font=("Segoe UI", 10, "bold"),
                fg="#0b3d91",
                bg="#f7fbff",
                cursor="hand2",
                padx=9,
            )
            drag_label.grid(row=0, column=0, sticky="w", pady=6)

            if DND_AVAILABLE:
                try:
                    drag_label.drag_source_register(1, DND_FILES)
                    def start_drag(_event, path=item["path"]):
                        return (COPY, DND_FILES, (str(path),))
                    drag_label.dnd_bind("<<DragInitCmd>>", start_drag)
                except Exception:
                    pass

            tk.Label(
                row,
                text=(
                    f"Pexels ID: {item.get('pexels_id', 'n/a')}  •  "
                    f"{item['type']}  •  {item.get('duration_text', '')}"
                ),
                bg="#f7fbff",
                fg="#334e68",
                font=("Segoe UI", 9),
                anchor="w",
            ).grid(row=0, column=1, sticky="w", padx=6)

            tk.Button(
                row,
                text="✕ Delete",
                command=lambda idx=i - 1: self._delete_download(idx),
                bg="#d64545",
                fg="white",
                activebackground="#b83232",
                relief="flat",
                bd=0,
                font=("Segoe UI", 8, "bold"),
                padx=9,
                pady=4,
                cursor="hand2",
            ).grid(row=0, column=2, padx=(6, 6), pady=4)

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
            messagebox.showerror(
                "Pexels API",
                "PEXELS_API_KEY not found in config.py or environment.",
            )
            return

        self.status.set(f"Searching: {q}")
        self.update_idletasks()

        kind = self.kind.get()

        try:
            if kind == "both":
                rv = requests.get(
                    VIDEO_URL,
                    headers={"Authorization": API_KEY},
                    params={
                        "query": q,
                        "per_page": 80,
                        "orientation": "landscape",
                    },
                    timeout=30,
                )
                rv.raise_for_status()

                rp = requests.get(
                    PHOTO_URL,
                    headers={"Authorization": API_KEY},
                    params={
                        "query": q,
                        "per_page": 80,
                        "orientation": "landscape",
                    },
                    timeout=30,
                )
                rp.raise_for_status()

                videos = [
                    self._video(x)
                    for x in rv.json().get("videos", [])
                ]
                photos = [
                    self._photo(x)
                    for x in rp.json().get("photos", [])
                ]

                # Both mode: 3 videos + 1 image in every row.
                self.results = []
                vi = pi = 0

                while vi < len(videos) or pi < len(photos):
                    for _ in range(3):
                        if vi < len(videos):
                            self.results.append(videos[vi])
                            vi += 1
                    if pi < len(photos):
                        self.results.append(photos[pi])
                        pi += 1
                    elif vi >= len(videos):
                        break

            else:
                url = VIDEO_URL if kind == "videos" else PHOTO_URL
                r = requests.get(
                    url,
                    headers={"Authorization": API_KEY},
                    params={
                        "query": q,
                        "per_page": 80,
                        "orientation": "landscape",
                    },
                    timeout=30,
                )
                r.raise_for_status()

                raw = r.json().get(
                    "videos" if kind == "videos" else "photos",
                    [],
                )
                self.results = (
                    [self._video(x) for x in raw]
                    if kind == "videos"
                    else [self._photo(x) for x in raw]
                )

            self.visible_count = min(12, len(self.results))

        except requests.RequestException as exc:
            messagebox.showerror("Search failed", str(exc))
            self.status.set("Search failed")
            return

        self._render()
        self.status.set(
            f"{len(self.results)} results loaded • showing {self.visible_count}"
        )
        self.after(
            10,
            lambda: self._load_thumbnails_async(
                list(self.results[:self.visible_count])
            ),
        )

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
            "thumb": src.get("small") or src.get("medium") or src.get("large"),
            "url": src.get("original") or src.get("large2x") or src.get("large"),
            "width": x.get("width"),
            "height": x.get("height"),
        }

    def _load_thumbnails_async(self, items):
        """Load small thumbnails quickly in parallel after search results appear."""
        import concurrent.futures

        def load_one(item):
            thumb = item.get("thumb")
            if not thumb:
                return None
            try:
                response = requests.get(
                    thumb,
                    timeout=5,
                    stream=True,
                )
                response.raise_for_status()
                data = response.content
                im = Image.open(BytesIO(data)).convert("RGB")
                im.thumbnail((240, 135), Image.LANCZOS)
                return item.get("id"), im
            except Exception:
                return None

        def worker():
            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(load_one, item) for item in items]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        results.append(result)

            def apply():
                cards = {
                    getattr(widget, "_pexels_item_id", None): widget
                    for widget in self.results_frame.winfo_children()
                }
                for item_id, im in results:
                    card = cards.get(item_id)
                    if card is None:
                        continue
                    children = card.winfo_children()
                    if not children:
                        continue
                    image_box = children[0]
                    labels = image_box.winfo_children()
                    if not labels:
                        continue

                    label = labels[0]
                    ph = ImageTk.PhotoImage(im)
                    label.configure(image=ph, text="")
                    label.image = ph
                    self.thumb_refs.append(ph)

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def _render(self):
        self._clear()
        visible = self.results[:self.visible_count]

        for i, item in enumerate(visible):
            r, c = divmod(i, 4)

            card = tk.Frame(
                self.results_frame,
                bg="#ffffff",
                bd=1,
                relief="solid",
                highlightthickness=1,
                highlightbackground="#d8e2ec",
            )
            card.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            self.results_frame.grid_columnconfigure(c, weight=1)
            card._pexels_item_id = item.get("id")

            image_box = tk.Frame(card, bg="#eef5fb", height=170)
            image_box.pack(fill="x")
            image_box.pack_propagate(False)

            img_label = tk.Label(
                image_box,
                text="Loading preview…",
                bg="#eef5fb",
                fg="#6b7c8c",
                font=("Segoe UI", 9),
            )
            img_label.pack(expand=True, fill="both")

            # Small type ribbon in the top-right corner of each card.
            # Orange = VIDEO, blue = IMAGE, so Both mode is instantly clear.
            ribbon_text = "VIDEO" if item.get("type") == "video" else "IMAGE"
            ribbon_bg = "#f39c12" if item.get("type") == "video" else "#2f80ed"
            ribbon = tk.Label(
                card,
                text=ribbon_text,
                bg=ribbon_bg,
                fg="white",
                font=("Segoe UI", 8, "bold"),
                padx=7,
                pady=2,
            )
            ribbon.place(relx=1.0, x=-8, y=8, anchor="ne")

            tk.Label(
                card,
                text=f"Pexels ID  {item.get('id')}",
                bg="#ffffff",
                fg="#17324d",
                font=("Segoe UI", 9, "bold"),
                anchor="w",
            ).pack(anchor="w", padx=10, pady=(8, 2))

            if item["type"] == "video":
                duration = item.get("duration")
                media_line = (
                    f"VIDEO  •  {float(duration):.1f} sec"
                    if duration is not None else "VIDEO"
                )
            else:
                media_line = "PHOTO"

            tk.Label(
                card,
                text=media_line,
                bg="#ffffff",
                fg="#52677d",
                font=("Segoe UI", 9),
                anchor="w",
            ).pack(anchor="w", padx=10)

            tk.Label(
                card,
                text=f"{item.get('width','?')} × {item.get('height','?')}",
                bg="#ffffff",
                fg="#718096",
                font=("Segoe UI", 8),
                anchor="w",
            ).pack(anchor="w", padx=10, pady=(1, 5))

            btns = tk.Frame(card, bg="#ffffff")
            btns.pack(fill="x", padx=10, pady=(4, 10))

            tk.Button(
                btns,
                text="▶  Preview",
                command=lambda x=item: self.preview(x),
                bg="#22a65a",
                fg="white",
                activebackground="#1b8748",
                relief="flat",
                bd=0,
                font=("Segoe UI", 9, "bold"),
                padx=12,
                pady=6,
                cursor="hand2",
            ).pack(side="left")

            tk.Button(
                btns,
                text="⬇  Download",
                command=lambda x=item: self.download(x),
                bg="#f08a24",
                fg="white",
                activebackground="#d87311",
                relief="flat",
                bd=0,
                font=("Segoe UI", 9, "bold"),
                padx=12,
                pady=6,
                cursor="hand2",
            ).pack(side="right")

        nav = tk.Frame(
            self.results_frame,
            bg="#f6f9fc",
            bd=1,
            relief="solid",
        )
        nav.grid(
            row=(len(visible) + 3) // 4,
            column=0,
            columnspan=4,
            sticky="ew",
            padx=6,
            pady=(4, 10),
        )

        tk.Label(
            nav,
            text=f"Showing {len(visible)} of {len(self.results)} results",
            bg="#f6f9fc",
            fg="#5d7187",
            font=("Segoe UI", 9),
            padx=10,
            pady=8,
        ).pack(side="left")

        if self.visible_count < len(self.results):
            tk.Button(
                nav,
                text="＋  See more",
                command=self.see_more,
                bg="#2f80ed",
                fg="white",
                activebackground="#2568bd",
                relief="flat",
                bd=0,
                font=("Segoe UI", 9, "bold"),
                padx=14,
                pady=6,
                cursor="hand2",
            ).pack(side="right", padx=8, pady=6)

        self._bind_wheel_recursive(self.results_frame)

    def see_more(self):
        old_count = self.visible_count
        self.visible_count = min(
            self.visible_count + 12,
            len(self.results),
        )
        self._render()
        self.status.set(
            f"Showing {self.visible_count} of {len(self.results)} results"
        )
        self.after(
            10,
            lambda: self._load_thumbnails_async(
                list(self.results[old_count:self.visible_count])
            ),
        )

    def preview(self, item):
        url = item.get("url")
        if not url:
            messagebox.showwarning("Preview", "No preview URL available.")
            return

        # Photos: show an actual in-app image preview.
        if item.get("type") == "photo":
            try:
                r = requests.get(
                    url,
                    timeout=30,
                )
                r.raise_for_status()

                im = Image.open(BytesIO(r.content)).convert("RGB")
                max_w, max_h = 1400, 820
                scale = min(
                    max_w / max(1, im.width),
                    max_h / max(1, im.height),
                    1.0,
                )
                if scale < 1:
                    im = im.resize(
                        (
                            max(1, int(im.width * scale)),
                            max(1, int(im.height * scale)),
                        ),
                        Image.LANCZOS,
                    )

                win = tk.Toplevel(self)
                win.title(f"Pexels Photo Preview • ID {item.get('id')}")
                win.transient(self)
                win.configure(bg="#111111")

                photo = ImageTk.PhotoImage(im)
                label = tk.Label(
                    win,
                    image=photo,
                    bg="#111111",
                )
                label.image = photo
                label.pack(
                    padx=12,
                    pady=12,
                )

                ttk.Label(
                    win,
                    text=f"Pexels ID: {item.get('id')}",
                ).pack(pady=(0, 10))

                win.update_idletasks()
                ww, wh = win.winfo_reqwidth(), win.winfo_reqheight()
                px = self.winfo_rootx() + max(0, (self.winfo_width() - ww) // 2)
                py = self.winfo_rooty() + max(0, (self.winfo_height() - wh) // 2)
                win.geometry(f"+{px}+{py}")
                win.bind("<Escape>", lambda _e: win.destroy())
                win.focus_set()
                return

            except Exception as exc:
                messagebox.showerror(
                    "Photo preview failed",
                    str(exc),
                )
                return

        # Videos: keep the working stream-preview behavior.
        for player in (
            ["ffplay", "-autoexit", "-window_title", f"Pexels {item.get('id')}", url],
            ["mpv", "--force-window=yes", "--title", f"Pexels {item.get('id')}", url],
        ):
            try:
                subprocess.Popen(
                    player,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.status.set(
                    f"Streaming preview: Pexels {item.get('id')}"
                )
                return
            except FileNotFoundError:
                continue
            except Exception:
                break

        try:
            webbrowser.open(url)
            self.status.set("Opened preview URL in browser.")
        except Exception as exc:
            messagebox.showerror("Preview failed", str(exc))

    def _stock_label_filter(self, label):
        # Final locked stock-video badge:
        # bottom-right, yellow Arial 42px, black background at 99% opacity.
        return (
            "scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,setsar=1,"
            "drawbox=x=1575:y=954:w=310:h=66:color=black@0.99:t=fill,"
            "drawtext="
            f"text='{label}':"
            "fontcolor=yellow:"
            "fontsize=42:"
            "fontfile='C\\:/Windows/Fonts/arial.ttf':"
            "x=1595:"
            "y=970"
        )


    def _burn_stock_label_video(self, source, output, label):
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(source),
                "-vf", self._stock_label_filter(label),
                "-an",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-r", "30",
                str(output),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _burn_stock_label_image(self, source, output, label):
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(source),
                "-vf", self._stock_label_filter(label),
                "-frames:v", "1",
                "-q:v", "2",
                str(output),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _ask_duration(self, original_duration, pexels_id):
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
            text=f"Original duration: {original:.1f} sec",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        value = tk.StringVar(value=f"{min(original, 5.0):.1f}")
        entry = ttk.Entry(
            body,
            textvariable=value,
            width=14,
            font=("Segoe UI", 11),
        )
        entry.grid(row=2, column=0, sticky="ew", pady=(12, 8))

        def use_original():
            result["value"] = original
            dlg.destroy()

        tk.Button(
            body,
            text="Use original  →  Download",
            command=use_original,
            bg="#2f80ed",
            fg="white",
            activebackground="#2568bd",
            relief="flat",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=16,
            pady=7,
            cursor="hand2",
        ).grid(row=2, column=1, padx=(8, 0), pady=(12, 8))

        ttk.Label(
            body,
            text=f"Enter 0.1–{original:.1f} sec, or click Use original.",
            foreground="#666666",
        ).grid(row=3, column=0, columnspan=3, sticky="w")

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=3, sticky="e", pady=(14, 0))

        def ok():
            try:
                number = float(value.get().strip())
            except ValueError:
                messagebox.showwarning(
                    "Video duration",
                    "Please enter a valid number.",
                    parent=dlg,
                )
                return

            if number < 0.1 or number > original:
                messagebox.showwarning(
                    "Video duration",
                    f"Duration must be between 0.1 and {original:.1f} seconds.",
                    parent=dlg,
                )
                return

            result["value"] = number
            dlg.destroy()

        ttk.Button(
            buttons,
            text="Cancel",
            command=dlg.destroy,
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            buttons,
            text="OK",
            command=ok,
            bg="#27ae60",
            fg="white",
            activebackground="#1e8449",
            relief="flat",
            bd=0,
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=5,
            cursor="hand2",
        ).pack(side="right")

        dlg.update_idletasks()
        dw, dh = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        px = self.winfo_rootx() + max(0, (self.winfo_width() - dw) // 2)
        py = self.winfo_rooty() + max(0, (self.winfo_height() - dh) // 2)
        dlg.geometry(f"{dw}x{dh}+{px}+{py}")

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

        source_duration = item.get("duration")
        requested_duration = None

        if item.get("type") == "video" and source_duration is not None:
            requested_duration = self._ask_duration(
                source_duration,
                item.get("id"),
            )
            if requested_duration is None:
                return

        ext = ".mp4" if item.get("type") == "video" else ".jpg"
        target = self._next_name(ext)
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
                        self.progress_var.set(done * 100 / total)
                        self.progress_label.set(
                            f"{done/1048576:.1f} / {total/1048576:.1f} MB"
                        )
                    else:
                        self.progress_label.set(
                            f"{done/1048576:.1f} MB"
                        )
                    self.update_idletasks()

            if item.get("type") == "video" and requested_duration is not None:
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
                final_duration = f"{requested_duration:.1f} sec"
            else:
                temp.replace(target)
                final_duration = (
                    f"{float(source_duration):.1f} sec"
                    if source_duration is not None else ""
                )

            if self.add_stock_label.get():
                label = (
                    "STOCK VIDEO"
                    if item.get("type") == "video"
                    else "STOCK IMAGE"
                )
                labeled_target = target.with_name(
                    f".{target.stem}_labeled{target.suffix}"
                )

                self.status.set(f"Applying {label} label…")
                self.progress_label.set("Labeling…")
                self.update_idletasks()

                if item.get("type") == "video":
                    self._burn_stock_label_video(
                        target,
                        labeled_target,
                        label,
                    )
                else:
                    self._burn_stock_label_image(
                        target,
                        labeled_target,
                        label,
                    )

                target.unlink(missing_ok=True)
                labeled_target.replace(target)

            self.download_cards.append(
                {
                    "name": target.name,
                    "path": target,
                    "type": item["type"],
                    "duration_text": final_duration,
                    "pexels_id": item.get("id"),
                }
            )
            self._render_downloads()

            self.progress_var.set(100)
            self.progress_label.set("Complete")
            self.status.set(
                f"Downloaded: {target.name} • Pexels ID {item.get('id')}"
            )

        except (
            requests.RequestException,
            subprocess.CalledProcessError,
            OSError,
        ) as exc:
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
