<template>
  <div class="stock-container">
    <!-- コントロールパネル -->
    <div class="control-panel" style="background:#f5f5f5;padding:1rem;border-radius:.5rem;margin-bottom:1.5rem;">
      <h3 style="margin-top:0;font-size:1.2rem;">株価データ</h3>
      <div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap;">
        <label>シンボル:</label>
        <input v-model="symbol" placeholder="例：AAPL" />
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
    </div>

    <!-- チャート表示（日足ローソク足 + 出来高バー + タートル ATR サブパネル + 下部ズームスライダー） -->
    <v-chart ref="chartRef" :option="chartOptions" :style="{ height: turtleEnabled ? '640px' : '480px' }" v-if="data.length > 0"></v-chart>

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
        <label>買値:
          <!-- データ取得時に最新終値が自動設定される（手動入力後は上書きしない） -->
          <input type="number" v-model.number="turtleBuyPrice" min="0" style="width:7rem;" @input="buyPriceManual = true" />
        </label>
      </div>
      <table v-if="turtleEnabled && latestAtr !== null" class="turtle-table">
        <tbody>
          <tr>
            <th>直近 N (ATR)</th>
            <td>{{ latestAtr.toFixed(2) }}</td>
          </tr>
          <tr>
            <th>1ユニット推奨株数<br /><small>floor((口座資金×0.01) ÷ (N×買値))</small></th>
            <td>{{ unitShares }} 株</td>
          </tr>
          <tr v-if="targets">
            <th>ピラミッド目標 / ストップ</th>
            <td>
              +0.5N: {{ targets.target1.toFixed(2) }} ／ +1.0N: {{ targets.target2.toFixed(2) }} ／
              +1.5N: {{ targets.target3.toFixed(2) }} ／ ストップ(-2N): {{ targets.stop.toFixed(2) }}
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="turtleEnabled && data.length > 0" class="turtle-hint">
        ATR を計算するには {{ atrPeriod }} 日以上のデータが必要です
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import axios from 'axios';
import VChart from 'vue-echarts';
import type { EChartsOption, SeriesOption } from 'echarts';
// vue-echarts v8 では echarts のレンダラー・チャート・コンポーネントを
// アプリ側で登録する必要がある（公式 README のサンプルを参照）
import { use } from 'echarts/core';
import type { EChartsType } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, CandlestickChart, LineChart, ScatterChart } from 'echarts/charts';
import { TooltipComponent, GridComponent, DataZoomComponent } from 'echarts/components';
// 表示ウィンドウ（表示期間 / ローソク足本数）計算モジュール
import { DISPLAY_PRESETS, getDisplayRange } from '../utils/display';
// タートルズ型 (Donchian + ATR) 計算モジュール（ルックアヘッドなし: 前日までのデータのみ使用）
import { computePyramidTargets, computeTurtle, computeUnitShares } from '../utils/turtle';
import type { PyramidTargets, TurtleBar } from '../utils/turtle';

use([CanvasRenderer, CandlestickChart, BarChart, LineChart, ScatterChart, TooltipComponent, GridComponent, DataZoomComponent]);

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
// Yahoo Finance 取得期間（yfinance の period 値）
const period = ref('1mo');
const data = ref<StockRecord[]>([]);
// 表示ウィンドウ: 表示期間プリセット（営業日換算、既定は 1 年分を表示）
const displayPeriod = ref('1y');
// 表示ウィンドウ: ローソク足本数指定（表示期間より優先。null / 空欄 = 期間に従う）
const displayCount = ref<number | string | null>(null);
// vue-echarts コンポーネント参照（dispatchAction でズームを操作するため）
const chartRef = ref<InstanceType<typeof VChart> | null>(null);
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
watch(
  () => chartRef.value?.chart,
  (chart) => {
    removeWheelListener?.();
    removeWheelListener = null;
    if (!chart) return;
    const rootEl = (chartRef.value?.root as unknown as HTMLElement | undefined) ?? null;
    if (!rootEl) return;
    rootEl.addEventListener('wheel', onChartWheel, { passive: false, capture: true });
    removeWheelListener = () => {
      rootEl.removeEventListener('wheel', onChartWheel, { capture: true });
    };
  },
);
onBeforeUnmount(() => {
  removeWheelListener?.();
  removeWheelListener = null;
  if (wheelThrottleTimer !== null) clearTimeout(wheelThrottleTimer);
});

