#!/usr/bin/env python3
"""取得済みの一覧を、ローカルで開ける単一HTMLとして保存する。公開は行わない。"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


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
    data = json.loads((ROOT / 'docs/data/tenders.json').read_text(encoding='utf-8'))
    template = (ROOT / 'docs/index.html').read_text(encoding='utf-8')
    output = ROOT / 'docs/private-report.html'
    output.write_text(build_report(template, data), encoding='utf-8')
    print(f"保存版を作成しました: {output.name} / {len(data.get('items', []))} 件")


if __name__ == '__main__':
    main()
