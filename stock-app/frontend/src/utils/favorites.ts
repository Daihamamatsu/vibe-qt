// お気に入り銘柄ユーティリティ (Issue #50)
// シンボル検証・リスト操作の純関数群とバックエンド API ヘルパー。
// バックエンド API（/api/favorites/、/api/favorite-lists/）の
// バリデーション・ステータスコードと整合した挙動をフロント側でも共用するためのモジュール。

import axios from 'axios';

/** お気に入り銘柄エントリ（バックエンド GET /api/favorites/ 応答の stocks 要素と同一形式）。 */
export interface FavoriteEntry {
  symbol: string;
  name: string;
}

/** お気に入りリストグループ（バックエンド GET /api/favorites/ 応答の要素、空リストも含まれる）。 */
export interface FavoriteGroup {
  id: number;
  name: string;
  stocks: FavoriteEntry[];
}

/** シンボル形式（バックエンド SYMBOL_RE と一致: 英大文字・数字・. - ^ =、最大 10 文字）。 */
export const SYMBOL_PATTERN = /^[A-Z0-9.\-^=]{1,10}$/;

/** シンボルが有効か判定する（trim / 大文字化してから検証）。 */
export function isValidSymbol(symbol: string): boolean {
  return SYMBOL_PATTERN.test(symbol.trim().toUpperCase());
}

/** リスト名の最大文字数（バックエンドのバリデーションと一致）。 */
export const LIST_NAME_MAX_LENGTH = 50;

/** リスト名が有効か判定する（trim 後: 空でなく LIST_NAME_MAX_LENGTH 字以内）。 */
export function isValidListName(name: string): boolean {
  const trimmed = name.trim();
  return trimmed.length > 0 && trimmed.length <= LIST_NAME_MAX_LENGTH;
}

/** リスト内のシンボル位置（大文字・小文字を無視）を探し、見つからなければ -1。 */
export function indexOfStock(
  stocks: readonly FavoriteEntry[],
  symbol: string,
): number {
  const target = symbol.trim().toUpperCase();
  return stocks.findIndex((f) => f.symbol === target);
}

/** シンボルがリストに登録されているか判定する（大文字・小文字を無視）。 */
export function isStockInList(
  stocks: readonly FavoriteEntry[],
  symbol: string,
): boolean {
  return indexOfStock(stocks, symbol) !== -1;
}

/** 指定リストにシンボルを追加したコピーを返す（既登録・リスト不在なら元参照をそのまま返す）。 */
export function addStockToList(
  groups: readonly FavoriteGroup[],
  listId: number,
  symbol: string,
  name = '',
): readonly FavoriteGroup[] {
  const target = symbol.trim().toUpperCase();
  let changed = false;
  const next = groups.map((g) => {
    if (g.id !== listId || isStockInList(g.stocks, target)) return g;
    changed = true;
    return { ...g, stocks: [...g.stocks, { symbol: target, name }] };
  });
  return changed ? next : groups;
}

/** 指定リストからシンボルを削除したコピーを返す（未登録・リスト不在なら元参照をそのまま返す）。 */
export function removeStockFromList(
  groups: readonly FavoriteGroup[],
  listId: number,
  symbol: string,
): readonly FavoriteGroup[] {
  const target = symbol.trim().toUpperCase();
  let changed = false;
  const next = groups.map((g) => {
    if (g.id !== listId) return g;
    const idx = indexOfStock(g.stocks, target);
    if (idx === -1) return g;
    changed = true;
    return { ...g, stocks: [...g.stocks.slice(0, idx), ...g.stocks.slice(idx + 1)] };
  });
  return changed ? next : groups;
}

/** バックエンド POST /api/favorites/ 応答ステータスに応じたユーザー向けエラーメッセージを返す。 */
export function favoriteErrorMessage(status?: number, detail?: string): string {
  switch (status) {
    case 400:
      return detail ? `お気に入りに追加できません: ${detail}` : 'お気に入りに追加できません';
    case 404:
      return 'リストが存在しません。リストを再取得してください';
    case 409:
      return 'この銘柄は既にこのリストに登録されています';
    case undefined:
      return 'お気に入りに追加できません（通信エラー）';
    default:
      return `お気に入りに追加できません（${status}）`;
  }
}

// =====================================================================
// バックエンド API ヘルパー (Issue #50)
// =====================================================================

/** GET /api/favorite-lists/ — 全リストと各リストの所属銘柄数を返す。 */
export async function fetchFavoriteLists(): Promise<
  { id: number; name: string; count: number }[]
> {
  const res = await axios.get('/api/favorite-lists/');
  return res.data;
}

/** GET /api/favorites/ — 全リスト（空リスト含む）と各リストの所属銘柄を返す。 */
export async function fetchFavoriteGroups(): Promise<FavoriteGroup[]> {
  const res = await axios.get('/api/favorites/');
  return res.data;
}

/** POST /api/favorite-lists/ — 新しいリストを作成する（成功時: 作成したリスト）。 */
export async function createFavoriteList(
  name: string,
): Promise<{ id: number; name: string }> {
  const res = await axios.post('/api/favorite-lists/', { name: name.trim() });
  return res.data;
}

/** PATCH /api/favorite-lists/<id>/ — リスト名を変更する（成功時: 更新後のリスト）。 */
export async function renameFavoriteList(
  listId: number,
  name: string,
): Promise<{ id: number; name: string }> {
  const res = await axios.patch(`/api/favorite-lists/${listId}/`, { name: name.trim() });
  return res.data;
}

/** DELETE /api/favorite-lists/<id>/ — リストを削除する（所属行も一緒に削除される）。 */
export async function deleteFavoriteList(listId: number): Promise<void> {
  await axios.delete(`/api/favorite-lists/${listId}/`);
}

/** POST /api/favorites/ — リストに銘柄を追加する（銘柄名はバックエンドが StockMeta から設定）。 */
export async function addFavoriteStock(
  listId: number,
  symbol: string,
): Promise<FavoriteEntry & { list_id: number }> {
  const res = await axios.post('/api/favorites/', {
    symbol: symbol.trim().toUpperCase(),
    list_id: listId,
  });
  return res.data;
}

/** DELETE /api/favorites/<list_id>/<symbol>/ — リストから銘柄を削除する。 */
export async function removeFavoriteStock(listId: number, symbol: string): Promise<void> {
  await axios.delete(`/api/favorites/${listId}/${symbol.trim().toUpperCase()}/`);
}