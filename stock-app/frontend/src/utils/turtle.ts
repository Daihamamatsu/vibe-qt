// タートルズ型 ATR ボラティリティ・ブレイクアウト (Donchian Channel + ATR) の計算モジュール。
//
// ルックアヘッド・バイアス回避のため、各日のバンド値・シグナル判定には
// 「前日までのデータ」のみを使用する (当日のローソク足はシフトして除外)。
// 将来の日付の価格を一切参照しない。
//
// 本モジュールは Vue 非依存の純粋関数のみで構成しており、
// Node でもそのまま実行・検証できる。

export interface Bar {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

export interface TurtleParams {
  /** エントリー用 Donchian 期間 (既定 20 日) */
  entryDays?: number;
  /** 手仕舞い用 Donchian 期間 (既定 10 日) */
  exitDays?: number;
  /** N(ATR) の期間 (14 または 20、既定 20 = クラシック・タートル) */
  atrPeriod?: number;
}

export interface TurtleBar {
  date: string;
  close: number;
  /** 前日までの entryDays 日間の最高値 (エントリーライン) */
  donchianUpper: number | null;
  /** 前日までの exitDays 日間の最安値 (手仕舞いライン) */
  donchianLower: number | null;
  /** N(ATR): True Range の単純移動平均 */
  atr: number | null;
  /** トレーリングストップ: 直近 exitDays 日高値 (前日終了時点) - 2*N */
  trailingStop: number | null;
  /** 終値が Donchian Upper を上抜け (エントリー) */
  buy: boolean;
  /** 終値が Donchian Lower を下抜け、またはトレーリングストップに達した日 */
  exit: boolean;
}

/**
 * Donchian バンド / ATR / BUY・EXIT シグナルを全日分計算する。
 * 戻り値は引数の bars と同じ長さ・同じ順番 (日付昇順)。
 * バンドは「前日までの N 日間」の最高/最安値であり、
 * 直近 N 日分のデータが揃う日までは null (描画されない)。
 */
export function computeTurtle(bars: Bar[], params: TurtleParams = {}): TurtleBar[] {
  const entryDays = params.entryDays ?? 20;
  const exitDays = params.exitDays ?? 10;
  const atrPeriod = params.atrPeriod ?? 20;
  const n = bars.length;

  // open/high/low が null のレコードはチャート描画と同一のフォールバック (close)
  const hi = bars.map(b => Number(b.high ?? b.close));
  const lo = bars.map(b => Number(b.low ?? b.close));
  const cl = bars.map(b => Number(b.close));

  // --- True Range と ATR (TR の単純移動平均) ---
  // TR[i] は当日 (i) と前営業日 (i-1) のデータのみ使用 (未来参照なし)
  const tr: number[] = new Array(n);
  for (let i = 0; i < n; i++) {
    tr[i] = i === 0
      ? hi[i] - lo[i]
      : Math.max(
          hi[i] - lo[i],
          Math.abs(hi[i] - cl[i - 1]),
          Math.abs(lo[i] - cl[i - 1]),
        );
  }
  const atr: (number | null)[] = new Array(n).fill(null);
  let trSum = 0;
  for (let i = 0; i < n; i++) {
    trSum += tr[i];
    if (i >= atrPeriod) trSum -= tr[i - atrPeriod];
    if (i >= atrPeriod - 1) atr[i] = trSum / atrPeriod;
  }

  // --- Donchian バンド (前日までの範囲: 当日は除外してシフト) とシグナル ---
  const out: TurtleBar[] = new Array(n);
  for (let i = 0; i < n; i++) {
    // エントリーライン: 前日までの entryDays 日間の最高値
    let upper: number | null = null;
    if (i >= entryDays) {
      upper = -Infinity;
      for (let j = i - entryDays; j < i; j++) upper = Math.max(upper, hi[j]);
    }
    // 手仕舞いライン: 前日までの exitDays 日間の最安値
    let lower: number | null = null;
    let recentHigh: number | null = null;
    if (i >= exitDays) {
      lower = Infinity;
      recentHigh = -Infinity;
      for (let j = i - exitDays; j < i; j++) {
        lower = Math.min(lower, lo[j]);
        recentHigh = Math.max(recentHigh, hi[j]);
      }
    }
    // トレーリングストップ: 直近高値 (前日終了時点) - 2*N
    let stop: number | null = null;
    if (recentHigh !== null && atr[i] !== null) {
      stop = recentHigh - 2 * (atr[i] as number);
    }
    // 当日終値でのブレイクアウト判定 (バンドは前日までのデータのみ参照)
    const buy = upper !== null && cl[i] > upper;
    const exit =
      (lower !== null && cl[i] < lower) ||
      (stop !== null && cl[i] <= stop);

    out[i] = {
      date: bars[i].date,
      close: cl[i],
      donchianUpper: upper,
      donchianLower: lower,
      atr: atr[i],
      trailingStop: stop,
      buy,
      exit,
    };
  }
  return out;
}

/**
 * 1 ユニットの推奨購入株数。
 * 計算式: floor((口座資金 * 0.01) / (N * 1株あたりの価値))
 */
export function computeUnitShares(
  accountValue: number,
  atrN: number,
  shareValue: number,
): number {
  if (
    !Number.isFinite(accountValue) ||
    !Number.isFinite(atrN) ||
    !Number.isFinite(shareValue) ||
    accountValue <= 0 || atrN <= 0 || shareValue <= 0
  ) {
    return 0;
  }
  return Math.floor((accountValue * 0.01) / (atrN * shareValue));
}

export interface PyramidTargets {
  /** 買値 + 0.5*N (ピラミッド 2 段目) */
  target1: number;
  /** 買値 + 1.0*N (ピラミッド 3 段目) */
  target2: number;
  /** 買値 + 1.5*N (ピラミッド 4 段目) */
  target3: number;
  /** 買値 - 2*N (ストップロス) */
  stop: number;
}

/** ピラミッディング目標価格 (+0.5N / +1.0N / +1.5N) とストップロス (-2N)。 */
export function computePyramidTargets(sharePrice: number, atrN: number): PyramidTargets {
  return {
    target1: sharePrice + 0.5 * atrN,
    target2: sharePrice + 1.0 * atrN,
    target3: sharePrice + 1.5 * atrN,
    stop: sharePrice - 2.0 * atrN,
  };
}
