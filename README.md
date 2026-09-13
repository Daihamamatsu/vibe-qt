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
│   │   │   ├── components/Stock.vue   # チャート + 移動平均 / タートル戦略 UI
│   │   │   └── utils/turtle.ts        # タートルズ型 (Donchian + ATR) 計算ロジック
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

## 備考（Issue #29: タートルズ型 ATR ボラティリティ・ブレイクアウト (Donchian + ATR)）

- タートルズ戦略のインジケータと BUY / EXIT シグナルを表示（フロントエンドの純粋 TS モジュール `src/utils/turtle.ts` で計算、バックエンド / DB は変更なし）
- **計算ロジック（ルックアヘッド・バイアス回避: バンドと判定は前日までのデータのみ使用）**
  - Donchian Upper（エントリーライン）: 前日までの 20 日間の最高値（当日は除外してシフト）
  - Donchian Lower（手仕舞いライン）: 前日までの 10 日間の最安値
  - N (ATR): True Range の単純移動平均（14 / 20 日選択可、既定 20）
  - BUY: 当日終値が Donchian Upper を上抜け / EXIT: 終値が Donchian Lower を下抜けまたはトレーリングストップ（直近 10 日高値 − 2×N、前日終了時点）に達した日
  - 1 ユニット推奨株数: `floor((口座資金 × 0.01) / (N × 1株あたりの価値))`
  - ピラミッディング目標: 買値 +0.5N / +1.0N / +1.5N、ストップロス: 買値 −2N
- **描画**: メインチャートに DC20 / DC10 を破線でオーバーレイ、BUY（赤）/ EXIT（緑）マーカー（日本式カラー）、ピラミッド目標・ストップを破線ガイド（markLine）、下部サブパネルに ATR ライン
- **情報パネル**: 表示 ON/OFF、ATR 期間 (N) 選択、口座資金・買値入力（買値は最新終値を既定）、直近 N / 推奨株数 / 目標価格リストを表示
- `chartOptions` を computed 化し、パラメータ変更でチャートが自動再描画されるように変更
- 完全な使い方ガイド（UI 操作手順 / チャートの見方 / ポジションサイジング）は [`docs/turtle-strategy.md`](docs/turtle-strategy.md) を参照

## 備考（Issue #36: チャートの表示ウィンドウ指定 + ドラッグ・スクロールによるパン）

- **表示ウィンドウ指定**: チャートの初期表示範囲を「表示期間」（1mo / 3mo / 6mo / 1y / 2y / 全、営業日換算の概算）または「本数」で指定可能に（本数指定が期間より優先、本数欄の空欄 = 期間に従う）。既定は 1y（約 261 本）。チャートには**取得済みデータすべて**が入り、表示期間 / 本数は初期表示範囲（直近 N 本）を dataZoom percent として適用するだけなので、**より古いデータはパン（ホイール / ドラッグ / スライダー）で表示できる**。計算ロジックは `src/utils/display.ts` の純関数（`resolveDisplayCount` / `getDisplayRange`）に分離し、`src/utils/display.test.ts` でユニットテスト
- **パン / スクロール / ズーム（ECharts `dataZoom`）**:
  - ドラッグ（マウス長押し+移動）= 横移動（パン）
  - ホイール = スクロール（パン）
  - Ctrl + ホイール = ズーム
  - チャート下部にスライダー（`type: 'slider'`）を追加し、可視範囲の表示と直接操作（ドラッグ選択・ハンドル操作）に対応
- 新データ取得時（取得ボタン / 銘柄変更など）・表示期間 / 本数切替時は `dispatchAction` で表示ウィンドウ（直近 N 本分）を適用。チャートには全データが残るため、適用後もパン（ホイール / ドラッグ / スライダー）でより古いデータを辿れる
- 表示期間の営業日換算: 1mo=22 / 3mo=66 / 6mo=132 / 1y=261 / 2y=522 本（`DISPLAY_PRESETS`）

## 備考（Issue #40: タートル戦略数値エリア（ホバー時点の値））

