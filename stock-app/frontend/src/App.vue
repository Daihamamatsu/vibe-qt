<template>
  <div id="app">
    <h1>株価表示アプリ</h1>

    <!-- Stock コンポーネント -->
    <Stock />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
// Stock コンポーネントを明示的に import（<script setup> ではテンプレートで使用するには必須）
import Stock from './components/Stock.vue';
// import axios から直接使用しない（Stock.vue で API コールを行うため）

onMounted(() => {
  console.log('アプリが起動しました');
});
</script>

<style scoped>
#app { font-family: Arial, sans-serif; padding:20px; }
</style>