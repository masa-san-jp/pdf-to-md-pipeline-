# 設計仕様書 vol.3：完全クラウド版

**作成日**: 2026-04-17  
**対象環境**: Google Cloud Platform（GCS + Document AI + Cloud Run + Cloud Scheduler）  
**OCRエンジン**: Google Cloud Document AI（Enterprise Document OCR）  
**スキャンPDF対応**: ✅ Document AI によるクラウドOCR  
**共同作業**: ✅ Google Drive + GCS で複数人対応  
**定期実行**: ✅ Cloud Scheduler で完全自動化

-----

## 1. 概要

ローカルPCへの依存をゼロにした完全サーバーレス構成。
PDFをGoogleドライブ（またはGCS）にアップロードするだけで、Cloud Schedulerが定期的にCloud Runジョブを起動し、Document AI OCRでMarkdownへ変換する。
メンテナンス対象のサーバーが存在しないため、運用コストが低い。

**なぜDocument AIを選ぶか**  
`opendataloader-pdf` はローカル実行前提のツールであり、サーバーレス環境でのJVM起動はコールドスタートのコスト・複雑さが増す。
Document AIは200以上の言語に対応したOCRエンジンをAPIとして提供しており、スキャンPDFを含むあらゆるPDFをクラウド上でOCR処理できる。
ただしDocument AIはMarkdownを直接返さないため、OCR結果からMarkdown変換する後処理レイヤーを実装する。

-----

## 2. アーキテクチャ

```
[ユーザー]
    │ PDFをアップロード
    ▼
Google Drive（input/フォルダ）
    │ Drive→GCS同期（Drive APIまたはGcsfuse）
    ▼
GCS: input バケット
    │
    ▼
Cloud Scheduler（定期トリガー or 手動）
    │ Cloud Run ジョブを起動
    ▼
Cloud Run ジョブ（Python）
    ├─ GCS input/ のPDFをスキャン
    ├─ Document AI API でOCR
    │       └─ テキスト + レイアウト情報（段落・テーブル・見出し）取得
    ├─ Markdown変換（後処理）
    ├─ GCS output/ にMarkdownを保存
    └─ GCS input/ → GCS done/ にPDFを移動
    │
    ▼
GCS: output バケット
    │ GCS→Drive同期
    ▼
Google Drive（output/フォルダ）
    │
[ユーザー] Markdownを参照・共有
```

-----

## 3. GCSバケット構成

```
gs://[PROJECT]-pdf-converter/
├── input/               # 変換対象PDF
│   ├── single.pdf
│   └── 001_まとめ/
│       ├── 01_intro.pdf
│       └── 02_body.pdf
├── output/              # 変換済みMarkdown
├── done/                # 処理済みPDF
└── logs/                # 処理ログ（JSON Lines形式）
```

-----

## 4. 技術スタック

|コンポーネント|サービス                                             |役割                   |
|-------|-------------------------------------------------|---------------------|
|OCR    |Google Cloud Document AI（Enterprise Document OCR）|スキャン・テキストPDF問わずOCR   |
|変換ジョブ実行|Cloud Run Jobs                                   |ステートレスなバッチ処理         |
|定期実行   |Cloud Scheduler                                  |cron式でジョブをトリガー       |
|ストレージ  |Cloud Storage (GCS)                              |PDF・Markdownの保管      |
|Drive連携|Google Drive API                                 |ユーザーのDriveフォルダとGCSを同期|
|ログ     |Cloud Logging                                    |処理ログの管理・検索           |
|認証     |Service Account + IAM                            |最小権限で各サービスに認証        |

-----

## 5. Document AI OCR → Markdown変換仕様

Document AIはブロック・段落・行・単語・記号レベルで文書構造を検出する。この構造情報を使ってMarkdownを組み立てる。

### 変換マッピング

|Document AI の検出要素          |Markdown出力                 |
|---------------------------|---------------------------|
|`HEADING_1` / `HEADING_2` 等|`# ` / `## `               |
|`PARAGRAPH`                |通常テキスト段落                   |
|`TABLE`                    |Markdownテーブル（`|col|col|`形式）|
|`LIST_ITEM`                |`- ` リスト                   |
|改ページ                       |`---`（水平線）                 |

### 変換コード概要

```python
from google.cloud import documentai
from google.cloud import storage

def process_pdf_to_markdown(gcs_input_uri: str, gcs_output_uri: str):
    # Document AI クライアント
    client = documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": "us-documentai.googleapis.com"}
    )
    
    # バッチ処理リクエスト（大容量PDF対応）
    request = documentai.BatchProcessRequest(
        name=PROCESSOR_NAME,
        input_documents=documentai.BatchDocumentsInputConfig(
            gcs_prefix=documentai.GcsPrefix(gcs_uri_prefix=gcs_input_uri)
        ),
        document_output_config=documentai.DocumentOutputConfig(
            gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
                gcs_uri=gcs_output_uri
            )
        ),
    )
    operation = client.batch_process_documents(request=request)
    operation.result()  # 完了まで待機
    
    # GCSの出力JSONからMarkdown変換
    return convert_docai_json_to_markdown(gcs_output_uri)

def convert_docai_json_to_markdown(gcs_output_uri: str) -> str:
    """Document AIのJSON出力をMarkdownに変換"""
    # 段落・テーブル・見出しを構造に応じてMarkdownに組み立て
    ...
```

