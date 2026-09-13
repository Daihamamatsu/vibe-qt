// お気に入り銘柄ユーティリティ (Issue #50)
// シンボル検証とお気に入りリスト操作の純関数群。
// バックエンド API（/api/favorites/）のバリデーション・ステータスコードと
// 整合した挙動をフロント側でも共用するためのモジュール。

/** お気に入り銘柄エントリ（バックエンド /api/favorites/ 応答と同一形式）。 */
export interface FavoriteEntry {
  symbol: string;
  name: string;
}

/** シンボル形式（バックエンド SYMBOL_RE と一致: 英大文字・数字・. - ^ =、最大 10 文字）。 */
export const SYMBOL_PATTERN = /^[A-Z0-9.\-^=]{1,10}$/;

/** シンボルが有効か判定する（trim / 大文字化してから検証）。 */
export function isValidSymbol(symbol: string): boolean {
  return SYMBOL_PATTERN.test(symbol.trim().toUpperCase());
}

/** お気に入りリストからシンボル位置（大文字・小文字を無視）を探し、見つからなければ -1。 */
export function indexOfFavorite(
  favorites: readonly FavoriteEntry[],
  symbol: string,
): number {
  const target = symbol.trim().toUpperCase();
  return favorites.findIndex((f) => f.symbol === target);
}

/** 指定シンボルのお気に入りエントリを返す（無ければ null）。 */
export function getFavorite(
  favorites: readonly FavoriteEntry[],
  symbol: string,
): FavoriteEntry | null {
  const idx = indexOfFavorite(favorites, symbol);
  return idx === -1 ? null : favorites[idx];
}

/** 末尾にシンボルを追加したコピーを返す（既登録なら元リストをそのまま返す）。 */
export function addFavorite(
  favorites: readonly FavoriteEntry[],
  symbol: string,
  name = '',
): readonly FavoriteEntry[] {
  if (indexOfFavorite(favorites, symbol) !== -1) return favorites;
  return [...favorites, { symbol: symbol.trim().toUpperCase(), name }];
}

/** 指定シンボルを削除したコピーを返す（未登録なら元リストをそのまま返す）。 */
export function removeFavorite(
  favorites: readonly FavoriteEntry[],
  symbol: string,
): readonly FavoriteEntry[] {
  const idx = indexOfFavorite(favorites, symbol);
  if (idx === -1) return favorites;
  return [...favorites.slice(0, idx), ...favorites.slice(idx + 1)];
}

/** バックエンド応答ステータスに応じたユーザー向けエラーメッセージを返す。 */
export function favoriteErrorMessage(status?: number, detail?: string): string {
  switch (status) {
    case 400:
      return detail ? `お気に入りに追加できません: ${detail}` : 'お気に入りに追加できません';
    case 409:
      return 'この銘柄は既にお気に入りに登録されています';
    case undefined:
      return 'お気に入りに追加できません（通信エラー）';
    default:
      return `お気に入りに追加できません（${status}）`;
  }
}