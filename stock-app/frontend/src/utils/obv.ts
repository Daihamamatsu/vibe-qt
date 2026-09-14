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

// =====================================================================
// OBV 20 日間最高値更新 と タートル・ブレイク日の OBV 検証条件 (Issue #63)
// =====================================================================

/** OBV 20 日間最高値更新の 1 日分。 */
export interface Obv20DayHighRow {
  date: string;
  /** 当日の OBV 値 */
  obv: number;
  /** 直近 20 日間（当日除く）の OBV 最高値。履歴が 20 日未満なら null */
  priorMax20: number | null;
  /** 当日 OBV が priorMax20 を厳密に上回れば true（更新）。履歴 20 日未満は false */
  isHigh: boolean;
}

/**
 * 各日について、直近 20 日間（当日除く）の OBV 最高値と
 * それが「過去 20 日間の OBV 最高値」の更新日か（isHigh）を求める。
 * - 「更新」= 当日 OBV が直前 20 日 OBV 最高値を厳密に超える場合（同値は更新にしない）。
 * - ルックアヘッドしない（前日までのデータのみ参照）。
 * - 履歴が 20 日未満の日（先頭 20 日）は priorMax20 = null / isHigh = false。
 */
export function computeObv20DayHighs(obvRows: ObvRow[]): Obv20DayHighRow[] {
  const rows: Obv20DayHighRow[] = [];
  for (let i = 0; i < obvRows.length; i++) {
    const r = obvRows[i];
    let priorMax: number | null = null;
    if (i >= 20) {
      let m = -Infinity;
      for (let j = i - 20; j < i; j++) {
        if (obvRows[j].obv > m) m = obvRows[j].obv;
      }
      priorMax = m;
    }
    rows.push({
      date: r.date,
      obv: r.obv,
      priorMax20: priorMax,
      isHigh: priorMax !== null && r.obv > priorMax,
    });
  }
  return rows;
}

/** タートル・ブレイク日の OBV 検証条件（①②③）の判定結果。 */
export interface BreakoutObvCheck {
  /** ブレイク日 */
  date: string;
  /** ① ブレイク日当日 OBV が過去 20 日間 OBV 最高値を更新（直前 20 日 OBV 最高値を厳密に超える） */
  c1: boolean;
  /** ② ブレイク日が 20 日以上（取引日）ぶりのブレイク日（過去 BUY なし = 満たした扱い） */
  c2: boolean;
  /** ③ ブレイク日の直近 5 日（取引日、当日除く）以内に OBV 20 日間最高値更新日がある */
  c3: boolean;
  /** 3 条件 ①②③ をすべて満たす */
  all: boolean;
  /** ブレイク日当日の OBV 値 */
  obvOnDay: number;
  /** ブレイク日より直近 20 日間の OBV 最高値（履歴 20 日未満なら null） */
  priorMax20: number | null;
  /** 直前の BUY シグナル日（なければ null） */
  lastBreakoutDate: string | null;
  /** 前回ブレイクからの経過日数（取引日。過去 BUY がなければ null） */
  daysSinceLastBreakout: number | null;
  /** ブレイク日より直近 5 日以内に OBV 20 日間最高値を更新した日付（昇順） */
  recentHighDates: string[];
}

/**
 * `date` をタートル・ブレイク日（BUY シグナル日）として OBV 検証条件（①②③）を評価する。
 *
 * - `bars` と `obvRows` はインデックス一致を前提とする（computeTurtle / computeObv と同じ並び）
 * - `buyDates` は BUY シグナル日すべての昇順リスト
 * - `date` が BUY シグナル日でない場合・データに無い場合は null を返す
 */
export function evaluateBreakoutObv(
  bars: Bar[],
  obvRows: ObvRow[],
  buyDates: string[],
  date: string,
): BreakoutObvCheck | null {
  const idx = bars.findIndex(b => b.date === date);
  if (idx < 0 || !buyDates.includes(date)) return null;
  return evaluateBreakoutObvAt(bars, computeObv20DayHighs(obvRows), buyDates, idx);
}

/**
 * 全 BUY シグナル日について OBV 検証条件を評価する（チャートの BUY マーカー色分け用）。
 * 日付をキーに持つ Map を返す。
 */
export function computeBreakoutObvChecks(
  bars: Bar[],
  obvRows: ObvRow[],
  buyDates: string[],
): Map<string, BreakoutObvCheck> {
  const highs = computeObv20DayHighs(obvRows);
  const buySet = new Set(buyDates);
  const map = new Map<string, BreakoutObvCheck>();
  for (let i = 0; i < bars.length; i++) {
    if (buySet.has(bars[i].date)) {
      // evaluateBreakoutObvAt は内部で Set を生成するため、ここで渡すのは配列側
      map.set(bars[i].date, evaluateBreakoutObvAt(bars, highs, buyDates, i));
    }
  }
  return map;
}

/** evaluateBreakoutObv / computeBreakoutObvChecks 共通の実装（インデックス指定版）。 */
function evaluateBreakoutObvAt(
  bars: Bar[],
  highs: Obv20DayHighRow[],
  buyDates: string[],
  idx: number,
): BreakoutObvCheck {
  const date = bars[idx].date;
  const h = highs[idx];
  // ① ブレイク日当日 OBV が過去 20 日間 OBV 最高値を更新
  const c1 = h.isHigh;
  // ② ブレイク日が 20 日以上（取引日）ぶりのブレイク日（過去 BUY なし = 満たした扱い）
  const buySet = new Set(buyDates);
  let lastJ = -1;
  for (let k = idx - 1; k >= 0; k--) {
    if (buySet.has(bars[k].date)) {
      lastJ = k;
      break;
    }
  }
  const daysSinceLastBreakout = lastJ < 0 ? null : idx - lastJ;
  const c2 = lastJ < 0 || idx - lastJ >= 20;
  // ③ ブレイク日の直近 5 日（取引日、当日除く）以内に OBV 20 日間最高値更新日がある
  const recentHighDates: string[] = [];
  for (let k = Math.max(0, idx - 5); k < idx; k++) {
    if (highs[k].isHigh) recentHighDates.push(bars[k].date);
  }
  const c3 = recentHighDates.length > 0;
  return {
    date,
    c1,
    c2,
    c3,
    all: c1 && c2 && c3,
    obvOnDay: h.obv,
    priorMax20: h.priorMax20,
    lastBreakoutDate: lastJ < 0 ? null : bars[lastJ].date,
    daysSinceLastBreakout,
    recentHighDates,
  };
}
