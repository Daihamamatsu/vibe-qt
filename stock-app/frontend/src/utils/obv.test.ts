// obv.ts モジュールのユニットテスト (Issue #61)
//
// 合成 OHLC データで OBV (On-Balance Volume) の計算式を固定する:
// - 初日の出来高を最初の OBV とする
// - ① 上昇日: OBV[i] = OBV[i-1] + 出来高[i]
// - ② 下降日: OBV[i] = OBV[i-1] − 出来高[i]
// - ③ 同値日: OBV[i] = OBV[i-1]（不変）
// - 出来高が null の日は出来高 0 扱い (OBV は横ばい)

import { describe, expect, it } from 'vitest';
import type { Bar } from './turtle';
import {
  computeBreakoutObvChecks,
  computeObv,
  computeObv20DayHighs,
  evaluateBreakoutObv,
} from './obv';
import type { ObvRow } from './obv';

/** 指定した終値・出来高の 1 本バーを生成 (始値 = 高値 = 安値 = 終値)。 */
function makeBar(i: number, close: number, volume: number | null): Bar {
  return {
    date: `2026-09-${String(i + 1).padStart(2, '0')}`,
    open: close,
    high: close,
    low: close,
    close,
    volume,
  };
}

/** closes / volumes からバー列を生成（長さは closes を基準にする）。 */
function makeBars(closes: number[], volumes: (number | null)[]): Bar[] {
  return closes.map((c, i) => makeBar(i, c, volumes[i]));
}

/**
 * 参照実装: Issue の計算式 (①②③) をそのまま記述。
 * computeObv と独立に実装し、固定シードの擬似乱数系列での回帰比較に使う。
 */
function referenceObv(bars: Bar[]): number[] {
  const out: number[] = [];
  for (let i = 0; i < bars.length; i++) {
    const volume = bars[i].volume ?? 0;
    if (i === 0) {
      out.push(volume); // 最初の出来高 = 最初の OBV
    } else if (bars[i].close > bars[i - 1].close) {
      out.push(out[i - 1] + volume); // ①
    } else if (bars[i].close < bars[i - 1].close) {
      out.push(out[i - 1] - volume); // ②
    } else {
      out.push(out[i - 1]); // ③
    }
  }
  return out;
}

// 固定シードの擬似乱数生成器 (mulberry32)。テストの再現性を担保する。
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

describe('computeObv', () => {
  it('空の入力は空配列を返す', () => {
    expect(computeObv([])).toEqual([]);
  });

  it('単一バー: OBV はその出来高に等しい', () => {
    expect(computeObv(makeBars([100], [1000])).map(r => r.obv)).toEqual([1000]);
  });

  it('単一バーで出来高 null: OBV は 0', () => {
    expect(computeObv(makeBars([100], [null])).map(r => r.obv)).toEqual([0]);
  });

  it('①②③ 基本式: 上昇は加算・下降は減算・同値は不変', () => {
    // 終値: 10, 11, 12, 12, 11, 12, 13 → 上昇, 上昇, 同値, 下降, 上昇, 上昇
    const bars = makeBars(
      [10, 11, 12, 12, 11, 12, 13],
      [1000, 1000, 1000, 1000, 1000, 1000, 1000],
    );
    expect(computeObv(bars).map(r => r.obv)).toEqual([1000, 2000, 3000, 3000, 2000, 3000, 4000]);
  });

  it('すべて同値: OBV は初日出来高のまま一定（出来高の大小は無関係）', () => {
    const bars = makeBars([100, 100, 100, 100], [1000, 2000, 3000, 4000]);
    expect(computeObv(bars).map(r => r.obv)).toEqual([1000, 1000, 1000, 1000]);
  });

  it('連続下落: OBV は減少し負にもなる', () => {
    const bars = makeBars([10, 9, 8, 7], [1000, 1000, 1000, 1000]);
    expect(computeObv(bars).map(r => r.obv)).toEqual([1000, 0, -1000, -2000]);
  });

  it('出来高 null の日は 0 扱い (OBV 横ばい)', () => {
    // 初日 null → OBV[0] = 0。上昇日だが出来高 null → 不変。翌日 +2000
    const bars = makeBars([10, 11, 12], [null, null, 2000]);
    expect(computeObv(bars).map(r => r.obv)).toEqual([0, 0, 2000]);
  });

  it('出来高が日ごとに変動しても計算式は成立', () => {
    // 終値: 10 → 12 → 11 → 13 (上昇, 下降, 上昇)
    const bars = makeBars([10, 12, 11, 13], [100, 500, 300, 700]);
    // [100, 100+500=600, 600-300=300, 300+700=1000]
    expect(computeObv(bars).map(r => r.obv)).toEqual([100, 600, 300, 1000]);
  });

  it('昇順日付をそのまま保持する', () => {
    const bars = makeBars([10, 11], [100, 100]);
    const rows = computeObv(bars);
    expect(rows.map(r => r.date)).toEqual(bars.map(b => b.date));
    expect(rows).toHaveLength(bars.length);
  });

  it('乱数系列: 参照実装 (Issue の計算式①②③) と一致する (回帰)', () => {
    const rand = mulberry32(20260914);
    let price = 100;
    const closes: number[] = [];
    const volumes: number[] = [];
    for (let i = 0; i < 200; i++) {
      price = Math.max(1, price + (rand() - 0.5) * 4); // ランダムウォーク
      closes.push(Number(price.toFixed(2)));
      volumes.push(Math.floor(rand() * 10000));
    }
    // 同値日（差分 0）も確実に含める
    closes[50] = closes[49];
    const bars = makeBars(closes, volumes);
    expect(computeObv(bars).map(r => r.obv)).toEqual(referenceObv(bars));
  });
});

