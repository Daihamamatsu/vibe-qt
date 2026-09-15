// 引け後自動リフレッシュ判定モジュール
//
// 「取得」ボタン押下時に Yahoo Finance へ再取得するかどうかを判定する。
// DB の最新レコードが最近の日付（直近 recentDays 日以内）であれば、
// 日中（引け前）に保存されたイントラデースナップショットかもしれないため
// Yahoo へ再取得し、バックエンドの upsert で同日行を引け後最終値に上書きしてもらう。

/** Date をローカル時間ベースの YYYY-MM-DD（ISO 日付文字列）へ変換する。 */
export function toLocalIsoDate(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

/**
 * 最新レコードの日付から Yahoo Finance へ自動リフレッシュするべきかを判定する。
 *
 * @param latestDate 最新レコード日付（YYYY-MM-DD）。無データ（undefined / 空）は非リフレッシュ。
 * @param recentDays 「最近」とみなす日数（既定 7 日: 週末・祝日・米株のタイムゾーンズレを吸収）
 * @param now 基準時刻（既定は現在。テストで注入する）
 * @returns 最新レコードがローカル日付ベースで直近 recentDays 日以内（境界含む）なら true
 */
export function shouldAutoRefreshYahoo(
  latestDate: string | undefined,
  recentDays = 7,
  now: Date = new Date(),
): boolean {
  if (!latestDate) return false;
  const threshold = new Date(now.getFullYear(), now.getMonth(), now.getDate() - recentDays);
  return latestDate >= toLocalIsoDate(threshold);
}
