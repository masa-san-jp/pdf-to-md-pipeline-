# 設計仕様書 vol.1：完全ローカル版

**作成日**: 2026-04-17  
**対象環境**: Linux / macOS / Windows  
**スキャンPDF対応**: ✅ hybridモード（ローカルOCR）

-----

## 1. 概要

すべての処理をローカルマシン上で完結させる構成。
インターネット接続不要・データが外部に出ない・追加費用なし。
安定性はsystemdサービス（Linux/macOS）またはタスクスケジューラ（Windows）で担保する。

-----

## 2. フォルダ構成

```
project-root/
├── input/               # 作業フォルダ
│   ├── single.pdf
│   └── 001_まとめフォルダ/
│       ├── 01_intro.pdf
│       └── 02_body.pdf
├── output/              # 成果物フォルダ（Markdown）
├── done/                # 作業済みフォルダ
├── logs/                # 処理ログ
├── config.yaml          # 設定ファイル
├── run.py               # メインスクリプト
└── requirements.txt
```

-----

## 3. 処理フロー

```
[起動] 手動 or システムサービス
    │
    ▼
input/ を走査
    ├─ .pdf ファイル（単体）
    │     └─ opendataloader-pdf で変換
    │           └─ output/{stem}.md
    │                 └─ input/{file} → done/{stem}_{timestamp}.pdf
    │
    └─ サブフォルダ
          └─ フォルダ内PDFをファイル名昇順でソート
                └─ 各PDF変換 → Markdown連結
                      └─ output/{folder_name}.md
                            └─ input/{folder}/ → done/{folder}_{timestamp}/
    │
    ▼
ログ書き込み（logs/YYYY-MM-DD.log）
```

-----

## 4. 技術スタック

### 変換エンジン

|用途                   |ライブラリ                           |備考                       |
|---------------------|--------------------------------|-------------------------|
|PDF→Markdown（テキストPDF）|`opendataloader-pdf`            |Apache 2.0、CPU only、GPU不要|
|PDF→Markdown（スキャンPDF）|`opendataloader-pdf` + hybridモード|docling-fastバックエンドでOCR実行 |

**スキャンPDF変換コード例**

```python
import opendataloader_pdf

opendataloader_pdf.convert(
    input_path=["scanned.pdf"],
    output_dir="output/",
    format="markdown",
    hybrid="docling-fast",   # OCRモード有効化
    use_struct_tree=True,
)
```

hybrid バックエンドの起動（初回のみ）:

```bash
# インストール
pip install opendataloader-pdf[hybrid]

# バックエンドをバックグラウンドで起動（日本語OCR対応）
opendataloader-pdf-hybrid --port 5002 --ocr-lang "ja,en" &
```

### その他依存ライブラリ

|ライブラリ    |用途        |
|---------|----------|
|`PyYAML` |設定ファイル読み込み|
|`pathlib`|ファイルパス操作  |

-----

## 5. 設定ファイル（config.yaml）

```yaml
paths:
  input: ./input
  output: ./output
  done: ./done
  logs: ./logs

conversion:
  format: markdown
  use_struct_tree: true
  image_output: "off"
  hybrid: "docling-fast"     # スキャンPDF対応のため有効化
  hybrid_port: 5002
  ocr_lang: "ja,en"

done:
  add_timestamp: true        # done/移動時に {name}_{YYYYMMDD_HHMMSS} を付与
```

-----

## 6. メインスクリプト仕様（run.py）

```bash
# 即時実行（手動）
python run.py

# ログレベル指定
python run.py --log-level DEBUG
```

**処理ロジック概要**

```python
def process_input_dir(input_dir, output_dir, done_dir):
    for item in sorted(input_dir.iterdir()):
        if item.is_file() and item.suffix == ".pdf":
            convert_single(item, output_dir)
            move_to_done(item, done_dir)

        elif item.is_dir():
            pdfs = sorted(item.glob("*.pdf"))  # ファイル名昇順
            convert_folder(pdfs, item.name, output_dir)
            move_to_done(item, done_dir)
```

-----

## 7. 定期実行設定

### Linux / macOS：systemdサービス（推奨）

cron より再起動時の自動復旧・ログ管理が優れる。

**/etc/systemd/system/pdf-watcher.service**

```ini
[Unit]
Description=PDF to Markdown Converter
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/project-root
ExecStartPre=/bin/bash -c 'opendataloader-pdf-hybrid --port 5002 --ocr-lang "ja,en" &'
ExecStart=/usr/bin/python3 /path/to/project-root/run.py --loop
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable pdf-watcher
sudo systemctl start pdf-watcher
```

`--loop` モード時は `config.yaml` の `schedule.interval_minutes` で実行間隔を制御する。

### macOS：launchd（代替）

```xml
<!-- ~/Library/LaunchAgents/pdf-converter.plist -->
<key>StartInterval</key>
<integer>3600</integer>  <!-- 秒単位: 3600 = 1時間 -->
```

### Windows：タスクスケジューラ

```powershell
schtasks /create /tn "PDF-Converter" /tr "python C:\project\run.py" /sc hourly
```

-----

## 8. ログ仕様

```
logs/2026-04-17.log:

[2026-04-17 10:00:01] INFO  処理開始
[2026-04-17 10:00:02] INFO  変換: input/single.pdf → output/single.md
[2026-04-17 10:00:05] INFO  移動: input/single.pdf → done/single_20260417_100005.pdf
[2026-04-17 10:00:06] INFO  変換: input/001_まとめ/ (3ファイル) → output/001_まとめ.md
[2026-04-17 10:00:10] INFO  処理完了 (2件)
```

-----

## 9. 必要環境・セットアップ手順

```bash
# 1. 依存環境確認
java -version    # Java 11+ 必須
python --version # Python 3.10+ 必須

# 2. インストール
pip install opendataloader-pdf[hybrid] PyYAML

# 3. フォルダ作成
mkdir -p input output done logs

# 4. 動作確認（手動）
python run.py
```

-----

## 10. 制約・注意事項

- hybridモード（OCR）はJVMとdoclingバックエンドの両方が起動している必要がある
- スキャンPDFの精度はdocling-fastの性能に依存（複雑なレイアウトは `docling` モードで精度向上）
- 大量ページ処理時はメモリ使用量に注意（目安: 100ページ/秒、CPU only）
- `done/` への移動はタイムスタンプ付きのため、同名ファイルの上書きは発生しない

-----

## 11. 未確定事項

- [ ] 実行環境のOS（systemd / launchd / タスクスケジューラ）
- [ ] OCR言語（日本語のみ / 日英混在）
- [ ] 1回あたりの最大処理ファイル数（タイムアウト設定の要否）
- [ ] 出力Markdownのファイル名規則（元ファイル名そのまま / 日付prefix）
