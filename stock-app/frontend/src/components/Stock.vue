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
        <button @click="fetchStockData">取得</button>
        <button :disabled="fetching" @click="fetchFromYahoo">Yahoo Finance から取得</button>
      </div>
      <!-- Yahoo Finance 取得ステータス -->
      <p v-if="yahooMessage" :style="{ marginTop: '.5rem', marginBottom: 0, color: yahooError ? '#c0392b' : '#2c7a2c' }">
        {{ yahooMessage }}
      </p>
    </div>

    <!-- チャート表示（日足ローソク足 + 出来高バー + タートル ATR サブパネル） -->
    <v-chart :option="chartOptions" :style="{ height: turtleEnabled ? '640px' : '480px' }" v-if="data.length > 0"></v-chart>

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
import { computed, ref, watch } from 'vue';
import axios from 'axios';
import VChart from 'vue-echarts';
import type { EChartsOption, SeriesOption } from 'echarts';
// vue-echarts v8 では echarts のレンダラー・チャート・コンポーネントを
// アプリ側で登録する必要がある（公式 README のサンプルを参照）
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, CandlestickChart, LineChart, ScatterChart } from 'echarts/charts';
import { TooltipComponent, GridComponent } from 'echarts/components';
// タートルズ型 (Donchian + ATR) 計算モジュール（ルックアヘッドなし: 前日までのデータのみ使用）
import { computePyramidTargets, computeTurtle, computeUnitShares } from '../utils/turtle';
import type { PyramidTargets, TurtleBar } from '../utils/turtle';

use([CanvasRenderer, CandlestickChart, BarChart, LineChart, ScatterChart, TooltipComponent, GridComponent]);

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
  const records = data.value;
  if (records.length === 0) return {};
  const dates = records.map(d => d.date);
  const on = turtleEnabled.value;
  const rows = turtle.value;
  const tg = on ? targets.value : null;

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
    grid: on
      ? [
          { left: 70, right: 20, top: 30, height: '45%' },      // 上段: ローソク足
          { left: 70, right: 20, top: '58%', height: '14%' },   // 中段: 出来高
          { left: 70, right: 20, bottom: 15, height: '12%' },   // 下段: ATR
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