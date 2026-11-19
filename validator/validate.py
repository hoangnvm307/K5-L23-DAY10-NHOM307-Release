"""Kiểm luật và lập danh sách ứng viên từ hai bộ nhãn trong delivery."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations, groupby
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pngutil import read_rgb


@dataclass(frozen=True)
class Box:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top

    @property
    def area(self):
        return self.width * self.height

    def intersection(self, other):
        return max(0, min(self.right, other.right) - max(self.left, other.left)) * max(
            0, min(self.bottom, other.bottom) - max(self.top, other.top)
        )

    def as_list(self):
        return [round(v, 2) for v in (self.left, self.top, self.right, self.bottom)]


@dataclass(frozen=True)
class Detection:
    line: int
    name: str
    box: Box


@dataclass
class Segment:
    id: int
    name: str
    spans: list[tuple[int, int, int]]
    area: int
    box: Box

    def pixels_in(self, box):
        # A small margin accommodates pixel centres and rounded YOLO coordinates.
        left = math.ceil(box.left - 1.5)
        right = math.ceil(box.right + 0.5)
        top = math.ceil(box.top - 1.5)
        bottom = math.ceil(box.bottom + 0.5)
        return sum(
            max(0, min(right, end) - max(left, start))
            for y, start, end in self.spans
            if top <= y < bottom
        )


@dataclass(frozen=True)
class Pair:
    detection: Detection
    segment: Segment
    iou: float
    coverage: float
    segment_extent: float
    box_extent: float


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def class_names(path):
    return {
        int(number): name
        for number, name in (line.split(maxsplit=1) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    }


def local_file(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Đường dẫn nằm ngoài delivery: {relative}")
    return path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_detections(path, names, width, height):
    detections = []
    faults = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        category, *coords = line.split()
        try:
            number = float(category)
            name = names[int(number)] if number.is_integer() else None
        except (ValueError, OverflowError, KeyError):
            name = None
        if name is None:
            faults.add("invalid_class")
        try:
            x, y, w, h = map(float, coords)
        except ValueError:
            faults.add("bbox_out_of_bounds")
            continue
        if not all(math.isfinite(v) for v in (x, y, w, h)):
            faults.add("bbox_out_of_bounds")
            continue
        left, top, right, bottom = x - w / 2, y - h / 2, x + w / 2, y + h / 2
        # Six-decimal YOLO serialization can move a true edge by up to 0.75e-6.
        tolerance = 1e-6
        if w <= 0 or h <= 0 or min(left, top) < -tolerance or max(right, bottom) > 1 + tolerance:
            faults.add("bbox_out_of_bounds")
            continue
        if name is not None:
            detections.append(Detection(line_number, name, Box(left * width, top * height, right * width, bottom * height)))

    for first, second in combinations(detections, 2):
        a, b = first.box, second.box
        if (
            first.name == second.name
            and max(abs(a.width - b.width), abs(a.height - b.height)) <= 0.01
            and max(abs(a.left - b.left), abs(a.top - b.top)) <= 2.1
        ):
            faults.add("duplicate_box")
            break
    return detections, faults


def mask_spans(width, height, pixels, ids):
    spans = defaultdict(list)
    for y in range(height):
        row = pixels[y * width * 3 : (y + 1) * width * 3]
        x = 0
        for (r, g, b), run in groupby(zip(row[::3], row[1::3], row[2::3])):
            end = x + sum(1 for _ in run)
            sid = r + (g << 8) + (b << 16)
            if sid in ids:
                spans[sid].append((y, x, end))
            x = end
    return spans


def read_segments(segments_info, categories, width, height, pixels):
    faults = set()
    things = []
    for item in segments_info:
        category = categories.get(item["category_id"])
        if category is None:
            faults.add("invalid_category_id")
        elif category["isthing"] and item["id"]:
            things.append((item, category["name"]))
    if not things:
        return [], faults
    spans = mask_spans(width, height, pixels, {item["id"] for item, _ in things})
    segments = []
    for item, name in things:
        runs = spans[item["id"]]
        area = sum(end - start for _, start, end in runs)
        if area < item["area"]:
            faults.add("thing_overlap")
        if area and not item.get("iscrowd"):
            bounds = Box(min(s for _, s, _ in runs), runs[0][0], max(e for _, _, e in runs), runs[-1][0] + 1)
            segments.append(Segment(item["id"], name, runs, area, bounds))
    return segments, faults


def nearby_pairs(detections, segments):
    for detection in detections:
        for segment in segments:
            intersection = detection.box.intersection(segment.box)
            if not intersection:
                continue
            yield Pair(
                detection, segment,
                intersection / (detection.box.area + segment.box.area - intersection),
                segment.pixels_in(detection.box) / segment.area,
                intersection / segment.box.area,
                intersection / detection.box.area,
            )


def candidate(image, kind, width, height, segment, pairs=(), alternatives=()):
    return {
        "image": image,
        "type": kind,
        "types": [kind, *alternatives],
        "size": [width, height],
        "segment": {"id": segment.id, "class": segment.name, "bbox": segment.box.as_list(), "area": segment.area},
        "boxes": [
            {"line": p.detection.line, "class": p.detection.name, "bbox": p.detection.box.as_list(),
             "iou": round(p.iou, 3), "mask_coverage": round(p.coverage, 3)}
            for p in pairs
        ],
    }


def find_candidates(image, width, height, detections, segments):
    pairs = list(nearby_pairs(detections, segments))
    same_class = [p for p in pairs if p.detection.name == p.segment.name]
    matched_boxes = set()
    matched_segments = set()
    for p in sorted(same_class, key=lambda p: (p.iou, p.coverage), reverse=True):
        if p.coverage >= 0.90 and (p.iou >= 0.48 or p.box_extent >= 0.72):
            if p.detection.line not in matched_boxes and p.segment.id not in matched_segments:
                matched_boxes.add(p.detection.line)
                matched_segments.add(p.segment.id)

    proposals = []
    for seg in segments:
        if seg.id in matched_segments:
            continue
        plausible = [
            p for p in same_class
            if p.segment.id == seg.id and p.detection.line not in matched_boxes
            and p.box_extent >= 0.68 and p.coverage >= 0.13
        ]
        for first, second in combinations(sorted(plausible, key=lambda p: p.coverage, reverse=True), 2):
            a, b = first.detection.box, second.detection.box
            if a.intersection(b) <= 0.24 * min(a.area, b.area) and first.coverage + second.coverage >= 0.76:
                proposals.append(candidate(image, "instance_merge", width, height, seg, (first, second)))
                matched_boxes.update((first.detection.line, second.detection.line))
                matched_segments.add(seg.id)
                break

    for p in sorted(pairs, key=lambda p: (p.iou, p.coverage), reverse=True):
        box, seg = p.detection, p.segment
        if box.line in matched_boxes or seg.id in matched_segments:
            continue
        if box.name != seg.name and p.iou >= 0.57 and p.coverage >= 0.84:
            proposals.append(candidate(image, "class_swap", width, height, seg, (p,), ("category_swap",)))
        elif (
            box.name == seg.name and p.iou >= 0.23 and 0.22 <= p.coverage < 0.90
            and 0.42 <= box.box.area / seg.box.area <= 2.25
        ):
            proposals.append(candidate(image, "bbox_drift", width, height, seg, (p,)))
        else:
            continue
        matched_boxes.add(box.line)
        matched_segments.add(seg.id)

    for seg in segments:
        if seg.id in matched_segments or seg.area < max(650, 0.005 * width * height):
            continue
        nearby = [p for p in pairs if p.segment.id == seg.id]
        if not any(p.coverage >= 0.22 or (p.detection.name == seg.name and p.iou >= 0.12) for p in nearby):
            proposals.append(candidate(image, "missing_box", width, height, seg))
    return proposals


def validate(delivery, include_candidates):
    manifest = load_json(local_file(delivery, "manifest.json"))["items"]
    metadata = {m["image"]: m for m in load_json(local_file(delivery, "metadata.json"))["items"]}
    jobs = {row["job_id"]: row for row in read_csv(local_file(delivery, "jobs.csv"))}
    names = class_names(local_file(delivery, "classes.txt"))
    panoptic = load_json(local_file(delivery, "panoptic.json"))
    categories = {c["id"]: c for c in panoptic["categories"]}
    annotations = {Path(a["file_name"]).name: a["segments_info"] for a in panoptic["annotations"]}

    faults = set()
    candidates = []
    scenes = defaultdict(set)
    for name, item in sorted(manifest.items()):
        meta = metadata[name]
        scenes[meta["scene_id"]].add(meta["split"])
        doc = {key: local_file(delivery, item[key]) for key in ("image", "label", "mask")}
        image_faults = set()
        if not doc["image"].is_file():
            image_faults.add("missing_image")
        if any(path.is_file() and sha256(path) != item[f"{key}_sha256"] for key, path in doc.items()):
            image_faults.add("wrong_hash")
        if meta["guideline_version"] != jobs[meta["job_id"]]["guideline"]:
            image_faults.add("guideline_mismatch")
        width, height, pixels = read_rgb(doc["mask"])
        detections, detection_faults = read_detections(doc["label"], names, width, height)
        segments, panoptic_faults = read_segments(annotations[doc["mask"].name], categories, width, height, pixels)
        image_faults.update(detection_faults | panoptic_faults)
        faults.update((kind, name) for kind in image_faults)
        if include_candidates and not image_faults:
            candidates.extend(find_candidates(name, width, height, detections, segments))

    faults.update(("scene_leak", scene) for scene, splits in scenes.items() if len(splits) > 1)
    return [{"type": kind, "target": name} for kind, name in sorted(faults)], candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--candidates", type=Path)
    args = parser.parse_args()
    delivery = args.delivery.resolve()
    outputs = [p.resolve() for p in (args.out, args.candidates) if p is not None]
    if len(set(outputs)) != len(outputs) or any(p.is_relative_to(delivery) for p in outputs):
        parser.error("Hai file đầu ra phải tách biệt và nằm ngoài delivery.")
    errors, candidates = validate(delivery, args.candidates is not None)
    write_json(args.out, {"errors": errors})
    if args.candidates is not None:
        write_json(args.candidates, {"candidates": candidates})
    print(f"Lỗi luật: {len(errors)}. Ứng viên: {len(candidates)}.")


if __name__ == "__main__":
    main()