- タートル戦略 (Donchian Channel + ATR) を ON にしている場合、固定情報パネル（現在値エリア）内に現在値テーブルと**視覚的に分離された専用セクション**を追加し、**ホバー中のインデックス時点**の戦略数値を表示（Issue #41 で標準 tooltip の内容表示が無効化されたことで、DC20 / DC10 / N (ATR) が画面のどこにも見られなくなった問題への対応）
- 表示項目: 日付 / DC20 (エントリーライン) / DC10 (手仕舞いライン) / N (ATR) / トレーリングストップ / BUY・EXIT シグナル（日本式カラー: BUY = 赤、EXIT = 緑）
- 値はクロスヘア（axisPointer）のホバーに追従（現在値パネルと同一の dataIndex マッピング）、ポインタがグリッド外に出たときは直近の値を保持、データ取得（銘柄切替・再取得）時は古い値をリセット（すべて固定情報パネルの既存ロジックを再利用し、新規の計算・イベントコードは追加してない）
- タートル戦略 OFF 時にはセクションが非表示になる
- 現在値テーブルから `ATR (N)` 行を削除し、タートル戦略数値エリアへ集約した（現在値エリアは価格・出来高のみ）
- 画面下部の静的なテーブル（直近 ATR / 1 ユニット推奨株数 / ピラミッド目標・ストップ）は従来通り**最新日**の値を表示するもので、ホバー時点の数値エリアとは別物

## 備考（Issue #44: タートル戦略のブレイク日選択 + 買い増し / EXIT 計画表示）

- **1 ユニット推奨株数の数式変更**: `floor(口座資金 × 0.01 / N)`（1 株あたりの価値 = 1 ポイント固定のため、買値を掛けない。従来の `floor((口座資金 × 0.01) / (N × 買値))` を置換）
- **`computeTurtlePlan`（`src/utils/turtle.ts`）**: ブレイク日（BUY シグナル日）と買値を指定すると、ブレイク日以降をシミュレートする
  - 買い増し (P2/P3/P4): 毎日その日の N で目標を再計算し（`買値 + {0.5, 1.0, 1.5} × N`）、終値が到達 (≥) した日に買い増し（同日の複数レベル到達を許容）
  - EXIT: 終値 ≤ `買値 − 2N`（ストップロス）、または終値 < DC10（手仕舞いライン下抜け）の初回到達（同日に両方該当すればストップを優先）
  - ブレイク日・買値が不正 / ATR 不足なら `null`（UI は計画行を非表示）
- **フロントエンド（`Stock.vue`）**:
  - タートルパネルに**ブレイク日**セレクタを追加（候補は BUY シグナル日のみ、既定は最新の BUY 日。手動選択後は次回取得でも上書きしない。銘柄変更でリセット）
  - ブレイク日選択時に、買値がその日終値へ自動設定される（買値の手動入力優先）
  - 情報パネルの表に**買い増し計画 (P2/P3/P4)**（到達日・目標価格・到達日終値）と **EXIT 計画**（到達日・理由・終値）を追加表示
  - チャートに買い増し（◇ 紫）/ 計画 EXIT（■ 緑）のマーカーを追加（既存の指標 BUY/EXIT マーカーとは別物として表示）
- `turtle.test.ts` に `computeTurtlePlan` のケースを追加（同日複数買い増し / ストップ EXIT / DC10 EXIT / ブレイク日欠落・買値不正 / ATR 不足）。ユニットテスト計 29 件で検証、`npm run typecheck` / `npm run build` はパス

## 備考（Issue #46: BUY/EXIT シグナルマーカーをローソク足と重ならない位置に表示）

- チャートの BUY / EXIT シグナルマーカーをローソク足と重ならない位置に変更（従来は終値に配置しておりローソク足と重なって見づらかったため）
  - **BUY**: 当日ローソク足の高値より**上側**に配置
  - **EXIT**: 当日ローソク足の安値より**下側**に配置
- ローソク足からの隙間は**当日 ATR の半分**を優先（ATR 未算出時はレンジ幅の 2%）
- チャート表示エリア（y 軸自動レンジ: ローソク足 + Donchian バンド + markLine 値）の上下限を超えそうな場合はレンジ内にクランプし、ローソク足との重なりを許容
- `Stock.vue` の `chartOptions` 内の BUY/EXIT scatter のみ変更（`turtle.ts` の計算ロジックは変更なし、買い増し / 計画 EXIT マーカー（Issue #44）は対象外）
- `npm test`（29 件パス）/ `npm run typecheck` / `npm run build` で検証
