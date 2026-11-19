"""Chốt bài từ phiếu xem ảnh, tạo v2 và chạy các script kiểm tra gốc."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from trace_query import trace
from validate import class_names, load_json, local_file, read_csv, sha256, write_json
from pack_release import build_zip

ROOT = Path(__file__).resolve().parents[1]
DETECTION_REWORK = {
    "missing_image", "invalid_class", "bbox_out_of_bounds", "duplicate_box",
    "class_swap", "bbox_drift", "missing_box",
}
PANOPTIC_ERRORS = {"invalid_category_id", "thing_overlap", "category_swap", "instance_merge"}


def run_script(name, *args):
    subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / name), *map(str, args)],
        cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"}, check=True,
    )


def write_csv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def verify_review(review, candidates):
    rows = review["reviewed"]
    if len(rows) != len(candidates):
        raise ValueError("Số dòng review chưa khớp danh sách ứng viên.")
    for row, candidate in zip(rows, candidates):
        if (
            row["image"] != candidate["image"] or row["type"] not in candidate["types"]
            or row["verdict"] not in {"confirmed", "rejected"}
            or not re.fullmatch(r"\[[^\]]+\]\s+.{20,}", row["note"].strip(), re.S)
        ):
            raise ValueError(f"Dòng {candidate['image']} cần kết luận và ghi chú có tên người xem.")
    return rows


def merge(delivery, out, rules, candidates, review):
    rows = verify_review(review, load_json(candidates)["candidates"])
    out.mkdir(parents=True, exist_ok=True)
    log = out / "review_log.csv"
    write_csv(log, ("image", "type", "verdict", "note"), (
        (r["image"], r["type"], r["verdict"], r["note"]) for r in rows
    ))
    run_script("merge_review.py", "--rules", rules, "--review", log, "--out", out / "errors.json")
    write_json(out / "trace.json", trace(delivery))
    return load_json(out / "errors.json")["errors"]


def scene_majority(metadata):
    splits = defaultdict(Counter)
    for m in metadata.values():
        splits[m["scene_id"]][m["split"]] += 1
    selected = {}
    for scene, counts in splits.items():
        ranked = counts.most_common()
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            raise ValueError(f"Cần xác định split của {scene} vì số ảnh hai split bằng nhau.")
        selected[scene] = ranked[0][0]
    return selected


def write_security(path, face):
    path.write_text(f"""# Bảo mật khi làm việc

## 1. Ca USB

Tôi lưu trạng thái job trên máy và hệ thống được cấp, rồi xin người phụ trách sắp xếp tiếp ca hoặc cấp phương thức truy cập từ xa đã duyệt. Chép lô qua USB hoặc email cá nhân đưa ảnh, nhãn và mã người làm ra ngoài hệ thống kiểm soát. Nhờ người khác dùng tài khoản của mình làm sai lịch sử truy vết và quyền truy cập.

## 2. Năm việc

- Mở job được giao trên máy công ty. Được, trong phạm vi quyền cho job đó.
- Chụp màn hình gửi người quen. Không được vì ảnh và giao diện có thể chứa dữ liệu hoặc thông tin dự án.
- Chép lô ra USB cá nhân. Không được vì bản sao nằm ngoài kiểm soát truy cập và nhật ký.
- Dán nhãn thật của dự án vào chatbot. Không được vì dịch vụ bên ngoài có thể nhận và lưu dữ liệu của dự án.
- Đưa tài khoản CVAT cho đồng nghiệp. Không được. Người phụ trách cấp quyền trên tài khoản riêng để mỗi thao tác gắn đúng người.

## 3. Ca khuôn mặt

