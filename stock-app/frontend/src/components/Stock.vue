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

    <!-- チャート表示（日足ローソク足） -->
    <v-chart :option="chartOptions" style="height:400px;" v-if="data.length > 0"></v-chart>

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
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import axios from 'axios';
import VChart from 'vue-echarts';
import type { EChartsOption } from 'echarts';
// vue-echarts v8 では echarts のレンダラー・チャート・コンポーネントを
// アプリ側で登録する必要がある（公式 README のサンプルを参照）
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { CandlestickChart } from 'echarts/charts';
import { TooltipComponent, GridComponent } from 'echarts/components';

use([CanvasRenderer, CandlestickChart, TooltipComponent, GridComponent]);

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

const symbol = ref('AAPL');
// Yahoo Finance 取得期間（yfinance の period 値）
const period = ref('1mo');
const data = ref<StockRecord[]>([]);
const chartOptions = ref<EChartsOption>({});
const maDays = ref(5);
const movingAverage = ref<number | null>(null);
const fetching = ref(false);
const yahooMessage = ref('');
const yahooError = ref(false);

async function fetchStockData() {
  try {
    const res = await axios.get(`/api/stocks/${symbol.value.trim()}`);
    // 日付昇順（古い順）でチャートに表示する
    const records = (res.data as StockRecord[]).sort((a, b) => a.date.localeCompare(b.date));
    data.value = records;
    if (records.length > 0) {
      chartOptions.value = {
        tooltip: { trigger: 'axis' },
        grid: { left: 70, right: 20, top: 30, bottom: 40 },
        xAxis: { type: 'category', data: records.map(d => d.date) },
        yAxis: { type: 'value', scale: true },
        series: [{
          name: symbol.value,
          type: 'candlestick',
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
        }],
      };
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
  chartOptions.value = {};
  movingAverage.value = null;
  yahooMessage.value = '';
  yahooError.value = false;
});
</script>

<style scoped>
.stock-container { font-family: Arial, sans-serif; }
.control-panel input, .control-panel select { padding:.4rem; border:1px solid #ccc; border-radius:.3rem; }
.moving-average-panel p { margin-top:.5rem;font-weight:bold; }
</style>