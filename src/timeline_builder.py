import re
from pathlib import Path
from collections import deque

from moviepy.audio.io.AudioFileClip import AudioFileClip

from src.transcript import TranscriptGenerator
from src.scene_analyzer import SceneAnalyzer
from src.image_matcher import ImageMatcher
from src.pexels_api import PexelsAPI
from src.search_query import SearchQueryGenerator


class TimelineBuilder:

    def __init__(
        self,
        audio_file,
        images_dir,
    ):

        self.stock_image_topics = [
            "breakfast food",
            "restaurant food",
            "happy family vacation",
            "tourists exploring",
            "tropical beach",
            "ocean beach",
            "mountain landscape",
            "tropical nature",
            "sunset landscape",
            "travelers walking",
            "boat island",
            "local street",
            "travel activity",
            "swimming",
        ]

        self.audio_file = Path(
            audio_file
        )

        self.images_dir = Path(
            images_dir
        )

        self.transcript = (
            TranscriptGenerator()
        )

        self.scene = (
            SceneAnalyzer()
        )

        self.matcher = (
            ImageMatcher()
        )

        self.pexels = (
            PexelsAPI()
        )

        self.query_generator = (
            SearchQueryGenerator()
        )

        # Every visual used in this video
        self.used_visuals = set()

        # Last visual source types
        self.recent_visuals = deque(
            maxlen=4
        )

        # Counters
        self.stock_image_count = 0
        self.stock_video_count = 0
        self.visual_count = 0
        self.current_visual_queries = []
        self.current_visual_query_index = 0
        self.current_sentence_id = -1
        self.current_visual_query_index = 0

        # Target approximately 15% stock images.
        # Selection is based on visual_count and remains separate
        # from original hotel images and GPU rendering.
        self.stock_image_target_ratio = 0.15

        # Minimum acceptable match score for an "original" hotel image.
        # Below this, the match is too weak/generic to trust — fall
        # back to stock instead of forcing an unrelated original photo.
        self.min_original_score = 0.17

    # =========================================================
    # ORIGINAL IMAGE
    # =========================================================

    def find_first_original(
        self,
        text,
        scene,
    ):
        """Force intro.jpg to be the very first visual when available."""
        intro = self.images_dir / "intro.jpg"
        if intro.exists():
            key = str(intro.resolve())
            if key not in self.used_visuals:
                self.used_visuals.add(key)
                self.recent_visuals.append("original")
                return {
                    "media": intro,
                    "media_type": "image",
                    "source_type": "original",
                    "label": None,
                    "score": 1.0,
                }

        result = self.matcher.find_best(
            prompt=text,
            scene=scene,
        )

        if not result:
            result = self.matcher.find_best(
                prompt="hotel exterior hotel resort",
                scene="outside",
            )

        if not result:
            return None

        image_path, score = result
        image_path = Path(image_path)
        key = str(image_path.resolve())

        if key in self.used_visuals:
            return None

        self.used_visuals.add(key)
        self.recent_visuals.append("original")

        return {
            "media": image_path,
            "media_type": "image",
            "source_type": "original",
            "label": None,
            "score": score,
        }

    def find_original(
        self,
        text,
        scene,
    ):

        result = self.matcher.find_best(
            prompt=text,
            scene=scene,
        )

        if not result:
            return None

        image_path, score = result

        # Reject weak matches: better to fall back to a relevant
        # stock clip than force an unrelated original hotel photo.
        if score is not None and score < self.min_original_score:
            return None

        image_path = Path(
            image_path
        )

        key = str(
            image_path.resolve()
        )

        if image_path.name.lower().startswith("intro."):
            return None

        if key in self.used_visuals:
            return None

        self.used_visuals.add(
            key
        )

        self.recent_visuals.append(
            "original"
        )

        return {
            "media": image_path,
            "media_type": "image",
            "source_type": "original",
            "label": None,
            "score": score,
        }

    # =========================================================
    # STOCK VIDEO
    # =========================================================

    def find_stock_video(
        self,
        query,
    ):

        video = self.pexels.download(
            query
        )

        if video is None:
            return None

        video = Path(
            video
        )

        key = str(
            video.resolve()
        )

        if key in self.used_visuals:
            return None

        self.used_visuals.add(
            key
        )

        self.recent_visuals.append(
            "stock_video"
        )

        return {
            "media": video,
            "media_type": "video",
            "source_type": "stock_video",
            "label": "STOCK VIDEO",
            "score": None,
        }

    # =========================================================
    # STOCK IMAGE
    # =========================================================

    def find_stock_image(
        self,
        query,
    ):

        if self.visual_count > 0:
            target_images = max(
                1,
                int(
                    self.visual_count
                    * self.stock_image_target_ratio
                )
            )

            if self.stock_image_count >= target_images:
                return None

        # Use the sentence-derived query directly.
        stock_query = query.strip()

        if not stock_query:
            return None

        print(
            f"[STOCK IMAGE QUERY] "
            f"{stock_query}"
        )

        image = self.pexels.download_image(
            stock_query
        )

        if image is None:
            return None

        image = Path(image)

        key = str(
            image.resolve()
        )

        if key in self.used_visuals:
            return None

        self.used_visuals.add(
            key
        )

        self.recent_visuals.append(
            "stock_image"
        )

        self.stock_image_count += 1

        return {
            "media": image,
            "media_type": "image",
            "source_type": "stock_image",
            "label": "STOCK IMAGE",
            "score": None,
        }

    # =========================================================
    # TWO ORIGINALS CHECK
    # =========================================================

    def should_prefer_stock(self):

        if len(
            self.recent_visuals
        ) < 2:

            return False

        last_two = list(
            self.recent_visuals
        )[-2:]

        return (
            last_two[0] == "original"
            and
            last_two[1] == "original"
        )

    # =========================================================
    # STOCK IMAGE OPPORTUNITY
    # =========================================================

    def should_try_stock_image(self):

        if self.visual_count <= 0:
            return False

        target_images = max(
            1,
            int(
                self.visual_count
                * self.stock_image_target_ratio
            )
        )

        # Only request an image when the current count is
        # below the approximate 15% target.
        return (
            self.stock_image_count
            < target_images
        )

    # =========================================================
    # STRICT SENTENCE VISUAL QUERY
    # =========================================================

    def build_visual_query(self, text, scene):
        """Build a concise visual query from the actual sentence."""
        original = str(text).strip()
        t = re.sub(r"[^a-z0-9]+", " ", original.lower()).strip()

        # Explicit named/semantic concepts. More specific concepts win.
        rules = [
            ("wifi", ["wi fi", "wifi", "wireless internet"]),
            ("air conditioning", ["air conditioning", "air conditioner", "air conditioned"]),
            ("mini fridge", ["mini fridge", "mini bar", "minibar", "refrigerator"]),
            ("coffee maker", ["coffee maker", "coffee machine", "kettle", "electric kettle"]),
            ("hotel bathroom", ["bathroom", "shower", "bathtub", "toiletries", "shampoo", "soap", "towels"]),
            ("hotel bed", ["king bed", "queen bed", "twin bed", "twin beds", "bunk bed", "bed", "beds"]),
            ("breakfast", ["breakfast", "buffet"]),
            ("hotel restaurant dining", ["restaurant", "restaurants", "dining", "dinner", "lunch", "meal", "culinary", "coffee shop", "cafe"]),
            ("room service", ["room service", "in room dining", "inroom dining"]),
            ("housekeeping", ["housekeeping", "cleanliness", "cleaning", "spotless"]),
            ("hotel staff", ["staff", "hospitality", "concierge", "receptionist", "service"]),
            ("parking", ["parking", "car park", "parking lot"]),
            ("electric vehicle charging station", ["electric car charging", "ev charging", "charging station"]),
            ("airport", ["airport"]),
            ("transportation", ["transportation", "transport", "taxi", "shuttle", "transit center", "station"]),
            ("museum", ["museum", "archaeological museum"]),
            ("temple", ["temple", "temples"]),
            ("stadium", ["stadium"]),
            ("landmark attractions", ["attraction", "attractions", "landmark", "sightseeing", "cultural center", "art center", "theater", "theatre"]),
            ("swimming pool", ["swimming pool", "pool", "poolside"]),
            ("gym", ["gym", "fitness center", "fitness centre", "workout"]),
            ("spa", ["spa", "wellness", "massage", "treatment"]),
            ("game room", ["game room", "games room"]),
            ("meeting room", ["meeting room", "business center", "business centre", "conference"]),
            ("family vacation", ["family", "families", "kids", "children"]),
            ("hotel balcony", ["balcony", "terrace", "patio", "veranda"]),
            ("hotel courtyard", ["courtyard", "palm lined courtyard"]),
            ("beach", ["beach", "beaches", "beachfront", "ocean", "sea", "coast", "shore"]),
            ("island", ["island", "islands"]),
            ("nature", ["nature", "jungle", "forest", "waterfall", "wildlife"]),
            ("snorkeling", ["snorkeling", "snorkelling"]),
            ("diving", ["scuba diving", "diving"]),
            ("kayaking", ["kayaking", "kayak"]),
            ("surfing", ["surfing", "surf"]),
            ("hiking", ["hiking", "hike", "trekking"]),
            ("cycling", ["cycling", "bicycle", "biking"]),
            ("golf", ["golf", "golf course"]),
            ("tennis", ["tennis"]),
            ("water sports", ["water sports", "watersports"]),
            ("check in reception", ["check in", "checkin", "arrival", "front desk"]),
            ("check out departure", ["check out", "checkout", "departure"]),
            ("hotel price", ["price", "cost", "per night", "budget", "affordable", "fees", "taxes"]),
            ("hotel reviews", ["review", "reviews", "rating", "ratings", "score", "guest"]),
        ]

        negative_parking = any(
            phrase in t for phrase in [
                "no parking", "no parking space", "no parking spaces",
                "parking unavailable", "does not offer parking",
                "doesnt offer parking", "without parking"
            ]
        )

        found = []
        for label, words in rules:
            if any(word in t for word in words):
                if label == "parking" and negative_parking:
                    continue
                if label not in found:
                    found.append(label)

        # Negative parking still needs a relevant visual, but not a
        # positive "hotel parking" search.
        if negative_parking:
            return "empty street parking roadside access"

        if found:
            # Keep the query compact. Multiple concepts are intentionally
            # combined when they occur in the same sentence.
            return " ".join(found[:3])

        # Preserve useful nouns from the sentence for places/brands.
        # This is deliberately conservative; filler words are excluded.
        stop = {
            "the", "a", "an", "and", "or", "but", "so", "to", "of", "in",
            "on", "at", "for", "with", "from", "by", "as", "is", "are",
            "was", "were", "be", "been", "being", "this", "that", "these",
            "those", "it", "its", "they", "their", "them", "there", "here",
            "just", "also", "very", "quite", "really", "now", "then",
            "some", "many", "most", "more", "less", "only", "about",
            "around", "roughly", "nearly", "even", "still", "back",
            "well", "like", "one", "two", "three", "four", "five",
            "minute", "minutes", "night", "per", "day", "today", "tomorrow",
            "will", "would", "could", "should", "can", "may", "might",
            "you", "your", "we", "our", "they", "their", "guest", "guests",
        }

        words = re.findall(r"[a-z0-9]+", t)
        useful = []
        for word in words:
            if len(word) < 3 or word in stop:
                continue
            if word.isdigit():
                continue
            if word not in useful:
                useful.append(word)

        # Don't turn generic prose into a bad Pexels query.
        if useful:
            return " ".join(useful[:5])

        scene_text = str(scene).lower()
        defaults = [
            ("room", "hotel room interior"),
            ("amenit", "hotel amenities"),
            ("dining", "hotel restaurant dining"),
            ("location", "hotel location city center"),
            ("review", "hotel review"),
            ("policy", "hotel reception"),
            ("intro", "hotel exterior"),
            ("outside", "hotel exterior"),
        ]

        for key, value in defaults:
            if key in scene_text:
                return value

        # Safe hotel-specific fallback instead of "travel destination".
        return "hotel interior"


    def _visual_result_is_new(self, result):
        if not result:
            return False
        media = result.get("media")
        if not media:
            return False
        key = str(Path(media).resolve())
        if key in self.used_visuals:
            return False
        self.used_visuals.add(key)
        return True

    def clean_visual_query(self, query):
        """Final guard: turn any stale/generic query into a clean Pexels query."""
        q = re.sub(r"\s+", " ", str(query).strip())

        # Pexels search should receive normal words, not debug separators.
        q = q.replace("|", " ")

        # Collapse duplicate location phrases, e.g. "san diego ... san diego".
        words = q.split()
        cleaned = []
        for word in words:
            if not cleaned or word.lower() != cleaned[-1].lower():
                cleaned.append(word)
        q = " ".join(cleaned)

        replacements = {
            "hotel wifi": "wifi",
            "hotel bathroom": "bathroom",
            "luxury hotel bathroom shower": "bathroom",
            "hotel room coffee maker": "coffee maker",
            "hotel room mini fridge": "mini fridge",
            "luxury hotel swimming pool": "swimming pool",
            "hotel gym fitness center": "gym",
            "hotel tennis court": "tennis court",
            "hotel booking": "hotel booking",
            "hotel check in": "reception desk",
            "hotel check out": "hotel checkout",
            "hotel interior": "room interior",
        }

        low = q.lower()
        if low in replacements:
            q = replacements[low]

        return q.strip()

    # =========================================================
    # VISUAL SELECTION
    # =========================================================

    def select_visual(
        self,
        text,
        is_first=False,
        is_new_sentence=False,
        context_before="",
        context_after="",
    ):

        scene_data = self.scene.analyze(text)
        scene = scene_data["scene"]

        visual_queries = self.current_visual_queries or [
            q.strip()
            for q in self.query_generator.generate(text=text, scene=scene).split("||")
            if q.strip()
        ]
        if not visual_queries:
            visual_queries = ["hotel exterior"]

        if is_new_sentence:
            self.current_visual_query_index = 0
        else:
            self.current_visual_query_index = min(
                self.current_visual_query_index + 1,
                len(visual_queries) - 1,
            )

        prompt = self.clean_visual_query(
            visual_queries[self.current_visual_query_index]
        )

        print(f"[SEARCH QUERY] {prompt}")
        self.visual_count += 1

        # First visual: explicit intro/first segment must use original hotel image.
        if is_first:
            result = self.find_first_original(
                text=text,
                scene=scene,
            )
            if result:
                return result

        # Prefer original hotel imagery, but never let originals dominate
        # with 3+ consecutive original clips.
        recent = list(self.recent_visuals)
        allow_original = not (
            len(recent) >= 2
            and recent[-1] == "original"
            and recent[-2] == "original"
        )

        if allow_original:
            result = self.find_original(
                text=text,
                scene=scene,
            )
            if result:
                return result

        # If no original exists, relevant stock image can fill the 15% mix.
        if self.should_try_stock_image():
            print("[MIX] Trying relevant stock image...")
            result = self.find_stock_image(query=prompt)
            if result:
                return result

        # Then use a relevant stock video.
        result = self.find_stock_video(
            query=prompt
        )
        if result:
            self.stock_video_count += 1
            return result

        # Final image attempt.
        result = self.find_stock_image(
            query=prompt
        )
        if result:
            return result

        # Never leave a segment with no media: the renderer would otherwise
        # visually hold the previous clip. A longer, more varied list
        # avoids exhausting Pexels results for a small set of repeated
        # generic queries on long scripts.
        fallbacks = [
            "hotel interior",
            "hotel lobby",
            "hotel exterior",
            "hotel bedroom",
            "hotel room interior",
            "boutique hotel design",
            "hotel courtyard",
            "hotel pool area",
            "travel destination",
            "hotel hallway",
            "city hotel building",
            "hotel amenities",
        ]

        for fallback in fallbacks:
            result = self.find_stock_video(
                query=fallback
            )
            if result:
                self.stock_video_count += 1
                print(f"[FALLBACK VISUAL] {fallback}")
                return result

        for fallback in fallbacks:
            result = self.find_stock_image(
                query=fallback
            )
            if result:
                print(f"[FALLBACK IMAGE] {fallback}")
                return result

        # Absolute final fallback: reuse an already selected visual instead of
        # crashing and leaving an uncovered audio segment. This should only
        # happen when Pexels has no result and the original matcher has no
        # acceptable unused image.
        if self.used_visuals:
            reusable_path = next(iter(self.used_visuals))
            reusable = Path(reusable_path)

            if reusable.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                media_type = "image"
                source_type = "reused_image"
            else:
                media_type = "video"
                source_type = "reused_video"

            print(
                f"[FALLBACK REUSE] {reusable.name}"
            )

            return {
                "media": reusable,
                "media_type": media_type,
                "source_type": source_type,
                "label": None,
                "score": None,
            }

        print("[WARNING] No visual source available for sentence.")
        return None

    # =========================================================
    # BUILD TIMELINE
    # =========================================================

    def build(self):

        print(
            "\n========================================"
        )

        print(
            "Generating hotel review timeline"
        )

        print(
            "========================================"
        )

        # -----------------------------------------------------
        # TRANSCRIPT
        # -----------------------------------------------------

        segments = (
            self.transcript.transcribe(
                self.audio_file
            )
        )

        if not segments:

            raise RuntimeError(
                "No transcript segments found."
            )

        # -----------------------------------------------------
        # ORIGINAL IMAGES
        # -----------------------------------------------------

        print(
            "\n[INFO] Indexing original hotel images..."
        )

        self.matcher.index_images(
            self.images_dir
        )

        # -----------------------------------------------------
        # AUDIO DURATION
        # -----------------------------------------------------

        with AudioFileClip(
            str(self.audio_file)
        ) as audio:

            audio_duration = float(
                audio.duration
            )

        timeline = []

        # -----------------------------------------------------
        # VISUAL TIMELINE
        # -----------------------------------------------------

        # Keep transcript/audio order unchanged. Only the explicit intro
        # segment receives first-visual priority.
        intro_index = None

        for idx, segment in enumerate(segments):
            segment_text = str(
                segment.get("text", "")
            ).strip().lower()

            if (
                segment_text == "intro"
                or segment_text.startswith("intro:")
                or segment_text.startswith("[intro]")
            ):
                intro_index = idx
                break

        for position, (i, segment) in enumerate(
            enumerate(segments)
        ):

            if i == 0:

                start = 0.0

            else:

                start = float(
                    segments[i - 1]["end"]
                )

            if i < len(
                segments
            ) - 1:

                end = float(
                    segments[i]["end"]
                )

            else:

                end = audio_duration

            if end <= start:
                continue

            duration = (
                end - start
            )

            text = segment[
                "text"
            ].strip()

            if not text:
                continue

            context_before = (
                str(segments[i - 1].get("text", "")).strip()
                if i > 0 else ""
            )
            context_after = (
                str(segments[i + 1].get("text", "")).strip()
                if i < len(segments) - 1 else ""
            )

            self.current_visual_queries = [
                self.clean_visual_query(q)
                for q in self.query_generator.generate(
                    text=text,
                    scene=self.scene.analyze(text)["scene"],
                ).split("||")
                if q.strip()
            ]
            if not self.current_visual_queries:
                self.current_visual_queries = ["hotel interior"]
            self.current_visual_query_index = 0

            print(
                f"\n[{i:03d}] "
                f"{start:.2f} -> "
                f"{end:.2f}"
            )

            print(
                f"TEXT: {text}"
            )

            context_before = (
                str(segments[i - 1].get("text", "")).strip()
                if i > 0 else ""
            )
            context_after = (
                str(segments[i + 1].get("text", "")).strip()
                if i < len(segments) - 1 else ""
            )

            first_visual = self.select_visual(
                text,
                is_first=(i == 0 if intro_index is None else i == intro_index),
                is_new_sentence=True,
                context_before=context_before,
                context_after=context_after,
            )

            if first_visual is None:
                continue

            # Every visual piece must be no longer than 4 seconds.
            # A sentence can therefore become 1, 2, 3... visual pieces based
            # strictly on its duration, while still trying to use distinct media.
            max_visual_duration = 4.0
            visual_count_needed = max(1, int((duration + max_visual_duration - 1e-9) // max_visual_duration))

            visuals = [first_visual]

            # Fetch enough distinct visuals to keep every visual <= 4 seconds.
            while len(visuals) < visual_count_needed:
                extra = self.select_visual(
                    text,
                    is_first=False,
                    is_new_sentence=False,
                    context_before=context_before,
                    context_after=context_after,
                )

                if extra is not None and str(extra.get("media")) not in {
                    str(v.get("media")) for v in visuals
                }:
                    visuals.append(extra)
                    continue

                # If Pexels/original media cannot provide another distinct
                # visual, reuse the last selected visual so the hard 4-second
                # duration limit is still guaranteed.
                visuals.append(visuals[-1])

            piece_duration = duration / len(visuals)

            for piece_index, visual in enumerate(visuals):
                piece_start = start + piece_index * piece_duration
                piece_end = (
                    end
                    if piece_index == len(visuals) - 1
                    else piece_start + piece_duration
                )

                timeline.append({
                    "start": piece_start,
                    "end": piece_end,
                    "duration": piece_end - piece_start,
                    "text": text,
                    "media": visual["media"],
                    "media_type": visual["media_type"],
                    "source_type": visual["source_type"],
                    "label": visual["label"],
                    "score": visual["score"],
                    "query": self.current_visual_queries[min(piece_index, len(self.current_visual_queries)-1)],
                    "sentence_index": i,
                    "visual_piece": piece_index + 1,
                    "visual_pieces_total": len(visuals),
                })

                print(
                    f"[SEARCH QUERY] {self.current_visual_queries[min(piece_index, len(self.current_visual_queries)-1)]}"
                )
                print(
                    f"SOURCE: {visual['source_type']}"
                )

                print(
                    f"MEDIA: {Path(visual['media']).name}"
                )

        # -----------------------------------------------------
        # DEBUG
        # -----------------------------------------------------

        print(
            "\n========================================"
        )

        print(
            f"Segments : {len(segments)}"
        )

        print(
            f"Timeline : {len(timeline)}"
        )

        print(
            f"Audio    : "
            f"{audio_duration:.3f} sec"
        )

        print(
            f"Stock Images Used : "
            f"{self.stock_image_count}"
        )

        print(
            f"Stock Videos Used : "
            f"{self.stock_video_count}"
        )

        print(
            "========================================"
        )

        total = 0.0

        for i, item in enumerate(
            timeline
        ):

            total += float(
                item["duration"]
            )

            print(
                f"{i:03d} | "
                f"{item['start']:.3f} -> "
                f"{item['end']:.3f} | "
                f"{item['duration']:.3f} | "
                f"{item['source_type']} | "
                f"{Path(item['media']).name}"
            )

        print(
            "----------------------------------------"
        )

        print(
            f"Timeline Total : "
            f"{total:.3f} sec"
        )

        print(
            f"Audio Duration : "
            f"{audio_duration:.3f} sec"
        )

        print(
            "========================================"
        )

        return timeline