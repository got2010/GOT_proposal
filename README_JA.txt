非公開・GitHub画面で読む地域別一覧への変更

差し替えは2ファイルです。Publicへの変更やPagesの設定は不要です。

1. make_private_report.py をリポジトリの一番上にアップロード
https://github.com/got2010/GOT_proposal/upload/main
Commit changesで保存してください。ファイル名に (1) などを付けないでください。

2. daily.yml はルートにアップロードしません。
このZIPの daily.yml をメモ帳で開き、全文をコピーしてください。
次の編集画面の内容を全文置き換え、Commit changesで保存します。
https://github.com/got2010/GOT_proposal/edit/main/.github/workflows/daily.yml

3. 新しく実行
https://github.com/got2010/GOT_proposal/actions/workflows/daily.yml
左側の daily-collect を選び、Run workflow → main → 緑のRun workflow。
古い履歴のRe-run jobsは使いません。

4. 成功後の閲覧先（実行前はまだありません）
https://github.com/got2010/GOT_proposal/blob/main/docs/reports/README.md
GitHubにログインした状態で開き、地域 → 一覧を選びます。
このURLをブックマークしてください。以後は更新するだけです。
Markdownの文字列が見える場合はPreviewを選びます。

毎朝7時（日本時間）の実行予定は維持します。GitHubの混雑等で遅れる場合があります。
実行成功時に一覧も更新されます。最終更新時刻を確認してください。
今のHTMLダウンロード版も残ります。
一覧は関連度順で100件ずつに分かれます。締切は推定であり、過去案件も表示します。
保存本文は軽量化のため抜粋です。受付状況や詳しい条件は原文リンクで確認してください。
新しい docs/reports フォルダは自動生成専用です。手書きのファイルは入れないでください。
