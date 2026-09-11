# vibe-qt（株価表示アプリ）

株価データを取得してチャート（折れ線グラフ）と移動平均で表示するフルスタック Web アプリケーションです。

## 技術スタック

| 層 | 技術 |
|---|---|
| フロントエンド | Vue 3 + TypeScript、Vite、ECharts（vue-echarts）、axios |
| バックエンド | Django 4.2 / Django REST Framework |
| データベース | SQLite（`stock-app/backend/db/stock.db`） |
| コンテナ化 | Docker / Docker Compose |

## アーキテクチャ

```
┌────────────────────────┐        ┌─────────────────────────────┐        ┌────────────┐
│  frontend (nginx:80)   │  /api/ │  backend (gunicorn:8000)    │        │ db         │
│  Vue3 SPA (本番ビルド)  │ ──────▶│  Django/DRF                 │ ──────▶│ SQLite     │
└────────────────────────┘        │  /api/stocks/...            │        │ (共有ファイル)│
                                  └─────────────────────────────┘        └────────────┘
開発時: vite dev server (:5173) が同様に /api を backend へプロキシ
```

- 本番ビルドは nginx が配信し、`/api/` リクエストを backend へ転送（`frontend/nginx.conf`）
- 開発時は Vite のプロキシが `/api` を backend へ転送（`frontend/vite.config.ts`）
- `db` サービスは backend と同一の SQLite ファイルを共有し、クエリ確認用のデータホストとして動作

## ディレクトリ構成

```
.
├── stock-app/
│   ├── backend/                # Django / DRF バックエンド
│   │   ├── stockapp/           # プロジェクト（settings, urls, wsgi）
│   │   │   └── app/            # StockRecord モデル / ViewSet / シリアライザー
│   │   ├── db/                 # SQLite DB ファイルの置き場（コミットしない）
│   │   └── Dockerfile
│   ├── frontend/               # Vue 3 フロントエンド
│   │   ├── src/
│   │   │   ├── App.vue
│   │   │   └── components/Stock.vue   # チャート + 移動平均 UI
│   │   ├── vite.config.ts    # 開発用プロキシ（/api -> backend）
│   │   ├── nginx.conf        # 本番用 nginx 設定（/api -> backend）
│   │   └── Dockerfile
│   └── docker-compose.yml
├── tests/test_api.py           # API テスト（pytest + pytest-django）
├── postman/                    # Postman コレクション
├── pytest.ini
└── requirements-dev.txt        # テスト実行用依存関係
```

## 起動方法

### 方法 1: Docker Compose（推奨）

```bash
cd stock-app
docker compose up -d --build
```

| サービス | ポート | 説明 |
|---|---|---|
| frontend | http://localhost:80 | nginx が Vue アプリを配信し、`/api/` を backend へプロキシ |
| backend | http://localhost:8000 | Django/DRF API（起動時に `migrate` が自動実行される） |
| db | - | backend と SQLite ファイルを共有するデータホスト |

起動確認:

```bash
curl http://localhost:8000/api/stocks/
curl http://localhost/api/stocks/   # frontend (nginx) 経由
```

### 方法 2: ローカル開発（ホットリロード付き）

バックエンド（ターミナル 1）:

```bash
cd stock-app/backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 8000
```

フロントエンド（ターミナル 2）:

```bash
cd stock-app/frontend
npm install
npm run dev
# http://localhost:5173 で起動。/api は自動的に http://localhost:8000 へプロキシ
```

## API リファレンス

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/stocks/` | 全レコードのリスト（日付降順） |
| GET | `/api/stocks/<symbol>/` | 指定シンボルの株価（日付降順） |
| GET | `/api/moving_average/<symbol>/?days=N` | 直近 N 日（既定 5）の終値移動平均。`days` は正の整数（非整数・1 未満は 400）。データなしなら 404 |
| POST | `/api/stocks/fetch/` | Yahoo Finance（yfinance）から日足 OHLC を取得して DB に保存（upsert）。Body: `{"symbol": "AAPL", "period": "1mo"}`（period: 5d / 1mo / 3mo / 6mo / 1y / 2y / 5y）。データなし 404、Yahoo 通信エラー 502 |

レスポンスの例:

```json
// GET /api/stocks/AAPL/
[
  {"id": 1, "symbol": "AAPL", "date": "2026-09-10", "close": "154.0000"}
]