describe('computeObv20DayHighs', () => {
  it('空の入力は空配列を返す', () => {
    expect(computeObv20DayHighs([])).toEqual([]);
  });

  it('履歴 20 日未満の日: priorMax20 は null / isHigh は false', () => {
    const bars = makeBars([10, 11, 12], [1000, 1000, 1000]);
    const rows = computeObv20DayHighs(computeObv(bars));
    expect(rows).toHaveLength(3);
    for (const r of rows) {
      expect(r.priorMax20).toBeNull();
      expect(r.isHigh).toBe(false);
    }
  });

  it('単調増加 OBV 系列: 21 日目（index 20）以降は毎日「更新」', () => {
    const n = 30;
    const closes = Array.from({ length: n }, (_, i) => i + 1);
    const volumes = Array.from({ length: n }, () => 1000);
    const obvRows = computeObv(makeBars(closes, volumes));
    const rows = computeObv20DayHighs(obvRows);
    for (let i = 0; i < 20; i++) expect(rows[i].isHigh).toBe(false);
    for (let i = 20; i < n; i++) {
      // OBV 単調増加 → 直前 20 日の最高は前日 OBV
      expect(rows[i].priorMax20).toBe(obvRows[i - 1].obv);
      expect(rows[i].isHigh).toBe(true);
    }
  });

  it('OBV が直前 20 日 OBV 最高値と同値なら更新としない（厳密に大きい場合のみ更新）', () => {
    // 0-19: 同値 (OBV=1000) / 20: 下降 (OBV=0) / 21: 回復 (OBV=1000 = 直前最高と同一) / 22: 上昇 (OBV=2000 > 1000)
    const closes = [...Array.from({ length: 20 }, () => 10), 9, 10, 11];
    const volumes = closes.map(() => 1000);
    const bars = makeBars(closes, volumes);
    const rows = computeObv20DayHighs(computeObv(bars));
    expect(rows[21].obv).toBe(1000);
    expect(rows[21].priorMax20).toBe(1000);
    expect(rows[21].isHigh).toBe(false); // 同値は更新しない
    expect(rows[22].priorMax20).toBe(1000);
    expect(rows[22].isHigh).toBe(true);
  });

  it('priorMax20 は直前 20 日分のみを対象にする（21 日以前はスコープ外）', () => {
    // 日 9 に OBV=5000 のスパイク（それ以外は 1000、日 30 は 2000）
    // - 日 29 の直前 20 日 [9..28] は日 9 を含む → priorMax20 = 5000
    // - 日 30 の直前 20 日 [10..29] は日 9 を含まない → priorMax20 = 1000 → 2000 が更新
    const rows: ObvRow[] = [];
    for (let i = 0; i < 31; i++) {
      const obv = i === 9 ? 5000 : i === 30 ? 2000 : 1000;
      rows.push({ date: `2026-09-${String(i + 1).padStart(2, '0')}`, obv });
    }
    const highs = computeObv20DayHighs(rows);
    expect(highs[29].priorMax20).toBe(5000);
    expect(highs[29].isHigh).toBe(false);
    expect(highs[30].priorMax20).toBe(1000);
    expect(highs[30].isHigh).toBe(true);
  });
});

