import axios from 'axios';

export interface MovingAverageResponse {
  symbol: string;
  moving_average: number;
}

export async function fetchMovingAverage(
  symbol: string,
  days = 5
): Promise<MovingAverageResponse> {
  const resp = await axios.get<MovingAverageResponse>(
    `/api/moving_average/${symbol}/?days=${days}`
  );
  return resp.data;
}