// GET /api/moving_average/AAPL/?days=3
{"symbol": "AAPL", "moving_average": 153.33333333333334}
```

## テスト

### API テスト（pytest / Django/DRF）

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

### Postman

`postman/MyApp API Tests.postman_collection.json` をインポートし、環境変数 `BASE_URL` を `http://localhost:8000` に設定して使用してください。

## データベースの確認

`db` サービスは backend と同一の SQLite ファイル（`stock-app/backend/db/stock.db`）を共有しています:

```bash
docker compose -f stock-app/docker-compose.yml exec db sqlite3 /data/db/stock.db ".tables"
```

## セキュリティ設定（Django）

`settings.py` は以下を環境変数から読みます（既定値は開発向けです）:

| 変数 | 既定値 | 説明 |
|---|---|---|
| `DJANGO_DEBUG` | `False` | デバッグモード。docker-compose.yml が `true` を明示（本番では設定しないこと） |
| `DJANGO_SECRET_KEY` | 開発用フォールバックキー | 本番環境では必ず上書き |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | カンマ区切り。`DEBUG=true` のときは `*` に自動変更 |

## 備考（Issue #19 での修正内容）

- テストを FastAPI 前提から Django/DRF 前提（pytest-django）に変更し実行可能に
- vite のプロキシから `/api` プレフィックス除去（rewrite）を削除（backend の URL は `/api/...` 始まりのため）
- `db` サービスを backend の SQLite ファイルと共有し接続（named volume の廃止）
- frontend の nginx に `/api/` → backend へのプロキシ設定を追加（`nginx.conf`）
- backend コンテナ起動時に `migrate` を自動実行するよう変更
- `INSTALLED_APPS` に `django.contrib.auth` を追加（DRF の無名ユーザー生成に必要）
- URL 解決順を修正（router の `{pk}` がシンボル文字列を先取りしていた問題）
- バックエンド用のマイグレーション（`app/migrations`）を追加

## 備考（Issue #23: yfinance 株価取得 + ローソク足チャート）

- `StockRecord` に `open` / `high` / `low` / `volume` フィールドを追加（既存行は close 値で backfill）
- `POST /api/stocks/fetch/` を追加（yfinance で日足 OHLC を取得し DB に upsert、シンボルは `SYMBOL_RE` で検証）
- フロントエンドのチャートを日足ローソク足に変更（日本式: 陽線=赤 / 陰線=緑、日付昇順で表示）
- backend コンテナは Yahoo Finance（query1.finance.yahoo.com）と通信可能なネットワーク接続を必要とする

## 備考（PR #20 レビュー対応）

- `moving_average` の `days` パラメータをバリデーション（非整数・1 未満は 400、従来は 500）
- 汎用 router を廃止し、関数ビューでルートを明示（到達不能な detail ルートの排除）
- `.dockerignore` 追加（backend: 開発用 DB・pycache / frontend: node_modules・dist）
- `DEBUG` / `SECRET_KEY` / `ALLOWED_HOSTS` を環境変数から読み込むように変更
- `unique_together`（非推奨）を `UniqueConstraint` 制約に置換
- CI（GitHub Actions で pytest を実行するワークフロー）を追加

## 備考（Issue #25: 出来高バーのチャート表示）

- ローソク足チャートの下に出来高バーを追加（2 グリッド＋2 y 軸、`axisPointer.link` で tooltip / 軸カーソルを連動）
- 出来高バーは陽線=赤 / 陰線=緑でローソク足と同様に色分け（volume が null のレコード（close のみ手入力）はバー非表示）
- バックエンド・DB の変更は不要（`volume` は Issue #23 で既に DB 保存・API 返却済み）
