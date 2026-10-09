#!/usr/bin/env python3
"""官公需情報ポータルサイト検索APIから、映像制作関連の公告を収集して JSON に保存する。

- API仕様: https://www.kkj.go.jp/doc/ja/api_guide.pdf
- 条件は config.json で変更できる
- 出力: docs/data/tenders.json (前回までの結果に新規分をマージ。初回取得日を first_seen に記録)
"""
import json
import html
import re
import sys
import time
import urllib.parse
import urllib.request
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
DATA_PATH = ROOT / "docs" / "data" / "tenders.json"
API_URLS = ["https://www.kkj.go.jp/api/", "http://www.kkj.go.jp/api/"]
JST = timezone(timedelta(hours=9))

DATE_RE = re.compile(
    r"(?:(令和)\s*(元|\d{1,2})\s*年|(\d{4})\s*年)\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
DEADLINE_WORDS = re.compile(
    r"提出期限|提出期間|提出締切|締切|締め切り|受付期限|受付期間|応募期限|申込期限|参加表明"
)


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def fetch(params):
    """APIを呼び出して XML のバイト列を返す。https → http の順に試し、各3回までリトライ。"""
    qs = urllib.parse.urlencode(params)
    last_error = None
    for base in API_URLS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    f"{base}?{qs}", headers={"User-Agent": "proposal-watch/1.0"}
                )
                with urllib.request.urlopen(req, timeout=60) as res:
                    return res.read()
            except Exception as e:  # noqa: BLE001
                last_error = e
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"API呼び出しに失敗しました: {last_error}")


def _text(el, tag):
    child = el.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _day(value):
    """ISO8601 文字列から YYYY-MM-DD だけを取り出す。"""
    return value[:10] if value and re.match(r"\d{4}-\d{2}-\d{2}", value) else ""


def _to_iso(match):
    reiwa, r_year, y_year, month, day = match.groups()
    if reiwa:
        year = 2018 + (1 if r_year == "元" else int(r_year))
    else:
        year = int(y_year)
    try:
        return date(year, int(month), int(day)).isoformat()
    except ValueError:
        return ""


def guess_deadline(description, issue_date):
    """公告文から締切日の目安を推定する(確実ではない)。

    「提出期限」「受付期間」などの語の直後にある日付のうち、最も遅いものを採用する。
    """
    if not description:
        return ""
    candidates = []
    for word in DEADLINE_WORDS.finditer(description):
        window = description[word.end(): word.end() + 80]
        for m in DATE_RE.finditer(window):
            iso = _to_iso(m)
            if iso and iso >= issue_date:
                candidates.append(iso)
    return max(candidates) if candidates else ""


def parse_results(raw):
    """XML をパースして (ヒット件数, 案件リスト) を返す。"""
    root = ET.fromstring(raw)
    err = root.find("Error")
    if err is not None:
        raise RuntimeError(f"APIエラー: {(err.text or '').strip()}")
    hits = int(root.findtext("SearchResults/SearchHits") or 0)
    items = []
    for r in root.iterfind("SearchResults/SearchResult"):
        description = _text(r, "ProjectDescription")
        cft = _day(_text(r, "CftIssueDate")) or _day(_text(r, "Date"))
        attachments = []
        for a in r.iterfind("Attachments/Attachment"):
            uri = _text(a, "Uri")
            if uri:
                attachments.append({"name": _text(a, "Name") or "添付ファイル", "uri": uri})
        url = _text(r, "ExternalDocumentURI")
        items.append(
            {
                "key": _text(r, "Key") or url,
                "title": _text(r, "ProjectName"),
                "org": _text(r, "OrganizationName"),
                "lg_code": _text(r, "LgCode"),
                "pref": _text(r, "PrefectureName"),
                "city": _text(r, "CityName"),
                "cft": cft,
                "deadline": guess_deadline(description, cft),
                "opening": _day(_text(r, "OpeningTendersEvent")),
                "category": _text(r, "Category"),
                "procedure": _text(r, "ProcedureType"),
                "url": url,
                "attachments": attachments[:5],
                "snippet": re.sub(r"\s+", " ", description)[:200],
                "description": description,
            }
        )
    return hits, items


