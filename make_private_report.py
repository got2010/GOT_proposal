#!/usr/bin/env python3
"""取得済みの一覧を、ローカルで開ける単一HTMLとして保存する。公開は行わない。"""
import json
import re
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parent



class PlainText(HTMLParser):
    """公告のHTMLから本文だけを残す。画像・スクリプト・CSSは保存しない。"""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg"} and self.hidden is None:
            self.hidden = tag
        if not self.hidden and tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == self.hidden:
            self.hidden = None
        if not self.hidden and tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def plain_text(value):
    parser = PlainText()
    parser.feed(str(value or ""))
    parser.close()
    return re.sub(r"[^\S\n]+", " ", "".join(parser.parts)).strip()


def compact_data(data):
    """件名・原文リンク・判定結果は保持し、保存用本文を抜粋にする。"""
    result = dict(data)
    result["items"] = []
    for original in data.get("items", []):
        item = dict(original)
        body = plain_text(item.get("description") or item.get("snippet", ""))
        evidence = plain_text(item.get("evidence", ""))
        # 再判定用に映像業務の根拠も残す。全文は元の公告リンクで確認する。
        excerpt = body[:12000]
        if evidence and evidence not in excerpt:
            excerpt += "\n" + evidence
        item["description"] = excerpt
        item["description_truncated"] = len(body) > 12000
        item["snippet"] = re.sub(r"\s+", " ", body)[:200]
        item.pop("_body", None)
        result["items"].append(item)
    return result


def build_report(template, data):
    # scriptタグを抜け出す文字列をエスケープ。JSON.parseで元の文字に戻る。
    embedded = json.dumps(data, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    embedded = embedded.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    pattern = r'const res = await fetch\("data/tenders\.json", \{ cache: "no-cache" \}\);\s*if \(!res\.ok\) throw new Error\(res\.status\);\s*const data = await res\.json\(\);'
    page, count = re.subn(pattern, 'const data = JSON.parse(document.getElementById("saved-data").textContent);', template)
    if count != 1:
        raise ValueError("docs/index.html の形式が変わっています。データ読込部分を確認してください。")
    page = re.sub(r'<link\b[^>]*href="https://fonts\.[^"]*"[^>]*>\s*', '', page)
    page = page.replace('<title>映像プロポーザル情報</title>', '<title>映像プロポーザル情報 — 保存版</title>')
    page = page.replace('<div class="stats"', '<p>このファイルは保存時点の一覧です。最新の一覧はGitHubからダウンロードしてください。</p>\n    <div class="stats"', 1)
    # 埋め込む収集データは検査対象にせず、テンプレートの読込処理を確認する。
    if 'fetch(' in page:
        raise ValueError("一覧に外部データの読込処理が残っています。")
    marker = '<script>'
    if page.count(marker) != 1:
        raise ValueError("一覧テンプレートのscriptタグを確認してください。")
    page = page.replace(marker, '<script id="saved-data" type="application/json">' + embedded + '</script>\n' + marker, 1)
    return page


def main():
    data_path = ROOT / 'docs/data/tenders.json'
    original_bytes = data_path.stat().st_size
    data = compact_data(json.loads(data_path.read_text(encoding='utf-8')))
    template = (ROOT / 'docs/index.html').read_text(encoding='utf-8')
    output = ROOT / 'docs/private-report.html'
    data_bytes = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    page_bytes = build_report(template, data).encode('utf-8')
    # GitHubの制限に達する前に、保存段階で分かるメッセージを出す。
    if max(len(data_bytes), len(page_bytes)) >= 90 * 1024 * 1024:
        raise ValueError("軽量化後も90MiB以上あります。件数・異常に長い項目を確認してください。")
    data_path.write_bytes(data_bytes)
    output.write_bytes(page_bytes)
    print(f"本文を軽量化: {original_bytes / 1024**2:.2f} MiB → {len(data_bytes) / 1024**2:.2f} MiB")
    print(f"保存版を作成しました: {output.name} / {len(data.get('items', []))} 件 / {len(page_bytes) / 1024**2:.2f} MiB")


if __name__ == '__main__':
    main()
