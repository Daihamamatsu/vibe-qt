// OBV (On-Balance Volume) の計算モジュール (Issue #61)。
//
// OBV は終値の方向に応じて出来高を足し引きして累積する指標。
// 計算式:
// - 初日の出来高を最初の OBV とする（出来高 null は 0 扱い）
// - ① 終値 > 前日終値: OBV[i] = OBV[i-1] + 出来高[i]
// - ② 終値 < 前日終値: OBV[i] = OBV[i-1] − 出来高[i]
// - ③ 終値 = 前日終値: OBV[i] = OBV[i-1]（不変）
// 出来高が null の日は出来高 0 扱い（OBV は横ばい）。
//
// 本モジュールは Vue 非依存の純粋関数のみで構成しており、
// Node でもそのまま実行・検証できる。

import type { Bar } from './turtle';

export interface ObvRow {
  date: string;
  /** OBV 値（出来高の累積値。下落が続くと負になる） */
  obv: number;
}

/**
 * OBV を全日分計算する。
 * 戻り値は引数の bars と同じ長さ・同じ順番 (日付昇順)。
 */
export function computeObv(bars: Bar[]): ObvRow[] {
  const n = bars.length;
  const out: ObvRow[] = new Array(n);
  let obv = 0;
  for (let i = 0; i < n; i++) {
    const volume = Number(bars[i].volume ?? 0);
    if (i === 0) {
      obv = volume; // 初日: 初日の出来高が最初の OBV
    } else {
      const diff = Number(bars[i].close) - Number(bars[i - 1].close);
      if (diff > 0) obv += volume; // ① 上昇日: 出来高を足す
      else if (diff < 0) obv -= volume; // ② 下降日: 出来高を引く
      // ③ 同値日: 不変
    }
    out[i] = { date: bars[i].date, obv };
  }
  return out;
}
