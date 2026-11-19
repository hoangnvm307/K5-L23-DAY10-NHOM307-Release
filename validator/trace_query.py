"""Truy vết ticket theo cảnh, phiên bản guideline của job và lớp detection."""

import argparse
import re
from pathlib import Path

from validate import class_names, load_json, local_file, read_csv, write_json


def trace(delivery):
    ticket = local_file(delivery, "incoming/ticket.md").read_text(encoding="utf-8")
    changelog = local_file(delivery, "guideline/changelog.md").read_text(encoding="utf-8")
    change = re.search(r"(?im)^\s*-\s*Lớp\s+`([^`]+)`[^\n]*?\b(v\d+\.\d+)\b", changelog)
    if not change:
        raise ValueError("Không xác định được lớp thay đổi và phiên bản cũ từ changelog.")
    name, old_guideline = change.groups()
    reported_scenes = set(re.findall(r"\bscene_[\w-]+\b", ticket))
    if not reported_scenes:
        raise ValueError("Ticket không ghi mã cảnh.")
    names = class_names(local_file(delivery, "classes.txt"))
    class_id = next(number for number, label in names.items() if label == name)
    jobs = {j["job_id"]: j for j in read_csv(local_file(delivery, "jobs.csv"))}
    manifest = load_json(local_file(delivery, "manifest.json"))["items"]
    metadata = load_json(local_file(delivery, "metadata.json"))["items"]

    result = {"tier_a": [], "tier_b": [], "notify": []}
    people = set()
    for entry in metadata:
        job = jobs[entry["job_id"]]
        if job["guideline"] != old_guideline:
            continue
        image = entry["image"]
        label_path = local_file(delivery, manifest[image]["label"])
        labels = [line.split() for line in label_path.read_text(encoding="utf-8").splitlines()]
        if not any(fields and float(fields[0]) == class_id for fields in labels):
            continue
        tier = "tier_a" if entry["scene_id"] in reported_scenes else "tier_b"
        result[tier].append(image)
        people.update((job["annotator"], job["reviewer"]))
    result["notify"] = list(people)
    return {key: sorted(values) for key, values in result.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    delivery = args.delivery.resolve()
    if args.out.resolve().is_relative_to(delivery):
        parser.error("File truy vết phải nằm ngoài delivery.")
    result = trace(delivery)
    write_json(args.out, result)
    print(" · ".join(f"{key}: {len(values)}" for key, values in result.items()))
