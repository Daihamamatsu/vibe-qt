import { defineStore } from 'pinia';
import { fetchMovingAverage, MovingAverageResponse } from '../api/stock';

export const useMovingAverageStore = defineStore('movingAverage', {
  state: () => ({
    symbol: '' as string,
    moving_average: 0 as number,
    isLoading: false as boolean,
    errorMessage: '' as string
  }),
  actions: {
    async getMovingAverage(symbol: string, days = 5) {
      this.isLoading = true;
      this.errorMessage = '';
      try {
        const data: MovingAverageResponse = await fetchMovingAverage(symbol, days);
        this.symbol = data.symbol;
        this.moving_average = data.moving_average;
      } catch (e: any) {
        this.errorMessage = e?.response?.data?.detail || e.message || '通信エラー';
      } finally {
        this.isLoading = false;
      }
    }
  }
});