def normalized(value):
    value = re.sub(r"<\s*(?:br\b[^>]*|/?(?:p|div|li|tr|h[1-6])\b[^>]*)>", "\n", value or "", flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"[^\S\r\n]+", " ", unicodedata.normalize("NFKC", html.unescape(value))).strip()


def classify(item, cfg):
    """業務としての映像制作を優先。一般PR語や提案書の提出方法だけでは採用しない。"""
    title = normalized(item.get("title", ""))
    body = normalized(item.get("description") or item.get("_body") or item.get("snippet", ""))
    rules = cfg["relevance_rules"]
    flags = re.IGNORECASE

    def hits(text, patterns):
        return list(dict.fromkeys(m.group(0) for p in patterns for m in re.finditer(p, text, flags)))

    # 医療撮影、測量、機材保守などが件名の主目的なら対象外。
    # 広報動画の本文に「医療」等があるだけでは除外しない。
    if hits(title, rules["exclude_title_patterns"]):
        return None

    title_hits = hits(title, rules["work_patterns"])
    body_hits = []
    evidence = ""
    for sentence in re.split(r"[。！？\n\r]", body):
        # 提案・実績・審査用動画などは委託成果物の根拠にしない。
        if hits(sentence, rules["ignore_body_patterns"]):
            continue
        matched = hits(sentence, rules["work_patterns"])
        if matched:
            body_hits.extend(matched)
            if not evidence:
                first = min(m.start() for p in rules["work_patterns"] for m in re.finditer(p, sentence, flags))
                evidence = sentence[max(0, first - 35):first + 165]
    if not title_hits and not body_hits:
        return None

    result = dict(item)
    result.pop("_body", None)
    result["is_proposal"] = any(normalized(w) in title or normalized(w) in body for w in cfg["proposal_words"])
    result["match"] = "title" if title_hits else "body"
    result["keywords"] = list(dict.fromkeys(title_hits or body_hits))[:8]
    result["relevance_score"] = 100 if title_hits else 60
    result["relevance_label"] = "件名に映像業務" if title_hits else "本文に映像業務"
    result["evidence"] = title if title_hits else evidence
    return result


def load_store():
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return {"updated_at": None, "items": []}


def main():
    cfg = load_config()
    today = datetime.now(JST).date()
    since = (today - timedelta(days=cfg["lookback_days"])).isoformat()

    found = {}
    failures = 0
    for kw in cfg["video_keywords"]:
        params = {
            "Query": kw,
            "LG_Code": ",".join(cfg["lg_codes"]),
            "CFT_Issue_Date": f"{since}/",
            "Count": cfg["count"],
        }
        try:
            hits, items = parse_results(fetch(params))
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"[警告] キーワード「{kw}」の取得に失敗: {e}", file=sys.stderr)
            continue
        print(f"キーワード「{kw}」: ヒット {hits} 件 / 取得 {len(items)} 件")
        if hits > len(items):
            print(f"[警告] 「{kw}」は取得上限を超えています。lookback_days を短くしてください。", file=sys.stderr)
        for item in items:
            if not item["key"]:
                continue
            # 不採用の最新データも保持し、旧判定が残り続けることを防ぐ。
            found.setdefault(item["key"], item)
        time.sleep(1)

    if failures == len(cfg["video_keywords"]):
        print("すべての取得に失敗したため、データを更新しません。", file=sys.stderr)
        sys.exit(1)

    store = load_store()
    old = {i["key"]: i for i in store["items"]}
    previous_keys = set(old)
    today_s = today.isoformat()
    new_count = 0
    for key, item in found.items():
        if key in old:
            item["first_seen"] = old[key].get("first_seen", today_s)
        else:
            item["first_seen"] = today_s
            new_count += 1
        old[key] = item

    cutoff = (today - timedelta(days=cfg["keep_days"])).isoformat()
    merged = []
    for item in old.values():
        if (item.get("cft") or today_s) < cutoff:
            continue
        classified = classify(item, cfg)
        if classified:
            merged.append(classified)
    merged.sort(key=lambda i: (i["relevance_score"], i.get("cft", ""), i["key"]), reverse=True)
    new_count = sum(i["key"] not in previous_keys for i in merged)

    store = {"updated_at": datetime.now(JST).isoformat(timespec="minutes"), "items": merged}
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"完了: 新着 {new_count} 件 / 保存済み合計 {len(merged)} 件")


if __name__ == "__main__":
    main()
