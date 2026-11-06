#!/usr/bin/env python3
"""考研数学一持久学习记录；仅使用 Python 标准库。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
import uuid
from zoneinfo import ZoneInfo

KINDS = ("profile", "problem", "weakness", "card", "review", "summary", "correction")
LABELS = dict(zip(KINDS, ("个人设置", "题目", "薄弱点", "经验卡", "复测", "总结", "修正")))
MASTERY = ("待检查", "需要提示", "能独立完成", "间隔后仍能完成", "能迁移到变式")
STUDY = ("已讲解", "自述理解", "提示后完成", "独立完成", "未作答")
SELECT = """SELECT e.* FROM events e JOIN
 (SELECT kind,id,MAX(revision) revision FROM events GROUP BY kind,id) v
 ON e.kind=v.kind AND e.id=v.id AND e.revision=v.revision"""


def output(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def config_path():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "kaoyan-math-one-settings.json"


def root_path(explicit=None):
    if explicit:
        return Path(explicit).expanduser().resolve()
    cfg = config_path()
    if cfg.exists():
        return Path(json.loads(cfg.read_text(encoding="utf-8"))["学习目录"]).expanduser().resolve()
    return (Path.home() / "Documents" / "Codex" / "math-one-learning").resolve()


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def connect(root, create=False):
    path = root / "learning.sqlite3"
    if not create and not path.exists():
        raise ValueError("学习档案尚未建立，请先运行 init；读取操作没有创建空档案。")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=20, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=20000")
    db.execute("PRAGMA foreign_keys=ON")
    if create:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise ValueError("学习档案版本不受支持，未修改数据。")
        db.execute("""CREATE TABLE IF NOT EXISTS events (
          kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
          recorded_at TEXT NOT NULL, reason TEXT NOT NULL, payload TEXT NOT NULL,
          PRIMARY KEY(kind,id,revision))""")
        db.execute("PRAGMA user_version=1")
    if db.execute("PRAGMA user_version").fetchone()[0] != 1:
        raise ValueError("学习档案版本不受支持，未修改数据。")
    return db


def latest(db, kind, rid):
    return db.execute("SELECT * FROM events WHERE kind=? AND id=? ORDER BY revision DESC LIMIT 1",
                      (kind, rid)).fetchone()


def unpack(row):
    return {"类型": row["kind"], "编号": row["id"], "版本": row["revision"],
            "写入时间": row["recorded_at"], "变更原因": row["reason"],
            "内容": json.loads(row["payload"])}


def zone(db):
    row = latest(db, "profile", "learner")
    name = json.loads(row["payload"]).get("时区", "Asia/Shanghai") if row else "Asia/Shanghai"
    if name == "Asia/Shanghai":
        return timezone(timedelta(hours=8), "Asia/Shanghai")
    return ZoneInfo(name)


def valid_date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("日期应使用 YYYY-MM-DD。")


def validate(kind, rid, payload, db):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,95}", rid):
        raise ValueError("编号使用小写字母、数字和连字符，最长96字符。")
    if not isinstance(payload, dict) or not isinstance(payload.get("标题"), str) or not payload["标题"].strip():
        raise ValueError("内容必须是包含非空中文标题的 JSON 对象。")
    for key in ("学习日期", "日期", "到期日期", "范围开始", "范围结束"):
        if payload.get(key) is not None:
            valid_date(payload[key])
    required = {
        "profile": ("时区",), "problem": ("题目", "学习状态", "作答"),
        "weakness": ("诊断状态", "掌握状态", "证据"),
        "card": ("识别信号", "关键动作", "适用条件", "个人易错点", "回忆问题"),
        "review": ("到期日期", "状态", "目的"),
        "summary": ("类型", "范围开始", "范围结束", "正文"),
        "correction": ("原结论", "修正", "依据"),
    }[kind]
    if any(key not in payload for key in required):
        raise ValueError("缺少字段：" + "、".join(key for key in required if key not in payload))
    if kind == "profile":
        name = payload["时区"]
        if name != "Asia/Shanghai":
            ZoneInfo(name)
    if kind == "problem":
        if payload["学习状态"] not in STUDY or not isinstance(payload["作答"], list):
            raise ValueError("题目学习状态或作答列表不合法。")
        ids = []
        for attempt in payload["作答"]:
            if not isinstance(attempt, dict) or not all(k in attempt for k in ("编号", "日期", "状态", "提示", "证据来源")):
                raise ValueError("每次作答需要编号、日期、状态、提示、证据来源。")
            valid_date(attempt["日期"])
            if attempt["状态"] not in STUDY:
                raise ValueError("作答状态不合法。")
            ids.append(attempt["编号"])
        if len(set(ids)) != len(ids):
            raise ValueError("作答编号重复；不能重复追加同一次作答。")
    if kind == "weakness":
        if payload["掌握状态"] not in MASTERY or payload["诊断状态"] not in ("待检查", "有证据", "已撤销"):
            raise ValueError("薄弱点状态不合法。")
        if not isinstance(payload["证据"], list):
            raise ValueError("证据必须是列表。")
        if payload["掌握状态"] != "待检查" and not payload["证据"]:
            raise ValueError("升级掌握状态必须提供证据。")
    if kind == "review":
        if payload["状态"] not in ("待复测", "已完成", "已取消"):
            raise ValueError("复测状态不合法。")
        if payload["状态"] == "已完成" and not payload.get("结果"):
            raise ValueError("完成复测需要实际结果。")
    if kind == "summary" and payload["范围开始"] > payload["范围结束"]:
        raise ValueError("总结日期范围颠倒。")
    for key, target in (("题目编号", "problem"), ("薄弱点编号", "weakness")):
        values = payload.get(key, [])
        if not isinstance(values, list):
            raise ValueError(key + "必须是列表。")
        for ref in values:
            if not latest(db, target, ref):
                raise ValueError("关联记录不存在：" + target + "/" + str(ref))


def save(db, kind, rid, payload, expected, reason):
    db.execute("BEGIN IMMEDIATE")
    try:
        old = latest(db, kind, rid)
        revision = old["revision"] if old else 0
        if revision != expected:
            raise ValueError(f"版本冲突：期望 {expected}，实际 {revision}；请重读并合并，未覆盖旧记录。")
        validate(kind, rid, payload, db)
        if old:
            prev = json.loads(old["payload"])
            if prev == payload:
                db.commit()
                return unpack(old)
            if not reason.strip():
                raise ValueError("修改旧记录必须说明变更原因。")
            if kind == "problem":
                old_ids = {a["编号"] for a in prev["作答"]}
                new_ids = {a["编号"] for a in payload["作答"]}
                if not old_ids <= new_ids:
                    raise ValueError("不能删除旧作答；请保留并注明修正，版本历史也会保留。")
        now = datetime.now(zone(db)).isoformat(timespec="seconds")
        db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)",
                   (kind, rid, revision + 1, now, reason, json.dumps(payload, ensure_ascii=False)))
        db.commit()
        return unpack(latest(db, kind, rid))
    except BaseException:
        db.rollback()
        raise


def all_current(db):
    return [unpack(r) for r in db.execute(SELECT + " ORDER BY e.kind,e.id")]


def markdown_value(value, depth=0):
    if isinstance(value, dict):
        return "\n".join(f"{'  '*depth}- **{k}：** " +
            ("\n" + markdown_value(v, depth+1) if isinstance(v, (dict, list)) else str(v if v is not None else "未提供"))
            for k, v in value.items())
    if isinstance(value, list):
        return "\n".join(("  "*depth + "- " + str(v)) if not isinstance(v, (dict, list))
                          else markdown_value(v, depth) for v in value) or "  "*depth + "- 无"
    return str(value)


def export_views(db, root):
    # 与并行写入串行化，避免旧快照覆盖新可读视图；数据库为权威记录。
    db.execute("BEGIN IMMEDIATE")
    try:
        records = all_current(db)
        today = datetime.now(zone(db)).date().isoformat()
        lines = ["# 考研数学一学习档案", "", f"本地日期：{today}", "",
                 "这些 Markdown 是可读视图；learning.sqlite3 保存权威记录与全部修订。请通过技能更新记录，视图可重新生成。", ""]
        for kind in KINDS:
            subset = [r for r in records if r["类型"] == kind]
            if not subset:
                continue
            lines += ["## " + LABELS[kind], ""]
            for r in subset:
                p = r["内容"]
                state = p.get("掌握状态", p.get("学习状态", p.get("状态", "")))
                if p.get("诊断状态") == "已撤销":
                    state = "已撤销，不计入活跃薄弱点"
                target = f"views/{kind}/{r['编号']}.md"
                lines.append(f"- [{p['标题']}]({target})：{state}（版本 {r['版本']}）")
                body = f"# {p['标题']}\n\n编号：{r['编号']}；版本：{r['版本']}；写入时间：{r['写入时间']}\n\n" + markdown_value(p) + "\n"
                atomic_write(root / target, body)
            lines.append("")
        atomic_write(root / "学习总览.md", "\n".join(lines) + "\n")
        db.commit()
        return len(records)
    except BaseException:
        db.rollback()
        raise


def read_input(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description="考研数学一学习记录")
    parser.add_argument("--root", help="本次学习目录；未指定则读取固定设置")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init")
    p.add_argument("--set-default", action="store_true", help="记住当前目录供后续会话使用")
    sub.add_parser("status")
    for command in ("get", "history"):
        p = sub.add_parser(command)
        p.add_argument("kind", choices=KINDS)
        p.add_argument("id")
    p = sub.add_parser("list")
    p.add_argument("--kind", choices=KINDS)
    p.add_argument("--topic")
    p.add_argument("--date", help="按实际学习/作答日期筛选，不按导入日期")
    p.add_argument("--since")
    p.add_argument("--until")
    p.add_argument("--due", help="待复测项到期日不晚于此日")
    p.add_argument("--full", action="store_true")
    p = sub.add_parser("put")
    p.add_argument("kind", choices=KINDS)
    p.add_argument("id")
    p.add_argument("--file", required=True)
    p.add_argument("--expected-revision", required=True, type=int)
    p.add_argument("--reason", default="首次记录")
    p = sub.add_parser("append-attempt")
    p.add_argument("id")
    p.add_argument("--file", required=True)
    p.add_argument("--expected-revision", required=True, type=int)
    p.add_argument("--reason", default="追加实际作答")
    sub.add_parser("export")
    sub.add_parser("check")
    args = parser.parse_args()
    root = root_path(args.root)
    db = connect(root, create=args.command == "init")
    try:
        if args.command == "init":
            if not latest(db, "profile", "learner"):
                save(db, "profile", "learner", {"标题": "个人学习设置", "时区": "Asia/Shanghai",
                     "考试年份": None, "复习阶段": None, "主要教材": None, "目标": None,
                     "每天可用分钟": None, "讲解模式": "完整讲解", "首次设置已询问": False}, 0, "初始化；未推断未知信息")
            (root / "sources").mkdir(exist_ok=True)
            count = export_views(db, root)
            if args.set_default:
                atomic_write(config_path(), json.dumps({"学习目录": str(root)}, ensure_ascii=False, indent=2) + "\n")
            output({"成功": True, "学习目录": str(root), "记录数": count, "固定目录已保存": args.set_default})
        elif args.command == "status":
            today = datetime.now(zone(db)).date().isoformat()
            records = all_current(db)
            due = [r for r in records if r["类型"] == "review" and r["内容"]["状态"] == "待复测" and r["内容"]["到期日期"] <= today]
            output({"学习目录": str(root), "本地日期": today,
                    "个人设置": unpack(latest(db, "profile", "learner")),
                    "记录数": {LABELS[k]: sum(r["类型"] == k for r in records) for k in KINDS},
                    "活跃薄弱点": [{"编号": r["编号"], "标题": r["内容"]["标题"],
                                   "诊断状态": r["内容"]["诊断状态"], "掌握状态": r["内容"]["掌握状态"]}
                                  for r in records if r["类型"] == "weakness" and r["内容"]["诊断状态"] != "已撤销"],
                    "到期复测": [{"编号": r["编号"], "标题": r["内容"]["标题"], "到期日期": r["内容"]["到期日期"]} for r in due]})
        elif args.command in ("get", "history"):
            if not latest(db, args.kind, args.id):
                raise ValueError("记录不存在。")
            if args.command == "get":
                output(unpack(latest(db, args.kind, args.id)))
            else:
                output([unpack(r) for r in db.execute("SELECT * FROM events WHERE kind=? AND id=? ORDER BY revision", (args.kind, args.id))])
        elif args.command == "list":
            for value in (args.date, args.since, args.until, args.due):
                if value:
                    valid_date(value)
            matches = []
            for record in all_current(db):
                p = record["内容"]
                if args.kind and record["类型"] != args.kind:
                    continue
                if args.topic and args.topic.casefold() not in json.dumps(p, ensure_ascii=False).casefold():
                    continue
                days = [a["日期"] for a in p.get("作答", [])]
                days += [p[k] for k in ("学习日期", "日期") if p.get(k)]
                if (args.date or args.since or args.until) and not any(
                    (not args.date or d == args.date) and (not args.since or d >= args.since) and
                    (not args.until or d <= args.until) for d in days):
                    continue
                if args.due and not (record["类型"] == "review" and p["状态"] == "待复测" and p["到期日期"] <= args.due):
                    continue
                if args.full:
                    matches.append(record)
                else:
                    matches.append({"类型": record["类型"], "编号": record["编号"], "版本": record["版本"],
                        "标题": p["标题"], "状态": p.get("诊断状态") if p.get("诊断状态") == "已撤销" else p.get("掌握状态", p.get("学习状态", p.get("状态"))),
                        "学习日期": sorted(set(days)), "到期日期": p.get("到期日期")})
            output(matches)
        elif args.command in ("put", "append-attempt"):
            payload = read_input(args.file)
            kind = args.kind if args.command == "put" else "problem"
            if args.command == "append-attempt":
                row = latest(db, kind, args.id)
                if not row:
                    raise ValueError("题目不存在，先保存题目。")
                attempt = payload
                payload = json.loads(row["payload"])
                payload["作答"].append(attempt)
                payload["学习状态"] = attempt["状态"]
            saved = save(db, kind, args.id, payload, args.expected_revision, args.reason)
            result = {"成功": True, "学习目录": str(root), "已保存": {k: saved[k] for k in ("类型", "编号", "版本")}}
            try:
                export_views(db, root)
                result["可读视图已更新"] = True
            except (OSError, sqlite3.Error) as exc:
                result["可读视图已更新"] = False
                result["说明"] = "数据库已保存，可读视图更新失败；运行 export 可恢复：" + str(exc)
            output(result)
        elif args.command == "export":
            output({"成功": True, "导出记录数": export_views(db, root), "学习目录": str(root)})
        elif args.command == "check":
            check = db.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise ValueError("数据库完整性检查失败：" + check)
            records = all_current(db)
            for r in records:
                validate(r["类型"], r["编号"], r["内容"], db)
            output({"成功": True, "数据库完整性": "通过", "当前记录检查数": len(records),
                    "历史版本数": db.execute("SELECT COUNT(*) FROM events").fetchone()[0]})
    finally:
        db.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        output({"成功": False, "错误": str(exc), "说明": "未确认保存成功，不应报告已记录。"})
        sys.exit(1)
