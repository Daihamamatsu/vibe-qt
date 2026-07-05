<template>
  <div class="stock-container">
    <!-- コントロールパネル -->
    <div class="control-panel" style="background:#f5f5f5;padding:1rem;border-radius:.5rem;margin-bottom:1.5rem;">
      <h3 style="margin-top:0;font-size:1.2rem;">株価データ取得</h3>
      <div style="display:flex;gap:1rem;align-items:center;">
        <label>シンボル:</label>
        <input v-model="symbol" placeholder="例：AAPL" />
        <button @click="fetchStockData">取得</button>
      </div>
    </div>

    <!-- チャート表示 -->
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

const symbol = ref('AAPL');
const data = ref<Array<{ date: string; close: number }>>([]);
const chartOptions = ref<EChartsOption>({});
const maDays = ref(5);
const movingAverage = ref<number | null>(null);

async function fetchStockData() {
  try {
    const res = await axios.get(`/api/stocks/${symbol.value}`);
    data.value = res.data;
    if (data.value.length > 0) {
      chartOptions.value = {
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: data.value.map(d => d.date) },
        yAxis: { type: 'value' },
        series: [{ name: 'Close', type: 'line', data: data.value.map(d => d.close), smooth: true }],
      };
    }
  } catch (e) {
    console.error('データ取得エラー:', e);
  }
}

async function fetchMovingAverage() {
  try {
    const res = await axios.get(`/api/moving_average/${symbol.value}`, { params: { days: maDays.value } });
    movingAverage.value = res.data.moving_average;
  } catch (e) {
    console.error('移動平均取得エラー:', e);
  }
}

watch(symbol, () => {
  data.value = [];
  chartOptions.value = {};
  movingAverage.value = null;
});
</script>

<style scoped>
.stock-container { font-family: Arial, sans-serif; }
.control-panel input { padding:.4rem; border:1px solid #ccc;border-radius:.3rem; }
.moving-average-panel p { margin-top:.5rem;font-weight:bold; }
</style>