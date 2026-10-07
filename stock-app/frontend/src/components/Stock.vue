<template>
  <div class="stock-container">
    <!-- コントロールパネル -->
    <div class="control-panel" style="background:#f5f5f5;padding:1rem;border-radius:.5rem;margin-bottom:1.5rem;">
      <h3 style="margin-top:0;font-size:1.2rem;">
        株価データ
        <span v-if="stockName || stockSector" style="margin-left:.75rem;color:#555;font-size:1rem;font-weight:normal;">
          {{ stockName }}<template v-if="stockName && stockSector"> / </template>{{ stockSector }}
        </span>
      </h3>
      <div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap;">
        <label>シンボル:</label>
        <input v-model="symbol" placeholder="例：AAPL" />
        <!-- 銘柄名（Yahoo Finance 取得、Issue #49）: 取得不能時は非表示 -->
        <span v-if="stockName" style="color:#555;">{{ stockName }}</span>
        <!-- お気に入り切替 (Issue #50): 現在入力のシンボルをアクティブリストに追加/削除 -->
        <button
          :disabled="favoriteBusy"
          :title="isFavorite ? 'このリストから削除' : 'このリストにお気に入りを追加'"
          :style="{ fontSize: '1.2rem', padding: '0.2rem 0.5rem', cursor: favoriteBusy ? 'wait' : 'pointer' }"
          @click="isFavorite ? removeFavorite(symbol.trim().toUpperCase()) : addFavorite()"
        >{{ isFavorite ? '★' : '☆' }}</button>
        <label>期間:</label>
        <select v-model="period">
          <option value="5d">5d</option>
          <option value="1mo">1mo</option>
          <option value="3mo">3mo</option>
          <option value="6mo">6mo</option>
          <option value="1y">1y</option>
          <option value="2y">2y</option>
          <option value="5y">5y</option>
        </select>
        <label>表示:</label>
        <select v-model="displayPeriod">
          <option v-for="p in DISPLAY_PRESETS" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
        <label>本数:</label>
        <!-- 表示するローソク足の本数指定（空欄 = 表示期間に従う。本数指定が期間より優先される） -->
        <input v-model.number="displayCount" type="number" min="1" step="1" placeholder="期間に連動" style="width:5.5rem;" />
        <!-- OBV (On-Balance Volume) 表示トグル (Issue #61): ON 時、出来高の下に OBV パネルを追加 -->
        <label style="display:flex;gap:.35rem;align-items:center;">
          <input type="checkbox" v-model="obvEnabled" />
          OBV 表示
        </label>
        <button :disabled="fetching" @click="fetchStockData">取得</button>
        <button :disabled="fetching" @click="fetchFromYahoo">Yahoo Finance から取得</button>
      </div>
      <!-- Yahoo Finance 取得ステータス -->
      <p v-if="yahooMessage" :style="{ marginTop: '.5rem', marginBottom: 0, color: yahooError ? '#c0392b' : '#2c7a2c' }">
        {{ yahooMessage }}
      </p>
      <!-- お気に入り銘柄リスト (Issue #50): select ボックスでリスト選択、シンボルクリックでその銘柄へ切替 -->
      <div style="margin-top:.5rem;">
        <p style="margin:0 0 .25rem;font-weight:bold;">★ お気に入り</p>
        <div style="display:flex;gap:.25rem;align-items:center;flex-wrap:wrap;">
          <!-- リスト選択 (Issue #50): select ボックス。値は文字列で届くため onListSelectChange で数値化 -->
          <select
            :value="activeListId ?? ''"
            :disabled="favoriteBusy"
            title="リストを選択（お気に入りをこのリストに追加/削除）"
            style="min-width:11rem;"
            @change="onListSelectChange"
          >
            <option v-for="g in favoriteGroups" :key="g.id" :value="g.id">{{ g.name }}（{{ g.stocks.length }}）</option>
          </select>
          <button
            :disabled="favoriteBusy || activeListId === null"
            title="選択中のリストの名前を変更"
            @click="renameActiveList(activeListId)"
          >名前変更</button>
          <button
            :disabled="favoriteBusy || activeListId === null"
            title="選択中のリストを削除"
            @click="deleteActiveList(activeListId)"
          >削除</button>
          <button :disabled="favoriteBusy" title="新しいリストを作成" @click="createList">＋ 新しいリストを作成</button>
        </div>
        <p v-if="favoriteGroups.length === 0" style="margin:.25rem 0 0;color:#888;">リストがありません</p>
        <ul style="margin:.5rem 0 0;padding:0;">
          <li v-for="f in activeGroup?.stocks ?? []" :key="f.symbol" style="margin:.15rem 0;">
            <a href="#" :style="{ color:'#1a73e8' }" @click.prevent="symbol = f.symbol">{{ f.symbol }}</a>
            <button
              :disabled="favoriteBusy || activeGroup === null || activeGroup.stocks[0]?.symbol === f.symbol"
              style="margin-left:.5rem;"
              title="一つ上へ移動"
              @click="moveFavorite(f.symbol, 'up')"
            >↑</button>
            <button
              :disabled="favoriteBusy || activeGroup === null || activeGroup.stocks[activeGroup.stocks.length - 1]?.symbol === f.symbol"
              title="一つ下へ移動"
              @click="moveFavorite(f.symbol, 'down')"
            >↓</button>
            <span v-if="f.name" style="margin-left:.5rem;color:#555;">{{ f.name }}</span>
            <span v-if="f.sector" style="margin-left:.5rem;color:#777;font-size:.9rem;">（{{ f.sector }}）</span>
            <button :disabled="favoriteBusy" style="margin-left:.5rem;" title="このリストから削除" @click="removeFavorite(f.symbol)">✕</button>
          </li>
          <li v-if="(activeGroup?.stocks.length ?? 0) === 0" style="color:#888;">このリストには銘柄がありません</li>
        </ul>
        <p v-if="favoriteMessage" style="margin:.25rem 0 0;color:#c0392b;">{{ favoriteMessage }}</p>
      </div>
    </div>

    <!-- チャート表示（日足ローソク足 + 出来高バー + タートル ATR サブパネル + 下部ズームスライダー） -->
    <!-- chart-wrapper: 固定情報パネルの position 参照容器 -->
    <div ref="wrapperRef" class="chart-wrapper">
      <v-chart ref="chartRef" :option="chartOptions" :style="{ height: turtleEnabled || classicTurtleEnabled || obvEnabled ? '640px' : '480px' }" v-if="data.length > 0"></v-chart>
      <!-- 固定情報パネル: ホバー中のローソク足の正確な価格・出来高を表示（ヘッダーでドラッグ可能） -->
      <div v-if="data.length > 0" ref="panelRef" class="info-panel" :style="panelStyle">
        <!-- ドラッグバー: ポインターはここだけ捕捉する（本体はクリック透過でクロスヘア維持） -->
        <div
          class="info-panel-handle"
          @pointerdown="onPanelPointerDown"
          @pointermove="onPanelPointerMove"
          @pointerup="onPanelPointerUp"
          @pointercancel="onPanelPointerUp"
        >⠿ 現在値</div>
        <table class="info-table">
          <tbody>
            <tr><th>日付</th><td>{{ hoverRecord ? hoverRecord.date : '—' }}</td></tr>
            <tr><th>始値</th><td>{{ fmtPrice(hoverRecord?.open) }}</td></tr>
            <tr><th>高値</th><td>{{ fmtPrice(hoverRecord?.high) }}</td></tr>
            <tr><th>安値</th><td>{{ fmtPrice(hoverRecord?.low) }}</td></tr>
            <tr><th>終値</th><td>{{ fmtPrice(hoverRecord?.close) }}</td></tr>
            <tr>
              <th>前日比</th>
              <td :style="hoverChange ? { color: hoverChange.diff >= 0 ? '#e2534f' : '#3ba272' } : {}">
                {{
                  hoverChange
                    ? `${hoverChange.diff > 0 ? '+' : ''}${hoverChange.diff.toFixed(2)} (${hoverChange.diff > 0 ? '+' : ''}${hoverChange.pct.toFixed(2)}%)`
                    : '—'
                }}
              </td>
            </tr>
            <tr><th>出来高</th><td>{{ fmtVolume(hoverRecord?.volume) }}</td></tr>
            <!-- OBV (Issue #61): OBV 表示 ON 時のみ行を表示 -->
            <tr v-if="obvEnabled"><th>OBV</th><td>{{ fmtVolume(hoverObv) }}</td></tr>
          </tbody>
        </table>
        <!-- タートル戦略数値エリア (Issue #40): ホバー中のインデックス時点の数値を表示。
             現在値テーブルと区切りの入った独立セクションで、turtleEnabled に連動して表示・非表示。
             dataIndex マッピング・グリッド外出時の直近値保持・データ取得時のリセットは現在値パネルと共通の既存ロジックをそのまま利用する。 -->
        <div v-if="turtleEnabled" class="turtle-section">
          <div class="turtle-section-header">タートル戦略 (Donchian + ATR)</div>
          <table class="info-table">
            <tbody>
              <tr><th>日付</th><td>{{ hoverTurtle ? hoverTurtle.date : '—' }}</td></tr>
              <tr><th>DC20 (エントリーライン)</th><td>{{ fmtPrice(hoverTurtle?.donchianUpper) }}</td></tr>
              <tr><th>DC10 (手仕舞いライン)</th><td>{{ fmtPrice(hoverTurtle?.donchianLower) }}</td></tr>
              <tr><th>N (ATR)</th><td>{{ fmtPrice(hoverTurtle?.atr) }}</td></tr>
              <tr><th>トレーリングストップ</th><td>{{ fmtPrice(hoverTurtle?.trailingStop) }}</td></tr>
              <tr>
                <th>シグナル</th>
                <!-- 日本式カラー: BUY = 赤 / EXIT = 緑（チャート本体と同一） -->
                <td
                  :style="hoverTurtle?.buy
                    ? { color: '#e2534f', fontWeight: 'bold' }
                    : hoverTurtle?.exit
                      ? { color: '#3ba272', fontWeight: 'bold' }
                      : {}"
                >
                  {{ hoverTurtle?.buy ? 'BUY' : hoverTurtle?.exit ? 'EXIT' : '—' }}
                </td>
              </tr>
              <!-- OBV 検証 (Issue #63): BUY シグナル日のみ ①②③ を表示（OBV 表示トグル非依存） -->
              <tr v-if="hoverTurtle?.buy">
                <th>OBV検証</th>
                <td>
                  <span class="obv-cond" :class="hoverObvCheck?.c1 ? 'obv-ok' : 'obv-ng'">①</span>
                  <span class="obv-cond" :class="hoverObvCheck?.c2 ? 'obv-ok' : 'obv-ng'">②</span>
                  <span class="obv-cond" :class="hoverObvCheck?.c3 ? 'obv-ok' : 'obv-ng'">③</span>
                  <span v-if="hoverObvCheck?.all" class="obv-all">★</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="classicTurtleEnabled" class="turtle-section classic-hover-section">
          <div class="turtle-section-header">古典タートルズ</div>
          <table class="info-table">
            <tbody>
              <tr><th>日付</th><td>{{ hoverClassicDay ? hoverClassicDay.date : '—' }}</td></tr>
              <tr><th>S1 状態</th><td>{{ classicPositionLabel(hoverClassicDay?.position, 'system1') }}</td></tr>
              <tr><th>S1 エントリー</th><td>{{ fmtClassicEntryLine(hoverClassicDay, 'system1') }}</td></tr>
              <tr><th>S1 EXIT（チャネル）</th><td>{{ fmtClassicExitLine(hoverClassicDay, 'system1') }}</td></tr>
              <tr><th>S2 状態</th><td>{{ classicPositionLabel(hoverClassicDay?.position, 'system2') }}</td></tr>
              <tr><th>S2 エントリー</th><td>{{ fmtClassicEntryLine(hoverClassicDay, 'system2') }}</td></tr>
              <tr><th>S2 EXIT（チャネル）</th><td>{{ fmtClassicExitLine(hoverClassicDay, 'system2') }}</td></tr>
              <tr><th>N（20日 Wilder）</th><td>{{ fmtPrice(hoverClassicDay?.indicator.n) }}</td></tr>
              <tr><th>EXIT（エントリー時2N）</th><td>{{ fmtPrice(hoverClassicInitialStop) }}</td></tr>
              <tr><th>EXIT（直近計算2N）</th><td>{{ fmtPrice(hoverClassicCurrentStop) }}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 移動平均計算 -->
    <div class="moving-average-panel" style="margin-top:1rem;background:#f9f9f9;padding:.5rem;border-radius:.3rem;">
      <h4>移動平均</h4>
      <div style="display:flex;gap:.8rem;align-items:center;">
        <label>日数:</label>
        <input type="number" v-model.number="maDays" min="1" />
        <button @click="fetchMovingAverage">計算</button>
      </div>
      <p v-if="movingAverage !== null">{{ symbol }} の {{ maDays }} 日移動平均: {{ movingAverage.toFixed(2) }}</p>
    </div>

    <!-- タートル戦略 (Donchian Channel + ATR) -->
    <div class="turtle-panel" style="margin-top:1rem;background:#f9f9f9;padding:.5rem;border-radius:.3rem;">
      <h4>タートル戦略 (Donchian Channel + ATR)</h4>
      <div style="display:flex;gap:.8rem;align-items:center;flex-wrap:wrap;">
        <label><input type="checkbox" v-model="turtleEnabled" /> 表示</label>
        <label>ATR 期間 N:
          <select v-model.number="atrPeriod">
            <option :value="14">14</option>
            <option :value="20">20</option>
          </select>
        </label>
        <label>口座資金:
          <input type="number" v-model.number="accountValue" min="0" style="width:9rem;" />
        </label>
        <label>ブレイク日:
          <!-- BUY シグナル日のみ候補。選択時、買値が空欄ならその日終値が自動設定される -->
          <select v-model="turtleBreakoutDate" style="width:9.5rem;">
            <option v-for="d in buySignalDates" :key="d" :value="d">{{ d }}</option>
          </select>
        </label>
        <label>買値:
          <!-- 保存状態のある銘柄は復元値、ない銘柄は空欄（自動設定なし） -->
          <input type="number" v-model.number="turtleBuyPrice" min="0" style="width:7rem;" />
        </label>
      </div>
      <!-- 銘柄ごとの保存状態 (Issue #53) -->
      <div style="display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;">
        <span style="font-size:.85rem;" :style="hasSavedTurtleState ? { color: '#16a34a' } : { color: '#9ca3af' }">
          {{ hasSavedTurtleState ? '● 状態: 保存済み' : '○ 状態: 未保存' }}
        </span>
        <button type="button" :disabled="!isValidSymbol(currentTurtleSymbol)" @click="saveCurrentTurtleState">状態を保存</button>
        <button type="button" :disabled="!hasSavedTurtleState" @click="releaseCurrentTurtleState">状態を解除</button>
        <span v-if="turtleStateMessage" style="font-size:.8rem;color:#6b7280;">{{ turtleStateMessage }}</span>
      </div>
      <!-- OBV 検証 (Issue #63): 選択ブレイク日の ①②③ 条件結果を表示（OBV 表示トグル非依存）。
           全条件満たしのブレイクはチャート上、BUY マーカーが金色三角で識別される -->
      <div v-if="selectedBreakoutObvCheck !== null" class="obv-check-row">
        <span class="obv-check-label">OBV検証 ({{ selectedBreakoutObvCheck.date }})</span>
        <span class="obv-cond" :class="selectedBreakoutObvCheck.c1 ? 'obv-ok' : 'obv-ng'">
          ① OBV 20日最高値更新 {{ selectedBreakoutObvCheck.c1 ? '✓' : '✗' }}
        </span>
        <span class="obv-cond" :class="selectedBreakoutObvCheck.c2 ? 'obv-ok' : 'obv-ng'">
          ② {{ selectedBreakoutObvCheck.daysSinceLastBreakout === null ? 'BUY 履歴なし' : `前回BUYから ${selectedBreakoutObvCheck.daysSinceLastBreakout} 日` }} {{ selectedBreakoutObvCheck.c2 ? '✓' : '✗' }}
        </span>
        <span class="obv-cond" :class="selectedBreakoutObvCheck.c3 ? 'obv-ok' : 'obv-ng'">
          ③ 直近5日に OBV 高値更新 {{ selectedBreakoutObvCheck.c3 ? '✓' : '✗' }}
        </span>
        <span v-if="selectedBreakoutObvCheck.all" class="obv-all">★ 全条件有効（チャート: 金色三角）</span>
      </div>
      <table v-if="turtleEnabled && latestAtr !== null" class="turtle-table">
        <tbody>
          <tr>
            <th>直近 N (ATR)</th>
            <td>{{ latestAtr.toFixed(2) }}</td>
          </tr>
          <tr>
            <th>1ユニット推奨株数<br /><small>floor(口座資金×0.01 ÷ N)</small></th>
            <td>{{ accountValueNumber === null ? '—' : `${unitShares} 株` }}</td>
          </tr>
          <tr v-if="targets">
            <th>ピラミッド目標 / ストップ<br /><small>直近 N での再計算</small></th>
            <td>
              +0.5N: {{ targets.target1.toFixed(2) }} ／ +1.0N: {{ targets.target2.toFixed(2) }} ／
              +1.5N: {{ targets.target3.toFixed(2) }} ／ ストップ(-2N): {{ targets.stop.toFixed(2) }}
            </td>
          </tr>
          <tr v-if="turtlePlan">
            <th>買い増し計画 (P2/P3/P4)<br /><small>毎日 直前ユニットの目標ライン + 0.5 × N で再計算 (到達後はライン固定)</small></th>
            <td>
              +0.5N: {{ fmtPlanLevel(turtlePlan.levels[0]) }}<br />
              +1.0N: {{ fmtPlanLevel(turtlePlan.levels[1]) }}<br />
              +1.5N: {{ fmtPlanLevel(turtlePlan.levels[2]) }}
            </td>
          </tr>
          <tr v-if="turtlePlan">
            <th>EXIT 計画<br /><small>終値 ≤ 最新エントリー−2N または 終値 &lt; DC10</small></th>
            <td>{{ fmtPlanExit(turtlePlan) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="turtleEnabled && data.length > 0" class="turtle-hint">
        ATR を計算するには {{ atrPeriod }} 日以上のデータが必要です
      </p>
      <p v-if="turtleEnabled && latestAtr !== null && !turtlePlan" class="turtle-hint">
        買い増し / EXIT 計画を表示するにはブレイク日 (BUY シグナル日) を指定してください
      </p>
    </div>

    <!-- 古典的タートルズ (Richard Dennis / William Eckhardt) -->
    <div class="classic-turtle-panel">
      <h4>古典タートルズ (System 1 / System 2)</h4>
      <div class="classic-turtle-controls">
        <label><input type="checkbox" v-model="classicTurtleEnabled" /> 表示</label>
        <label>表示システム:
          <select v-model="classicTurtleSystem">
            <option value="both">System 1 + 2</option>
            <option value="system1">System 1</option>
            <option value="system2">System 2</option>
          </select>
        </label>
        <label>取引方向:
          <select v-model="classicTradeSide">
            <option value="both">ロング + ショート</option>
            <option value="long">ロングのみ</option>
            <option value="short">ショートのみ</option>
          </select>
        </label>
        <label>口座資金（{{ classicTurtleCurrency }}）:
          <input type="number" v-model.number="classicAccountValue" min="0" style="width:9rem;" />
        </label>
        <label>為替レート（円/USD）:
          <input type="number" v-model.number="classicUsdJpyRate" min="0.01" step="0.01" style="width:7rem;" />
        </label>
        <label>履歴開始日:
          <input type="date" v-model="classicTradeStartDate" />
        </label>
        <label>履歴終了日:
          <input type="date" v-model="classicTradeEndDate" />
        </label>
        <button
          v-if="classicTradeStartDate || classicTradeEndDate"
          type="button"
          @click="clearClassicTradePeriod"
        >期間をクリア</button>
        <label style="display:flex;gap:.35rem;align-items:center;">
          <input type="checkbox" v-model="classicObvFilterEnabled" />
          OBVフィルター
        </label>
        <label>OBV X（日）:
          <input type="number" v-model.number="classicObvX" min="1" step="1" style="width:4.5rem;" />
        </label>
        <label>OBV Y（日）:
          <input type="number" v-model.number="classicObvY" min="1" step="1" style="width:4.5rem;" />
        </label>
        <label>OBV Z（上位率）:
          <input type="number" v-model.number="classicObvZ" min="0" max="1" step="0.01" style="width:5rem;" />
        </label>
        <span class="classic-turtle-note">S1: 20日 / 決済10日、S2: 55日 / 決済20日、N: 20日Wilder</span>
      </div>
      <template v-if="classicTurtleEnabled">
        <div class="classic-turtle-summary">
          <span>完了取引: {{ classicClosedTrades.length }}件</span>
          <span :class="classicTotalPnl >= 0 ? 'classic-profit' : 'classic-loss'">損益: {{ fmtMoney(classicTotalPnl, classicTurtleCurrency) }}</span>
          <span>SQN: {{ classicSqn === null ? '—' : classicSqn.value.toFixed(2) }}</span>
          <span v-if="classicSqn !== null">平均R: {{ classicSqn.meanRiskMultiple.toFixed(2) }} / σ: {{ classicSqn.standardDeviation.toFixed(2) }}</span>
          <span v-if="classicTradePeriodLabel">対象期間: {{ classicTradePeriodLabel }}</span>
          <span v-if="classicObvFilterEnabled">OBV条件: 直前{{ classicObvXNumber }}日最大 ≥ 直前{{ classicObvYNumber }}日 {{ (classicObvZNumber * 100).toFixed(0) }}パーセンタイル</span>
          <span v-if="classicLatestPosition">
            保有: {{ classicLatestPosition.side === 'long' ? 'ロング' : 'ショート' }} {{ classicLatestPosition.entries.length }}ユニット
            （{{ classicHoldingShares }}株）
            ／ 次回買い増し: {{ classicLatestPosition.nextAddPrice === null ? 'なし' : fmtPrice(classicLatestPosition.nextAddPrice) }}
            ／ 現在の2N損切り: {{ fmtPrice(classicLatestPosition.stopPrice) }}
          </span>
          <span v-else>保有: なし</span>
        </div>
        <table v-if="classicFilteredTrades.length > 0" class="turtle-table classic-trades">
          <thead><tr><th>System</th><th>方向</th><th>エントリー詳細（1ユニット株数 / 購入価格 / N / 2N損切り）</th><th>決済</th><th>損益</th><th>R</th></tr></thead>
          <tbody>
            <tr v-for="(trade, index) in classicFilteredTrades" :key="`${trade.system}-${trade.side}-${index}`">
              <td>{{ trade.system === 'system1' ? 'S1' : 'S2' }}</td>
              <td>{{ trade.side === 'long' ? 'Long' : 'Short' }}</td>
              <td>
                <div class="classic-unit-shares">
                  1ユニット: {{ trade.entries[0]?.shares ?? 0 }}株 / 平均取得価格: {{ fmtPrice(computeClassicAverageEntryPrice(trade.entries)) }}
                </div>
                <div
                  v-for="entry in classicEntryRows(trade)"
                  :key="`${entry.unit}-${entry.date}-${entry.price}`"
                  class="classic-entry-detail"
                  :class="{ 'classic-entry-pending': entry.pending }"
                >
                  <template v-if="entry.pending">
                    U{{ entry.unit }} 未到達 / 買い増し価格 {{ fmtPrice(entry.price) }} / {{ entry.shares }}株
                  </template>
                  <template v-else>
                    U{{ entry.unit }} {{ entry.date }} / 購入価格 {{ fmtPrice(entry.price) }} / {{ entry.shares }}株 / N={{ fmtPrice(entry.n) }} / 2N={{ fmtPrice(classicStopPrice(entry)) }}
                  </template>
                </div>
              </td>
              <td>{{ trade.exit ? `${trade.exit.date} / ${fmtPrice(trade.exit.price)}` : '保有中' }}</td>
              <td :class="trade.pnl >= 0 ? 'classic-profit' : 'classic-loss'">{{ fmtMoney(trade.pnl, classicTurtleCurrency) }}</td>
              <td>{{ trade.riskMultiple.toFixed(2) }}R</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="turtle-hint">表示可能な古典タートルズ取引はありません。</p>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import axios from 'axios';
import VChart from 'vue-echarts';
import type { EChartsOption, SeriesOption } from 'echarts';
// vue-echarts v8 では echarts のレンダラー・チャート・コンポーネントを
// アプリ側で登録する必要がある（公式 README のサンプルを参照）
import { use } from 'echarts/core';
import type { EChartsType } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, CandlestickChart, LineChart, ScatterChart } from 'echarts/charts';
import { TooltipComponent, GridComponent, DataZoomComponent, TitleComponent } from 'echarts/components';
// 表示ウィンドウ（表示期間 / ローソク足本数）計算モジュール
import { DISPLAY_PRESETS, chartTitle, getDisplayRange } from '../utils/display';
// 引け後自動リフレッシュ判定モジュール（同日レコードを引け後最終値へ更新する）
import { shouldAutoRefreshYahoo } from '../utils/freshness';
// タートルズ型 (Donchian + ATR) 計算モジュール（ルックアヘッドなし: 前日までのデータのみ使用）
import { computePyramidTargets, computeTurtle, computeTurtlePlan, computeUnitShares } from '../utils/turtle';
import type { PyramidTargets, TurtleBar, TurtlePlan, TurtlePlanLevel } from '../utils/turtle';
import { backtestClassicTurtle, computeClassicAverageEntryPrice, computeClassicTurtleSqn, filterClassicTurtleTrades } from '../utils/classicTurtle';
import type { ClassicTradeSideFilter, ClassicTurtleBacktest, ClassicTurtleDay, ClassicTurtleEntry, ClassicTurtlePosition, ClassicTurtleTrade, TurtleSystem } from '../utils/classicTurtle';
import {
  DEFAULT_USD_JPY_RATE,
  convertAccountEquity,
  convertToAccountEquityYen,
  getClassicTurtleCurrency,
  loadClassicTurtleSettings,
  saveClassicTurtleSettings,
} from '../utils/classicTurtleSettings';
// OBV (On-Balance Volume) 計算モジュール (Issue #61 / タートル BUY ブレイクの OBV 検証 Issue #63)
import {
  DEFAULT_CLASSIC_TURTLE_OBV_X,
  DEFAULT_CLASSIC_TURTLE_OBV_Y,
  DEFAULT_CLASSIC_TURTLE_OBV_Z,
  computeObv,
  computeBreakoutObvChecks,
  evaluateClassicTurtleObvFilter,
} from '../utils/obv';
import type { BreakoutObvCheck } from '../utils/obv';
// タートル戦略の銘柄ごとの保存状態（localStorage 永続化。Issue #53）
import {
  buildTurtleState,
  clearTurtleState,
  loadAllTurtleStates,
  normalizeTurtleSymbol,
  saveTurtleState,
  type TurtleState,
} from '../utils/turtleState';
import {
  SYMBOL_PATTERN,
  LIST_NAME_MAX_LENGTH,
  addFavoriteStock,
  createFavoriteList,
  deleteFavoriteList,
  favoriteErrorMessage,
  fetchFavoriteGroups,
  isValidListName,
  isValidSymbol,
  moveStockInList,
  removeFavoriteStock,
  renameFavoriteList,
  updateFavoriteOrder,
} from '../utils/favorites';
import type { FavoriteGroup } from '../utils/favorites';

use([CanvasRenderer, CandlestickChart, BarChart, LineChart, ScatterChart, TooltipComponent, GridComponent, DataZoomComponent, TitleComponent]);

interface StockRecord {
  id: number;
  symbol: string;
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

// 大きな数を K/M 単位でコンパクトに表示（例: 30000000 -> "30M"）。
// 出来高軸のラベルと tooltip の両方で使用する。
function formatCompact(value: number): string {
  if (value >= 1e6) return `${(value / 1e6).toFixed(1).replace(/\.0$/, '')}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1).replace(/\.0$/, '')}K`;
  return `${value}`;
}

const symbol = ref('AAPL');
// 銘柄名（Yahoo Finance、Issue #49）: 株価データ表示付近に示す
const stockName = ref('');
const stockSector = ref('');
// Yahoo Finance 取得期間（yfinance の period 値）
const period = ref('1mo');
// シンボル入力の銘柄名取得デバウンス (Issue #49)
let metaTimer: ReturnType<typeof setTimeout> | null = null;
// =====================================================================
// お気に入り銘柄リスト (Issue #50)
// =====================================================================
// 全リスト（空リスト含む）と所属銘柄（バックエンド GET /api/favorites/、作成順）。
// 銘柄名はバックエンドが StockMeta と同期するので、ここでは表示のみ。
const favoriteGroups = ref<FavoriteGroup[]>([]);
// 現在選択中のリスト ID（null = なし。最後にリストを削除した直後など）
const activeListId = ref<number | null>(null);
// お気に入り・リスト操作の操作中フラグ（二重クリック防止）
const favoriteBusy = ref(false);
// お気に入り操作のメッセージ（エラー表示用）
const favoriteMessage = ref('');
// 現在選択中のリスト（未選択なら null）
const activeGroup = computed(
  () => favoriteGroups.value.find((g) => g.id === activeListId.value) ?? null,
);
// 現在入力のシンボルがアクティブリストに登録されているか（大文字・小文字を無視）
const isFavorite = computed(
  () =>
    activeGroup.value !== null &&
    activeGroup.value.stocks.some((f) => f.symbol === symbol.value.trim().toUpperCase()),
);
const data = ref<StockRecord[]>([]);
// 表示ウィンドウ: 表示期間プリセット（営業日換算、既定は 1 年分を表示）
const displayPeriod = ref('1y');
// 表示ウィンドウ: ローソク足本数指定（表示期間より優先。null / 空欄 = 期間に従う）
const displayCount = ref<number | string | null>(null);
// vue-echarts コンポーネント参照（dispatchAction でズームを操作するため）
const chartRef = ref<InstanceType<typeof VChart> | null>(null);
// チャート容器参照（固定情報パネルの position 基準）
const wrapperRef = ref<HTMLDivElement | null>(null);
// 固定情報パネルの要素参照（クランプ時にサイズを測定する）
const panelRef = ref<HTMLDivElement | null>(null);
// ブラウザ自動化での挙動確認のためチャート参照を公開（開発サーバーのみ、本番ビルドには含まれない）(Issue #36)
if (import.meta.env.DEV) {
  (window as Window & { __stockChartRef?: typeof chartRef }).__stockChartRef = chartRef;
}

// =====================================================================
// マウスホイール操作 (Issue #36): Ctrl+ホイール = ズーム / 通常ホイール = パン
// ECharts 内蔵の inside-dataZoom ではこの 2 つを分離できない（Ctrl+ホイールで
// ズームとスクロールが同時に発動するため）、内蔵のホイール処理は
// zoomOnMouseWheel / moveOnMouseWheel = false で無効化し、こちらで実装する。
// （ドラッグパンは内蔵の moveOnMouseMove を使い続ける）
// handler はチャート容器にキャプチャ位相で付け、そこでイベントを消費するため、
// 同じホイールイベントが ECharts 内部の roam にも渡らず二重適用されない。
// =====================================================================
const WHEEL_MIN_SPAN = 2; // dataZoom-inside の minSpan と一致させること
const WHEEL_STEP_PX = 120; // ホイール 1 ステップに相当する deltaY のピクセル数
const WHEEL_MAX_STEPS = 3; // 1 イベントで処理するステップ数の上限（高速スクロールの暴走防止）
const ZOOM_FACTOR_PER_STEP = 1.1; // ステップあたりのズーム係数（最大 1.1^3 ≒ 1.33）
const PAN_RATIO_PER_STEP = 0.05; // ステップあたりのパン量（表示幅の 5%）
const WHEEL_THROTTLE_MS = 100; // ECharts 内蔵 roam と同じ 100ms fixRate 絞り込み

type WheelGridRect = { x: number; y: number; width: number; height: number };

// vue-echarts のコンポーネント参照から ECharts インスタンスを取得（未初期化時 null）
function getChartInstance(): EChartsType | null {
  const chart = chartRef.value?.chart;
  // vue-echarts の型定義では chart が ShallowRef だが、アクセス時には既にアンラップされて
  // ECharts インスタンスそのものが返る
  return (chart as unknown as EChartsType | undefined) ?? null;
}

// 全グリッドの矩形（チャート未準備時は null）
function getGridRects(m: unknown): WheelGridRect[] | null {
  const getComponent = (
    m as {
      getComponent?: (type: string, index: number) => {
        coordinateSystem?: { getRect?: () => WheelGridRect };
      } | undefined;
    }
  )?.getComponent;
  if (typeof getComponent !== 'function') return null;
  const grids: WheelGridRect[] = [];
  for (let i = 0; ; i++) {
    const gridModel = getComponent.call(m, 'grid', i);
    const rect = gridModel?.coordinateSystem?.getRect?.();
    if (!gridModel || !rect) break;
    grids.push(rect);
  }
  return grids.length > 0 ? grids : null;
}

// 現在可視のローソク足が乗っている dataZoom (inside) の表示範囲 (percent) を取得
function getVisiblePercentRange(m: unknown): { start: number; end: number } {
  const dzModel = (
    m as {
      getComponent?: (type: string, index: number) => {
        get?: (key: string) => unknown;
      } | undefined;
    }
  )?.getComponent?.('dataZoom', 0);
  const start = dzModel?.get?.('start');
  const end = dzModel?.get?.('end');
  return typeof start === 'number' && typeof end === 'number' ? { start, end } : { start: 0, end: 100 };
}

// 新規表示範囲を適用（dispatchAction dataZoom。link された全 dataZoom がまとめて更新される）
function applyWheelRange(start: number, end: number) {
  const inst = getChartInstance();
  if (!inst || inst.isDisposed()) return;
  inst.dispatchAction({
    type: 'dataZoom',
    start,
    end,
    // ECharts 内蔵 roam と同じアニメーションパラメータ
    animation: { easing: 'cubicOut', duration: 100 },
  });
}

let wheelThrottleTimer: ReturnType<typeof setTimeout> | null = null;
let wheelNextAllowedAt = 0;

// fixRate 絞り込み（ECharts 内蔵 roam と同じ挙動）: 100ms ごとに最大 1 回。
// 間に溜まったイベントは最後の範囲のみが有効。
function throttledApplyRange(start: number, end: number) {
  const now = Date.now();
  const delay = Math.max(0, wheelNextAllowedAt - now);
  if (wheelThrottleTimer !== null) {
    // 未適用の古い範囲を破棄（最新の範囲を優先する fixRate の语义）
    clearTimeout(wheelThrottleTimer);
    wheelThrottleTimer = null;
  }
  wheelNextAllowedAt = now + WHEEL_THROTTLE_MS;
  if (delay === 0) {
    applyWheelRange(start, end);
  } else {
    wheelThrottleTimer = setTimeout(() => {
      wheelThrottleTimer = null;
      applyWheelRange(start, end);
    }, delay);
  }
}

function onChartWheel(e: WheelEvent) {
  const inst = getChartInstance();
  const rootEl = (chartRef.value?.root as unknown as HTMLElement | undefined) ?? null;
  if (!inst || !rootEl) return;
  // ヒット判定: プロット領域内（ローソク足グリッドの x 範囲 × 全グリッドの y 範囲）でのみ反応し、
  // 外側ではイベントを通す（ページが通常通りスクロールできる）
  // getModel は型定義上 private なので、必要な部分だけ拾う型にキャストする
  const gm = (inst as unknown as { getModel: () => unknown }).getModel();
  const grids = getGridRects(gm);
  if (!grids || grids[0].width <= 0) return;
  const box = rootEl.getBoundingClientRect();
  const px = e.clientX - box.left;
  const py = e.clientY - box.top;
  const gridX0 = grids[0].x;
  const gridX1 = gridX0 + grids[0].width;
  let gridTop = Infinity;
  let gridBottom = -Infinity;
  for (const g of grids) {
    gridTop = Math.min(gridTop, g.y);
    gridBottom = Math.max(gridBottom, g.y + g.height);
  }
  if (px < gridX0 || px > gridX1 || py < gridTop || py > gridBottom) return;
  // イベントを消費: ページスクロール抑制 + ECharts 内部 roam での二重処理防止
  e.preventDefault();
  e.stopPropagation();

  const { start, end } = getVisiblePercentRange(gm);
  const span = Math.min(Math.max(end - start, WHEEL_MIN_SPAN), 100);

  // ホイール量をステップ化（deltaMode=1 は行単位のため 40px/行 に換算）
  const rawDelta = e.deltaY === 0 ? e.deltaX : e.deltaY;
  if (rawDelta === 0) return;
  const delta = e.deltaMode === 1 ? rawDelta * 40 : rawDelta;
  const steps = Math.min(WHEEL_MAX_STEPS, Math.max(1, Math.round(Math.abs(delta) / WHEEL_STEP_PX)));

  if (e.ctrlKey || e.metaKey) {
    // ズーム（カーソル位置のデータを固定して縮放）: スクロール下 = ズームイン / 上 = ズームアウト
    const factor = Math.pow(ZOOM_FACTOR_PER_STEP, steps);
    const newSpan = Math.min(Math.max(span * (delta > 0 ? 1 / factor : factor), WHEEL_MIN_SPAN), 100);
    // カーソル位置に対応する percent
    const cursor = ((px - gridX0) / grids[0].width) * span + start;
    const ratio = newSpan / span;
    const s = Math.min(Math.max(cursor - (cursor - start) * ratio, 0), 100 - newSpan);
    throttledApplyRange(s, s + newSpan);
  } else {
    // パン: ホイール下 = 新データ側へ (start 増) / ホイール上 = 旧データ側へ (start 減)
    // （ECharts 内蔵 moveOnMouseWheel と同じ方向: 上 = 旧データ側へ移動）
    const shift = span * PAN_RATIO_PER_STEP * steps * (delta > 0 ? 1 : -1);
    const s = Math.min(Math.max(start + shift, 0), 100 - span);
    throttledApplyRange(s, s + span);
  }
}

// カスタム wheel handler の install / 外しをチャート実例のライフサイクルに合わせて行う
// （v-chart はシンボル切替・データ消去時の再マウントで容器も実例も入れ替わるため）
let removeWheelListener: (() => void) | null = null;
// 'updateAxisPointer' イベントの購読解除関数（固定情報パネル用）
let removeAxisPointerHandler: (() => void) | null = null;
// チャート容器の ResizeObserver 破棄関数（情報パネルの位置を再クランプする）
let removePanelResizeObserver: (() => void) | null = null;

// 'updateAxisPointer' イベントのハンドラ: ホバー中のローソク足の dataIndex（生インデックス）で
// 固定情報パネルを更新する。グリッド外など dataIndex が無い場合は更新せず直近の値を保持する
function onAxisPointerUpdate(...args: unknown[]) {
  const params = args[0] as { dataIndex?: number } | undefined;
  const i = params?.dataIndex;
  if (typeof i === 'number' && i >= 0 && i < data.value.length) {
    hoverIndex.value = i;
  }
}

watch(
  () => chartRef.value?.chart,
  (chart) => {
    removeWheelListener?.();
    removeWheelListener = null;
    removeAxisPointerHandler?.();
    removeAxisPointerHandler = null;
    removePanelResizeObserver?.();
    removePanelResizeObserver = null;
    if (!chart) return;
    const rootEl = (chartRef.value?.root as unknown as HTMLElement | undefined) ?? null;
    if (!rootEl) return;
    rootEl.addEventListener('wheel', onChartWheel, { passive: false, capture: true });
    removeWheelListener = () => {
      rootEl.removeEventListener('wheel', onChartWheel, { capture: true });
    };
    // 固定情報パネル: 軸カーソルイベントに購読する。
    // ECharts はアクション由来のイベント名を小文字化して発火するため
    // （registerAction 内で createEventType が toLowerCase）、実際には発火する
    // 小文字版と、将来のバージョンのために大文字版の両方に購読する。
    // payload は axisTrigger の戻り値で、ホバー中のローソク足の生 dataIndex を持つ
    // （グリッド外 = leave の時は dataIndex が無い）
    const inst = chart as unknown as EChartsType;
    for (const name of ['updateAxisPointer', 'updateaxispointer']) {
      inst.on(name, onAxisPointerUpdate);
    }
    removeAxisPointerHandler = () => {
      for (const name of ['updateAxisPointer', 'updateaxispointer']) {
        inst.off(name, onAxisPointerUpdate);
      }
    };
    // 固定情報パネル: 容器サイズが変わった時（タートル表示の切替 / ウィンドウリサイズ）に
    // パネル位置を再クランプする
    const wrapperEl = wrapperRef.value;
    if (wrapperEl && typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(() => {
        clampPanelPos();
      });
      ro.observe(wrapperEl);
      removePanelResizeObserver = () => {
        ro.disconnect();
      };
    }
  },
);
onBeforeUnmount(() => {
  removeWheelListener?.();
  removeWheelListener = null;
  removeAxisPointerHandler?.();
  removeAxisPointerHandler = null;
  removePanelResizeObserver?.();
  removePanelResizeObserver = null;
  if (wheelThrottleTimer !== null) clearTimeout(wheelThrottleTimer);
  if (metaTimer !== null) clearTimeout(metaTimer);
});

const maDays = ref(5);
const movingAverage = ref<number | null>(null);
const fetching = ref(false);
const yahooMessage = ref('');
const yahooError = ref(false);
// --- OBV (On-Balance Volume) 表示トグル (Issue #61): ON 時、出来高の下に OBV パネルを追加 ---
const obvEnabled = ref(false);

// --- 古典タートルズ (System 1 / System 2) ---
// 既存の簡略版タートルズとは独立して表示・計算する。
const classicTurtleEnabled = ref(true);
const classicTurtleSystem = ref<TurtleSystem | 'both'>('both');
const classicTradeSide = ref<ClassicTradeSideFilter>('both');
const classicSettings = ref(loadClassicTurtleSettings());
const classicAccountEquityYen = ref(classicSettings.value.accountEquityYen);
const classicUsdJpyRate = ref<number | string>(classicSettings.value.usdJpyRate);
const classicTradeStartDate = ref('');
const classicTradeEndDate = ref('');
const classicObvFilterEnabled = ref(true);
const classicObvX = ref<number | string>(DEFAULT_CLASSIC_TURTLE_OBV_X);
const classicObvY = ref<number | string>(DEFAULT_CLASSIC_TURTLE_OBV_Y);
const classicObvZ = ref<number | string>(DEFAULT_CLASSIC_TURTLE_OBV_Z);

const classicTurtleCurrency = computed(() => getClassicTurtleCurrency(symbol.value));
const classicUsdJpyRateNumber = computed(() => {
  const value = classicUsdJpyRate.value;
  const numberValue = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numberValue) && numberValue > 0 ? numberValue : DEFAULT_USD_JPY_RATE;
});
// 表示通貨の入力値を円建ての共通資金へ変換する writable computed。
// 米国株で編集しても共通円資金が更新され、日本株の表示へ反映される。
const classicAccountValue = computed<number | null>({
  get: () => convertAccountEquity(
    classicAccountEquityYen.value,
    classicTurtleCurrency.value,
    classicUsdJpyRateNumber.value,
  ),
  set: (value) => {
    const numberValue = typeof value === 'number' ? value : Number(value);
    if (!Number.isFinite(numberValue) || numberValue < 0) return;
    classicAccountEquityYen.value = convertToAccountEquityYen(
      numberValue,
      classicTurtleCurrency.value,
      classicUsdJpyRateNumber.value,
    );
  },
});

const classicAccountValueNumber = computed<number | null>(() => {
  const value = classicAccountValue.value;
  return value !== null && Number.isFinite(value) ? value : null;
});

const classicObvXNumber = computed(() => {
  const value = typeof classicObvX.value === 'number' ? classicObvX.value : Number(classicObvX.value);
  return Number.isInteger(value) && value > 0 ? value : DEFAULT_CLASSIC_TURTLE_OBV_X;
});
const classicObvYNumber = computed(() => {
  const value = typeof classicObvY.value === 'number' ? classicObvY.value : Number(classicObvY.value);
  return Number.isInteger(value) && value > 0 ? value : DEFAULT_CLASSIC_TURTLE_OBV_Y;
});
const classicObvZNumber = computed(() => {
  const value = typeof classicObvZ.value === 'number' ? classicObvZ.value : Number(classicObvZ.value);
  return Number.isFinite(value) && value >= 0 && value <= 1 ? value : DEFAULT_CLASSIC_TURTLE_OBV_Z;
});

watch([classicAccountEquityYen, classicUsdJpyRateNumber], () => {
  const settings = {
    accountEquityYen: classicAccountEquityYen.value,
    usdJpyRate: classicUsdJpyRateNumber.value,
  };
  classicSettings.value = settings;
  saveClassicTurtleSettings(settings);
});

// --- タートル戦略 (Donchian Channel + ATR) の状態 (Issue #53: 既定値なし・保存状態のみ使用) ---
const turtleEnabled = ref(false);
const atrPeriod = ref(20); // N (ATR) の期間: 14 / 20
const accountValue = ref<number | string | null>(null); // 口座資金（保存状態のない銘柄は空欄）
const turtleBuyPrice = ref<number | string | null>(null); // 買値（保存状態のない銘柄は空欄）
// ブレイク日 (BUY シグナル日。保存状態のない銘柄は空欄)
const turtleBreakoutDate = ref<string | null>(null);
// --- タートル戦略の銘柄ごとの保存状態 (Issue #53) ---
const turtleStates = ref<Record<string, TurtleState>>(loadAllTurtleStates());
const turtleStateMessage = ref('');

// Donchian バンド / ATR / BUY・EXIT シグナルの計算結果
// （ルックアヘッド回避: バンドと判定は前日までのデータのみ参照）
const turtle = computed<TurtleBar[]>(() =>
  computeTurtle(data.value, { atrPeriod: atrPeriod.value }),
);
// OBV (On-Balance Volume) の計算結果 (Issue #61)
// 初日 OBV = 初日出来高。①上昇日 +出来高 ②下降日 −出来高 ③同値日 不変
const obv = computed(() => computeObv(data.value));

// 古典仕様のバックテスト結果。口座資金は表示中の通貨へ換算して渡す。
const classicTurtle = computed<ClassicTurtleBacktest>(() =>
  backtestClassicTurtle(data.value, {
    accountEquity: classicAccountValueNumber.value ?? 0,
    nPeriod: 20,
  }),
);
const classicVisibleTrades = computed<ClassicTurtleTrade[]>(() =>
  classicTurtle.value.trades
    .filter(trade =>
      classicTurtleSystem.value === 'both' || trade.system === classicTurtleSystem.value,
    )
    // 取引履歴は初回エントリー日が新しいものから表示する。
    .sort((a, b) => (b.entries[0]?.date ?? '').localeCompare(a.entries[0]?.date ?? '')),
);
// チャート上の古典マーカーにも、パネルの取引方向選択を適用する。
const classicChartTrades = computed<ClassicTurtleTrade[]>(() =>
  classicVisibleTrades.value.filter(trade =>
    classicTradeSide.value === 'both' || trade.side === classicTradeSide.value,
  ),
);
const classicObvFilteredTrades = computed<ClassicTurtleTrade[]>(() => {
  if (!classicObvFilterEnabled.value) return classicVisibleTrades.value;
  return classicVisibleTrades.value.filter((trade) => {
    const entryDate = trade.entries[0]?.date;
    if (!entryDate) return false;
    const result = evaluateClassicTurtleObvFilter(
      obv.value,
      entryDate,
      classicObvXNumber.value,
      classicObvYNumber.value,
      classicObvZNumber.value,
      trade.side,
    );
    return result?.passed === true;
  });
});
const classicFilteredTrades = computed<ClassicTurtleTrade[]>(() =>
  filterClassicTurtleTrades(classicObvFilteredTrades.value, classicTradeSide.value).filter((trade) => {
    const entryDate = trade.entries[0]?.date;
    if (!entryDate) return false;
    if (classicTradeStartDate.value && entryDate < classicTradeStartDate.value) return false;
    if (classicTradeEndDate.value && entryDate > classicTradeEndDate.value) return false;
    return true;
  }),
);
const classicClosedTrades = computed(() =>
  classicFilteredTrades.value.filter(trade => trade.exit !== null),
);
const classicTotalPnl = computed(() =>
  classicClosedTrades.value.reduce((sum, trade) => sum + trade.pnl, 0),
);
const classicSqn = computed(() => computeClassicTurtleSqn(classicClosedTrades.value));
const classicTradePeriodLabel = computed(() => {
  if (!classicTradeStartDate.value && !classicTradeEndDate.value) return '';
  return `${classicTradeStartDate.value || '最初'} ～ ${classicTradeEndDate.value || '最後'}`;
});

function clearClassicTradePeriod(): void {
  classicTradeStartDate.value = '';
  classicTradeEndDate.value = '';
}
const classicLatestPosition = computed(() => {
  for (let i = classicTurtle.value.days.length - 1; i >= 0; i--) {
    const position = classicTurtle.value.days[i].position;
    if (position !== null && (classicTurtleSystem.value === 'both' || position.system === classicTurtleSystem.value)) {
      return position;
    }
  }
  return null;
});
const classicHoldingShares = computed(() =>
  classicLatestPosition.value?.entries.reduce((sum, entry) => sum + entry.shares, 0) ?? 0,
);

// 直近の N (ATR): ATR が計算できる最新の日の値
const latestAtr = computed<number | null>(() => {
  const rows = turtle.value;
  for (let i = rows.length - 1; i >= 0; i--) {
    const v = rows[i].atr;
    if (v !== null) return v;
  }
  return null;
});
// 口座資金の数値形（未指定 / 数値でなければ null）
const accountValueNumber = computed<number | null>(() => {
  const v = accountValue.value;
  if (v === null || v === '') return null;
  const num = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(num) ? num : null;
});
// 買値の数値形（未指定 / 数値でなければ null）
const turtleBuyPriceNumber = computed<number | null>(() => {
  const v = turtleBuyPrice.value;
  if (v === null || v === '') return null;
  const num = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(num) ? num : null;
});
// 現在表示中のシンボル（大文字正規化済み）
const currentTurtleSymbol = computed(() => normalizeTurtleSymbol(symbol.value));
// 現在表示中の銘柄の保存済み状態（未保存なら undefined）
const savedTurtleState = computed<TurtleState | undefined>(() => turtleStates.value[currentTurtleSymbol.value]);
const hasSavedTurtleState = computed(() => savedTurtleState.value !== undefined);
// ピラミッディング目標 (+0.5N / +1.0N / +1.5N) とストップロス (-2N)
const targets = computed<PyramidTargets | null>(() => {
  const price = turtleBuyPriceNumber.value;
  const atr = latestAtr.value;
  if (price === null || price <= 0 || atr === null || atr <= 0) return null;
  return computePyramidTargets(price, atr);
});
// 1 ユニットの推奨購入株数: floor((口座資金 * 0.01) / N)
// （株式は 1 ポイントあたり価値 = 1 固定のため買値は掛けない）
const unitShares = computed<number>(() => {
  const av = accountValueNumber.value;
  const atr = latestAtr.value;
  if (av === null || atr === null || atr <= 0) return 0;
  return computeUnitShares(av, atr);
});
// ブレイク日の候補 (BUY シグナルが出た日付の昇順リスト)
const buySignalDates = computed<string[]>(() =>
  turtle.value.filter(r => r.buy).map(r => r.date),
);
// OBV 検証 (Issue #63): 全 BUY シグナル日について ①②③ 条件を評価（日付をキーに持つ Map）。
// チャートの BUY マーカー色分け・タートルパネル / 情報パネルの OBV 検証表示に使用する。
// OBV 表示トグル (obvEnabled) には依存しない（データがあれば常に利用可能）。
const breakoutObvChecks = computed(() =>
  computeBreakoutObvChecks(data.value, obv.value, buySignalDates.value),
);
// 選択中のブレイク日の OBV 検証結果（BUY シグナル日でなければ null）
const selectedBreakoutObvCheck = computed<BreakoutObvCheck | null>(() => {
  const d = turtleBreakoutDate.value;
  if (d === null) return null;
  return breakoutObvChecks.value.get(d) ?? null;
});
// タートル計画: ブレイク日以降の買い増し (P2/P3/P4) と EXIT を機械的にシミュレートする
// （毎日その日の N で目標・ストップを再計算。詳細は turtle.ts の computeTurtlePlan 参照）
const turtlePlan = computed<TurtlePlan | null>(() => {
  const d = turtleBreakoutDate.value;
  const price = turtleBuyPriceNumber.value;
  if (!d || price === null || price <= 0) return null;
  if (!buySignalDates.value.includes(d)) return null;
  return computeTurtlePlan(turtle.value, d, price);
});
// 買い増し計画の行表示 (到達: 日付・目標・終値 / 未到達: 「未到達」)
function fmtPlanLevel(lv: TurtlePlanLevel): string {
  if (lv.date === null) return '未到達';
  return `${lv.date} (目標 ${fmtPrice(lv.price)} / 終値 ${fmtPrice(lv.hitClose)})`;
}
// EXIT 計画の行表示 (到達: 日付・理由・終値 / 未到達: 「未到達」)
function fmtPlanExit(plan: TurtlePlan): string {
  if (plan.exit.date === null) return '未到達';
  const reason =
    plan.exit.reason === 'stop'
      ? 'ストップロス (終値 ≤ 最新エントリー−2N)'
      : 'DC10 下抜け (終値 < DC10)';
  return `${plan.exit.date} ${reason} (終値 ${fmtPrice(plan.exit.close)})`;
}
// ブレイク日選択で買値が空欄のときはその日終値を自動設定（既に入力 / 復元済みの場合は上書きしない）
watch(turtleBreakoutDate, (d) => {
  const bp = turtleBuyPrice.value;
  if (d === null || (bp !== null && bp !== '')) return;
  const row = turtle.value.find(r => r.date === d);
  if (row) turtleBuyPrice.value = Number(row.close);
});

// =====================================================================
// タートル戦略の銘柄ごとの保存状態 (Issue #53)
// =====================================================================

// 指定銘柄の保存状態を復元する（保存状態のない銘柄は全入力を空欄に戻す）
function applyTurtleState(sym: string): void {
  const st = turtleStates.value[normalizeTurtleSymbol(sym)];
  if (st) {
    accountValue.value = st.accountValue;
    atrPeriod.value = st.atrPeriod;
    turtleBreakoutDate.value = st.breakoutDate;
    turtleBuyPrice.value = st.buyPrice;
  } else {
    accountValue.value = null;
    atrPeriod.value = 20;
    turtleBreakoutDate.value = null;
    turtleBuyPrice.value = null;
  }
}

// 現在の入力を現在の銘柄の保存状態として上書き保存する
function saveCurrentTurtleState(): void {
  turtleStateMessage.value = '';
  const sym = currentTurtleSymbol.value;
  if (!isValidSymbol(sym)) {
    turtleStateMessage.value = '有効な銘柄を指定してください';
    return;
  }
  const result = buildTurtleState({
    accountValue: accountValue.value,
    breakoutDate: turtleBreakoutDate.value,
    buyPrice: turtleBuyPrice.value,
    atrPeriod: atrPeriod.value,
  });
  if (!result.ok) {
    turtleStateMessage.value = result.error;
    return;
  }
  try {
    saveTurtleState(sym, result.state);
  } catch (e) {
    console.error('タートル戦略状態の保存に失敗しました:', e);
    turtleStateMessage.value = '状態の保存に失敗しました（ブラウザストレージエラー）';
    return;
  }
  turtleStates.value = { ...turtleStates.value, [sym]: result.state };
  turtleStateMessage.value = `${sym} の状態を保存しました`;
}

// 現在の銘柄の保存状態を削除し、入力を空欄に戻す
function releaseCurrentTurtleState(): void {
  turtleStateMessage.value = '';
  const sym = currentTurtleSymbol.value;
  try {
    clearTurtleState(sym);
  } catch (e) {
    console.error('タートル戦略状態の削除に失敗しました:', e);
    turtleStateMessage.value = '状態の削除に失敗しました（ブラウザストレージエラー）';
    return;
  }
  const next = { ...turtleStates.value };
  delete next[sym];
  turtleStates.value = next;
  applyTurtleState(sym); // 保存状態がなくなったため全入力を空欄に戻す
  turtleStateMessage.value = `${sym} の状態を削除しました`;
}

// =====================================================================
// 固定情報パネル（ホバー中のローソク足の正確な価格・出来高を表示）
// - 標準 tooltip の内容表示は tooltip.showContent = false で無効化し、
//   クロスヘア（軸カーソル）はそのまま維持する
// - ECharts の 'updateAxisPointer' イベントの dataIndex（生インデックス）を
//   受け取って data.value 配列の該当レコードを表示する
// - ポインタがグリッド外に出ると payload は空になるため、その時は直近の
//   値を保持する（「固定」パネルの挙動。データ更新時にのみリセットする）
// - タートル戦略数値エリア (Issue #40): 同一パネル内に現在値テーブルと
//   区切りの入った独立セクションで、ホバー中のインデックス時点の
//   Donchian / ATR / シグナルを表示する。turtleEnabled に連動して
//   表示・非表示になるだけで、dataIndex マッピング・グリッド外出時の
//   値保持・データ取得時のリセットは現在値パネルと共通のロジックをそのまま
//   利用するため、スクリプト側の追加ロジックは不要
// =====================================================================
// ホバー中のローソク足のインデックス（data.value 配列の生インデックス、null = まだホバーしていない）
const hoverIndex = ref<number | null>(null);
// 情報パネルの位置（チャート容器内の左上座標。既定は左上隅）
const panelPos = ref({ x: 10, y: 10 });

// ホバー中のローソク足（範囲外なら null。例: データ更新直後の古いインデックス）
const hoverRecord = computed<StockRecord | null>(() => {
  const i = hoverIndex.value;
  if (i === null || i < 0 || i >= data.value.length) return null;
  return data.value[i];
});
// 同じローソク足のタートル行（ATR は N 日分データが揃うまで null）
const hoverTurtle = computed<TurtleBar | null>(() => {
  const i = hoverIndex.value;
  if (i === null || i < 0 || i >= turtle.value.length) return null;
  return turtle.value[i];
});
// 同じローソク足の古典タートルズ行。日付で検索し、表示順の差に依存しない。
const hoverClassicDay = computed<ClassicTurtleDay | null>(() => {
  const date = hoverRecord.value?.date;
  if (!date) return null;
  return classicTurtle.value.days.find(day => day.date === date) ?? null;
});
// ホバー中の古典タートルズのエントリー時2N EXIT。
const hoverClassicInitialStop = computed<number | null>(() => {
  const position = hoverClassicDay.value?.position;
  const first = position?.entries[0];
  return first ? classicStopPrice(first) : null;
});
// ホバー中の古典タートルズの直近計算2N EXIT。
const hoverClassicCurrentStop = computed<number | null>(() => hoverClassicDay.value?.position?.stopPrice ?? null);
// 同じローソク足の OBV 値 (Issue #61)
const hoverObv = computed<number | null>(() => {
  const i = hoverIndex.value;
  if (i === null || i < 0 || i >= obv.value.length) return null;
  return obv.value[i].obv;
});
// 同じローソク足の OBV 検証結果 (Issue #63、BUY シグナル日のみ)
const hoverObvCheck = computed<BreakoutObvCheck | null>(() => {
  const t = hoverTurtle.value;
  if (!t?.buy) return null;
  return breakoutObvChecks.value.get(t.date) ?? null;
});
// 前日比（前日終値に対する終値の差と変化率）
const hoverChange = computed<{ diff: number; pct: number } | null>(() => {
  const i = hoverIndex.value;
  if (i === null || i < 1) return null;
  const cur = data.value[i];
  const prev = data.value[i - 1];
  if (cur.close == null || prev.close == null || prev.close === 0) return null;
  const diff = cur.close - prev.close;
  return { diff, pct: (diff / prev.close) * 100 };
});

// 情報パネルの位置スタイル
const panelStyle = computed(() => ({
  left: `${panelPos.value.x}px`,
  top: `${panelPos.value.y}px`,
}));

// --- 値の書式化（K/M 省略なしの正確な値を表示） ---
// 価格系: 桁区切り + 小数 2〜4 桁
function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return v.toLocaleString('ja-JP', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}
// 出来高: 桁区切りの整数（例: 53,456,789）
function fmtVolume(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Math.round(v).toLocaleString('ja-JP');
}

// 古典タートルズの損益表示（株式のポイント価値は1）。
function fmtMoney(v: number, currency: 'JPY' | 'USD' = 'JPY'): string {
  if (!Number.isFinite(v)) return '—';
  const suffix = currency === 'USD' ? ' USD' : ' 円';
  return `${v >= 0 ? '+' : ''}${v.toLocaleString('ja-JP', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${suffix}`;
}

// 古典タートルズの各エントリーに対応する2N損切り価格を表示する。
function classicStopPrice(entry: Pick<ClassicTurtleEntry, 'side' | 'price' | 'n'>): number {
  return entry.side === 'long' ? entry.price - 2 * entry.n : entry.price + 2 * entry.n;
}

function classicPositionLabel(position: ClassicTurtlePosition | null | undefined, system: TurtleSystem): string {
  if (!position || position.system !== system) return 'ポジションなし';
  return position.side === 'long' ? 'ロング保有中' : 'ショート保有中';
}

function fmtClassicEntryLine(day: ClassicTurtleDay | null, system: TurtleSystem): string {
  if (!day) return '—';
  const position = day.position?.system === system ? day.position : null;
  if (position?.side === 'long') return `上限 ${fmtPrice(system === 'system1' ? day.indicator.system1LongEntry : day.indicator.system2LongEntry)}`;
  if (position?.side === 'short') return `下限 ${fmtPrice(system === 'system1' ? day.indicator.system1ShortEntry : day.indicator.system2ShortEntry)}`;
  const upper = system === 'system1' ? day.indicator.system1LongEntry : day.indicator.system2LongEntry;
  const lower = system === 'system1' ? day.indicator.system1ShortEntry : day.indicator.system2ShortEntry;
  return `上限 ${fmtPrice(upper)} / 下限 ${fmtPrice(lower)}`;
}

function fmtClassicExitLine(day: ClassicTurtleDay | null, system: TurtleSystem): string {
  if (!day) return '—';
  const position = day.position?.system === system ? day.position : null;
  if (position?.side === 'long') return `下限 ${fmtPrice(system === 'system1' ? day.indicator.system1LongExit : day.indicator.system2LongExit)}`;
  if (position?.side === 'short') return `上限 ${fmtPrice(system === 'system1' ? day.indicator.system1ShortExit : day.indicator.system2ShortExit)}`;
  return '—（ポジションなし）';
}

interface ClassicEntryRow {
  unit: number;
  date: string;
  price: number;
  shares: number;
  n: number;
  side: ClassicTurtleEntry['side'];
  pending: boolean;
}

// 保有中の取引は、未到達の買い増し価格をU4まで表示する。
function classicEntryRows(trade: ClassicTurtleTrade): ClassicEntryRow[] {
  const entries: ClassicEntryRow[] = trade.entries.map(entry => ({
    unit: entry.unit,
    date: entry.date,
    price: entry.price,
    shares: entry.shares,
    n: entry.n,
    side: entry.side,
    pending: false,
  }));
  if (trade.exit !== null || entries.length >= 4 || entries.length === 0) return entries;

  let previous = entries[entries.length - 1];
  for (let unit = entries.length + 1; unit <= 4; unit++) {
    const price = previous.side === 'long'
      ? previous.price + 0.5 * previous.n
      : previous.price - 0.5 * previous.n;
    const pending: ClassicEntryRow = {
      unit,
      date: '未到達',
      price,
      shares: entries[0].shares,
      n: previous.n,
      side: previous.side,
      pending: true,
    };
    entries.push(pending);
    previous = pending;
  }
  return entries;
}

// --- パネルのドラッグ（ドラッグバーのみポインターを捕捉する） ---
let panelDragStart: { pointerX: number; pointerY: number; startX: number; startY: number } | null = null;

// パネル位置をチャート容器の範囲内に収める
function clampPanelPos() {
  const wrapper = wrapperRef.value;
  const panel = panelRef.value;
  if (!wrapper || !panel) return;
  const maxX = Math.max(0, wrapper.clientWidth - panel.offsetWidth);
  const maxY = Math.max(0, wrapper.clientHeight - panel.offsetHeight);
  panelPos.value = {
    x: Math.min(Math.max(panelPos.value.x, 0), maxX),
    y: Math.min(Math.max(panelPos.value.y, 0), maxY),
  };
}

function onPanelPointerDown(e: PointerEvent) {
  if (e.button !== 0) return;
  // ポインターをキャプチャすると、バーの外に出ても move/up を確実に受信できる
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  panelDragStart = {
    pointerX: e.clientX,
    pointerY: e.clientY,
    startX: panelPos.value.x,
    startY: panelPos.value.y,
  };
  e.preventDefault();
}

function onPanelPointerMove(e: PointerEvent) {
  if (!panelDragStart) return;
  const wrapper = wrapperRef.value;
  const panel = panelRef.value;
  if (!wrapper || !panel) return;
  // 移動分を適用し、容器の範囲内にクランプする
  const maxX = Math.max(0, wrapper.clientWidth - panel.offsetWidth);
  const maxY = Math.max(0, wrapper.clientHeight - panel.offsetHeight);
  panelPos.value = {
    x: Math.min(Math.max(panelDragStart.startX + (e.clientX - panelDragStart.pointerX), 0), maxX),
    y: Math.min(Math.max(panelDragStart.startY + (e.clientY - panelDragStart.pointerY), 0), maxY),
  };
}

function onPanelPointerUp(e: PointerEvent) {
  if (!panelDragStart) return;
  panelDragStart = null;
  const el = e.currentTarget as HTMLElement | null;
  if (el && el.hasPointerCapture?.(e.pointerId)) {
    el.releasePointerCapture(e.pointerId);
  }
}

// チャート設定: ローソク足 + 出来高 +（タートル表示ON時）Donchian バンド / シグナル / ATR パネル。
// computed 化により、データ・ATR 期間・口座資金・買値の変更で自動再描画される。
const chartOptions = computed<EChartsOption>(() => {
  // チャートには取得済みデータすべてを入れる (Issue #36)。
  // 表示期間 / 本数は初期表示範囲（dataZoom）だけを制御し、
  // 表示ウィンドウより古いデータはパン（ホイール / ドラッグ / スライダー）で見られる。
  const records = data.value;
  if (records.length === 0) return {};
  const dates = records.map(d => d.date);
  const on = turtleEnabled.value;
  const obvOn = obvEnabled.value;
  const rows = turtle.value;
  const tg = on ? targets.value : null;
  // サブパネル数: ローソク足 + 出来高 + (タートルON時) ATR + (OBV ON時) OBV
  const panelCount = 2 + (on ? 1 : 0) + (obvOn ? 1 : 0);
  // OBV パネルの grid / 軸インデックス（タートル ON 時は ATR パネルが 2 に入るため 1 つずれる）
  const obvAxisIndex = on ? 3 : 2;
  // dataZoom が操作する X 軸インデックス（全パネル分）
  const xAxisIndexes = Array.from({ length: panelCount }, (_, gi) => gi);

  // --- 系列の定義 ---
  const series: SeriesOption[] = [
    {
      name: symbol.value,
      type: 'candlestick',
      xAxisIndex: 0,
      yAxisIndex: 0,
      // ECharts のローソク足データ形式: [open, close, low, high]
      data: records.map(d => [
        Number(d.open ?? d.close),
        Number(d.close),
        Number(d.low ?? d.close),
        Number(d.high ?? d.close),
      ]),
      // 日本式: 陽線（上昇）= 赤、陰線（下落）= 緑
      itemStyle: {
        color: '#e2534f',
        color0: '#3ba272',
        borderColor: '#e2534f',
        borderColor0: '#3ba272',
      },
      // ピラミッディング目標 (+0.5N / +1.0N / +1.5N) とストップロス (-2N) のガイドライン
      markLine: tg
        ? {
            silent: true,
            symbol: 'none',
            data: [
              {
                yAxis: tg.target1,
                lineStyle: { type: 'dashed', color: '#9c36b5' },
                label: { position: 'insideEndTop', formatter: 'ピラミッド2 (+0.5N)', color: '#9c36b5' },
              },
              {
                yAxis: tg.target2,
                lineStyle: { type: 'dashed', color: '#9c36b5' },
                label: { position: 'insideEndTop', formatter: 'ピラミッド3 (+1.0N)', color: '#9c36b5' },
              },
              {
                yAxis: tg.target3,
                lineStyle: { type: 'dashed', color: '#9c36b5' },
                label: { position: 'insideEndTop', formatter: 'ピラミッド4 (+1.5N)', color: '#9c36b5' },
              },
              {
                yAxis: tg.stop,
                lineStyle: { type: 'dashed', color: '#c0392b' },
                label: { position: 'insideEndTop', formatter: 'ストップ (-2N)', color: '#c0392b' },
              },
            ],
          }
        : undefined,
    },
    {
      name: '出来高',
      type: 'bar',
      xAxisIndex: 1,
      yAxisIndex: 1,
      // ローソク足と同様に陽線=赤 / 陰線=緑で色分け（volume が null の日はバー非表示）
      data: records.map(d => {
        const bullish = Number(d.close) >= Number(d.open ?? d.close);
        return {
          value: d.volume,
          itemStyle: { color: bullish ? '#e2534f' : '#3ba272' },
        };
      }),
    },
  ];

  // --- BUY/EXIT マーカー配置パラメータ (Issue #46) ---
  // マーカーはローソク足の高値 / 安値から MARK_GAP_PX ピクセル上 / 下に配置する。
  // （三角形 symbolSize 12 の半高さ 6px に 4px の空きを確保）
  // y 軸 min/max 関数（下記）がデータ範囲の上下に PAD_TOP_PX / PAD_BOT_PX
  // ピクセルの余白を常に確保するため、マーカーがグリッド端で
  // 切れたりローソク足と重なったりしない。
  // 上段グリッド高さ（チャート 640px × 上段グリッド高さ。タートル+OBV 両ON の 4 パネル時は 36%）
  const PRICE_GRID_PX = 640 * (on && obvOn ? 0.36 : 0.45);
  const PAD_TOP_PX = 20; // グリッド上部: BUY マーカー (△) の表示余白
  const PAD_BOT_PX = 20; // グリッド下部: EXIT マーカー (▽) の表示余白
  const MARK_GAP_PX = 10; // マーカー点とローソク足高値 / 安値の間隔 (px)
  let priceMin = Infinity;
  let priceMax = -Infinity;
  const widenRange = (v: number | null) => {
    if (v === null || !Number.isFinite(v)) return;
    if (v < priceMin) priceMin = v;
    if (v > priceMax) priceMax = v;
  };
  for (const d of records) {
    widenRange(Number(d.low ?? d.close));
    widenRange(Number(d.high ?? d.close));
  }
  if (classicTurtleEnabled.value) {
    for (const row of classicTurtle.value.indicators) {
      if (classicTurtleSystem.value !== 'system2') widenRange(row.system1LongEntry);
      if (classicTurtleSystem.value !== 'system1') widenRange(row.system2LongEntry);
      if (classicTurtleSystem.value !== 'system2') widenRange(row.system1ShortEntry);
      if (classicTurtleSystem.value !== 'system1') widenRange(row.system2ShortEntry);
    }
    for (const trade of classicChartTrades.value) {
      for (const entry of trade.entries) widenRange(entry.price);
      widenRange(trade.exit?.price ?? null);
    }
  }
  const priceSpan = priceMax - priceMin;
  const pxPerPoint =
    priceSpan > 0 ? priceSpan / Math.max(PRICE_GRID_PX - PAD_TOP_PX - PAD_BOT_PX, 1) : 0;
  const markerGapPrice = MARK_GAP_PX * pxPerPoint;
  const axisBound = (v: { min: number; max: number }, isMax: boolean): number => {
    const span = v.max - v.min;
    if (!(span > 0)) return isMax ? v.max * 1.001 : v.min * 0.999;
    const pp = span / Math.max(PRICE_GRID_PX - PAD_TOP_PX - PAD_BOT_PX, 1);
    return isMax ? v.max + PAD_TOP_PX * pp : v.min - PAD_BOT_PX * pp;
  };
  // 価格軸 (grid 0) の min/max 関数 (タートル表示 ON 時のみ使用)
  const priceAxisMin = (v: { min: number; max: number }) => axisBound(v, false);
  const priceAxisMax = (v: { min: number; max: number }) => axisBound(v, true);

  // タートル表示ON時の追加系列
  if (on) {
    // --- BUY/EXIT マーカー配置用の価格レンジ (Issue #46) ---
    // 全データ（ローソク足 + Donchian バンド + markLine 値）の価格レンジ。
    // 固定ピクセル間隔 MARK_GAP_PX を価格に変換するためにのみ使用する。
    for (const r of rows) {
      widenRange(r.donchianUpper);
      widenRange(r.donchianLower);
    }

    // ピラミッド目標 / ストップの markLine はローソク足レンジの外側に伸び得る
    if (tg) {
      widenRange(tg.target1);
      widenRange(tg.target2);
      widenRange(tg.target3);
      widenRange(tg.stop);
    }
    series.push(
      {
        name: 'DC20 (エントリーライン)',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        // 過去 20 日間の最高値（前日までのデータのみ。当日は除外 = ルックアヘッドなし）
        data: rows.map(r => r.donchianUpper),
        symbol: 'none',
        showSymbol: false,
        connectNulls: false,
        lineStyle: { type: 'dashed', width: 1.5, color: '#e67e22' },
        itemStyle: { color: '#e67e22' },
      },
      {
        name: 'DC10 (手仕舞いライン)',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        // 過去 10 日間の最安値（前日までのデータのみ）
        data: rows.map(r => r.donchianLower),
        symbol: 'none',
        showSymbol: false,
        connectNulls: false,
        lineStyle: { type: 'dashed', width: 1.5, color: '#1971c2' },
        itemStyle: { color: '#1971c2' },
      },
      {
        // BUY マーカー: 終値がエントリーラインを上抜けした日（日本式: 赤）
        // OBV 検証 (Issue #63) で ①②③ 全条件を満たすブレイクは金色三角で識別。
        // ローソク足の高値より MARK_GAP_PX ピクセル上側に配置 (Issue #46)
        name: 'BUY',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: rows.map((r, i) => {
          if (!r.buy) return null;
          const high = Number(records[i].high ?? records[i].close);
          const allOk = breakoutObvChecks.value.get(r.date)?.all === true;
          return {
            value: high + markerGapPrice,
            itemStyle: { color: allOk ? '#d4a017' : '#e2534f' },
          };
        }),
        symbol: 'triangle',
        symbolSize: 12,
        itemStyle: { color: '#e2534f' },
      },
      {
        // EXIT マーカー: 手仕舞いライン下抜けまたはトレーリングストップ到達の日（日本式: 緑）
        // ローソク足の安値より MARK_GAP_PX ピクセル下側に配置 (Issue #46)
        name: 'EXIT',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: rows.map((r, i) => {
          if (!r.exit) return null;
          const low = Number(records[i].low ?? records[i].close);
          return low - markerGapPrice;
        }),
        symbol: 'triangle',
        symbolRotate: 180, // 下向き三角形
        symbolSize: 12,
        itemStyle: { color: '#3ba272' },
      },
      {
        // N (ATR): True Range の単純移動平均（サブパネルに表示）
        name: 'N (ATR)',
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: rows.map(r => r.atr),
        symbol: 'none',
        showSymbol: false,
        connectNulls: false,
        lineStyle: { type: 'solid', width: 1.5, color: '#8e44ad' },
        itemStyle: { color: '#8e44ad' },
      },
    );

    // 買い増し計画 (P2/P3/P4) と計画 EXIT のマーカー (Issue #44)。
    // 指標シグナル (BUY/EXIT マーカー) とは別物で、計画上の到達日を示す。
    const plan = turtlePlan.value;
    if (plan) {
      const buyAdds = plan.levels.filter(
        (lv): lv is TurtlePlanLevel & { date: string; hitClose: number } =>
          lv.date !== null && lv.hitClose !== null,
      );
      if (buyAdds.length > 0) {
        series.push({
          // 買い増し: 終値が 直前ユニットの目標ライン + 0.5 × N (当日 N で再計算 / 到達後は到達時の価格でライン固定) に到達した日
          name: '買い増し 2/3/4',
          type: 'scatter',
          xAxisIndex: 0,
          yAxisIndex: 0,
          symbol: 'diamond',
          symbolSize: 10,
          itemStyle: { color: '#9c36b5' },
          data: buyAdds.map(lv => ({
            value: [lv.date, lv.hitClose],
            label: {
              show: true,
              position: 'top',
              formatter: `買い増し${lv.level}`,
              color: '#9c36b5',
              fontSize: 10,
            },
          })),
        });
      }
      if (plan.exit.date !== null && plan.exit.close !== null) {
        series.push({
          // 計画 EXIT: 終値 ≤ 最新エントリー−2N (ストップ) または 終値 < DC10 の初回到達日
          name: '計画 EXIT',
          type: 'scatter',
          xAxisIndex: 0,
          yAxisIndex: 0,
          symbol: 'rect',
          symbolSize: 9,
          itemStyle: { color: '#3ba272' },
          data: [
            {
              value: [plan.exit.date, plan.exit.close],
              label: {
                show: true,
                position: 'bottom',
                formatter: '計画 EXIT',
                color: '#3ba272',
                fontSize: 10,
              },
            },
          ],
        });
      }
    }
  }

  // 古典版の価格レンジは既存タートル表示に依存せず計算する。
  if (classicTurtleEnabled.value) {
    for (const row of classicTurtle.value.indicators) {
      if (classicTurtleSystem.value !== 'system2') widenRange(row.system1LongEntry);
      if (classicTurtleSystem.value !== 'system1') widenRange(row.system2LongEntry);
      if (classicTurtleSystem.value !== 'system2') widenRange(row.system1ShortEntry);
      if (classicTurtleSystem.value !== 'system1') widenRange(row.system2ShortEntry);
    }
    for (const trade of classicVisibleTrades.value) {
      for (const entry of trade.entries) widenRange(entry.price);
      widenRange(trade.exit?.price ?? null);
    }

    const classic = classicTurtle.value;
    const showSystem = (system: TurtleSystem) => classicTurtleSystem.value === 'both' || classicTurtleSystem.value === system;
    const classicLineValues = (
      system: TurtleSystem,
      line: 'entryLong' | 'entryShort' | 'exitLong' | 'exitShort',
    ): (number | null)[] => classic.days.map(day => {
      const position = day.position?.system === system
        && (classicTradeSide.value === 'both' || day.position.side === classicTradeSide.value)
        ? day.position
        : null;
      const hasPositionForSystem = position !== null;
      const indicator = day.indicator;
      if (line === 'entryLong') {
        if (hasPositionForSystem && position.side !== 'long') return null;
        return system === 'system1' ? indicator.system1LongEntry : indicator.system2LongEntry;
      }
      if (line === 'entryShort') {
        if (hasPositionForSystem && position.side !== 'short') return null;
        return system === 'system1' ? indicator.system1ShortEntry : indicator.system2ShortEntry;
      }
      if (!position) return null;
      if (line === 'exitLong') {
        return position.side === 'long'
          ? (system === 'system1' ? indicator.system1LongExit : indicator.system2LongExit)
          : null;
      }
      return position.side === 'short'
        ? (system === 'system1' ? indicator.system1ShortExit : indicator.system2ShortExit)
        : null;
    });
    for (const day of classic.days) {
      const position = day.position
        && (classicTradeSide.value === 'both' || day.position.side === classicTradeSide.value)
        ? day.position
        : null;
      if (!position || !showSystem(position.system)) continue;
      widenRange(
        position.side === 'long'
          ? (position.system === 'system1' ? day.indicator.system1LongExit : day.indicator.system2LongExit)
          : (position.system === 'system1' ? day.indicator.system1ShortExit : day.indicator.system2ShortExit),
      );
    }
    const addClassicLine = (
      name: string,
      values: (number | null)[],
      color: string,
      lineType: 'dotted' | 'dashed' = 'dotted',
    ) => {
      series.push({
        name,
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: values,
        symbol: 'none',
        showSymbol: false,
        connectNulls: false,
        lineStyle: { type: lineType, width: lineType === 'dashed' ? 1.4 : 1.2, color },
        itemStyle: { color },
      });
    };
    if (showSystem('system1')) {
      addClassicLine('古典 S1 DC20 上限', classicLineValues('system1', 'entryLong'), '#c0392b');
      addClassicLine('古典 S1 DC20 下限', classicLineValues('system1', 'entryShort'), '#2980b9');
      addClassicLine('古典 S1 決済10 下限', classicLineValues('system1', 'exitLong'), '#5dade2', 'dashed');
      addClassicLine('古典 S1 決済10 上限', classicLineValues('system1', 'exitShort'), '#e67e22', 'dashed');
    }
    if (showSystem('system2')) {
      addClassicLine('古典 S2 DC55 上限', classicLineValues('system2', 'entryLong'), '#b7950b');
      addClassicLine('古典 S2 DC55 下限', classicLineValues('system2', 'entryShort'), '#8e44ad');
      addClassicLine('古典 S2 決済20 下限', classicLineValues('system2', 'exitLong'), '#bb8fce', 'dashed');
      addClassicLine('古典 S2 決済20 上限', classicLineValues('system2', 'exitShort'), '#b9770e', 'dashed');
    }
    const entries = classicChartTrades.value.flatMap(trade => trade.entries.map(entry => ({ trade, entry })));
    const exits = classicChartTrades.value
      .filter(trade => trade.exit !== null)
      .map(trade => ({ trade, exit: trade.exit! }));
    series.push({
      name: '古典エントリー',
      type: 'scatter',
      xAxisIndex: 0,
      yAxisIndex: 0,
      symbol: 'triangle',
      symbolSize: 11,
      data: entries.map(({ trade, entry }) => {
        const i = records.findIndex(record => record.date === entry.date);
        const high = i >= 0 ? Number(records[i].high ?? records[i].close) : entry.price;
        return { value: [entry.date, high + markerGapPrice], itemStyle: { color: entry.side === 'long' ? '#d35400' : '#2980b9' }, label: { show: true, position: 'top', formatter: `${trade.system === 'system1' ? 'S1' : 'S2'} ${entry.side === 'long' ? 'L' : 'S'}${entry.kind === 'pyramid' ? '+' : ''}`, fontSize: 9 } };
      }),
    });
    series.push({
      name: '古典決済',
      type: 'scatter',
      xAxisIndex: 0,
      yAxisIndex: 0,
      symbol: 'triangle',
      symbolRotate: 180,
      symbolSize: 11,
      data: exits.map(({ trade, exit }) => {
        const i = records.findIndex(record => record.date === exit.date);
        const low = i >= 0 ? Number(records[i].low ?? records[i].close) : exit.price;
        return { value: [exit.date, low - markerGapPrice], itemStyle: { color: trade.side === 'long' ? '#27ae60' : '#16a085' }, label: { show: true, position: 'bottom', formatter: `${trade.system === 'system1' ? 'S1' : 'S2'} 決済`, fontSize: 9 } };
      }),
    });
  }

  // OBV 系列 (Issue #61): 出来高の累積値（初日 OBV = 初日出来高。
  // ①上昇日 +出来高 ②下降日 −出来高 ③同値日 不変）
  if (obvOn) {
    series.push({
      name: 'OBV',
      type: 'line',
      xAxisIndex: obvAxisIndex,
      yAxisIndex: obvAxisIndex,
      data: obv.value.map(r => r.obv),
      symbol: 'none',
      showSymbol: false,
      connectNulls: false,
      lineStyle: { type: 'solid', width: 1.5, color: '#d35400' },
      itemStyle: { color: '#d35400' },
    });
  }

  return {
    // 銘柄名タイトル (Issue #49): チャート左上に表示（grid の top 30px 余白内）
    title: {
      text: chartTitle(symbol.value, stockName.value),
      left: 70,
      top: 5,
      textStyle: { fontSize: 14, fontWeight: 'bold' },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      // 標準 tooltip の内容表示を無効化（クロスヘアは維持）—
      // ホバー中のローソク足の正確な価格・出来高は固定情報パネルに表示する
      showContent: false,
    },
    // 各グリッドの軸カーソルを同期する（tooltip は全系列共通で表示）
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    // dataZoom (Issue #36): inside = ドラッグでパン（ホイール操作は後述のカスタム handler が担当）、
    // slider = 下部スライダー（可視範囲の表示と直接操作）
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: xAxisIndexes,
        // Ctrl+ホイール = ズーム / 通常ホイール = パンは下のカスタム handler で実現するため、
        // ECharts 内蔵のホイール処理は無効化（内蔵では両方を分離できない:
        // Ctrl+ホイールでズームとスクロールが同時に発動してしまう）
        zoomOnMouseWheel: false,
        moveOnMouseWheel: false,
        moveOnMouseMove: true, // ドラッグ = パン
        minSpan: 2, // 最小表示幅（ウィンドウの 2%。単一ローソクへの退化を防ぐ）
      },
      {
        type: 'slider',
        xAxisIndex: xAxisIndexes,
        bottom: 5,
        height: 25,
        showDetail: false,
        minSpan: 2, // 最小表示幅（inside と同一。ハンドルを同一点に寄せて単一ローソク化するのを防ぐ）
      },
    ],
    // ECharts 6 以降: outerBoundsMode のデフォルト 'auto' では各 grid が自身の軸ラベル幅に応じて
    // 独立してプロット領域を縮めるため、3 パネルの水平位置がズレる（Issue #59）。
    // 'none' は left/right がプロット領域を正確に定義する ECharts 5 時代の挙動。
    grid:
      on && obvOn
        ? [
            { left: 70, right: 20, top: 30, height: '36%', outerBoundsMode: 'none' },      // 上段: ローソク足
            { left: 70, right: 20, top: '45%', height: '11%', outerBoundsMode: 'none' },   // 中1: 出来高
            { left: 70, right: 20, top: '61%', height: '11%', outerBoundsMode: 'none' },   // 中2: ATR
            { left: 70, right: 20, bottom: 45, height: '12%', outerBoundsMode: 'none' },   // 下段: OBV（bottom 45 = 下部スライダー 0〜30px を避ける）
          ]
        : on || obvOn
          ? [
              { left: 70, right: 20, top: 30, height: '45%', outerBoundsMode: 'none' },      // 上段: ローソク足
              { left: 70, right: 20, top: '58%', height: '14%', outerBoundsMode: 'none' },   // 中段: 出来高
              { left: 70, right: 20, bottom: 45, height: '12%', outerBoundsMode: 'none' },   // 下段: ATR (タートル) か OBV（bottom 45 = 下部スライダー 0〜30px を避ける）
            ]
          : [
              { left: 70, right: 20, top: 30, height: '55%', outerBoundsMode: 'none' },      // 上段: ローソク足
              { left: 70, right: 20, bottom: 50, height: '18%', outerBoundsMode: 'none' },   // 下段: 出来高
            ],
    xAxis: Array.from({ length: panelCount }, (_, gi) => ({
      type: 'category' as const,
      data: dates,
      gridIndex: gi,
      // サブパネルの日付ラベルは非表示（上段に表示済み）
      axisLabel: gi > 0 ? { show: false } : undefined,
    })),
    yAxis:
      obvOn
        ? on
          ? [
              {
                type: 'value',
                gridIndex: 0,
                // BUY/EXIT マーカー + 文字ラベル分を固定ピクセルで確保 (Issue #46)。
                // 関数形のため dataZoom が可視ウィンドウを変えても再評価され、
                // 可視ローソク足への自動フィット（スケール変化）は維持される。
                min: priceAxisMin,
                max: priceAxisMax,
              },
              {
                type: 'value',
                gridIndex: 1,
                splitNumber: 2,
                axisLabel: {
                  // 大きな数を K/M 単位でコンパクトに表示（tooltip と共通の書式）
                  formatter: (value: number) => formatCompact(value),
                },
              },
              { type: 'value', scale: true, gridIndex: 2, splitNumber: 2 },
              {
                type: 'value',
                gridIndex: 3,
                scale: true,
                splitNumber: 2,
                axisLabel: {
                  // OBV は累積値のため数値が大きい: K/M 単位でコンパクトに表示
                  formatter: (value: number) => formatCompact(value),
                },
              },
            ]
          : [
              { type: 'value', scale: true, gridIndex: 0 },
              {
                type: 'value',
                gridIndex: 1,
                splitNumber: 2,
                axisLabel: {
                  // 大きな数を K/M 単位でコンパクトに表示（tooltip と共通の書式）
                  formatter: (value: number) => formatCompact(value),
                },
              },
              {
                type: 'value',
                gridIndex: 2,
                scale: true,
                splitNumber: 2,
                axisLabel: {
                  // OBV は累積値のため数値が大きい: K/M 単位でコンパクトに表示
                  formatter: (value: number) => formatCompact(value),
                },
              },
            ]
        : on
          ? [
              {
                type: 'value',
                gridIndex: 0,
                // BUY/EXIT マーカー + 文字ラベル分を固定ピクセルで確保 (Issue #46)。
                // 関数形のため dataZoom が可視ウィンドウを変えても再評価され、
                // 可視ローソク足への自動フィット（スケール変化）は維持される。
                min: priceAxisMin,
                max: priceAxisMax,
              },
              {
                type: 'value',
                gridIndex: 1,
                splitNumber: 2,
                axisLabel: {
                  // 大きな数を K/M 単位でコンパクトに表示（tooltip と共通の書式）
                  formatter: (value: number) => formatCompact(value),
                },
              },
              { type: 'value', scale: true, gridIndex: 2, splitNumber: 2 },
            ]
          : [
              { type: 'value', scale: true, gridIndex: 0 },
              {
                type: 'value',
                gridIndex: 1,
                splitNumber: 2,
                axisLabel: {
                  // 大きな数を K/M 単位でコンパクトに表示（tooltip と共通の書式）
                  formatter: (value: number) => formatCompact(value),
                },
              },
            ],
    series,
  };
});

// DB から保存済みデータをチャートへ読み込む（Yahoo Finance には問い合わせない）。
// 日付昇順（古い順）に整えて返す。
async function loadStockDataFromDb(): Promise<StockRecord[]> {
  const res = await axios.get(`/api/stocks/${symbol.value.trim()}`);
  // 日付昇順（古い順）でチャートに表示する
  return (res.data as StockRecord[]).sort((a, b) => a.date.localeCompare(b.date));
}

async function fetchStockData() {
  if (fetching.value) return; // 既に Yahoo 更新中なら二重リクエストしない
  let records: StockRecord[];
  try {
    records = await loadStockDataFromDb();
  } catch (e) {
    console.error('データ取得エラー:', e);
    return;
  }
  data.value = records;
  // 引け後自動リフレッシュ: 最新レコードが最近の日付（直近 7 日以内）なら、
  // それが日中（引け前）のイントレーダースナップショットかもしれないため
  // Yahoo Finance へ一度だけ再取得する。引け後に Yahoo は当日の最終
  // 終値・出来高を返し、バックエンドの upsert が既存の同日行を上書きする。
  // 古いデータ / 無データでは Yahoo リクエストを行わない（レート制限対策）。
  const latest = records[records.length - 1];
  if (shouldAutoRefreshYahoo(latest?.date)) {
    await refreshFromYahoo();
  }
}

// 銘柄名を取得 (Issue #49): バックエンド /api/stocks/<symbol>/meta/ 経由
// （取得不能の場合は空名称として扱い、表示側では穏当に非表示にする）
async function fetchStockMeta() {
  const target = symbol.value.trim().toUpperCase();
  if (!SYMBOL_PATTERN.test(target)) {
    stockName.value = '';
    stockSector.value = '';
    return;
  }
  try {
    const res = await axios.get(`/api/stocks/${target}/meta/`);
    // 応答到着までにシンボルが変更された場合は古い結果を捨てる（古い名称を保持しない）
    if (symbol.value.trim().toUpperCase() !== target) return;
    stockName.value = res.data.name ?? '';
    stockSector.value = res.data.sector ?? '';
  } catch (e) {
    console.error('銘柄名取得エラー:', e);
    if (symbol.value.trim().toUpperCase() === target) {
      stockName.value = '';
      stockSector.value = '';
    }
  }
}

// =====================================================================
// お気に入り銘柄リスト (Issue #50): バックエンド /api/favorites/・/api/favorite-lists/ 経由
// =====================================================================

// バックエンドエラーからステータス・detail を取り出す
function apiError(e: unknown): { status?: number; detail?: string } {
  const response = (e as { response?: { status?: number; data?: { detail?: string } } })
    ?.response;
  return { status: response?.status, detail: response?.data?.detail };
}

// リスト操作（作成・名前変更・削除）のエラーメッセージ
function listErrorMessage(e: unknown): string {
  const { status, detail } = apiError(e);
  if (status === 409) return detail ? `作成できません: ${detail}` : '同じ名前のリストが既に存在します';
  if (detail) return `リスト操作に失敗しました: ${detail}`;
  if (status !== undefined) return `リスト操作に失敗しました（${status}）`;
  return 'リスト操作に失敗しました（通信エラー）';
}

// 全リスト（空リスト含む）・所属銘柄をバックエンドから再取得する。
// 銘柄名の同期もここで取り込む。選択中のリストが削除された場合は先頭を選択し直す。
async function fetchFavorites() {
  try {
    favoriteGroups.value = await fetchFavoriteGroups();
    if (!favoriteGroups.value.some((g) => g.id === activeListId.value)) {
      activeListId.value = favoriteGroups.value[0]?.id ?? null;
    }
  } catch (e) {
    console.error('お気に入り取得エラー:', e);
  }
}

// 現在入力のシンボルをアクティブリストに追加する（POST /api/favorites/）
async function addFavorite() {
  const target = symbol.value.trim().toUpperCase();
  if (!isValidSymbol(target)) {
    favoriteMessage.value = 'シンボル形式が不正です（英大文字・数字、最大 10 文字）';
    return;
  }
  if (favoriteBusy.value) return;
  if (activeListId.value === null) {
    favoriteMessage.value = 'リストが未選択です。リストを作成または選択してください。';
    return;
  }
  favoriteBusy.value = true;
  favoriteMessage.value = '';
  try {
    await addFavoriteStock(activeListId.value, target);
    await fetchFavorites();
  } catch (e) {
    const { status, detail } = apiError(e);
    favoriteMessage.value = favoriteErrorMessage(status, detail);
  } finally {
    favoriteBusy.value = false;
  }
}

// アクティブリストから銘柄を削除する（DELETE /api/favorites/<list_id>/<symbol>/）
// 他のリストへの所属は影響を受けない。
async function removeFavorite(target: string) {
  if (favoriteBusy.value || activeListId.value === null) return;
  favoriteBusy.value = true;
  favoriteMessage.value = '';
  try {
    await removeFavoriteStock(activeListId.value, target);
    await fetchFavorites();
  } catch (e) {
    console.error('お気に入り削除エラー:', e);
  } finally {
    favoriteBusy.value = false;
  }
}

// アクティブリスト内の銘柄を一つ上または下へ移動し、順序を保存する。
async function moveFavorite(target: string, direction: 'up' | 'down') {
  if (favoriteBusy.value || activeListId.value === null || activeGroup.value === null) return;
  const nextGroups = moveStockInList(favoriteGroups.value, activeListId.value, target, direction);
  if (nextGroups === favoriteGroups.value) return;
  const nextGroup = nextGroups.find((group) => group.id === activeListId.value);
  if (nextGroup === undefined) return;

  favoriteBusy.value = true;
  favoriteMessage.value = '';
  favoriteGroups.value = nextGroups as FavoriteGroup[];
  try {
    await updateFavoriteOrder(
      activeListId.value,
      nextGroup.stocks.map((stock) => stock.symbol),
    );
  } catch (e) {
    favoriteMessage.value = 'お気に入りの並び順を保存できませんでした';
    await fetchFavorites();
    console.error('お気に入り並び順更新エラー:', e);
  } finally {
    favoriteBusy.value = false;
  }
}

// 新しいリストを作成する（POST /api/favorite-lists/）。作成後は自動で選択する。
async function createList() {
  if (favoriteBusy.value) return;
  const input = window.prompt('新しいリスト名（50 字以内）:', '');
  if (input === null) return; // キャンセル
  const name = input.trim();
  if (!isValidListName(name)) {
    favoriteMessage.value = `無効なリスト名です（空以外・${LIST_NAME_MAX_LENGTH} 字以内）`;
    return;
  }
  favoriteBusy.value = true;
  favoriteMessage.value = '';
  try {
    const created = await createFavoriteList(name);
    await fetchFavorites();
    activeListId.value = created.id;
  } catch (e) {
    favoriteMessage.value = listErrorMessage(e);
  } finally {
    favoriteBusy.value = false;
  }
}

// select ボックスでのリスト選択 (Issue #50)。option の value は文字列で届くため数値化する。
function onListSelectChange(e: Event) {
  const value = (e.target as HTMLSelectElement).value;
  activeListId.value = value === '' ? null : Number(value);
}

// リスト名を変更する（PATCH /api/favorite-lists/<id>/）
async function renameActiveList(listId: number | null) {
  if (favoriteBusy.value || listId === null) return;
  const current = favoriteGroups.value.find((g) => g.id === listId);
  if (current === undefined) return;
  const input = window.prompt('リスト名を変更（50 字以内）:', current.name);
  if (input === null) return; // キャンセル
  const name = input.trim();
  if (!isValidListName(name)) {
    favoriteMessage.value = `無効なリスト名です（空以外・${LIST_NAME_MAX_LENGTH} 字以内）`;
    return;
  }
  favoriteBusy.value = true;
  favoriteMessage.value = '';
  try {
    await renameFavoriteList(listId, name);
    await fetchFavorites();
  } catch (e) {
    favoriteMessage.value = listErrorMessage(e);
  } finally {
    favoriteBusy.value = false;
  }
}

// リストを削除する（DELETE /api/favorite-lists/<id>/）。所属銘柄の行も一緒に削除される。
async function deleteActiveList(listId: number | null) {
  if (favoriteBusy.value || listId === null) return;
  const current = favoriteGroups.value.find((g) => g.id === listId);
  if (current === undefined) return;
  const ok = window.confirm(
    `リスト「${current.name}」を削除します。このリストの${current.stocks.length}件の銘柄も削除されます。よろしいですか？`,
  );
  if (!ok) return;
  favoriteBusy.value = true;
  favoriteMessage.value = '';
  try {
    await deleteFavoriteList(listId);
    await fetchFavorites();
  } catch (e) {
    favoriteMessage.value = listErrorMessage(e);
  } finally {
    favoriteBusy.value = false;
  }
}

async function fetchFromYahoo() {
  // Yahoo ボタンは refreshFromYahoo の別名（取得ボタンの引け後自動リフレッシュと同一経路）
  await refreshFromYahoo();
}

// Yahoo Finance から取得して DB に保存し、結果をチャートへ反映する。
// 「Yahoo Finance から取得」ボタンと、引け後自動リフレッシュで共有する。
// 既に実行中の場合は何もしない（二重クリック / 並行呼び出しの重複防止）。
// 成功で true、スキップ・失敗で false を返す。
async function refreshFromYahoo(): Promise<boolean> {
  if (fetching.value) return false;
  const target = symbol.value.trim();
  if (!target) return false;
  fetching.value = true;
  yahooError.value = false;
  yahooMessage.value = `${target}（${period.value}）を Yahoo Finance から取得中...`;
  try {
    const res = await axios.post('/api/stocks/fetch/', { symbol: target, period: period.value });
    const r = res.data;
    yahooMessage.value =
      `${r.symbol} の株価 ${r.fetched} 件を取得して保存しました` +
      `（新規 ${r.created} 件 / 更新 ${r.updated} 件、${r.start_date} 〜 ${r.end_date}）`;
    // 保存されたデータを DB から読み直してチャートに反映
    data.value = await loadStockDataFromDb();
    // 直前に最新データを保存したばかりなので銘柄名も再取得 (Issue #49)
    void fetchStockMeta();
    // お気に入り銘柄の名称は StockMeta と同期されるため一覧も再取得 (Issue #50)
    void fetchFavorites();
    return true;
  } catch (e: any) {
    const detail = e?.response?.data?.detail ?? e?.message ?? 'リクエストに失敗しました';
    yahooError.value = true;
    yahooMessage.value = `株価取得に失敗しました: ${detail}`;
    return false;
  } finally {
    fetching.value = false;
  }
}

async function fetchMovingAverage() {
  try {
    const res = await axios.get(`/api/moving_average/${symbol.value.trim()}`, { params: { days: maDays.value } });
    movingAverage.value = res.data.moving_average;
  } catch (e) {
    console.error('移動平均取得エラー:', e);
  }
}

watch(symbol, () => {
  data.value = [];
  movingAverage.value = null;
  yahooMessage.value = '';
  yahooError.value = false;
  // タートル戦略の状態を新銘柄の保存状態へ復元 (Issue #53)（未保存なら全入力空欄）
  applyTurtleState(symbol.value);
  // 銘柄名をリセットしてデバウンス取得 (Issue #49)
  stockName.value = '';
  if (metaTimer !== null) clearTimeout(metaTimer);
  metaTimer = setTimeout(() => {
    void fetchStockMeta();
  }, 400);
});

// 表示ウィンドウ（表示期間 / 本数 = 直近 N 本）を表示範囲に適用する (Issue #36)。
// チャートには全データが入っているため、適用後はパン（ホイール / ドラッグ / スライダー）で
// 表示ウィンドウより古いデータも表示できる。
function applyDisplayWindow() {
  const total = data.value.length;
  if (total < 2) return; // チャート非表示 / 単一ローソク時は範囲調整の対象外
  const { start, end } = getDisplayRange(total, displayPeriod.value, displayCount.value);
  applyWheelRange(start, end);
}

// 新データ取得時（取得ボタン / 銘柄変更など）に表示ウィンドウを適用 (Issue #36)。
// nextTick で遅らせるのは、vue-echarts が新オプションをチャートに反映した
// 後に dispatchAction を実行するため。
watch(data, () => {
  // 新データ: ホバー中のインデックスをリセット（古いインデックスは範囲外になり得るため）
  hoverIndex.value = null;
  nextTick(applyDisplayWindow);
});

// 表示期間 / 本数の切替時は表示ウィンドウを再適用する。
// （旧データはチャートに残り続けるので、切替後もパンで過去を辿れる）
watch([displayPeriod, displayCount], () => {
  applyDisplayWindow();
});

// 初期表示でお気に入り一覧を読み込む (Issue #50)
// および初期銘柄のタートル戦略保存状態を復元 (Issue #53)
onMounted(() => {
  applyTurtleState(symbol.value);
  void fetchFavorites();
});
</script>

<style scoped>
.stock-container { font-family: Arial, sans-serif; }
.control-panel input, .control-panel select { padding:.4rem; border:1px solid #ccc; border-radius:.3rem; }
.moving-average-panel p { margin-top:.5rem;font-weight:bold; }
.turtle-panel input, .turtle-panel select { padding:.3rem; border:1px solid #ccc; border-radius:.3rem; }
.turtle-panel p { margin-top:.5rem; font-weight:bold; }
.turtle-table { margin-top:.5rem; border-collapse:collapse; }
.turtle-table th, .turtle-table td { border:1px solid #ddd; padding:.3rem .6rem; text-align:left; font-size:.9rem; }
.turtle-table th { background:#eee; }
/* --- 固定情報パネル（チャート容器内の position 基準） --- */
.chart-wrapper { position:relative; }
.info-panel {
  position:absolute; z-index:10; min-width:10rem;
  background:rgba(255,255,255,.93); border:1px solid #bbb; border-radius:.4rem;
  box-shadow:0 2px 8px rgba(0,0,0,.18); font-size:.85rem;
  pointer-events:none; /* 本体はポインター透過: クロスヘアが更新され続ける */
  user-select:none;
}
.info-panel-handle {
  pointer-events:auto; cursor:move; touch-action:none;
  padding:.2rem .5rem; background:#f0f0f0; border-bottom:1px solid #ddd;
  border-radius:.4rem .4rem 0 0; font-weight:bold;
}
.info-table { width:100%; border-collapse:collapse; }
.info-table th, .info-table td { padding:.1rem .5rem; text-align:left; white-space:nowrap; }
.info-table th { color:#555; font-weight:normal; }
.info-table td { font-variant-numeric:tabular-nums; }
/* --- タートル戦略数値エリア（固定情報パネル内、Issue #40） --- */
/* 現在値テーブルとの視覚的な分離: 上側の区切り線 + 淡いオレンジ背景 */
.turtle-section {
  border-top:1px solid #bbb;
  border-radius:0 0 .4rem .4rem;
  background:rgba(230,126,34,.06);
}
.turtle-section-header {
  padding:.2rem .5rem; background:#fdf1e3; color:#9c5a00;
  font-weight:bold; font-size:.8rem;
}
/* --- OBV 検証チップ (Issue #63): タートルパネル / 情報パネルの ①②③ 表示 --- */
.obv-cond {
  display:inline-block; padding:0 .35rem; margin-right:.3rem;
  border:1px solid; border-radius:.25rem; font-size:.82rem; white-space:nowrap;
}
.obv-ok { background:#e3f4e3; border-color:#a5d6a7; color:#2c7a2c; }
.obv-ng { background:#fdecea; border-color:#f2b8b1; color:#c0392b; }
.obv-all { color:#b8860b; font-weight:bold; font-size:.85rem; }
.obv-check-row {
  display:flex; gap:.5rem; align-items:center; flex-wrap:wrap;
  margin-top:.5rem; font-size:.88rem;
}
.obv-check-label { font-weight:bold; }

/* --- 古典タートルズ表示 --- */
.classic-turtle-panel {
  margin-top:1rem;
  background:#f3f6fb;
  padding:.6rem;
  border:1px solid #cbd5e1;
  border-radius:.3rem;
}
.classic-turtle-panel h4 { margin:.1rem 0 .6rem; }
.classic-turtle-controls {
  display:flex;
  gap:.8rem;
  align-items:center;
  flex-wrap:wrap;
}
.classic-turtle-controls input,
.classic-turtle-controls select { padding:.3rem; border:1px solid #cbd5e1; border-radius:.3rem; }
.classic-turtle-note { color:#64748b; font-size:.82rem; }
.classic-turtle-summary {
  display:flex;
  gap:1rem;
  flex-wrap:wrap;
  margin-top:.6rem;
  font-size:.9rem;
  font-weight:bold;
}
.classic-profit { color:#2c7a2c; }
.classic-loss { color:#c0392b; }
.classic-trades { background:#fff; }
.classic-entry-detail { white-space:nowrap; line-height:1.45; }
.classic-unit-shares { font-weight:600; margin-bottom:.15rem; }
.classic-entry-pending { color:#94a3b8; }
</style>