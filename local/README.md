# ローカル版（vol.1）

PDFをMarkdownに変換するパイプラインを、あなたのPC 1 台で完結させる実装です。
インターネット接続不要・データを外部に出さない・追加費用ゼロ。

仕様書: [`../docs/Spec-local.md`](../docs/Spec-local.md)

---

## クイックスタート（3分）

### 1. リポジトリを取得

```bash
git clone https://github.com/masa-san-jp/pdf-to-md-pipeline.git
cd pdf-to-md-pipeline/local
```

### 2. 必要環境

- **Python 3.10+** — `python --version`
- **Java 11+** — `java -version`（`opendataloader-pdf` が内部で利用）

### 3. 依存パッケージを入れる

```bash
python -m venv .venv
source .venv/bin/activate        # Windows は .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. PDF を置いて実行

```bash
# 単体PDF: input/ にファイルを置く
cp ~/Downloads/sample.pdf input/

# 複数PDFを結合したい場合: input/ にサブフォルダを作って入れる
mkdir -p input/001_議事録集
cp ~/Downloads/{01_intro,02_body}.pdf input/001_議事録集/

python run.py
```

実行後の挙動：

| 入力 | 出力Markdown | 処理済みの移動先 |
|---|---|---|
| `input/sample.pdf` | `output/sample.md` | `done/sample_20260417_120000.pdf` |
| `input/001_議事録集/` | `output/001_議事録集.md`（ファイル名昇順で連結） | `done/001_議事録集_20260417_120000/` |

ログは `logs/YYYY-MM-DD.log` に追記されます。

---

## よくあるオプション

```bash
python run.py --log-level DEBUG                       # 詳細ログ
python run.py --loop                                  # config の interval_minutes 間隔で繰返し
python run.py --config /path/to/custom-config.yaml    # 別の設定ファイル
```

### スキャンPDF（画像PDF）をOCRで変換したい

`config.yaml` の `hybrid:` 行のコメントを外し、別ターミナルで OCR バックエンドを常駐させてから `run.py` を実行します。

```bash
opendataloader-pdf-hybrid --port 5002 --ocr-lang "ja,en" &
python run.py
```

---

## 定期自動実行

### Linux（systemd）

`/etc/systemd/system/pdf-watcher.service`：

```ini
[Unit]
Description=PDF to Markdown Converter
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/pdf-to-md-pipeline/local
ExecStartPre=/bin/bash -c 'opendataloader-pdf-hybrid --port 5002 --ocr-lang "ja,en" &'
ExecStart=/path/to/pdf-to-md-pipeline/local/.venv/bin/python run.py --loop
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now pdf-watcher
journalctl -u pdf-watcher -f   # ログ確認
```

### macOS（launchd / cron）

```bash
# 1時間ごとに起動する例
(crontab -l 2>/dev/null; echo "0 * * * * cd $PWD && .venv/bin/python run.py") | crontab -
```

### Windows（タスクスケジューラ）

```powershell
schtasks /create /tn "PDF-Converter" /tr "python C:\path\to\pdf-to-md-pipeline\local\run.py" /sc hourly
```

---

## 開発者向け

```bash
# プロジェクトルートから
pip install pytest
pytest                 # すべてのテスト
pytest tests/test_converter.py -v
```

テストは `opendataloader_pdf` をスタブ化して実行するため、Java や hybrid バックエンドは不要です。

---

## トラブルシュート

| 症状 | 対処 |
|---|---|
| `java: command not found` | JDK 11+ をインストール（`apt install default-jdk` / `brew install openjdk@17`） |
| `opendataloader_pdf` が import で失敗 | `pip install -r requirements.txt` を再実行。pip ログにビルドエラーが出ていないか確認 |
| スキャンPDFがテキスト抽出されない | `config.yaml` で `hybrid: "docling-fast"` を有効化し、`opendataloader-pdf-hybrid` を起動 |
| `logs/YYYY-MM-DD.log` が出ない | `--log-level DEBUG` で再実行。`logs/` の書き込み権限を確認 |
