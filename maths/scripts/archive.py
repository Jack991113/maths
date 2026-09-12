#!/usr/bin/env python3
"""Append-only question revisions and attempt events; images stay in the archive."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys
import tempfile
import uuid
import zipfile

VERSION = 1
DB_NAME = "archive.sqlite3"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".heif", ".tif", ".tiff", ".bmp"}
SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO metadata VALUES ('schema_version', '1');
CREATE TABLE questions (id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
CREATE TABLE revisions (
  question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  version INTEGER NOT NULL, created_at TEXT NOT NULL, data TEXT NOT NULL,
  PRIMARY KEY (question_id, version));
CREATE TABLE identities (
  identity TEXT PRIMARY KEY,
  question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE);
CREATE TABLE attempts (
  id TEXT PRIMARY KEY,
  question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  question_version INTEGER NOT NULL, recorded_at TEXT NOT NULL, data TEXT NOT NULL,
  FOREIGN KEY (question_id, question_version) REFERENCES revisions(question_id, version));
CREATE TABLE attempt_annotations (
  id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
  recorded_at TEXT NOT NULL, data TEXT NOT NULL);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def obj(value, allowed, label):
    require(isinstance(value, dict), f"{label} 必须是 JSON 对象")
    require(not set(value) - set(allowed), f"{label} 含未知字段: {', '.join(sorted(set(value) - set(allowed)))}")
    return value


def string(value, label, required=False):
    require(isinstance(value, str), f"{label} 必须是文字")
    require(not required or bool(value.strip()), f"{label} 不能为空")
    return value.strip()


def choice(value, choices, label):
    require(isinstance(value, str) and value in choices, f"{label} 只支持 {', '.join(choices)}")
    return value


def strings(value, label, required=False):
    require(isinstance(value, list), f"{label} 必须是数组")
    result = list(dict.fromkeys(string(item, label, True) for item in value))
    require(not required or bool(result), f"{label} 不能为空")
    return result


def load_json(path):
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"JSON 字段重复: {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)


def prepare_images(paths, label):
    """Read now; validate every input before touching the archive."""
    require(isinstance(paths, list), f"{label} 必须是图片路径数组")
    records, blobs = [], {}
    for value in paths:
        path = Path(string(value, label, True)).expanduser()
        require(path.is_file(), f"图片不存在: {path}")
        suffix = path.suffix.lower()
        require(suffix in IMAGE_SUFFIXES, f"不支持的图片后缀: {suffix}")
        content = path.read_bytes()
        require(bool(content), f"图片为空: {path}")
        digest = hashlib.sha256(content).hexdigest()
        relative = f"assets/{digest}{suffix}"
        if relative not in blobs:
            records.append({"path": relative, "sha256": digest, "original_name": path.name})
        blobs[relative] = content
    return records, blobs


def prepare_question(raw):
    raw = obj(raw, ("stem", "topics", "source_images", "source_item_key", "recognition", "source", "answer", "notes"), "question")
    result = {"stem": string(raw.get("stem"), "stem", True),
              "topics": strings(raw.get("topics"), "topics", True),
              "notes": string(raw.get("notes", ""), "notes")}
    recognition = obj(raw.get("recognition", {}), ("status", "notes"), "recognition")
    result["recognition"] = {
        "status": choice(recognition.get("status", "needs_confirmation"), ("confirmed", "needs_confirmation"), "recognition.status"),
        "notes": string(recognition.get("notes", ""), "recognition.notes")}
    source = obj(raw.get("source", {}), ("type", "citation"), "source")
    source_type = choice(source.get("type"), ("user_upload", "original", "verified_past_paper", "adapted", "unverified_reference"), "source.type")
    result["source"] = {"type": source_type,
                        "citation": string(source.get("citation", ""), "source.citation", source_type == "verified_past_paper")}
    answer = obj(raw.get("answer", {}), ("text", "verification_status", "verification_notes"), "answer")
    verified = choice(answer.get("verification_status", "unverified"), ("unverified", "verified", "needs_review"), "answer.verification_status")
    result["answer"] = {"text": string(answer.get("text", ""), "answer.text", verified == "verified"),
                        "verification_status": verified,
                        "verification_notes": string(answer.get("verification_notes", ""), "answer.verification_notes", verified == "verified")}
    images, blobs = prepare_images(raw.get("source_images", []), "source_images")
    require(source_type != "user_upload" or bool(images), "user_upload 必须保留原始 source_images")
    result["source_images"] = images
    result["source_item_key"] = string(raw.get("source_item_key", ""), "source_item_key", bool(images))
    return result, blobs


def prepare_attempt(raw):
    raw = obj(raw, ("occurred_at", "kind", "process_text", "process_images", "result", "score", "max_score", "assistance", "error_analysis", "linked_attempt_id", "question_version", "notes"), "attempt")
    occurred_at = raw.get("occurred_at")
    if occurred_at is not None:
        string(occurred_at, "occurred_at", True)
        try:
            parsed = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("occurred_at 应为 ISO 8601 时间；不知道时填 null") from exc
        require(parsed.tzinfo is not None, "occurred_at 必须包含时区；不知道时填 null")
    result = {"occurred_at": occurred_at,
              "kind": choice(raw.get("kind", "initial"), ("initial", "correction", "retest"), "kind"),
              "process_text": string(raw.get("process_text", ""), "process_text"),
              "result": choice(raw.get("result", "unknown"), ("correct", "incorrect", "partial", "unknown"), "result"),
              "assistance": choice(raw.get("assistance", "unknown"), ("none", "hint", "answer_seen", "unknown"), "assistance"),
              "notes": string(raw.get("notes", ""), "notes")}
    result["process_images"], blobs = prepare_images(raw.get("process_images", []), "process_images")
    require(result["process_text"] or result["process_images"], "作答事件必须有实际作答文字、图片或学生明确报告；仅有题目不能生成事件")
    result.update(score=raw.get("score"), max_score=raw.get("max_score"))
    validate_score(result)
    result["error_analysis"] = prepare_error_analysis(raw.get("error_analysis", {}))
    linked = raw.get("linked_attempt_id")
    result["linked_attempt_id"] = None if linked is None else string(linked, "linked_attempt_id", True)
    version = raw.get("question_version")
    require(version is None or (type(version) is int and version >= 1), "question_version 必须是正整数")
    return result, blobs, version


def validate_score(result):
    score, maximum = result["score"], result["max_score"]
    require((score is None) == (maximum is None), "score 与 max_score 应同时提供或同时为 null")
    if score is not None:
        require(all(type(n) in (int, float) and (type(n) is int or math.isfinite(n)) for n in (score, maximum)), "分数必须是有限数值")
        require(maximum > 0 and 0 <= score <= maximum, "必须满足 0 <= score <= max_score 且满分大于 0")
        require(result["result"] != "correct" or score == maximum, "correct 与非满分 score 矛盾")
        require(result["result"] not in ("incorrect", "partial") or score < maximum, "错误/部分正确与满分 score 矛盾")


def prepare_error_analysis(raw):
    error = obj(raw, ("status", "causes", "evidence"), "error_analysis")
    status = choice(error.get("status", "unknown"), ("unknown", "hypothesis", "confirmed"), "error_analysis.status")
    causes = strings(error.get("causes", []), "error_analysis.causes")
    evidence = string(error.get("evidence", ""), "error_analysis.evidence", bool(causes))
    require(not causes or status != "unknown", "有错因时须明确 hypothesis 或 confirmed，并提供证据")
    require(status == "unknown" or bool(causes), "hypothesis/confirmed 须提供 causes")
    return {"status": status, "causes": causes, "evidence": evidence}


def connect(root):
    path = root / DB_NAME
    require(path.is_file(), f"档案未初始化: {path}；请先运行 init")
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA secure_delete = ON")
    try:
        version = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
        require(version is not None and version[0] == str(VERSION), "档案版本不兼容，未作任何覆盖")
    except Exception:
        db.close()
        raise
    return db


def initialize(root):
    root.mkdir(parents=True, exist_ok=True)
    path = root / DB_NAME
    if path.exists():
        with closing(connect(root)) as db:
            require(db.execute("PRAGMA quick_check").fetchone()[0] == "ok", "现有档案检查失败")
        return {"status": "existing", "root": str(root)}
    # Exclusive creation prevents accidentally replacing an existing database.
    with path.open("xb"):
        pass
    try:
        with closing(sqlite3.connect(path)) as db:
            db.executescript(SCHEMA)
        (root / "assets").mkdir(exist_ok=True)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {"status": "initialized", "root": str(root)}


def current(db, question_id):
    row = db.execute("SELECT q.id,q.created_at,r.version,r.created_at AS revised_at,r.data FROM questions q JOIN revisions r ON r.question_id=q.id WHERE q.id=? ORDER BY r.version DESC LIMIT 1", (question_id,)).fetchone()
    require(row is not None, f"题目不存在: {question_id}")
    return {"id": row["id"], "created_at": row["created_at"], "version": row["version"], "revised_at": row["revised_at"], "question": json.loads(row["data"])}


def question_identity(data):
    if not data["source_images"]:
        return None
    key = {"sha256": sorted(set(image["sha256"] for image in data["source_images"])), "item": data["source_item_key"]}
    return hashlib.sha256(encode(key).encode("utf-8")).hexdigest()


def write_blobs(root, blobs):
    created = []
    try:
        (root / "assets").mkdir(exist_ok=True)
        for relative, content in blobs.items():
            target = root / relative
            if target.exists():
                require(target.read_bytes() == content, f"原图完整性冲突: {target}")
                continue
            with target.open("xb") as file:
                created.append(target)
                file.write(content)
    except Exception:
        for target in created:
            target.unlink(missing_ok=True)
        raise
    return created


def save_question(root, db, raw, question_id=None):
    data, blobs = prepare_question(raw)
    identity = question_identity(data)
    created = []
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT question_id FROM identities WHERE identity=?", (identity,)).fetchone() if identity else None
        if existing and question_id is None:
            db.rollback()
            return {"status": "existing", "note": "同一原图与题号已归档，未修改题目或新增作答；修改请用 revise", **current(db, existing[0])}
        require(not existing or existing[0] == question_id, "原图和题号已属于另一题；请检查 source_item_key 或更新已有题目")
        timestamp = now()
        if question_id is None:
            question_id = "q_" + uuid.uuid4().hex
            version = 1
            db.execute("INSERT INTO questions VALUES (?,?)", (question_id, timestamp))
        else:
            version = current(db, question_id)["version"] + 1
        created = write_blobs(root, blobs)
        db.execute("INSERT INTO revisions VALUES (?,?,?,?)", (question_id, version, timestamp, encode(data)))
        if identity:
            db.execute("INSERT OR IGNORE INTO identities VALUES (?,?)", (identity, question_id))
        db.commit()
    except Exception:
        db.rollback()
        for target in created:
            target.unlink(missing_ok=True)
        raise
    return {"status": "added" if version == 1 else "revised", **current(db, question_id)}


def save_attempt(root, db, question_id, raw):
    data, blobs, version = prepare_attempt(raw)
    created = []
    try:
        db.execute("BEGIN IMMEDIATE")
        latest = current(db, question_id)
        version = version or latest["version"]
        require(db.execute("SELECT 1 FROM revisions WHERE question_id=? AND version=?", (question_id, version)).fetchone(), "所指定题目版本不存在")
        linked = data["linked_attempt_id"]
        if linked:
            require(db.execute("SELECT 1 FROM attempts WHERE id=? AND question_id=?", (linked, question_id)).fetchone(), "关联作答不存在或不属于同一题")
        created = write_blobs(root, blobs)
        attempt_id, timestamp = "a_" + uuid.uuid4().hex, now()
        db.execute("INSERT INTO attempts VALUES (?,?,?,?,?)", (attempt_id, question_id, version, timestamp, encode(data)))
        db.commit()
    except Exception:
        db.rollback()
        for target in created:
            target.unlink(missing_ok=True)
        raise
    return {"status": "added", "id": attempt_id, "question_id": question_id, "question_version": version, "recorded_at": timestamp, "attempt": data}


def list_questions(db, topic=None):
    result = [current(db, row[0]) for row in db.execute("SELECT id FROM questions ORDER BY created_at,id")]
    return [item for item in result if topic is None or topic in item["question"]["topics"]]


def effective_attempt(db, attempt_id):
    row = db.execute("SELECT question_version,recorded_at,data FROM attempts WHERE id=?", (attempt_id,)).fetchone()
    require(row is not None, f"作答不存在: {attempt_id}")
    original = json.loads(row[2])
    effective = dict(original)
    annotations = []
    for item in db.execute("SELECT id,recorded_at,data FROM attempt_annotations WHERE attempt_id=? ORDER BY rowid", (attempt_id,)):
        annotation = json.loads(item[2])
        annotations.append({"id": item[0], "recorded_at": item[1], **annotation})
        effective.update(annotation["changes"])
    return {"id": attempt_id, "question_version": row[0], "recorded_at": row[1],
            "attempt": original, "annotations": annotations, "effective_attempt": effective}


def annotate_attempt(db, attempt_id, raw):
    raw = obj(raw, ("reason", "changes"), "annotation")
    reason = string(raw.get("reason"), "reason", True)
    changes = dict(obj(raw.get("changes"), ("result", "score", "max_score", "assistance", "error_analysis"), "changes"))
    require(bool(changes), "changes 不能为空")
    if "result" in changes:
        changes["result"] = choice(changes["result"], ("correct", "incorrect", "partial", "unknown"), "result")
    if "assistance" in changes:
        changes["assistance"] = choice(changes["assistance"], ("none", "hint", "answer_seen", "unknown"), "assistance")
    if "error_analysis" in changes:
        changes["error_analysis"] = prepare_error_analysis(changes["error_analysis"])
    with db:
        db.execute("BEGIN IMMEDIATE")
        effective = effective_attempt(db, attempt_id)["effective_attempt"]
        effective.update(changes)
        validate_score(effective)
        annotation_id = "n_" + uuid.uuid4().hex
        db.execute("INSERT INTO attempt_annotations VALUES (?,?,?,?)", (annotation_id, attempt_id, now(), encode({"reason": reason, "changes": changes})))
    return {"status": "annotated", "annotation_id": annotation_id, **effective_attempt(db, attempt_id)}


def show_question(db, question_id):
    result = current(db, question_id)
    result["revisions"] = [{"version": r[0], "created_at": r[1], "question": json.loads(r[2])} for r in db.execute("SELECT version,created_at,data FROM revisions WHERE question_id=? ORDER BY version", (question_id,))]
    result["attempts"] = [effective_attempt(db, r[0]) for r in db.execute("SELECT id FROM attempts WHERE question_id=? ORDER BY rowid", (question_id,))]
    return result


def summary(db, topic=None):
    questions = list_questions(db, topic)
    results, confirmed, hypotheses, assistance = Counter(), Counter(), Counter(), Counter()
    for item in questions:
        for event in show_question(db, item["id"])["attempts"]:
            data = event["effective_attempt"]
            results[data["result"]] += 1
            assistance[data["assistance"]] += 1
            error = data["error_analysis"]
            if error["status"] == "confirmed":
                confirmed.update(error["causes"])
            elif error["status"] == "hypothesis":
                hypotheses.update(error["causes"])
    return {"topic": topic, "question_count": len(questions),
            "needs_confirmation": sum(q["question"]["recognition"]["status"] == "needs_confirmation" for q in questions),
            "unverified_answers": sum(q["question"]["answer"]["verification_status"] != "verified" for q in questions),
            "attempt_count": sum(results.values()), "recorded_results": dict(results),
            "assistance_counts": dict(assistance), "confirmed_error_cause_events": dict(confirmed),
            "hypothesized_error_cause_events": dict(hypotheses),
            "interpretation": "只统计归档记录和实际作答事件；同题复测单独计次，分析勘误不增次数，正误及错因按最后有效勘误计数。没有全部练习分母，不计算总体正确率或掌握率；看答案后的订正不视为独立做对。"}


def asset_records(db):
    records = {}
    for row in db.execute("SELECT data FROM revisions"):
        for item in json.loads(row[0])["source_images"]:
            records[item["path"]] = item["sha256"]
    for row in db.execute("SELECT data FROM attempts"):
        for item in json.loads(row[0])["process_images"]:
            records[item["path"]] = item["sha256"]
    return records


def delete_questions(root, db, question_id=None):
    with db:
        db.execute("BEGIN IMMEDIATE")
        before = asset_records(db)
        if question_id:
            current(db, question_id)
            count = db.execute("DELETE FROM questions WHERE id=?", (question_id,)).rowcount
        else:
            count = db.execute("DELETE FROM questions").rowcount
    removed = []
    # Recheck under the writer lock: another import may have reused a shared image.
    with db:
        db.execute("BEGIN IMMEDIATE")
        after = asset_records(db)
        for relative in before.keys() - after.keys():
            path = root / relative
            path.unlink(missing_ok=True)
            removed.append(relative)
    db.execute("VACUUM")
    return {"status": "deleted", "question_count": count, "removed_assets": sorted(removed),
            "note": "已删除当前档案中的对应题目、全部版本、作答及不再引用的原图。外部备份与导出文件未被修改。"}


def readable_export(db):
    return {"schema_version": VERSION, "exported_at": now(),
            "questions": [show_question(db, item["id"]) for item in list_questions(db)],
            "note": "图片路径相对于数据根；迁移请使用 backup，它包含数据库、原图和已有 profile.json。"}


def verify_archive(root):
    with closing(connect(root)) as db:
        require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "数据库完整性检查失败")
        require(not db.execute("PRAGMA foreign_key_check").fetchall(), "数据库关联检查失败")
        for relative, expected in asset_records(db).items():
            require(len(Path(relative).parts) == 2 and Path(relative).parts[0] == "assets", "档案图片路径无效")
            path = root / relative
            require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected, f"图片缺失或校验失败: {relative}")


def backup_archive(root, db, output):
    output = Path(output).expanduser().resolve()
    require(not output.exists(), f"备份目标已存在，未覆盖: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    created_output = False
    with tempfile.TemporaryDirectory(prefix="maths-backup-") as temporary:
        snapshot = Path(temporary) / DB_NAME
        # Hold a database read transaction so a concurrent delete cannot remove referenced assets.
        db.execute("BEGIN")
        try:
            db.execute("SELECT COUNT(*) FROM questions").fetchone()
            with closing(sqlite3.connect(snapshot)) as copied:
                db.backup(copied)
            with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
                created_output = True
                bundle.write(snapshot, DB_NAME)
                for relative, expected in asset_records(db).items():
                    path = root / relative
                    content = path.read_bytes()
                    require(hashlib.sha256(content).hexdigest() == expected, f"备份图片校验失败: {relative}")
                    bundle.writestr(relative, content)
                profile = root / "profile.json"
                if profile.exists():
                    bundle.write(profile, "profile.json")
                bundle.writestr("backup-info.json", encode({"schema_version": VERSION, "created_at": now(), "contents": "archive.sqlite3, referenced assets, optional profile.json"}))
        except Exception:
            if created_output:
                output.unlink(missing_ok=True)
            raise
        finally:
            db.rollback()
    return {"status": "backed_up", "path": str(output)}


def restore_archive(root, source):
    source = Path(source).expanduser().resolve()
    require(not root.exists() or (root.is_dir() and not any(root.iterdir())), "恢复目标必须为空目录；不会覆盖现有档案或 profile.json")
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".maths-restore-", dir=root.parent) as temporary:
        staged = Path(temporary) / "data"
        staged.mkdir()
        with zipfile.ZipFile(source) as bundle:
            names = bundle.namelist()
            require(len(names) == len(set(names)) and DB_NAME in names, "迁移包文件重复或缺少数据库")
            for info in bundle.infolist():
                name = info.filename
                parts = Path(name).parts
                allowed = name in (DB_NAME, "profile.json", "backup-info.json") or (len(parts) == 2 and parts[0] == "assets" and parts[1] not in (".", ".."))
                require(allowed and "\\" not in name and not info.is_dir() and (info.external_attr >> 16) & 0o170000 != 0o120000, f"迁移包含不允许的路径: {name}")
                target = staged / name
                target.parent.mkdir(exist_ok=True)
                with target.open("xb") as file:
                    file.write(bundle.read(info))
        verify_archive(staged)
        (staged / "backup-info.json").unlink(missing_ok=True)
        (staged / "assets").mkdir(exist_ok=True)
        if root.exists():
            root.rmdir()
        staged.rename(root)
    return {"status": "restored", "root": str(root)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="maths 本地题目、版本、原图和实际作答档案")
    parser.add_argument("--root", help="数据根目录；省略时由 paths.data_root() 定位")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    for name in ("add", "revise", "attempt"):
        command = commands.add_parser(name)
        command.add_argument("--file", required=True, help="UTF-8 JSON 文件")
        if name != "add":
            command.add_argument("--question", required=True)
    for name in ("list", "summary"):
        commands.add_parser(name).add_argument("--topic", help="精确匹配一个 topics 标签")
    commands.add_parser("show").add_argument("--question", required=True)
    annotation = commands.add_parser("annotate")
    annotation.add_argument("--attempt", required=True)
    annotation.add_argument("--file", required=True)
    commands.add_parser("export").add_argument("--out", help="可选 JSON 输出路径；已有文件不覆盖")
    deletion = commands.add_parser("delete").add_mutually_exclusive_group(required=True)
    deletion.add_argument("--question")
    deletion.add_argument("--all", action="store_true")
    commands.add_parser("backup").add_argument("--out", required=True)
    commands.add_parser("restore").add_argument("--from", dest="source", required=True)
    args = parser.parse_args(argv)
    try:
        if args.root:
            root = Path(args.root).expanduser().resolve()
        else:
            from paths import data_root
            root = Path(data_root()).expanduser().resolve()
        if args.command == "init":
            result = initialize(root)
        elif args.command == "restore":
            result = restore_archive(root, args.source)
        else:
            db = connect(root)
            try:
                if args.command in ("add", "revise"):
                    result = save_question(root, db, load_json(args.file), getattr(args, "question", None))
                elif args.command == "attempt":
                    result = save_attempt(root, db, args.question, load_json(args.file))
                elif args.command == "annotate":
                    result = annotate_attempt(db, args.attempt, load_json(args.file))
                elif args.command == "list":
                    result = list_questions(db, args.topic)
                elif args.command == "show":
                    result = show_question(db, args.question)
                elif args.command == "summary":
                    result = summary(db, args.topic)
                elif args.command == "delete":
                    result = delete_questions(root, db, args.question)
                elif args.command == "backup":
                    result = backup_archive(root, db, args.out)
                elif args.command == "export":
                    result = readable_export(db)
                    if args.out:
                        target = Path(args.out).expanduser()
                        with target.open("x", encoding="utf-8") as file:
                            json.dump(result, file, ensure_ascii=False, indent=2, allow_nan=False)
                            file.write("\n")
                        result = {"status": "exported", "path": str(target.resolve())}
            finally:
                db.close()
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, sqlite3.Error, zipfile.BadZipFile) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
