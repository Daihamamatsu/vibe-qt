<template>
  <div class="stock-container">
    <!-- コントロールパネル -->
    <div class="control-panel" style="background:#f5f5f5;padding:1rem;border-radius:.5rem;margin-bottom:1.5rem;">
      <h3 style="margin-top:0;font-size:1.2rem;">株価データ</h3>
      <div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap;">
        <label>シンボル:</label>
        <input v-model="symbol" placeholder="例：AAPL" />
        <!-- 銘柄名（Yahoo Finance 取得、Issue #49）: 取得不能時は非表示 -->
        <span v-if="stockName" style="color:#555;">{{ stockName }}</span>
        <!-- お気に入り切替 (Issue #50): 現在入力のシンボルをアクティブリストに追加/削除 -->
        <button
          :disabled="favoriteBusy"
          :title="isFavorite ? 'このリストから削除' : 'このリストにお気に入りを追加'"
          :style="{ fontSize: '1.2rem', padding: '0.2rem 0.5rem', cursor: favoriteBusy ? 'wait' : 'pointer' }"
          @click="isFavorite ? removeFavorite(symbol.trim().toUpperCase()) : addFavorite()"
        >{{ isFavorite ? '★' : '☆' }}</button>
        <label>期間:</label>
        <select v-model="period">
          <option value="5d">5d</option>
          <option value="1mo">1mo</option>
          <option value="3mo">3mo</option>
          <option value="6mo">6mo</option>
          <option value="1y">1y</option>
          <option value="2y">2y</option>
          <option value="5y">5y</option>
        </select>
        <label>表示:</label>
        <select v-model="displayPeriod">
          <option v-for="p in DISPLAY_PRESETS" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
        <label>本数:</label>
        <!-- 表示するローソク足の本数指定（空欄 = 表示期間に従う。本数指定が期間より優先される） -->
        <input v-model.number="displayCount" type="number" min="1" step="1" placeholder="期間に連動" style="width:5.5rem;" />
        <button @click="fetchStockData">取得</button>
        <button :disabled="fetching" @click="fetchFromYahoo">Yahoo Finance から取得</button>
      </div>
      <!-- Yahoo Finance 取得ステータス -->
      <p v-if="yahooMessage" :style="{ marginTop: '.5rem', marginBottom: 0, color: yahooError ? '#c0392b' : '#2c7a2c' }">
        {{ yahooMessage }}
      </p>
      <!-- お気に入り銘柄リスト (Issue #50): select ボックスでリスト選択、シンボルクリックでその銘柄へ切替 -->
      <div style="margin-top:.5rem;">
        <p style="margin:0 0 .25rem;font-weight:bold;">★ お気に入り</p>
        <div style="display:flex;gap:.25rem;align-items:center;flex-wrap:wrap;">
          <!-- リスト選択 (Issue #50): select ボックス。値は文字列で届くため onListSelectChange で数値化 -->
          <select
            :value="activeListId ?? ''"
            :disabled="favoriteBusy"
            title="リストを選択（お気に入りをこのリストに追加/削除）"
            style="min-width:11rem;"
            @change="onListSelectChange"
          >
            <option v-for="g in favoriteGroups" :key="g.id" :value="g.id">{{ g.name }}（{{ g.stocks.length }}）</option>
          </select>
          <button
            :disabled="favoriteBusy || activeListId === null"
            title="選択中のリストの名前を変更"
            @click="renameActiveList(activeListId)"
          >名前変更</button>
          <button
            :disabled="favoriteBusy || activeListId === null"
            title="選択中のリストを削除"
            @click="deleteActiveList(activeListId)"
          >削除</button>
          <button :disabled="favoriteBusy" title="新しいリストを作成" @click="createList">＋ 新しいリストを作成</button>
        </div>
        <p v-if="favoriteGroups.length === 0" style="margin:.25rem 0 0;color:#888;">リストがありません</p>
        <ul style="margin:.5rem 0 0;padding:0;">
          <li v-for="f in activeGroup?.stocks ?? []" :key="f.symbol" style="margin:.15rem 0;">
            <a href="#" :style="{ color:'#1a73e8' }" @click.prevent="symbol = f.symbol">{{ f.symbol }}</a>
            <span v-if="f.name" style="color:#555;">{{ f.name }}</span>
            <button :disabled="favoriteBusy" style="margin-left:.5rem;" title="このリストから削除" @click="removeFavorite(f.symbol)">✕</button>
          </li>
          <li v-if="(activeGroup?.stocks.length ?? 0) === 0" style="color:#888;">このリストには銘柄がありません</li>
        </ul>
        <p v-if="favoriteMessage" style="margin:.25rem 0 0;color:#c0392b;">{{ favoriteMessage }}</p>
      </div>
    </div>

    <!-- チャート表示（日足ローソク足 + 出来高バー + タートル ATR サブパネル + 下部ズームスライダー） -->
    <!-- chart-wrapper: 固定情報パネルの position 参照容器 -->
    <div ref="wrapperRef" class="chart-wrapper">
      <v-chart ref="chartRef" :option="chartOptions" :style="{ height: turtleEnabled ? '640px' : '480px' }" v-if="data.length > 0"></v-chart>
      <!-- 固定情報パネル: ホバー中のローソク足の正確な価格・出来高を表示（ヘッダーでドラッグ可能） -->
      <div v-if="data.length > 0" ref="panelRef" class="info-panel" :style="panelStyle">
        <!-- ドラッグバー: ポインターはここだけ捕捉する（本体はクリック透過でクロスヘア維持） -->
        <div
          class="info-panel-handle"
          @pointerdown="onPanelPointerDown"
          @pointermove="onPanelPointerMove"
          @pointerup="onPanelPointerUp"
          @pointercancel="onPanelPointerUp"
        >⠿ 現在値</div>
        <table class="info-table">
          <tbody>
            <tr><th>日付</th><td>{{ hoverRecord ? hoverRecord.date : '—' }}</td></tr>
            <tr><th>始値</th><td>{{ fmtPrice(hoverRecord?.open) }}</td></tr>
            <tr><th>高値</th><td>{{ fmtPrice(hoverRecord?.high) }}</td></tr>
            <tr><th>安値</th><td>{{ fmtPrice(hoverRecord?.low) }}</td></tr>
            <tr><th>終値</th><td>{{ fmtPrice(hoverRecord?.close) }}</td></tr>
            <tr>
              <th>前日比</th>
              <td :style="hoverChange ? { color: hoverChange.diff >= 0 ? '#e2534f' : '#3ba272' } : {}">
                {{
                  hoverChange
                    ? `${hoverChange.diff > 0 ? '+' : ''}${hoverChange.diff.toFixed(2)} (${hoverChange.diff > 0 ? '+' : ''}${hoverChange.pct.toFixed(2)}%)`
                    : '—'
                }}
              </td>
            </tr>
            <tr><th>出来高</th><td>{{ fmtVolume(hoverRecord?.volume) }}</td></tr>
          </tbody>
        </table>
        <!-- タートル戦略数値エリア (Issue #40): ホバー中のインデックス時点の数値を表示。
             現在値テーブルと区切りの入った独立セクションで、turtleEnabled に連動して表示・非表示。
             dataIndex マッピング・グリッド外出時の直近値保持・データ取得時のリセットは現在値パネルと共通の既存ロジックをそのまま利用する。 -->
        <div v-if="turtleEnabled" class="turtle-section">
          <div class="turtle-section-header">タートル戦略 (Donchian + ATR)</div>
          <table class="info-table">
            <tbody>
              <tr><th>日付</th><td>{{ hoverTurtle ? hoverTurtle.date : '—' }}</td></tr>
              <tr><th>DC20 (エントリーライン)</th><td>{{ fmtPrice(hoverTurtle?.donchianUpper) }}</td></tr>
              <tr><th>DC10 (手仕舞いライン)</th><td>{{ fmtPrice(hoverTurtle?.donchianLower) }}</td></tr>
              <tr><th>N (ATR)</th><td>{{ fmtPrice(hoverTurtle?.atr) }}</td></tr>
              <tr><th>トレーリングストップ</th><td>{{ fmtPrice(hoverTurtle?.trailingStop) }}</td></tr>
              <tr>
                <th>シグナル</th>
                <!-- 日本式カラー: BUY = 赤 / EXIT = 緑（チャート本体と同一） -->
                <td
                  :style="hoverTurtle?.buy
                    ? { color: '#e2534f', fontWeight: 'bold' }
                    : hoverTurtle?.exit
                      ? { color: '#3ba272', fontWeight: 'bold' }
                      : {}"
                >
                  {{ hoverTurtle?.buy ? 'BUY' : hoverTurtle?.exit ? 'EXIT' : '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 移動平均計算 -->
    <div class="moving-average-panel" style="margin-top:1rem;background:#f9f9f9;padding:.5rem;border-radius:.3rem;">
      <h4>移動平均</h4>
      <div style="display:flex;gap:.8rem;align-items:center;">
        <label>日数:</label>
        <input type="number" v-model.number="maDays" min="1" />
        <button @click="fetchMovingAverage">計算</button>
      </div>
      <p v-if="movingAverage !== null">{{ symbol }} の {{ maDays }} 日移動平均: {{ movingAverage.toFixed(2) }}</p>
    </div>

    <!-- タートル戦略 (Donchian Channel + ATR) -->
    <div class="turtle-panel" style="margin-top:1rem;background:#f9f9f9;padding:.5rem;border-radius:.3rem;">
      <h4>タートル戦略 (Donchian Channel + ATR)</h4>
      <div style="display:flex;gap:.8rem;align-items:center;flex-wrap:wrap;">
        <label><input type="checkbox" v-model="turtleEnabled" /> 表示</label>
        <label>ATR 期間 N:
          <select v-model.number="atrPeriod">
            <option :value="14">14</option>
            <option :value="20">20</option>
          </select>
        </label>
        <label>口座資金:
          <input type="number" v-model.number="accountValue" min="0" style="width:9rem;" />
        </label>
        <label>ブレイク日:
          <!-- BUY シグナル日のみ候補。選択時、買値が空欄ならその日終値が自動設定される -->
          <select v-model="turtleBreakoutDate" style="width:9.5rem;">
            <option v-for="d in buySignalDates" :key="d" :value="d">{{ d }}</option>
          </select>
        </label>
        <label>買値:
          <!-- 保存状態のある銘柄は復元値、ない銘柄は空欄（自動設定なし） -->
          <input type="number" v-model.number="turtleBuyPrice" min="0" style="width:7rem;" />
        </label>
      </div>
      <!-- 銘柄ごとの保存状態 (Issue #53) -->
      <div style="display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;">
        <span style="font-size:.85rem;" :style="hasSavedTurtleState ? { color: '#16a34a' } : { color: '#9ca3af' }">
          {{ hasSavedTurtleState ? '● 状態: 保存済み' : '○ 状態: 未保存' }}
        </span>
        <button type="button" :disabled="!isValidSymbol(currentTurtleSymbol)" @click="saveCurrentTurtleState">状態を保存</button>
        <button type="button" :disabled="!hasSavedTurtleState" @click="releaseCurrentTurtleState">状態を解除</button>
        <span v-if="turtleStateMessage" style="font-size:.8rem;color:#6b7280;">{{ turtleStateMessage }}</span>
      </div>
      <table v-if="turtleEnabled && latestAtr !== null" class="turtle-table">
        <tbody>
          <tr>
            <th>直近 N (ATR)</th>
            <td>{{ latestAtr.toFixed(2) }}</td>
          </tr>
          <tr>
            <th>1ユニット推奨株数<br /><small>floor(口座資金×0.01 ÷ N)</small></th>
            <td>{{ accountValueNumber === null ? '—' : `${unitShares} 株` }}</td>
          </tr>
          <tr v-if="targets">
            <th>ピラミッド目標 / ストップ<br /><small>直近 N での再計算</small></th>
            <td>
              +0.5N: {{ targets.target1.toFixed(2) }} ／ +1.0N: {{ targets.target2.toFixed(2) }} ／
              +1.5N: {{ targets.target3.toFixed(2) }} ／ ストップ(-2N): {{ targets.stop.toFixed(2) }}
            </td>
          </tr>
          <tr v-if="turtlePlan">
            <th>買い増し計画 (P2/P3/P4)<br /><small>毎日 直前ユニットの目標ライン + 0.5 × N で再計算 (到達後はライン固定)</small></th>
            <td>
              +0.5N: {{ fmtPlanLevel(turtlePlan.levels[0]) }}<br />
              +1.0N: {{ fmtPlanLevel(turtlePlan.levels[1]) }}<br />
              +1.5N: {{ fmtPlanLevel(turtlePlan.levels[2]) }}
            </td>
          </tr>
          <tr v-if="turtlePlan">
            <th>EXIT 計画<br /><small>終値 ≤ 最新エントリー−2N または 終値 &lt; DC10</small></th>
            <td>{{ fmtPlanExit(turtlePlan) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="turtleEnabled && data.length > 0" class="turtle-hint">
        ATR を計算するには {{ atrPeriod }} 日以上のデータが必要です
      </p>
      <p v-if="turtleEnabled && latestAtr !== null && !turtlePlan" class="turtle-hint">
        買い増し / EXIT 計画を表示するにはブレイク日 (BUY シグナル日) を指定してください
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import axios from 'axios';
import VChart from 'vue-echarts';
import type { EChartsOption, SeriesOption } from 'echarts';
// vue-echarts v8 では echarts のレンダラー・チャート・コンポーネントを
// アプリ側で登録する必要がある（公式 README のサンプルを参照）
import { use } from 'echarts/core';
import type { EChartsType } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, CandlestickChart, LineChart, ScatterChart } from 'echarts/charts';
import { TooltipComponent, GridComponent, DataZoomComponent, TitleComponent } from 'echarts/components';
// 表示ウィンドウ（表示期間 / ローソク足本数）計算モジュール
import { DISPLAY_PRESETS, chartTitle, getDisplayRange } from '../utils/display';
// タートルズ型 (Donchian + ATR) 計算モジュール（ルックアヘッドなし: 前日までのデータのみ使用）
import { computePyramidTargets, computeTurtle, computeTurtlePlan, computeUnitShares } from '../utils/turtle';
import type { PyramidTargets, TurtleBar, TurtlePlan, TurtlePlanLevel } from '../utils/turtle';
// タートル戦略の銘柄ごとの保存状態（localStorage 永続化。Issue #53）
import {
  buildTurtleState,
  clearTurtleState,
  loadAllTurtleStates,
  normalizeTurtleSymbol,
  saveTurtleState,
  type TurtleState,
} from '../utils/turtleState';
import {
  SYMBOL_PATTERN,
  LIST_NAME_MAX_LENGTH,
  addFavoriteStock,
  createFavoriteList,
  deleteFavoriteList,
  favoriteErrorMessage,
  fetchFavoriteGroups,
  isValidListName,
  isValidSymbol,
  removeFavoriteStock,
  renameFavoriteList,
} from '../utils/favorites';
import type { FavoriteGroup } from '../utils/favorites';

use([CanvasRenderer, CandlestickChart, BarChart, LineChart, ScatterChart, TooltipComponent, GridComponent, DataZoomComponent, TitleComponent]);

interface StockRecord {
  id: number;
  symbol: string;
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

// 大きな数を K/M 単位でコンパクトに表示（例: 30000000 -> "30M"）。
// 出来高軸のラベルと tooltip の両方で使用する。
function formatCompact(value: number): string {
  if (value >= 1e6) return `${(value / 1e6).toFixed(1).replace(/\.0$/, '')}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1).replace(/\.0$/, '')}K`;
  return `${value}`;
}

const symbol = ref('AAPL');
// 銘柄名（Yahoo Finance、Issue #49）: 株価データ表示付近に示す
const stockName = ref('');
// Yahoo Finance 取得期間（yfinance の period 値）
const period = ref('1mo');
// シンボル入力の銘柄名取得デバウンス (Issue #49)
let metaTimer: ReturnType<typeof setTimeout> | null = null;
// =====================================================================
// お気に入り銘柄リスト (Issue #50)
// =====================================================================
// 全リスト（空リスト含む）と所属銘柄（バックエンド GET /api/favorites/、作成順）。
// 銘柄名はバックエンドが StockMeta と同期するので、ここでは表示のみ。
const favoriteGroups = ref<FavoriteGroup[]>([]);
// 現在選択中のリスト ID（null = なし。最後にリストを削除した直後など）
const activeListId = ref<number | null>(null);
// お気に入り・リスト操作の操作中フラグ（二重クリック防止）
const favoriteBusy = ref(false);
// お気に入り操作のメッセージ（エラー表示用）
const favoriteMessage = ref('');
// 現在選択中のリスト（未選択なら null）
const activeGroup = computed(
  () => favoriteGroups.value.find((g) => g.id === activeListId.value) ?? null,
);
// 現在入力のシンボルがアクティブリストに登録されているか（大文字・小文字を無視）
const isFavorite = computed(
  () =>
    activeGroup.value !== null &&
    activeGroup.value.stocks.some((f) => f.symbol === symbol.value.trim().toUpperCase()),
);
const data = ref<StockRecord[]>([]);
// 表示ウィンドウ: 表示期間プリセット（営業日換算、既定は 1 年分を表示）
const displayPeriod = ref('1y');
// 表示ウィンドウ: ローソク足本数指定（表示期間より優先。null / 空欄 = 期間に従う）
const displayCount = ref<number | string | null>(null);
// vue-echarts コンポーネント参照（dispatchAction でズームを操作するため）
const chartRef = ref<InstanceType<typeof VChart> | null>(null);
// チャート容器参照（固定情報パネルの position 基準）
const wrapperRef = ref<HTMLDivElement | null>(null);
// 固定情報パネルの要素参照（クランプ時にサイズを測定する）
const panelRef = ref<HTMLDivElement | null>(null);
// ブラウザ自動化での挙動確認のためチャート参照を公開（開発サーバーのみ、本番ビルドには含まれない）(Issue #36)
if (import.meta.env.DEV) {
  (window as Window & { __stockChartRef?: typeof chartRef }).__stockChartRef = chartRef;
}

// =====================================================================
// マウスホイール操作 (Issue #36): Ctrl+ホイール = ズーム / 通常ホイール = パン
// ECharts 内蔵の inside-dataZoom ではこの 2 つを分離できない（Ctrl+ホイールで
// ズームとスクロールが同時に発動するため）、内蔵のホイール処理は
// zoomOnMouseWheel / moveOnMouseWheel = false で無効化し、こちらで実装する。
// （ドラッグパンは内蔵の moveOnMouseMove を使い続ける）
// handler はチャート容器にキャプチャ位相で付け、そこでイベントを消費するため、
// 同じホイールイベントが ECharts 内部の roam にも渡らず二重適用されない。
// =====================================================================
const WHEEL_MIN_SPAN = 2; // dataZoom-inside の minSpan と一致させること
const WHEEL_STEP_PX = 120; // ホイール 1 ステップに相当する deltaY のピクセル数
const WHEEL_MAX_STEPS = 3; // 1 イベントで処理するステップ数の上限（高速スクロールの暴走防止）
const ZOOM_FACTOR_PER_STEP = 1.1; // ステップあたりのズーム係数（最大 1.1^3 ≒ 1.33）
const PAN_RATIO_PER_STEP = 0.05; // ステップあたりのパン量（表示幅の 5%）
const WHEEL_THROTTLE_MS = 100; // ECharts 内蔵 roam と同じ 100ms fixRate 絞り込み

type WheelGridRect = { x: number; y: number; width: number; height: number };

// vue-echarts のコンポーネント参照から ECharts インスタンスを取得（未初期化時 null）
function getChartInstance(): EChartsType | null {
  const chart = chartRef.value?.chart;
  // vue-echarts の型定義では chart が ShallowRef だが、アクセス時には既にアンラップされて
  // ECharts インスタンスそのものが返る
  return (chart as unknown as EChartsType | undefined) ?? null;
}

// 全グリッドの矩形（チャート未準備時は null）
function getGridRects(m: unknown): WheelGridRect[] | null {
  const getComponent = (
    m as {
      getComponent?: (type: string, index: number) => {
        coordinateSystem?: { getRect?: () => WheelGridRect };
      } | undefined;
    }
  )?.getComponent;
  if (typeof getComponent !== 'function') return null;
  const grids: WheelGridRect[] = [];
  for (let i = 0; ; i++) {
    const gridModel = getComponent.call(m, 'grid', i);
    const rect = gridModel?.coordinateSystem?.getRect?.();
    if (!gridModel || !rect) break;
    grids.push(rect);
  }
  return grids.length > 0 ? grids : null;
}

// 現在可視のローソク足が乗っている dataZoom (inside) の表示範囲 (percent) を取得
function getVisiblePercentRange(m: unknown): { start: number; end: number } {
  const dzModel = (
    m as {
      getComponent?: (type: string, index: number) => {
        get?: (key: string) => unknown;
      } | undefined;
    }
  )?.getComponent?.('dataZoom', 0);
  const start = dzModel?.get?.('start');
  const end = dzModel?.get?.('end');
  return typeof start === 'number' && typeof end === 'number' ? { start, end } : { start: 0, end: 100 };
}

// 新規表示範囲を適用（dispatchAction dataZoom。link された全 dataZoom がまとめて更新される）
function applyWheelRange(start: number, end: number) {
  const inst = getChartInstance();
  if (!inst || inst.isDisposed()) return;
  inst.dispatchAction({
    type: 'dataZoom',
    start,
    end,
    // ECharts 内蔵 roam と同じアニメーションパラメータ
    animation: { easing: 'cubicOut', duration: 100 },
  });
}

let wheelThrottleTimer: ReturnType<typeof setTimeout> | null = null;
let wheelNextAllowedAt = 0;

// fixRate 絞り込み（ECharts 内蔵 roam と同じ挙動）: 100ms ごとに最大 1 回。
// 間に溜まったイベントは最後の範囲のみが有効。
function throttledApplyRange(start: number, end: number) {
  const now = Date.now();
  const delay = Math.max(0, wheelNextAllowedAt - now);
  if (wheelThrottleTimer !== null) {
    // 未適用の古い範囲を破棄（最新の範囲を優先する fixRate の语义）
    clearTimeout(wheelThrottleTimer);
    wheelThrottleTimer = null;
  }
  wheelNextAllowedAt = now + WHEEL_THROTTLE_MS;
  if (delay === 0) {
    applyWheelRange(start, end);
  } else {
    wheelThrottleTimer = setTimeout(() => {
      wheelThrottleTimer = null;
      applyWheelRange(start, end);
    }, delay);
  }
}

function onChartWheel(e: WheelEvent) {
  const inst = getChartInstance();
  const rootEl = (chartRef.value?.root as unknown as HTMLElement | undefined) ?? null;
  if (!inst || !rootEl) return;
  // ヒット判定: プロット領域内（ローソク足グリッドの x 範囲 × 全グリッドの y 範囲）でのみ反応し、
  // 外側ではイベントを通す（ページが通常通りスクロールできる）
  // getModel は型定義上 private なので、必要な部分だけ拾う型にキャストする
  const gm = (inst as unknown as { getModel: () => unknown }).getModel();
  const grids = getGridRects(gm);
  if (!grids || grids[0].width <= 0) return;
  const box = rootEl.getBoundingClientRect();
  const px = e.clientX - box.left;
  const py = e.clientY - box.top;
  const gridX0 = grids[0].x;
  const gridX1 = gridX0 + grids[0].width;
  let gridTop = Infinity;
  let gridBottom = -Infinity;
  for (const g of grids) {
    gridTop = Math.min(gridTop, g.y);
    gridBottom = Math.max(gridBottom, g.y + g.height);
  }
  if (px < gridX0 || px > gridX1 || py < gridTop || py > gridBottom) return;
  // イベントを消費: ページスクロール抑制 + ECharts 内部 roam での二重処理防止
  e.preventDefault();
  e.stopPropagation();

  const { start, end } = getVisiblePercentRange(gm);
  const span = Math.min(Math.max(end - start, WHEEL_MIN_SPAN), 100);

  // ホイール量をステップ化（deltaMode=1 は行単位のため 40px/行 に換算）
  const rawDelta = e.deltaY === 0 ? e.deltaX : e.deltaY;
  if (rawDelta === 0) return;
  const delta = e.deltaMode === 1 ? rawDelta * 40 : rawDelta;
  const steps = Math.min(WHEEL_MAX_STEPS, Math.max(1, Math.round(Math.abs(delta) / WHEEL_STEP_PX)));

  if (e.ctrlKey || e.metaKey) {
    // ズーム（カーソル位置のデータを固定して縮放）: スクロール下 = ズームイン / 上 = ズームアウト
    const factor = Math.pow(ZOOM_FACTOR_PER_STEP, steps);
    const newSpan = Math.min(Math.max(span * (delta > 0 ? 1 / factor : factor), WHEEL_MIN_SPAN), 100);
    // カーソル位置に対応する percent
    const cursor = ((px - gridX0) / grids[0].width) * span + start;
    const ratio = newSpan / span;
    const s = Math.min(Math.max(cursor - (cursor - start) * ratio, 0), 100 - newSpan);
    throttledApplyRange(s, s + newSpan);
  } else {
    // パン: ホイール下 = 新データ側へ (start 増) / ホイール上 = 旧データ側へ (start 減)
    // （ECharts 内蔵 moveOnMouseWheel と同じ方向: 上 = 旧データ側へ移動）
    const shift = span * PAN_RATIO_PER_STEP * steps * (delta > 0 ? 1 : -1);
    const s = Math.min(Math.max(start + shift, 0), 100 - span);
    throttledApplyRange(s, s + span);
  }
}

// カスタム wheel handler の install / 外しをチャート実例のライフサイクルに合わせて行う
// （v-chart はシンボル切替・データ消去時の再マウントで容器も実例も入れ替わるため）
let removeWheelListener: (() => void) | null = null;
// 'updateAxisPointer' イベントの購読解除関数（固定情報パネル用）
let removeAxisPointerHandler: (() => void) | null = null;
// チャート容器の ResizeObserver 破棄関数（情報パネルの位置を再クランプする）
let removePanelResizeObserver: (() => void) | null = null;

// 'updateAxisPointer' イベントのハンドラ: ホバー中のローソク足の dataIndex（生インデックス）で
// 固定情報パネルを更新する。グリッド外など dataIndex が無い場合は更新せず直近の値を保持する
function onAxisPointerUpdate(...args: unknown[]) {
  const params = args[0] as { dataIndex?: number } | undefined;
  const i = params?.dataIndex;
  if (typeof i === 'number' && i >= 0 && i < data.value.length) {
    hoverIndex.value = i;
  }
}

watch(
  () => chartRef.value?.chart,
  (chart) => {
    removeWheelListener?.();
    removeWheelListener = null;
    removeAxisPointerHandler?.();
    removeAxisPointerHandler = null;
    removePanelResizeObserver?.();
    removePanelResizeObserver = null;
    if (!chart) return;
    const rootEl = (chartRef.value?.root as unknown as HTMLElement | undefined) ?? null;
    if (!rootEl) return;
    rootEl.addEventListener('wheel', onChartWheel, { passive: false, capture: true });
    removeWheelListener = () => {
      rootEl.removeEventListener('wheel', onChartWheel, { capture: true });
    };
    // 固定情報パネル: 軸カーソルイベントに購読する。
    // ECharts はアクション由来のイベント名を小文字化して発火するため
    // （registerAction 内で createEventType が toLowerCase）、実際には発火する
    // 小文字版と、将来のバージョンのために大文字版の両方に購読する。
    // payload は axisTrigger の戻り値で、ホバー中のローソク足の生 dataIndex を持つ
    // （グリッド外 = leave の時は dataIndex が無い）
    const inst = chart as unknown as EChartsType;
    for (const name of ['updateAxisPointer', 'updateaxispointer']) {
      inst.on(name, onAxisPointerUpdate);
    }
    removeAxisPointerHandler = () => {
      for (const name of ['updateAxisPointer', 'updateaxispointer']) {
        inst.off(name, onAxisPointerUpdate);
      }
    };
    // 固定情報パネル: 容器サイズが変わった時（タートル表示の切替 / ウィンドウリサイズ）に
    // パネル位置を再クランプする
    const wrapperEl = wrapperRef.value;
    if (wrapperEl && typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(() => {
        clampPanelPos();
      });
      ro.observe(wrapperEl);
      removePanelResizeObserver = () => {
        ro.disconnect();
      };
    }
  },
);
onBeforeUnmount(() => {
  removeWheelListener?.();
  removeWheelListener = null;
  removeAxisPointerHandler?.();
  removeAxisPointerHandler = null;
  removePanelResizeObserver?.();
  removePanelResizeObserver = null;
  if (wheelThrottleTimer !== null) clearTimeout(wheelThrottleTimer);
  if (metaTimer !== null) clearTimeout(metaTimer);
});

const maDays = ref(5);
const movingAverage = ref<number | null>(null);
const fetching = ref(false);
const yahooMessage = ref('');
const yahooError = ref(false);

// --- タートル戦略 (Donchian Channel + ATR) の状態 (Issue #53: 既定値なし・保存状態のみ使用) ---
const turtleEnabled = ref(true);
const atrPeriod = ref(20); // N (ATR) の期間: 14 / 20
const accountValue = ref<number | string | null>(null); // 口座資金（保存状態のない銘柄は空欄）
const turtleBuyPrice = ref<number | string | null>(null); // 買値（保存状態のない銘柄は空欄）
// ブレイク日 (BUY シグナル日。保存状態のない銘柄は空欄)
const turtleBreakoutDate = ref<string | null>(null);
// --- タートル戦略の銘柄ごとの保存状態 (Issue #53) ---
const turtleStates = ref<Record<string, TurtleState>>(loadAllTurtleStates());
const turtleStateMessage = ref('');

// Donchian バンド / ATR / BUY・EXIT シグナルの計算結果
// （ルックアヘッド回避: バンドと判定は前日までのデータのみ参照）
const turtle = computed<TurtleBar[]>(() =>
  computeTurtle(data.value, { atrPeriod: atrPeriod.value }),
);
// 直近の N (ATR): ATR が計算できる最新の日の値
const latestAtr = computed<number | null>(() => {
  const rows = turtle.value;
  for (let i = rows.length - 1; i >= 0; i--) {
    const v = rows[i].atr;
    if (v !== null) return v;
  }
  return null;
});
// 口座資金の数値形（未指定 / 数値でなければ null）
const accountValueNumber = computed<number | null>(() => {
  const v = accountValue.value;
  if (v === null || v === '') return null;
  const num = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(num) ? num : null;
});
// 買値の数値形（未指定 / 数値でなければ null）
const turtleBuyPriceNumber = computed<number | null>(() => {
  const v = turtleBuyPrice.value;
  if (v === null || v === '') return null;
  const num = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(num) ? num : null;
});
// 現在表示中のシンボル（大文字正規化済み）
const currentTurtleSymbol = computed(() => normalizeTurtleSymbol(symbol.value));
// 現在表示中の銘柄の保存済み状態（未保存なら undefined）
const savedTurtleState = computed<TurtleState | undefined>(() => turtleStates.value[currentTurtleSymbol.value]);
const hasSavedTurtleState = computed(() => savedTurtleState.value !== undefined);
// ピラミッディング目標 (+0.5N / +1.0N / +1.5N) とストップロス (-2N)
const targets = computed<PyramidTargets | null>(() => {
  const price = turtleBuyPriceNumber.value;
  const atr = latestAtr.value;
  if (price === null || price <= 0 || atr === null || atr <= 0) return null;
  return computePyramidTargets(price, atr);
});
// 1 ユニットの推奨購入株数: floor((口座資金 * 0.01) / N)
// （株式は 1 ポイントあたり価値 = 1 固定のため買値は掛けない）
const unitShares = computed<number>(() => {
  const av = accountValueNumber.value;
  const atr = latestAtr.value;
  if (av === null || atr === null || atr <= 0) return 0;
  return computeUnitShares(av, atr);
});
// ブレイク日の候補 (BUY シグナルが出た日付の昇順リスト)
const buySignalDates = computed<string[]>(() =>
  turtle.value.filter(r => r.buy).map(r => r.date),
);
// タートル計画: ブレイク日以降の買い増し (P2/P3/P4) と EXIT を機械的にシミュレートする
// （毎日その日の N で目標・ストップを再計算。詳細は turtle.ts の computeTurtlePlan 参照）
const turtlePlan = computed<TurtlePlan | null>(() => {
  const d = turtleBreakoutDate.value;
  const price = turtleBuyPriceNumber.value;
  if (!d || price === null || price <= 0) return null;
  if (!buySignalDates.value.includes(d)) return null;
  return computeTurtlePlan(turtle.value, d, price);
});
// 買い増し計画の行表示 (到達: 日付・目標・終値 / 未到達: 「未到達」)
function fmtPlanLevel(lv: TurtlePlanLevel): string {
  if (lv.date === null) return '未到達';
  return `${lv.date} (目標 ${fmtPrice(lv.price)} / 終値 ${fmtPrice(lv.hitClose)})`;
}
// EXIT 計画の行表示 (到達: 日付・理由・終値 / 未到達: 「未到達」)
function fmtPlanExit(plan: TurtlePlan): string {
  if (plan.exit.date === null) return '未到達';
  const reason =
    plan.exit.reason === 'stop'
      ? 'ストップロス (終値 ≤ 最新エントリー−2N)'
      : 'DC10 下抜け (終値 < DC10)';
  return `${plan.exit.date} ${reason} (終値 ${fmtPrice(plan.exit.close)})`;
}
// ブレイク日選択で買値が空欄のときはその日終値を自動設定（既に入力 / 復元済みの場合は上書きしない）
watch(turtleBreakoutDate, (d) => {
  const bp = turtleBuyPrice.value;
  if (d === null || (bp !== null && bp !== '')) return;
  const row = turtle.value.find(r => r.date === d);
  if (row) turtleBuyPrice.value = Number(row.close);
});

// =====================================================================
// タートル戦略の銘柄ごとの保存状態 (Issue #53)
// =====================================================================

// 指定銘柄の保存状態を復元する（保存状態のない銘柄は全入力を空欄に戻す）
function applyTurtleState(sym: string): void {
  const st = turtleStates.value[normalizeTurtleSymbol(sym)];
  if (st) {
    accountValue.value = st.accountValue;
    atrPeriod.value = st.atrPeriod;
    turtleBreakoutDate.value = st.breakoutDate;
    turtleBuyPrice.value = st.buyPrice;
  } else {
    accountValue.value = null;
    atrPeriod.value = 20;
    turtleBreakoutDate.value = null;
    turtleBuyPrice.value = null;
  }
}

// 現在の入力を現在の銘柄の保存状態として上書き保存する
function saveCurrentTurtleState(): void {
  turtleStateMessage.value = '';
  const sym = currentTurtleSymbol.value;
  if (!isValidSymbol(sym)) {
    turtleStateMessage.value = '有効な銘柄を指定してください';
    return;
  }
  const result = buildTurtleState({
    accountValue: accountValue.value,
    breakoutDate: turtleBreakoutDate.value,
    buyPrice: turtleBuyPrice.value,
    atrPeriod: atrPeriod.value,
  });
  if (!result.ok) {
    turtleStateMessage.value = result.error;
    return;
  }
  try {
    saveTurtleState(sym, result.state);
  } catch (e) {
    console.error('タートル戦略状態の保存に失敗しました:', e);
    turtleStateMessage.value = '状態の保存に失敗しました（ブラウザストレージエラー）';
    return;
  }
  turtleStates.value = { ...turtleStates.value, [sym]: result.state };
  turtleStateMessage.value = `${sym} の状態を保存しました`;
}

// 現在の銘柄の保存状態を削除し、入力を空欄に戻す
function releaseCurrentTurtleState(): void {
  turtleStateMessage.value = '';
  const sym = currentTurtleSymbol.value;
  try {
    clearTurtleState(sym);
  } catch (e) {
    console.error('タートル戦略状態の削除に失敗しました:', e);
    turtleStateMessage.value = '状態の削除に失敗しました（ブラウザストレージエラー）';
    return;
  }
  const next = { ...turtleStates.value };
  delete next[sym];
  turtleStates.value = next;
  applyTurtleState(sym); // 保存状態がなくなったため全入力を空欄に戻す
  turtleStateMessage.value = `${sym} の状態を削除しました`;
}

// =====================================================================
// 固定情報パネル（ホバー中のローソク足の正確な価格・出来高を表示）
// - 標準 tooltip の内容表示は tooltip.showContent = false で無効化し、
//   クロスヘア（軸カーソル）はそのまま維持する
// - ECharts の 'updateAxisPointer' イベントの dataIndex（生インデックス）を
//   受け取って data.value 配列の該当レコードを表示する
// - ポインタがグリッド外に出ると payload は空になるため、その時は直近の
//   値を保持する（「固定」パネルの挙動。データ更新時にのみリセットする）
// - タートル戦略数値エリア (Issue #40): 同一パネル内に現在値テーブルと
//   区切りの入った独立セクションで、ホバー中のインデックス時点の
//   Donchian / ATR / シグナルを表示する。turtleEnabled に連動して
//   表示・非表示になるだけで、dataIndex マッピング・グリッド外出時の
//   値保持・データ取得時のリセットは現在値パネルと共通のロジックをそのまま
//   利用するため、スクリプト側の追加ロジックは不要
// =====================================================================
// ホバー中のローソク足のインデックス（data.value 配列の生インデックス、null = まだホバーしていない）
const hoverIndex = ref<number | null>(null);
// 情報パネルの位置（チャート容器内の左上座標。既定は左上隅）
const panelPos = ref({ x: 10, y: 10 });

// ホバー中のローソク足（範囲外なら null。例: データ更新直後の古いインデックス）
const hoverRecord = computed<StockRecord | null>(() => {
  const i = hoverIndex.value;
  if (i === null || i < 0 || i >= data.value.length) return null;
  return data.value[i];
});
// 同じローソク足のタートル行（ATR は N 日分データが揃うまで null）
const hoverTurtle = computed<TurtleBar | null>(() => {
  const i = hoverIndex.value;
  if (i === null || i < 0 || i >= turtle.value.length) return null;
  return turtle.value[i];
});
// 前日比（前日終値に対する終値の差と変化率）
const hoverChange = computed<{ diff: number; pct: number } | null>(() => {
  const i = hoverIndex.value;
  if (i === null || i < 1) return null;
  const cur = data.value[i];
  const prev = data.value[i - 1];
  if (cur.close == null || prev.close == null || prev.close === 0) return null;
  const diff = cur.close - prev.close;
  return { diff, pct: (diff / prev.close) * 100 };
});

// 情報パネルの位置スタイル
const panelStyle = computed(() => ({
  left: `${panelPos.value.x}px`,
  top: `${panelPos.value.y}px`,
}));

// --- 値の書式化（K/M 省略なしの正確な値を表示） ---
// 価格系: 桁区切り + 小数 2〜4 桁
function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return v.toLocaleString('ja-JP', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}
// 出来高: 桁区切りの整数（例: 53,456,789）
function fmtVolume(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Math.round(v).toLocaleString('ja-JP');
}

// --- パネルのドラッグ（ドラッグバーのみポインターを捕捉する） ---
let panelDragStart: { pointerX: number; pointerY: number; startX: number; startY: number } | null = null;

// パネル位置をチャート容器の範囲内に収める
function clampPanelPos() {
  const wrapper = wrapperRef.value;
  const panel = panelRef.value;
  if (!wrapper || !panel) return;
  const maxX = Math.max(0, wrapper.clientWidth - panel.offsetWidth);
  const maxY = Math.max(0, wrapper.clientHeight - panel.offsetHeight);
  panelPos.value = {
    x: Math.min(Math.max(panelPos.value.x, 0), maxX),
    y: Math.min(Math.max(panelPos.value.y, 0), maxY),
  };
}

function onPanelPointerDown(e: PointerEvent) {
  if (e.button !== 0) return;
  // ポインターをキャプチャすると、バーの外に出ても move/up を確実に受信できる
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  panelDragStart = {
    pointerX: e.clientX,
    pointerY: e.clientY,
    startX: panelPos.value.x,
    startY: panelPos.value.y,
  };
  e.preventDefault();
}

function onPanelPointerMove(e: PointerEvent) {
  if (!panelDragStart) return;
  const wrapper = wrapperRef.value;
  const panel = panelRef.value;
  if (!wrapper || !panel) return;
  // 移動分を適用し、容器の範囲内にクランプする
  const maxX = Math.max(0, wrapper.clientWidth - panel.offsetWidth);
  const maxY = Math.max(0, wrapper.clientHeight - panel.offsetHeight);
  panelPos.value = {
    x: Math.min(Math.max(panelDragStart.startX + (e.clientX - panelDragStart.pointerX), 0), maxX),
    y: Math.min(Math.max(panelDragStart.startY + (e.clientY - panelDragStart.pointerY), 0), maxY),
  };
}

function onPanelPointerUp(e: PointerEvent) {
  if (!panelDragStart) return;
  panelDragStart = null;
  const el = e.currentTarget as HTMLElement | null;
  if (el && el.hasPointerCapture?.(e.pointerId)) {
    el.releasePointerCapture(e.pointerId);
  }
}

// チャート設定: ローソク足 + 出来高 +（タートル表示ON時）Donchian バンド / シグナル / ATR パネル。
// computed 化により、データ・ATR 期間・口座資金・買値の変更で自動再描画される。
const chartOptions = computed<EChartsOption>(() => {
  // チャートには取得済みデータすべてを入れる (Issue #36)。
  // 表示期間 / 本数は初期表示範囲（dataZoom）だけを制御し、
  // 表示ウィンドウより古いデータはパン（ホイール / ドラッグ / スライダー）で見られる。
  const records = data.value;
  if (records.length === 0) return {};
  const dates = records.map(d => d.date);
  const on = turtleEnabled.value;
  const rows = turtle.value;
  const tg = on ? targets.value : null;
  // dataZoom が操作する X 軸インデックス（タートル表示ON時は ATR パネルの軸も含む）
  const xAxisIndexes = on ? [0, 1, 2] : [0, 1];

  // --- 系列の定義 ---
  const series: SeriesOption[] = [
    {
      name: symbol.value,
      type: 'candlestick',
      xAxisIndex: 0,
      yAxisIndex: 0,
      // ECharts のローソク足データ形式: [open, close, low, high]
      data: records.map(d => [
        Number(d.open ?? d.close),
        Number(d.close),
        Number(d.low ?? d.close),
        Number(d.high ?? d.close),
      ]),
      // 日本式: 陽線（上昇）= 赤、陰線（下落）= 緑
      itemStyle: {
        color: '#e2534f',
        color0: '#3ba272',
        borderColor: '#e2534f',
        borderColor0: '#3ba272',
      },
      // ピラミッディング目標 (+0.5N / +1.0N / +1.5N) とストップロス (-2N) のガイドライン
      markLine: tg
        ? {
            silent: true,
            symbol: 'none',
            data: [
              {
                yAxis: tg.target1,
                lineStyle: { type: 'dashed', color: '#9c36b5' },
                label: { position: 'insideEndTop', formatter: 'ピラミッド2 (+0.5N)', color: '#9c36b5' },
              },
              {
                yAxis: tg.target2,
                lineStyle: { type: 'dashed', color: '#9c36b5' },
                label: { position: 'insideEndTop', formatter: 'ピラミッド3 (+1.0N)', color: '#9c36b5' },
              },
              {
                yAxis: tg.target3,
                lineStyle: { type: 'dashed', color: '#9c36b5' },
                label: { position: 'insideEndTop', formatter: 'ピラミッド4 (+1.5N)', color: '#9c36b5' },
              },
              {
                yAxis: tg.stop,
                lineStyle: { type: 'dashed', color: '#c0392b' },
                label: { position: 'insideEndTop', formatter: 'ストップ (-2N)', color: '#c0392b' },
              },
            ],
          }
        : undefined,
    },
    {
      name: '出来高',
      type: 'bar',
      xAxisIndex: 1,
      yAxisIndex: 1,
      // ローソク足と同様に陽線=赤 / 陰線=緑で色分け（volume が null の日はバー非表示）
      data: records.map(d => {
        const bullish = Number(d.close) >= Number(d.open ?? d.close);
        return {
          value: d.volume,
          itemStyle: { color: bullish ? '#e2534f' : '#3ba272' },
        };
      }),
    },
  ];

  // --- BUY/EXIT マーカー配置パラメータ (Issue #46) ---
  // マーカーはローソク足の高値 / 安値から MARK_GAP_PX ピクセル上 / 下に配置する。
  // （三角形 symbolSize 12 の半高さ 6px に 4px の空きを確保）
  // y 軸 min/max 関数（下記）がデータ範囲の上下に PAD_TOP_PX / PAD_BOT_PX
  // ピクセルの余白を常に確保するため、マーカーがグリッド端で
  // 切れたりローソク足と重なったりしない。
  const PRICE_GRID_PX = 640 * 0.45; // 上段グリッド高さ（チャート 640px × 高さ 45%）
  const PAD_TOP_PX = 20; // グリッド上部: BUY マーカー (△) の表示余白
  const PAD_BOT_PX = 20; // グリッド下部: EXIT マーカー (▽) の表示余白
  const MARK_GAP_PX = 10; // マーカー点とローソク足高値 / 安値の間隔 (px)
  const axisBound = (v: { min: number; max: number }, isMax: boolean): number => {
    const span = v.max - v.min;
    if (!(span > 0)) return isMax ? v.max * 1.001 : v.min * 0.999;
    const pp = span / Math.max(PRICE_GRID_PX - PAD_TOP_PX - PAD_BOT_PX, 1);
    return isMax ? v.max + PAD_TOP_PX * pp : v.min - PAD_BOT_PX * pp;
  };

  // タートル表示ON時の追加系列
  if (on) {
    // --- BUY/EXIT マーカー配置用の価格レンジ (Issue #46) ---
    // 全データ（ローソク足 + Donchian バンド + markLine 値）の価格レンジ。
    // 固定ピクセル間隔 MARK_GAP_PX を価格に変換するためにのみ使用する。
    let priceMin = Infinity;
    let priceMax = -Infinity;
    const widenRange = (v: number | null) => {
      if (v === null || !Number.isFinite(v)) return;
      if (v < priceMin) priceMin = v;
      if (v > priceMax) priceMax = v;
    };
    for (const d of records) {
      widenRange(Number(d.low ?? d.close));
      widenRange(Number(d.high ?? d.close));
    }
    for (const r of rows) {
      widenRange(r.donchianUpper);
      widenRange(r.donchianLower);
    }
    // ピラミッド目標 / ストップの markLine はローソク足レンジの外側に伸び得る
    if (tg) {
      widenRange(tg.target1);
      widenRange(tg.target2);
      widenRange(tg.target3);
      widenRange(tg.stop);
    }
    const priceSpan = priceMax - priceMin;
    // 価格パネルの 1px あたりの価格量（パディング分を差し引いた有効高さで換算）
    const pxPerPoint =
      priceSpan > 0 ? priceSpan / Math.max(PRICE_GRID_PX - PAD_TOP_PX - PAD_BOT_PX, 1) : 0;
    const markerGapPrice = MARK_GAP_PX * pxPerPoint;

    series.push(
      {
        name: 'DC20 (エントリーライン)',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        // 過去 20 日間の最高値（前日までのデータのみ。当日は除外 = ルックアヘッドなし）
        data: rows.map(r => r.donchianUpper),
        symbol: 'none',
        showSymbol: false,
        connectNulls: false,
        lineStyle: { type: 'dashed', width: 1.5, color: '#e67e22' },
        itemStyle: { color: '#e67e22' },
      },
      {
        name: 'DC10 (手仕舞いライン)',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        // 過去 10 日間の最安値（前日までのデータのみ）
        data: rows.map(r => r.donchianLower),
        symbol: 'none',
        showSymbol: false,
        connectNulls: false,
        lineStyle: { type: 'dashed', width: 1.5, color: '#1971c2' },
        itemStyle: { color: '#1971c2' },
      },
      {
        // BUY マーカー: 終値がエントリーラインを上抜けした日（日本式: 赤）
        // ローソク足の高値より MARK_GAP_PX ピクセル上側に配置 (Issue #46)
        name: 'BUY',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: rows.map((r, i) => {
          if (!r.buy) return null;
          const high = Number(records[i].high ?? records[i].close);
          return high + markerGapPrice;
        }),
        symbol: 'triangle',
        symbolSize: 12,
        itemStyle: { color: '#e2534f' },
      },
      {
        // EXIT マーカー: 手仕舞いライン下抜けまたはトレーリングストップ到達の日（日本式: 緑）
        // ローソク足の安値より MARK_GAP_PX ピクセル下側に配置 (Issue #46)
        name: 'EXIT',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: rows.map((r, i) => {
          if (!r.exit) return null;
          const low = Number(records[i].low ?? records[i].close);
          return low - markerGapPrice;
        }),
        symbol: 'triangle',
        symbolRotate: 180, // 下向き三角形
        symbolSize: 12,
        itemStyle: { color: '#3ba272' },
      },
      {
        // N (ATR): True Range の単純移動平均（サブパネルに表示）
        name: 'N (ATR)',
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: rows.map(r => r.atr),
        symbol: 'none',
        showSymbol: false,
        connectNulls: false,
        lineStyle: { type: 'solid', width: 1.5, color: '#8e44ad' },
        itemStyle: { color: '#8e44ad' },
      },
    );

    // 買い増し計画 (P2/P3/P4) と計画 EXIT のマーカー (Issue #44)。
    // 指標シグナル (BUY/EXIT マーカー) とは別物で、計画上の到達日を示す。
    const plan = turtlePlan.value;
    if (plan) {
      const buyAdds = plan.levels.filter(
        (lv): lv is TurtlePlanLevel & { date: string; hitClose: number } =>
          lv.date !== null && lv.hitClose !== null,
      );
      if (buyAdds.length > 0) {
        series.push({
          // 買い増し: 終値が 直前ユニットの目標ライン + 0.5 × N (当日 N で再計算 / 到達後は到達時の価格でライン固定) に到達した日
          name: '買い増し 2/3/4',
          type: 'scatter',
          xAxisIndex: 0,
          yAxisIndex: 0,
          symbol: 'diamond',
          symbolSize: 10,
          itemStyle: { color: '#9c36b5' },
          data: buyAdds.map(lv => ({
            value: [lv.date, lv.hitClose],
            label: {
              show: true,
              position: 'top',
              formatter: `買い増し${lv.level}`,
              color: '#9c36b5',
              fontSize: 10,
            },
          })),
        });
      }
      if (plan.exit.date !== null && plan.exit.close !== null) {
        series.push({
          // 計画 EXIT: 終値 ≤ 最新エントリー−2N (ストップ) または 終値 < DC10 の初回到達日
          name: '計画 EXIT',
          type: 'scatter',
          xAxisIndex: 0,
          yAxisIndex: 0,
          symbol: 'rect',
          symbolSize: 9,
          itemStyle: { color: '#3ba272' },
          data: [
            {
              value: [plan.exit.date, plan.exit.close],
              label: {
                show: true,
                position: 'bottom',
                formatter: '計画 EXIT',
                color: '#3ba272',
                fontSize: 10,
              },
            },
          ],
        });
      }
    }
  }

  return {
    // 銘柄名タイトル (Issue #49): チャート左上に表示（grid の top 30px 余白内）
    title: {
      text: chartTitle(symbol.value, stockName.value),
      left: 70,
      top: 5,
      textStyle: { fontSize: 14, fontWeight: 'bold' },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      // 標準 tooltip の内容表示を無効化（クロスヘアは維持）—
      // ホバー中のローソク足の正確な価格・出来高は固定情報パネルに表示する
      showContent: false,
    },
    // 各グリッドの軸カーソルを同期する（tooltip は全系列共通で表示）
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    // dataZoom (Issue #36): inside = ドラッグでパン（ホイール操作は後述のカスタム handler が担当）、
    // slider = 下部スライダー（可視範囲の表示と直接操作）
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: xAxisIndexes,
        // Ctrl+ホイール = ズーム / 通常ホイール = パンは下のカスタム handler で実現するため、
        // ECharts 内蔵のホイール処理は無効化（内蔵では両方を分離できない:
        // Ctrl+ホイールでズームとスクロールが同時に発動してしまう）
        zoomOnMouseWheel: false,
        moveOnMouseWheel: false,
        moveOnMouseMove: true, // ドラッグ = パン
        minSpan: 2, // 最小表示幅（ウィンドウの 2%。単一ローソクへの退化を防ぐ）
      },
      {
        type: 'slider',
        xAxisIndex: xAxisIndexes,
        bottom: 5,
        height: 25,
        showDetail: false,
        minSpan: 2, // 最小表示幅（inside と同一。ハンドルを同一点に寄せて単一ローソク化するのを防ぐ）
      },
    ],
    // ECharts 6 以降: outerBoundsMode のデフォルト 'auto' では各 grid が自身の軸ラベル幅に応じて
    // 独立してプロット領域を縮めるため、3 パネルの水平位置がズレる（Issue #59）。
    // 'none' は left/right がプロット領域を正確に定義する ECharts 5 時代の挙動。
    grid: on
      ? [
          { left: 70, right: 20, top: 30, height: '45%', outerBoundsMode: 'none' },      // 上段: ローソク足
          { left: 70, right: 20, top: '58%', height: '14%', outerBoundsMode: 'none' },   // 中段: 出来高
          { left: 70, right: 20, bottom: 45, height: '12%', outerBoundsMode: 'none' },   // 下段: ATR（bottom 45 = 下部スライダー 0〜30px を避ける）
        ]
      : [
          { left: 70, right: 20, top: 30, height: '55%', outerBoundsMode: 'none' },      // 上段: ローソク足
          { left: 70, right: 20, bottom: 50, height: '18%', outerBoundsMode: 'none' },   // 下段: 出来高
        ],
    xAxis: on
      ? [
          { type: 'category', data: dates, gridIndex: 0 },
          { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } },
          { type: 'category', data: dates, gridIndex: 2, axisLabel: { show: false } },
        ]
      : [
          { type: 'category', data: dates, gridIndex: 0 },
          {
            type: 'category',
            data: dates,
            gridIndex: 1,
            axisLabel: { show: false }, // 下段チャートの日付ラベルは非表示（上段に表示済み）
          },
        ],
    yAxis: on
      ? [
          {
            type: 'value',
            gridIndex: 0,
            // BUY/EXIT マーカー + 文字ラベル分を固定ピクセルで確保 (Issue #46)。
            // 関数形のため dataZoom が可視ウィンドウを変えても再評価され、
            // 可視ローソク足への自動フィット（スケール変化）は維持される。
            min: (v: { min: number; max: number }) => axisBound(v, false),
            max: (v: { min: number; max: number }) => axisBound(v, true),
          },
          {
            type: 'value',
            gridIndex: 1,
            splitNumber: 2,
            axisLabel: {
              // 大きな数を K/M 単位でコンパクトに表示（tooltip と共通の書式）
              formatter: (value: number) => formatCompact(value),
            },
          },
          { type: 'value', scale: true, gridIndex: 2, splitNumber: 2 },
        ]
      : [
          { type: 'value', scale: true, gridIndex: 0 },
          {
            type: 'value',
            gridIndex: 1,
            splitNumber: 2,
            axisLabel: {
              // 大きな数を K/M 単位でコンパクトに表示（tooltip と共通の書式）
              formatter: (value: number) => formatCompact(value),
            },
          },
        ],
    series,
  };
});

async function fetchStockData() {
  try {
    const res = await axios.get(`/api/stocks/${symbol.value.trim()}`);
    // 日付昇順（古い順）でチャートに表示する
    const records = (res.data as StockRecord[]).sort((a, b) => a.date.localeCompare(b.date));
    data.value = records;
  } catch (e) {
    console.error('データ取得エラー:', e);
  }
}

// 銘柄名を取得 (Issue #49): バックエンド /api/stocks/<symbol>/meta/ 経由
// （取得不能の場合は空名称として扱い、表示側では穏当に非表示にする）
async function fetchStockMeta() {
  const target = symbol.value.trim().toUpperCase();
  if (!SYMBOL_PATTERN.test(target)) {
    stockName.value = '';
    return;
  }
  try {
    const res = await axios.get(`/api/stocks/${target}/meta/`);
    // 応答到着までにシンボルが変更された場合は古い結果を捨てる（古い名称を保持しない）
    if (symbol.value.trim().toUpperCase() !== target) return;
    stockName.value = res.data.name ?? '';
  } catch (e) {
    console.error('銘柄名取得エラー:', e);
    if (symbol.value.trim().toUpperCase() === target) stockName.value = '';
  }
}

// =====================================================================
// お気に入り銘柄リスト (Issue #50): バックエンド /api/favorites/・/api/favorite-lists/ 経由
// =====================================================================

// バックエンドエラーからステータス・detail を取り出す
function apiError(e: unknown): { status?: number; detail?: string } {
  const response = (e as { response?: { status?: number; data?: { detail?: string } } })
    ?.response;
  return { status: response?.status, detail: response?.data?.detail };
}

// リスト操作（作成・名前変更・削除）のエラーメッセージ
function listErrorMessage(e: unknown): string {
  const { status, detail } = apiError(e);
  if (status === 409) return detail ? `作成できません: ${detail}` : '同じ名前のリストが既に存在します';
  if (detail) return `リスト操作に失敗しました: ${detail}`;
  if (status !== undefined) return `リスト操作に失敗しました（${status}）`;
  return 'リスト操作に失敗しました（通信エラー）';
}

// 全リスト（空リスト含む）・所属銘柄をバックエンドから再取得する。
// 銘柄名の同期もここで取り込む。選択中のリストが削除された場合は先頭を選択し直す。
async function fetchFavorites() {
  try {
    favoriteGroups.value = await fetchFavoriteGroups();
    if (!favoriteGroups.value.some((g) => g.id === activeListId.value)) {
      activeListId.value = favoriteGroups.value[0]?.id ?? null;
    }
  } catch (e) {
    console.error('お気に入り取得エラー:', e);
  }
}

// 現在入力のシンボルをアクティブリストに追加する（POST /api/favorites/）
async function addFavorite() {
  const target = symbol.value.trim().toUpperCase();
  if (!isValidSymbol(target)) {
    favoriteMessage.value = 'シンボル形式が不正です（英大文字・数字、最大 10 文字）';
    return;
  }
  if (favoriteBusy.value) return;
  if (activeListId.value === null) {
    favoriteMessage.value = 'リストが未選択です。リストを作成または選択してください。';
    return;
  }
  favoriteBusy.value = true;
  favoriteMessage.value = '';
  try {
    await addFavoriteStock(activeListId.value, target);
    await fetchFavorites();
  } catch (e) {
    const { status, detail } = apiError(e);
    favoriteMessage.value = favoriteErrorMessage(status, detail);
  } finally {
    favoriteBusy.value = false;
  }
}

// アクティブリストから銘柄を削除する（DELETE /api/favorites/<list_id>/<symbol>/）
// 他のリストへの所属は影響を受けない。
async function removeFavorite(target: string) {
  if (favoriteBusy.value || activeListId.value === null) return;
  favoriteBusy.value = true;
  favoriteMessage.value = '';
  try {
    await removeFavoriteStock(activeListId.value, target);
    await fetchFavorites();
  } catch (e) {
    console.error('お気に入り削除エラー:', e);
  } finally {
    favoriteBusy.value = false;
  }
}

// 新しいリストを作成する（POST /api/favorite-lists/）。作成後は自動で選択する。
async function createList() {
  if (favoriteBusy.value) return;
  const input = window.prompt('新しいリスト名（50 字以内）:', '');
  if (input === null) return; // キャンセル
  const name = input.trim();
  if (!isValidListName(name)) {
    favoriteMessage.value = `無効なリスト名です（空以外・${LIST_NAME_MAX_LENGTH} 字以内）`;
    return;
  }
  favoriteBusy.value = true;
  favoriteMessage.value = '';
  try {
    const created = await createFavoriteList(name);
    await fetchFavorites();
    activeListId.value = created.id;
  } catch (e) {
    favoriteMessage.value = listErrorMessage(e);
  } finally {
    favoriteBusy.value = false;
  }
}

// select ボックスでのリスト選択 (Issue #50)。option の value は文字列で届くため数値化する。
function onListSelectChange(e: Event) {
  const value = (e.target as HTMLSelectElement).value;
  activeListId.value = value === '' ? null : Number(value);
}

// リスト名を変更する（PATCH /api/favorite-lists/<id>/）
async function renameActiveList(listId: number | null) {
  if (favoriteBusy.value || listId === null) return;
  const current = favoriteGroups.value.find((g) => g.id === listId);
  if (current === undefined) return;
  const input = window.prompt('リスト名を変更（50 字以内）:', current.name);
  if (input === null) return; // キャンセル
  const name = input.trim();
  if (!isValidListName(name)) {
    favoriteMessage.value = `無効なリスト名です（空以外・${LIST_NAME_MAX_LENGTH} 字以内）`;
    return;
  }
  favoriteBusy.value = true;
  favoriteMessage.value = '';
  try {
    await renameFavoriteList(listId, name);
    await fetchFavorites();
  } catch (e) {
    favoriteMessage.value = listErrorMessage(e);
  } finally {
    favoriteBusy.value = false;
  }
}

// リストを削除する（DELETE /api/favorite-lists/<id>/）。所属銘柄の行も一緒に削除される。
async function deleteActiveList(listId: number | null) {
  if (favoriteBusy.value || listId === null) return;
  const current = favoriteGroups.value.find((g) => g.id === listId);
  if (current === undefined) return;
  const ok = window.confirm(
    `リスト「${current.name}」を削除します。このリストの${current.stocks.length}件の銘柄も削除されます。よろしいですか？`,
  );
  if (!ok) return;
  favoriteBusy.value = true;
  favoriteMessage.value = '';
  try {
    await deleteFavoriteList(listId);
    await fetchFavorites();
  } catch (e) {
    favoriteMessage.value = listErrorMessage(e);
  } finally {
    favoriteBusy.value = false;
  }
}

async function fetchFromYahoo() {
  const target = symbol.value.trim();
  if (!target) return;
  fetching.value = true;
  yahooError.value = false;
  yahooMessage.value = `${target}（${period.value}）を Yahoo Finance から取得中...`;
  try {
    const res = await axios.post('/api/stocks/fetch/', { symbol: target, period: period.value });
    const r = res.data;
    yahooMessage.value =
      `${r.symbol} の株価 ${r.fetched} 件を取得して保存しました` +
      `（新規 ${r.created} 件 / 更新 ${r.updated} 件、${r.start_date} 〜 ${r.end_date}）`;
    // 保存されたデータを DB から読み直してチャートに反映
    await fetchStockData();
    // 直前に最新データを保存したばかりなので銘柄名も再取得 (Issue #49)
    void fetchStockMeta();
    // お気に入り銘柄の名称は StockMeta と同期されるため一覧も再取得 (Issue #50)
    void fetchFavorites();
  } catch (e: any) {
    const detail = e?.response?.data?.detail ?? e?.message ?? 'リクエストに失敗しました';
    yahooError.value = true;
    yahooMessage.value = `株価取得に失敗しました: ${detail}`;
  } finally {
    fetching.value = false;
  }
}

async function fetchMovingAverage() {
  try {
    const res = await axios.get(`/api/moving_average/${symbol.value.trim()}`, { params: { days: maDays.value } });
    movingAverage.value = res.data.moving_average;
  } catch (e) {
    console.error('移動平均取得エラー:', e);
  }
}

watch(symbol, () => {
  data.value = [];
  movingAverage.value = null;
  yahooMessage.value = '';
  yahooError.value = false;
  // タートル戦略の状態を新銘柄の保存状態へ復元 (Issue #53)（未保存なら全入力空欄）
  applyTurtleState(symbol.value);
  // 銘柄名をリセットしてデバウンス取得 (Issue #49)
  stockName.value = '';
  if (metaTimer !== null) clearTimeout(metaTimer);
  metaTimer = setTimeout(() => {
    void fetchStockMeta();
  }, 400);
});

// 表示ウィンドウ（表示期間 / 本数 = 直近 N 本）を表示範囲に適用する (Issue #36)。
// チャートには全データが入っているため、適用後はパン（ホイール / ドラッグ / スライダー）で
// 表示ウィンドウより古いデータも表示できる。
function applyDisplayWindow() {
  const total = data.value.length;
  if (total < 2) return; // チャート非表示 / 単一ローソク時は範囲調整の対象外
  const { start, end } = getDisplayRange(total, displayPeriod.value, displayCount.value);
  applyWheelRange(start, end);
}

// 新データ取得時（取得ボタン / 銘柄変更など）に表示ウィンドウを適用 (Issue #36)。
// nextTick で遅らせるのは、vue-echarts が新オプションをチャートに反映した
// 後に dispatchAction を実行するため。
watch(data, () => {
  // 新データ: ホバー中のインデックスをリセット（古いインデックスは範囲外になり得るため）
  hoverIndex.value = null;
  nextTick(applyDisplayWindow);
});

// 表示期間 / 本数の切替時は表示ウィンドウを再適用する。
// （旧データはチャートに残り続けるので、切替後もパンで過去を辿れる）
watch([displayPeriod, displayCount], () => {
  applyDisplayWindow();
});

// 初期表示でお気に入り一覧を読み込む (Issue #50)
// および初期銘柄のタートル戦略保存状態を復元 (Issue #53)
onMounted(() => {
  applyTurtleState(symbol.value);
  void fetchFavorites();
});
</script>

<style scoped>
.stock-container { font-family: Arial, sans-serif; }
.control-panel input, .control-panel select { padding:.4rem; border:1px solid #ccc; border-radius:.3rem; }
.moving-average-panel p { margin-top:.5rem;font-weight:bold; }
.turtle-panel input, .turtle-panel select { padding:.3rem; border:1px solid #ccc; border-radius:.3rem; }
.turtle-panel p { margin-top:.5rem; font-weight:bold; }
.turtle-table { margin-top:.5rem; border-collapse:collapse; }
.turtle-table th, .turtle-table td { border:1px solid #ddd; padding:.3rem .6rem; text-align:left; font-size:.9rem; }
.turtle-table th { background:#eee; }
/* --- 固定情報パネル（チャート容器内の position 基準） --- */
.chart-wrapper { position:relative; }
.info-panel {
  position:absolute; z-index:10; min-width:10rem;
  background:rgba(255,255,255,.93); border:1px solid #bbb; border-radius:.4rem;
  box-shadow:0 2px 8px rgba(0,0,0,.18); font-size:.85rem;
  pointer-events:none; /* 本体はポインター透過: クロスヘアが更新され続ける */
  user-select:none;
}
.info-panel-handle {
  pointer-events:auto; cursor:move; touch-action:none;
  padding:.2rem .5rem; background:#f0f0f0; border-bottom:1px solid #ddd;
  border-radius:.4rem .4rem 0 0; font-weight:bold;
}
.info-table { width:100%; border-collapse:collapse; }
.info-table th, .info-table td { padding:.1rem .5rem; text-align:left; white-space:nowrap; }
.info-table th { color:#555; font-weight:normal; }
.info-table td { font-variant-numeric:tabular-nums; }
/* --- タートル戦略数値エリア（固定情報パネル内、Issue #40） --- */
/* 現在値テーブルとの視覚的な分離: 上側の区切り線 + 淡いオレンジ背景 */
.turtle-section {
  border-top:1px solid #bbb;
  border-radius:0 0 .4rem .4rem;
  background:rgba(230,126,34,.06);
}
.turtle-section-header {
  padding:.2rem .5rem; background:#fdf1e3; color:#9c5a00;
  font-weight:bold; font-size:.8rem;
}
</style>