describe('evaluateBreakoutObv / computeBreakoutObvChecks', () => {
  // 基本シリーズ: 31 バー・全日同値 (OBV=1000)。個別日の終値を上げると OBV が +1000 増える。
  function baseBars(closes?: number[]): Bar[] {
    const n = 31;
    const cs = closes ?? Array.from({ length: n }, () => 10);
    return makeBars(cs, closes ? closes.map(() => 1000) : Array.from({ length: n }, () => 1000));
  }
  const d = (bars: Bar[], i: number): string => bars[i].date;

  it('BUY シグナル日でない日は null を返す', () => {
    const bars = baseBars();
    const obvRows = computeObv(bars);
    expect(evaluateBreakoutObv(bars, obvRows, [d(bars, 20)], d(bars, 21))).toBeNull();
    expect(evaluateBreakoutObv(bars, obvRows, [d(bars, 20)], '1999-01-01')).toBeNull();
  });

  it('① ブレイク日 OBV が 20 日間 OBV 最高値を更新 → c1 = true（数値も一致）', () => {
    const closes = Array.from({ length: 30 }, () => 10);
    closes[20] = 11; // OBV[20] = 2000 > 直前 20 日最高 1000
    const bars = baseBars(closes);
    const c = evaluateBreakoutObv(bars, computeObv(bars), [d(bars, 20)], d(bars, 20));
    expect(c).not.toBeNull();
    expect(c!.c1).toBe(true);
    expect(c!.obvOnDay).toBe(2000);
    expect(c!.priorMax20).toBe(1000);
  });

  it('① ブレイク日 OBV が直前 20 日最高値を超えない → c1 = false', () => {
    const bars = baseBars(); // 全日同値 OBV=1000
    const c = evaluateBreakoutObv(bars, computeObv(bars), [d(bars, 25)], d(bars, 25));
    expect(c!.c1).toBe(false);
  });

  it('② 過去 BUY が無い → c2 = true（lastBreakoutDate = null）', () => {
    const bars = baseBars();
    const c = evaluateBreakoutObv(bars, computeObv(bars), [d(bars, 10)], d(bars, 10));
    expect(c!.c2).toBe(true);
    expect(c!.lastBreakoutDate).toBeNull();
    expect(c!.daysSinceLastBreakout).toBeNull();
  });

  it('② 前回ブレイクから 20 取引日（境界）→ c2 = true', () => {
    const bars = baseBars();
    const c = evaluateBreakoutObv(bars, computeObv(bars), [d(bars, 10), d(bars, 30)], d(bars, 30));
    expect(c!.lastBreakoutDate).toBe(d(bars, 10));
    expect(c!.daysSinceLastBreakout).toBe(20);
    expect(c!.c2).toBe(true);
  });

  it('② 前回ブレイクから 19 取引日 → c2 = false', () => {
    const bars = baseBars();
    const c = evaluateBreakoutObv(bars, computeObv(bars), [d(bars, 11), d(bars, 30)], d(bars, 30));
    expect(c!.daysSinceLastBreakout).toBe(19);
    expect(c!.c2).toBe(false);
  });

  it('③ 直近 5 日（当日除く）に OBV 20 日間最高値更新日が無い → c3 = false', () => {
    const bars = baseBars(); // OBV 全日同値 → 更新日なし
    const c = evaluateBreakoutObv(bars, computeObv(bars), [d(bars, 30)], d(bars, 30));
    expect(c!.c3).toBe(false);
    expect(c!.recentHighDates).toEqual([]);
  });

  it('③ 4 日前に OBV 20 日間最高値更新日がある → c3 = true（日付も記録）', () => {
    const closes = Array.from({ length: 31 }, () => 10);
    closes[26] = 11; // OBV[26] = 2000 → 更新日（ブレイク日 30 から 4 日前 = ウィンドウ内）
    const bars = baseBars(closes);
    const c = evaluateBreakoutObv(bars, computeObv(bars), [d(bars, 30)], d(bars, 30));
    expect(c!.c3).toBe(true);
    expect(c!.recentHighDates).toEqual([d(bars, 26)]);
  });

  it('③ 更新日がブレイク日ちょうど 5 日前 → c3 = true（ウィンドウ境界）', () => {
    const closes = Array.from({ length: 31 }, () => 10);
    closes[25] = 11; // ブレイク日 30 からちょうど 5 日前
    const bars = baseBars(closes);
    const c = evaluateBreakoutObv(bars, computeObv(bars), [d(bars, 30)], d(bars, 30));
    expect(c!.c3).toBe(true);
    expect(c!.recentHighDates).toEqual([d(bars, 25)]);
  });

  it('③ 更新日がブレイク日 6 日前 → c3 = false（ウィンドウ外）', () => {
    const closes = Array.from({ length: 31 }, () => 10);
    closes[24] = 11; // ブレイク日 30 から 6 日前 = ウィンドウ外
    const bars = baseBars(closes);
    const c = evaluateBreakoutObv(bars, computeObv(bars), [d(bars, 30)], d(bars, 30));
    expect(c!.c3).toBe(false);
    expect(c!.recentHighDates).toEqual([]);
  });

  it('③ ブレイク日当日の OBV 更新は ③ の対象外（c3 = false、c1 = true）', () => {
    const closes = Array.from({ length: 30 }, () => 10);
    closes[30] = 11; // 当日のみ上昇 → 当日は OBV 更新だが ③ は前日〜5 日前のみ
    const bars = baseBars(closes);
    const c = evaluateBreakoutObv(bars, computeObv(bars), [d(bars, 30)], d(bars, 30));
    expect(c!.c1).toBe(true);
    expect(c!.c3).toBe(false);
  });

  it('3 条件すべてを満たすブレイク日 → all = true', () => {
    const closes = Array.from({ length: 31 }, () => 10);
    closes[26] = 11; // ③ 4 日前に OBV 更新 (2000)
    closes[27] = closes[28] = closes[29] = 11; // 高値維持 → OBV は 2000 のまま
    closes[30] = 12; // 当日上昇 → OBV 3000 > 直前 20 日最高 2000 = ①
    const bars = baseBars(closes);
    const c = evaluateBreakoutObv(bars, computeObv(bars), [d(bars, 10), d(bars, 30)], d(bars, 30));
    expect(c!.c1).toBe(true);
    expect(c!.c2).toBe(true); // 前回 BUY から 20 取引日
    expect(c!.c3).toBe(true);
    expect(c!.all).toBe(true);
    expect(c!.obvOnDay).toBe(3000);
    expect(c!.priorMax20).toBe(2000);
  });

  it('computeBreakoutObvChecks: 全 BUY 日分を日付キーの Map で返す', () => {
    const closes = Array.from({ length: 31 }, () => 10);
    closes[26] = 11;
    closes[27] = closes[28] = closes[29] = 11;
    closes[30] = 12;
    const bars = baseBars(closes);
    const obvRows = computeObv(bars);
    const map = computeBreakoutObvChecks(bars, obvRows, [d(bars, 10), d(bars, 30)]);
    expect(map.size).toBe(2);
    expect(map.get(d(bars, 10))!.c2).toBe(true);
    expect(map.get(d(bars, 10))!.all).toBe(false);
    expect(map.get(d(bars, 30))!.all).toBe(true);
  });
});
