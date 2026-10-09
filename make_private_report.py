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


REGIONS = [
    ('hokkaido', '北海道', '北海道'),
    ('tohoku', '東北', '青森県 岩手県 宮城県 秋田県 山形県 福島県'),
    ('kanto', '関東', '茨城県 栃木県 群馬県 埼玉県 千葉県 東京都 神奈川県'),
    ('koshinetsu', '甲信越', '新潟県 山梨県 長野県'),
    ('hokuriku', '北陸', '富山県 石川県 福井県'),
    ('tokai', '東海', '岐阜県 静岡県 愛知県 三重県'),
    ('kinki', '近畿', '滋賀県 京都府 大阪府 兵庫県 奈良県 和歌山県'),
    ('chugoku', '中国', '鳥取県 島根県 岡山県 広島県 山口県'),
    ('shikoku', '四国', '徳島県 香川県 愛媛県 高知県'),
    ('kyushu', '九州', '福岡県 佐賀県 長崎県 熊本県 大分県 宮崎県 鹿児島県'),
    ('okinawa', '沖縄', '沖縄県'),
    ('other', '全国機関・地域不明', ''),
]
PREFECTURES = '北海道 青森県 岩手県 宮城県 秋田県 山形県 福島県 茨城県 栃木県 群馬県 埼玉県 千葉県 東京都 神奈川県 新潟県 富山県 石川県 福井県 山梨県 長野県 岐阜県 静岡県 愛知県 三重県 滋賀県 京都府 大阪府 兵庫県 奈良県 和歌山県 鳥取県 島根県 岡山県 広島県 山口県 徳島県 香川県 愛媛県 高知県 福岡県 佐賀県 長崎県 熊本県 大分県 宮崎県 鹿児島県 沖縄県'.split()


def md(value, limit=240):
    from html import escape
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if len(text) > limit:
        text = text[:limit] + '…'
    text = escape(text, quote=False)
    for char in '\\`*_[]|':
        text = text.replace(char, '\\' + char)
    return text


def link(label, url):
    from urllib.parse import urlsplit, quote
    url = str(url or '').strip()
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            return md(label)
    except ValueError:
        return md(label)
    return '[' + md(label) + '](<' + quote(url, safe=':/?&=%#@+;,$!~*-._') + '>)'


def prefecture(item):
    pref = str(item.get('pref') or '').strip()
    if pref in PREFECTURES:
        return pref
    code = str(item.get('lg_code') or '').strip()
    if re.fullmatch(r'\d{2}|\d{5,6}', code) and 1 <= int(code[:2]) <= 47:
        return PREFECTURES[int(code[:2]) - 1]
    return ''


def write_markdown(data):
    """GitHubのPreviewで読める一覧。全件を100件ずつのページに分ける。"""
    import shutil
    directory = ROOT / 'docs/reports'
    # このスクリプト専用の出力先のみ再生成して、古いページを残さない。
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    groups = {slug: [] for slug, _, _ in REGIONS}
    mapping = {pref: slug for slug, _, prefs in REGIONS for pref in prefs.split()}
    for item in data.get('items', []):
        groups[mapping.get(prefecture(item), 'other')].append(item)
    updated = md(data.get('updated_at') or '不明')
    common = f'最終更新：{updated}（収集時点）\n\n'
    common += '締切は公告文からの推定です。受付状況・条件は必ず原文で確認してください。過去の案件も含みます。\n\n'
    home = '# 映像制作の案件一覧\n\n' + common
    home += '地域を選ぶと一覧が開きます。ダウンロードは不要です。ブラウザを更新して最新の保存結果を表示してください。\n\n'
    home += f'全国合計：**{len(data.get("items", []))}件**\n\n'
    warnings = data.get('collection_warnings', [])
    if warnings:
        home += '> 一部の検索に失敗しています：' + '、'.join(md(w) for w in warnings) + '\n\n'
    home += '| 地域 | 件数 |\n|---|---:|\n'
    for slug, name, prefs in REGIONS:
        items = sorted(groups[slug], key=lambda i: (i.get('relevance_score', 0), i.get('cft') or '', i.get('key') or ''), reverse=True)
        target = directory / slug
        target.mkdir()
        home += f'| [{name}]({slug}/README.md) | {len(items)} |\n'
        intro = f'# {name}の案件\n\n[地域選択へ戻る](../README.md)\n\n' + common
        intro += f'対象：{prefs or "都道府県を特定できない案件"}\n\n**{len(items)}件** ／ 映像業務の関連度順、同じ関連度では公告日が新しい順。\n\n'
        chunks = [items[i:i+100] for i in range(0, len(items), 100)]
        index = intro
        if not chunks:
            index += '現在、保存されている対象案件はありません。\n'
        for n, chunk in enumerate(chunks, 1):
            filename = f'page-{n:03d}.md'
            index += f'- [一覧 {n}：{(n-1)*100+1}〜{(n-1)*100+len(chunk)}件目]({filename})\n'
            page = intro + f'## 一覧 {n} / {len(chunks)}\n\n'
            nav = ['[この地域の目次](README.md)']
            if n > 1:
                nav.append(f'[前の100件](page-{n-1:03d}.md)')
            if n < len(chunks):
                nav.append(f'[次の100件](page-{n+1:03d}.md)')
            page += ' ｜ '.join(nav) + '\n\n'
            page += '| 都道府県 | 案件名・原文 | 発注元 | 公告日 | 締切の目安 | 判定根拠 | 資料 |\n|---|---|---|---|---|---|---|\n'
            for item in chunk:
                attachments = ' / '.join(link(a.get('name') or '資料', a.get('uri')) for a in item.get('attachments', [])[:5])
                row = [md(prefecture(item) or item.get('pref') or '不明'), link(item.get('title') or '名称不明', item.get('url')), md(item.get('org')), md(item.get('cft')), md(item.get('deadline') or '原文を確認'), md(item.get('evidence'), 160), attachments or '—']
                page += '| ' + ' | '.join(row) + ' |\n'
            page += '\n' + ' ｜ '.join(nav) + '\n'
            (target / filename).write_text(page, encoding='utf-8')
        (target / 'README.md').write_text(index, encoding='utf-8')
    (directory / 'README.md').write_text(home, encoding='utf-8')
    print(f'GitHub閲覧用一覧を作成: docs/reports/README.md / {len(data.get("items", []))} 件')


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
    write_markdown(data)
    print(f"本文を軽量化: {original_bytes / 1024**2:.2f} MiB → {len(data_bytes) / 1024**2:.2f} MiB")
    print(f"保存版を作成しました: {output.name} / {len(data.get('items', []))} 件 / {len(page_bytes) / 1024**2:.2f} MiB")


if __name__ == '__main__':
    main()