Ảnh {face}.jpg trong lô COCO luyện tập có khuôn mặt người nhìn rõ. Nếu guideline dự án yêu cầu làm mờ, tôi đặt **Hold** cho lô, dừng bàn giao và báo người phụ trách dữ liệu cùng người phụ trách bảo mật qua kênh nội bộ. Báo mã ảnh, mã lô, job và điều khoản guideline. Tôi giữ nguyên v1 để đối chiếu. Việc làm mờ hoặc loại ảnh cần người có quyền xử lý, duyệt lại nhãn, lập manifest mới và liên kết phiên bản trong lineage.
""", encoding="utf-8")


def build_v2(delivery, v2, rid, errors, review):
    manifest = load_json(local_file(delivery, "manifest.json"))["items"]
    metadata = {m["image"]: m for m in load_json(local_file(delivery, "metadata.json"))["items"]}
    jobs = {j["job_id"]: j for j in read_csv(local_file(delivery, "jobs.csv"))}
    names = class_names(local_file(delivery, "classes.txt"))
    splits = scene_majority(metadata)
    hashes = review.get("hash_review", {})
    hash_errors = {e["target"] for e in errors if e["type"] == "wrong_hash"}
    if set(hashes) != hash_errors or set(hashes.values()) - {"intact", "damaged"}:
        raise ValueError("Cần kết luận kiểm ảnh cho từng lỗi wrong_hash.")
    face = review.get("face_example")
    if face not in manifest or not local_file(delivery, manifest[face]["image"]).is_file():
        raise ValueError("Cần chọn ảnh khuôn mặt đã xem trong lô luyện tập.")

    rework = defaultdict(set)
    panoptic = []
    for error in errors:
        kind, image = error["type"], error["target"]
        if kind in DETECTION_REWORK or (kind == "wrong_hash" and hashes[image] == "damaged"):
            rework[image].add(kind)
        if kind in PANOPTIC_ERRORS:
            panoptic.append(f"{image} ({kind})")

    for folder in ("images", "labels"):
        (v2 / folder).mkdir(parents=True)
    counts = Counter()
    files, trace_rows, queue_rows = [], [], []
    guideline_jobs = defaultdict(set)
    split_changes, guideline_changes = [], []
    for image, item in sorted(manifest.items()):
        m = metadata[image]
        job = jobs[m["job_id"]]
        people = (job["annotator"], job["reviewer"])
        if image in rework:
            for kind in sorted(rework[image]):
                action = {
                    "missing_image": "Khôi phục file ảnh và kiểm lại nhãn",
                    "wrong_hash": "Yêu cầu lại ảnh đúng và kiểm lại nhãn",
                }.get(kind, "Gán lại nhãn detection rồi chuyển người kiểm")
                queue_rows.append((image, kind, *people, action))
            continue

        for key, folder, ext in (("image", "images", ".jpg"), ("label", "labels", ".txt")):
            source = local_file(delivery, item[key])
            target = v2 / folder / (image + ext)
            shutil.copyfile(source, target)
            digest = sha256(target)
            if digest != item[f"{key}_sha256"] and (key != "image" or hashes.get(image) != "intact"):
                raise ValueError(f"Hash ngoài phạm vi sửa của v2: {source}")
            files.append((target.relative_to(v2).as_posix(), digest))
            if key == "label":
                for line in target.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        counts[names[int(float(line.split()[0]))]] += 1
        scene, guideline = m["scene_id"], job["guideline"]
        trace_rows.append((image, scene, splits[scene], m["job_id"], *people, guideline))
        guideline_jobs[guideline].add(m["job_id"])
        if m["split"] != splits[scene]:
            split_changes.append(f"{image} ({scene}, {m['split']} → {splits[scene]})")
        if m["guideline_version"] != guideline:
            guideline_changes.append(f"{image} ({m['guideline_version']} → {guideline})")

    n_labels = sum(counts.values())
    n_images = len(trace_rows)
    n_defects = len({row["target"] for row in errors})
    rate = n_defects / len(manifest)
    v1_decision = "Hold" if rate > .02 else "Release"
    qc_percent = f"{rate:.1%}".replace(".", ",")
    write_csv(v2 / "manifest.csv", ("file", "sha256"), sorted(files))
    write_csv(v2 / "label_summary.csv", ("class", "count"), [
        *((name, counts[name]) for name in names.values() if counts[name]), ("TOTAL", n_labels),
    ])
    write_csv(v2 / "truyvet.csv", ("image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"), trace_rows)
    write_csv(v2 / "rework_queue.csv", ("image", "type", "annotator", "reviewer", "action"), queue_rows)
    guideline = "; ".join(f"{version} ({', '.join(sorted(job_ids))})" for version, job_ids in sorted(guideline_jobs.items()))
    hash_note = ", ".join(name for name, decision in sorted(hashes.items()) if decision == "intact") or "không có"
    owners = sorted({(row[0], row[2], row[3]) for row in queue_rows})
    note = [
        f"Ảnh mở được và đúng nội dung, đã tính lại SHA-256: {hash_note}.",
        f"Split theo đa số của cảnh: {', '.join(split_changes) or 'không cần đổi'}.",
        f"Guideline lấy theo job: {', '.join(guideline_changes) or 'không cần đổi'}.",
        f"Rework theo jobs.csv (mã người gán / người kiểm): "
        f"{', '.join(f'{i} ({a}/{r})' for i, a, r in owners) or 'không có'}.",
        f"Ảnh chỉ có lỗi panoptic giữ trong bản detection và báo team panoptic: {', '.join(sorted(panoptic)) or 'không có'}.",
    ]
    (v2 / "README.txt").write_text(
        f"Release: {v2.name}\nParent: {rid}\nSố ảnh: {n_images}\nSố nhãn: {n_labels}\n"
        f"Guideline: {guideline}\nQC v1: {n_defects}/{len(manifest)} = {qc_percent}\n"
        f"Kết luận v1: {v1_decision} — {qc_percent} {'vượt' if rate > .02 else 'trong'} ngưỡng 2%.\n"
        f"Kết luận v2: Release — 0/{n_images} ảnh còn lỗi detection đã phát hiện sau khi tách {len(rework)} ảnh "
        f"vào rework và sửa manifest, guideline, split; chỉ bàn giao detection.\n"
        f"Ghi chú: {' '.join(note)}\n",
        encoding="utf-8",
    )
    return face, v1_decision


def lineage_event(root, event, rid, **fields):
    path = root / "lineage.jsonl"
    target = {"event": event, "release_id": rid, **fields}
    if path.is_file() and any(
        target.items() <= json.loads(line).items()
        for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ):
        return
    args = [arg for key, value in fields.items() for arg in (f"--{key.replace('_', '-')}", value)]
    run_script("lineage.py", "--root", root, "record", "--event", event, "--release-id", rid, *args)


def finalize_practice(run, review):
    delivery = (run / "delivery").resolve()
    errors = merge(delivery, run, run / "rules.json", run / "candidates.json", review)
    rid = load_json(local_file(delivery, "release.json"))["release_id"]
    handover = run / "handover"
    handover.mkdir(exist_ok=True)
    v2 = handover / f"{rid}_v2"
    with TemporaryDirectory(prefix="handover-", dir=run) as work:
        staged = Path(work) / v2.name
        face, decision = build_v2(delivery, staged, rid, errors, review)
        run_script("pack_release.py", staged)
        if v2.exists():
            if build_zip(v2) != staged.with_suffix(".zip").read_bytes():
                raise FileExistsError(f"{v2} đã có nội dung khác với bản mới.")
        else:
            staged.replace(v2)
        for suffix in (".zip", ".sha256"):
            staged.with_suffix(suffix).replace(v2.with_suffix(suffix))
    write_security(run / "security.md", face)
    lineage_event(run.parent, "decision", rid, decision=decision.upper())
    lineage_event(run.parent, "release", v2.name, parent=rid)
    run_script("lineage.py", "--root", run.parent, "impact", "--release-id", rid)
    run_script("check_handover.py", "--run", run)
    run_script("score_findings.py", "--run", run)
    run_script("export_submission.py", "--run", run)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", type=Path, help="Thư mục lô luyện tập")
    mode.add_argument("--hidden", action="store_true", help="Đề ẩn giải nén ở delivery/")
    parser.add_argument("--review", required=True, type=Path, help="Tệp JSON xuất từ trang review")
    args = parser.parse_args()
    review = load_json(args.review)
    if args.hidden:
        out = ROOT / "submission" / "de_an"
        merge(ROOT / "delivery", out, ROOT / "runs" / "de_an" / "rules.json", out / "candidates.json", review)
    else:
        finalize_practice(args.run.resolve(), review)


if __name__ == "__main__":
    main()
