"""Tạo trang review ngoại tuyến, dùng ảnh và nhãn của lô được giao."""

import argparse
import base64
import json
from pathlib import Path

from validate import class_names, load_json, local_file, mask_spans, read_detections, read_rgb


def review_cases(delivery, candidates, rules=None, face_options=False):
    manifest = load_json(local_file(delivery, "manifest.json"))["items"]
    cases = []
    for index, candidate in enumerate(load_json(candidates)["candidates"]):
        item = manifest[candidate["image"]]
        width, height, pixels = read_rgb(local_file(delivery, item["mask"]))
        sid = candidate["segment"]["id"]
        runs = mask_spans(width, height, pixels, {sid})[sid]
        cases.append({
            **candidate,
            "id": f"candidate-{index}",
            "kind": "candidate",
            "mask": " ".join(f"M{left} {y + .5}h{right - left}" for y, left, right in runs),
        })
    if rules:
        for error in load_json(rules)["errors"]:
            if error["type"] == "wrong_hash":
                cases.append({"id": f"hash-{error['target']}", "kind": "hash", "image": error["target"]})
    if face_options:
        names = class_names(local_file(delivery, "classes.txt"))
        ranked = []
        for name, item in manifest.items():
            if not local_file(delivery, item["image"]).is_file():
                continue
            boxes, _ = read_detections(local_file(delivery, item["label"]), names, 1, 1)
            person = max((d.box.area for d in boxes if d.name == "person"), default=0)
            if person:
                ranked.append((person, name))
        for _, image in sorted(ranked, reverse=True)[:12]:
            cases.append({"id": f"face-{image}", "kind": "face", "image": image})

    photos = {}
    for case in cases:
        name = case["image"]
        if name not in photos:
            path = local_file(delivery, manifest[name]["image"])
            if path.is_file():
                data = base64.b64encode(path.read_bytes()).decode("ascii")
                photos[name] = f"data:image/jpeg;base64,{data}"
    return {"cases": cases, "photos": photos}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--rules", type=Path, help="Kèm kiểm tra ảnh có sai hash")
    parser.add_argument("--face-options", action="store_true", help="Thêm ảnh để chọn ví dụ bảo mật")
    parser.add_argument("--suggestions", type=Path, help="Gợi ý hiển thị để người xem đối chiếu")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    delivery = args.delivery.resolve()
    if args.out.resolve().is_relative_to(delivery):
        parser.error("Trang review phải nằm ngoài delivery.")
    data = review_cases(delivery, args.candidates, args.rules, args.face_options)
    data["lot"] = args.out.stem
    data["suggestions"] = load_json(args.suggestions) if args.suggestions else {}
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("review.html").read_text(encoding="utf-8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(template.replace("__REVIEW_DATA__", payload), encoding="utf-8")
    print(f"{len(data['cases'])} mục xem ảnh → {args.out}")


if __name__ == "__main__":
    main()