### 日本語設定

```python
process_options = documentai.ProcessOptions(
    ocr_config=documentai.OcrConfig(
        enable_native_pdf_parsing=True,   # テキストPDFは直接抽出
        language_hints=["ja", "en"],      # 日本語・英語OCR
    )
)
```

-----

## 6. Cloud Run ジョブ仕様

```python
# main.py（Cloud Runジョブのエントリポイント）

def main():
    gcs = storage.Client()
    bucket = gcs.bucket(BUCKET_NAME)
    
    # input/ を走査
    items = list_input_items(bucket, "input/")
    
    for item in items:
        try:
            if item.endswith(".pdf"):
                md = process_pdf_to_markdown(f"gs://{BUCKET_NAME}/{item}")
                save_markdown(bucket, item, md, "output/")
                move_to_done(bucket, item, "done/")
            elif is_folder(items, item):
                # フォルダ内PDF群をまとめて処理・結合
                md = process_folder_to_markdown(bucket, item)
                save_markdown(bucket, item.rstrip("/"), md, "output/")
                move_folder_to_done(bucket, item, "done/")
        except Exception as e:
            log_error(item, e)
    
    log_summary(results)

if __name__ == "__main__":
    main()
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
CMD ["python", "main.py"]
```

-----

## 7. Cloud Schedulerの設定

```bash
# 毎時0分に実行
gcloud scheduler jobs create http pdf-converter-job \
  --schedule="0 * * * *" \
  --uri="https://[REGION]-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/[PROJECT]/jobs/pdf-converter:run" \
  --oauth-service-account-email="pdf-converter-sa@[PROJECT].iam.gserviceaccount.com" \
  --location="asia-northeast1"
```

-----

## 8. GoogleドライブとGCSの連携

### パターンA: Drive API で直接連携（推奨）

Cloud Run ジョブ内でDrive APIを呼び出し、DriveフォルダとGCS inputを同期する。

```
ユーザーがDriveにPDFアップロード
    ↓
Cloud Run ジョブが起動時にDriveのinput/フォルダを確認
    ↓
新規PDFをGCS inputにコピー → 変換 → 結果をDrive outputにコピー
```

### パターンB: Drive デスクトップ + GCS（シンプル）

- GoogleドライブPC版で `pdf-to-markdown/` フォルダをローカルにマウント
- `gcsfuse` でGCSバケットもローカルにマウント
- rsyncで定期同期

-----

## 9. コスト試算（月額目安）

|サービス           |想定使用量      |月額目安               |
|---------------|-----------|-------------------|
|Document AI OCR|1,000ページ/月 |約$1.50（$0.0015/ページ）|
|Cloud Run Jobs |60回/月（1時間毎）|約$0.10             |
|Cloud Storage  |1GB        |$0.02              |
|Cloud Scheduler|1ジョブ       |無料枠内               |
|**合計**         |           |**約$2/月〜**         |


> 無料枠: Document AI は最初の1,000ページ/月が無料。Cloud Run は最初の50時間/月が無料。

-----

## 10. セットアップ手順（概要）

```bash
# 1. GCPプロジェクト作成・API有効化
gcloud services enable documentai.googleapis.com run.googleapis.com \
  cloudscheduler.googleapis.com storage.googleapis.com

# 2. Document AI プロセッサ作成（コンソールから）
#    Document AI → プロセッサを作成 → Enterprise Document OCR

# 3. GCSバケット作成
gsutil mb -l asia-northeast1 gs://[PROJECT]-pdf-converter

# 4. Cloud Runイメージのビルド・デプロイ
gcloud builds submit --tag gcr.io/[PROJECT]/pdf-converter
gcloud run jobs create pdf-converter --image gcr.io/[PROJECT]/pdf-converter \
  --region asia-northeast1

# 5. Cloud Scheduler設定（上記コマンド）
```

-----

## 11. 制約・注意事項

|項目           |内容                                     |
|-------------|---------------------------------------|
|Document AI制限|同期処理: 最大15ページ / 非同期(Batch): 無制限        |
|Markdown精度   |Document AIのJSONをMarkdownに変換する後処理の品質に依存|
|テーブル精度       |テーブル構造検出・行列構造の保持に対応するが複雑なレイアウトは要検証     |
|ランニングコスト     |ページ数に応じて課金発生（無料枠は1,000ページ/月）           |
|データ保管場所      |GCS（Googleのサーバー）に保管される                 |

-----

## 12. 未確定事項

- [ ] GCPプロジェクトの有無・作成権限
- [ ] Document AIのリージョン（`us` / `eu` / `asia`）
- [ ] DriveとGCSの連携パターン（A: API連携 / B: gcsfuse同期）
- [ ] 月間処理ページ数（コスト見積もりのため）
- [ ] Markdownの精度要件（Document AIの後処理品質が許容範囲か要検証）
