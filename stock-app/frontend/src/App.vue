<template>
  <div id="app">
    <h1>株価表示アプリ</h1>

    <!-- ボタンで任意のシンボルを取得する例 -->
    <button @click="loadData">AAPL の 5 日移動平均取得</button>

    <!-- ローディング・エラー表示 --------------------------------------------------- -->
    <div v-if="store.isLoading" class="loading">読み込み中…</div>
    <div v-else-if="store.errorMessage" class="error">
      エラー: {{ store.errorMessage }}
    </div>

    <!-- データ表示 ------------------------------------------------------------- -->
    <div v-else>
      <p>シンボル: {{ store.symbol }}</p>
      <p>5 日移動平均: {{ store.moving_average }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useMovingAverageStore } from './stores/movingAverageStore';
const store = useMovingAverageStore();
function loadData() {
  store.getMovingAverage('AAPL', 5);
}
</script>

<style scoped>
#app {
  font-family: Arial, sans-serif;
  padding: 20px;
}
.loading { color: blue; }
.error { color: red; }
</style>