const maDays = ref(5);
const movingAverage = ref<number | null>(null);
const fetching = ref(false);
const yahooMessage = ref('');
const yahooError = ref(false);

// --- タートル戦略 (Donchian Channel + ATR) の状態 ---
const turtleEnabled = ref(true);
const atrPeriod = ref(20); // N (ATR) の期間: 14 / 20
const accountValue = ref(1000000); // 口座資金（ユーザー入力）
const turtleBuyPrice = ref<number | null>(null); // 買値（既定: 最新終値を自動設定）
const buyPriceManual = ref(false); // ユーザーが買値を手動設定したフラグ

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
// ピラミッディング目標 (+0.5N / +1.0N / +1.5N) とストップロス (-2N)
const targets = computed<PyramidTargets | null>(() => {
  const price = turtleBuyPrice.value;
  const atr = latestAtr.value;
  if (price === null || price <= 0 || atr === null || atr <= 0) return null;
  return computePyramidTargets(price, atr);
});
// 1 ユニットの推奨購入株数: floor((口座資金 * 0.01) / (N * 1株あたりの価値))
const unitShares = computed<number>(() => {
  const price = turtleBuyPrice.value;
  const atr = latestAtr.value;
  if (price === null || atr === null) return 0;
  return computeUnitShares(accountValue.value, atr, price);
});

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

  // タートル表示ON時の追加系列
  if (on) {
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
        name: 'BUY',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: rows.map(r => (r.buy ? r.close : null)),
        symbol: 'triangle',
        symbolSize: 12,
        itemStyle: { color: '#e2534f' },
        label: { show: true, position: 'top', formatter: 'BUY', color: '#e2534f', fontSize: 10 },
      },
      {
        // EXIT マーカー: 手仕舞いライン下抜けまたはトレーリングストップ到達の日（日本式: 緑）
        name: 'EXIT',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: rows.map(r => (r.exit ? r.close : null)),
        symbol: 'triangle',
        symbolRotate: 180, // 下向き三角形
        symbolSize: 12,
        itemStyle: { color: '#3ba272' },
        label: { show: true, position: 'bottom', formatter: 'EXIT', color: '#3ba272', fontSize: 10 },
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
  }

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      // 出来高を tooltip でも K/M 表記にする（軸ラベルと揃える）。
      // ローソク足は [open, close, low, high] の配列値なのでそのまま連結表示
      // ローソク足は [open, close, low, high] の配列値になり型が広いので unknown で受け取る
      valueFormatter: (value: unknown): string =>
        Array.isArray(value) ? value.join(', ') : formatCompact(Number(value)),
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
      },
    ],
    grid: on
      ? [
          { left: 70, right: 20, top: 30, height: '45%' },      // 上段: ローソク足
          { left: 70, right: 20, top: '58%', height: '14%' },   // 中段: 出来高
          { left: 70, right: 20, bottom: 45, height: '12%' },   // 下段: ATR（bottom 45 = 下部スライダー 0〜30px を避ける）
        ]
      : [
          { left: 70, right: 20, top: 30, height: '55%' },      // 上段: ローソク足
          { left: 70, right: 20, bottom: 50, height: '18%' },   // 下段: 出来高
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
    // 買値は既定で最新終値を設定（ユーザーが手動設定した場合は上書きしない）
    if (records.length > 0 && !buyPriceManual.value) {
      turtleBuyPrice.value = Number(records[records.length - 1].close);
    }
  } catch (e) {
    console.error('データ取得エラー:', e);
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
  // タートル戦略の状態をリセット（買値は次回取得時に最新終値へ自動設定される）
  turtleBuyPrice.value = null;
  buyPriceManual.value = false;
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
  nextTick(applyDisplayWindow);
});

// 表示期間 / 本数の切替時は表示ウィンドウを再適用する。
// （旧データはチャートに残り続けるので、切替後もパンで過去を辿れる）
watch([displayPeriod, displayCount], () => {
  applyDisplayWindow();
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
</style>