# 当日運用ゲート仕様案（2026-07 分析ベース）

**状態:** Phase 1 **実装済み**（2026-08-03）  
**実装:** `src/predictor/ops_gates.py` / `config/ops_gates.json` / `race_day_notify.send_line_notifications`  
**根拠:** 2026/7 オフラインBT + R分析 + 当日 `compare_report`  
**対象外（変更なし）:** 重み JSON、三連自信度閾値、オフライン `backtest` 既定

---

## 0. 一言サマリー

7月の弱さは「重みが壊れた」より:

1. **ライブでオッズが動き、堅↔荒が入れ替わる**（T-10 の exotic 一致 ~66%）
2. **堅・かつ volatile の三連複が厚い・弱い**（7月 堅 三連 ROI 69.5% / volatile 67.8%）
3. **下旬クラッシュ**（W30=7/22週 三連 53%・単勝 55%、特に 7/23）

なので **Phase 1 は「買う・送らない」ゲート追加** とし、スコア本体は据え置く。

---

## 1. 背景データ（合意済み）

| 指標 | 値 |
|------|-----|
| 2026/7 単勝 ROI | 87.9% |
| 2026/7 三連複 ROI | 71.7%（157買い） |
| 堅三連 ROI | **69.5%** / 的中 45.7% / n=116 |
| 荒三連 ROI | 79.4% / 的中 29.3% / n=41 |
| volatile 三連 | 67.8% vs stable 76.7% |
| T-10 exotic_profile 一致 | ~66%（Final 比） |
| 最悪週 | 2026-W30（7/22 前後） |

Python: `scripts/analyze_july2026.py`  
R: `r_analysis/output/reports/july2026_logic_guidance.md`

---

## 2. 適用対象チャネル

現行の当日ライン・通知は主に次の2系統。

| ID | 内容 | 送信先 | ゲート適用 |
|----|------|--------|-----------|
| **S+** | 期待値 S/S+ の三連複フォーメーション（5点） | チーム LINE | **Phase1 必須** |
| **P6** | 荒×High×volatile×軸オッズ下限・日2R 上限 | 管理者 LINE | **Phase1 必須**（既存ゲートに追加） |
| デスクトップ / Streamlit UI | 手動確認用 | 人 | ゲート結果を**表示のみ**（買う/買わないは人任せ可） |
| オフライン `backtest_bets` | 全自信度高 | — | Phase1 では**変更しない**（まず運用だけで効果測定） |

**理由:** 7月のダメージは「当日に送って買う」経路が測りやすい。オフライン戦略を先にいじると因果が混ざる。

---

## 3. 用語

| 用語 | 定義 |
|------|------|
| **T-10 判定** | 発走10分前スナップで `build_race_bet_plan` した結果 |
| **T-30 参照** | 同一 `race_id` の `t_minus_30` スナップがあれば、同じ master 特徴量で再スコアした計画 |
| **プロフィール反転** | `exotic_profile` が 堅→荒 または 荒→堅 |
| **std ジャンプ** | T-30 と T-10 のオッズ標準偏差の絶対差 |
| **見送り** | 買い目 LINE を送らない。予想ログ・比較レポートは残す |

---

## 4. Phase 1 ルール（実装順）

### R1. プロフィール反転見送り（最優先）

**目的:** ライブで「流し ↔ BOX」が切り替わるレースに乗らない。

| 項目 | 内容 |
|------|------|
| **いつ** | T-10 の S+ / P6 送信判定の直前 |
| **前提** | 同日同レースの `t_minus_30` スナップが存在する |
| **欠落時** | T-30 が無い → **このルールはスキップ（従来どおり送信可）**。WARN ログのみ |
| **比較** | T-30 計画と T-10 計画の `exotic_profile` |
| **条件** | `T30.exotic_profile != T10.exotic_profile` → **見送り** |
| **拡張（任意・初期はOFF）** | `win_profile` 反転でも見送り（単勝通知がない現状では優先度低） |
| **ログ** | `FLIP_SKIP race_id=... T30=堅 T10=荒` |
| **ユーザー向け** | 送らない。チームには無通知でよい（ノイズ防止）。管理者ログ or Discord に1行可 |
| **設定** | `config/ops_gates.json` → `profile_flip_skip: true`（既定 true 推奨） |

**受け入れ条件**

1. T-30・T-10 ともあるレースで 堅→荒 にしたモックで S+ / P6 が送られない  
2. プロファイル一致時は従来どおり送れる  
3. T-30 欠落時は送信され、ログに `FLIP_SKIP_N/A no_t30`

**効果の事後検証（コード変更後・本番 or リプレイ）**

- 2026/7 の `compare_report` 上、T-10 で `ex_prof` が不一致だった日・レースを列挙  
- 「もし送っていなければ」仮想スキップ件数と、当日 S+ 実成績の突合  
- 合格目安: 送信回数が減っても、**送った分の ROI が悪化しない**（理想は改善）

---

### R2. odds_std ジャンプ見送り

**目的:** 市場が一気に広がり/縮まるレースは、upset スコアや volatile が不安定。

| 項目 | 内容 |
|------|------|
| **いつ** | R1 通過後、S+ / P6 送信前 |
| **入力** | `odds_std(T-30)`, `odds_std(T-10)`（`snapshot_compare` と同定義） |
| **条件（案A・推奨）** | `abs(std_T10 - std_T30) >= 40` かつ T-10 で `exotic_confidence == 高` → **見送り** |
| **条件（案B・緩い）** | 差 >= 50 のみ |
| **初期閾値** | **40**（7月 compare の日平均 delta が 35〜50 前後 → 中間） |
| **欠落時** | T-30 無し → スキップ（R1 と同様） |
| **設定** | `std_jump_skip: true`, `std_jump_threshold: 40` |
| **ログ** | `STD_JUMP_SKIP delta=45.2 thr=40` |

**受け入れ条件**

1. 閾値超えモックで見送り  
2. `std_jump_skip: false` で無効化できる  

**注意:** 閾値は **A/B とリプレイで確定**。最初は「観察モード」（ログだけ・見送りなし）でも可（§6）。

---

### R3. 堅 × volatile の三連を厳格化（オフライン連動は Phase 2）

**目的:** 7月で「堅」側の損失が大きく、volatile の的中が低い。

**Phase 1（運用・S+ のみ）**

| 項目 | 内容 |
|------|------|
| **条件** | T-10 で `exotic_profile == 堅` かつ `is_volatile == True` かつ 期待値 tier が S+ 候補 |
| **動作案** | **見送り**（強い）または **メッセージに警告ラベルのみ**（弱い） |
| **初期推奨** | 観察モード: LINE 本文に `【注意: 堅×volatile】` を付与し、**送る** |
| **設定** | `firm_volatile_mode: "observe" \| "skip" \| "off"` 既定 `"observe"` |

**Phase 2（オフライン・任意）**

| 項目 | 内容 |
|------|------|
| **候補A** | 堅×volatile は `exotic_firm` の gap を 0.70 → 0.80 にのみ適用 |
| **候補B** | 堅×volatile は三連点を流し6→流し4 or 1軸なし見送 |
| **検証** | `backtest_bets` を 2026/1–5 holdout + 6–7 validate。6–7改善かつ1–5を大きく悪化させない |

Phase 1 で「observe」のまま **少なくとも2開催週** ログを見てから `skip` に上げる。

---

### R4. 校正過信への対応（Phase 2 以降・情報表示）

**根拠:** 予測勝率 ~100% 帯でも実勝率 ~35–40%。

| 項目 | 内容 |
|------|------|
| **やらない（今）** | 単勝閾値の全面変更、表示温度の即変更 |
| **やる（表示）** | UI / 管理者メッセージに「校正注意: モデル勝率は過大になりやすい」注記（任意） |
| **やる（研究）** | 別タスクで `win_prob` デシル ROI を 2025 含め再確認してから閾値 |

---

### R5. 週次クラッシュ時の運用ルール（コード不要・運用手順）

| 項目 | 内容 |
|------|------|
| **トリガ** | **当日終了時点**で、その日のチーム三連（S+）仮想ROIが **50%未満**、または的中0 かつ投資3R以上 |
| **翌日以降** | 自動停止はしない。**人が**「P6 日上限を 2→1」または「S+ は様子見」を判断 |
| **記録** | `docs` または当日ログに理由を1行残す |

自動停止は誤検知リスクが高いので **Phase 1 では人が判断**。

---

## 5. 判定フロー（T-10 送信）

```
T-10 スナップ取得
  → score + build_race_bet_plan
  → S+ 対象? / P6 対象?（既存）
  → [R1] T-30 あり & exotic 反転? → 見送り
  → [R2] std ジャンプ? → 見送り（有効時）
  → [R3] 堅×volatile? → observe注記 or skip
  → 既存ゲート（P6 日上限・連敗ポーズ等）
  → LINE / Discord 送信
```

**既存との優先順位**

1. 技術失敗・休場・スナップ無し → 従来どおり未送信  
2. **R1 → R2 → R3**（新規）  
3. 既存 P6 日上限・連敗ゲート  
4. 送信  

---

## 6. 設定ファイル案

新規: `config/ops_gates.json`

```json
{
  "profile_flip_skip": true,
  "std_jump_skip": false,
  "std_jump_threshold": 40.0,
  "std_jump_mode": "observe",
  "firm_volatile_mode": "observe",
  "require_t30_for_buy": false,
  "comment": "2026-07 review; Phase1 defaults"
}
```

| キー | 既定 | 意味 |
|------|------|------|
| `profile_flip_skip` | true | R1 有効 |
| `std_jump_skip` | false | R2 見送りは最初 OFF |
| `std_jump_mode` | observe | R2 が off でもログに `STD_JUMP_WATCH` を残す |
| `firm_volatile_mode` | observe | R3 |
| `require_t30_for_buy` | false | true にすると T-30 無しは全見送り（厳しすぎるので初期 false） |

環境変数で上書きできるとよい（サーバ運用向け）:

- `OPS_PROFILE_FLIP_SKIP=0/1`
- `OPS_STD_JUMP_SKIP=0/1`

---

## 7. ログ・状態ファイル

| 出力 | 用途 |
|------|------|
| `data/processed/logs/watch_YYYYMMDD.log` | `FLIP_SKIP` / `STD_JUMP_*` / `FIRM_VOL_*` |
| （任意）`data/processed/snapshots/YYYYMMDD/ops_gate_decisions.jsonl` | 1レース1行: race_id, rule, action, metrics |

払戻後の夜間レポートに「今日ゲートで見送った件数」を1行足すと振り返りが楽（Phase 1.5）。

---

## 8. テスト計画

### 単体

- モック plan 2本（T30 堅 / T10 荒）→ R1 skip  
- std 差 45 → R2（skip 時）  
- 堅 volatile observe → 本文にラベル  

### 結合（サーバ）

1. 休場日で dry-run  
2. 開催日は `line` off でログだけ（`--no-line-notify` 相当）  
3. 1日分のログで R1 ヒット件数を確認  

### 効果測定（リリース後2〜4開催日 or 7月スナップリプレイ）

| 指標 | 見方 |
|------|------|
| 送信件数 | 前後比 |
| 送信した S+ の的中・ROI | ゲート後だけ集計 |
| 見送りレースの「送っていたら」仮想 ROI | 低ければルール有効 |

---

## 実装タスク分解（コーディング用）

| # | タスク | 状態 |
|---|--------|------|
| 1 | `config/ops_gates.json` + ローダ | ✅ |
| 2 | T-30 スナップ→plan 再計算ヘルパ | ✅ `build_plan_from_snapshot` |
| 3 | R1/R2/R3 判定関数 | ✅ `evaluate_buy_ops_gates` |
| 4 | `race_day_notify` の S+ / P6 送信直前に挿入 | ✅ |
| 5 | ユニットテスト | ✅ `tests/test_ops_gates.py` |
| 6 | （任意）UI にゲート結果バッジ | 未 |
| 7 | PROJECT_STATUS / README 追記 | ✅ |

**実装しないもの（この仕様の外）**

- `tuned_weights_*.json` 変更  
- `exotic_thresholds.json` 変更  
- オフライン既定戦略の変更（Phase 2）

---

## 10. 意思決定メモ

| 決定 | 内容 |
|------|------|
| 優先 | **運用ゲート** > 重み再チューニング |
| 荒BOXは当面維持 | 7月は荒 ROI が堅より良い |
| 単勝ロジック大改修なし | 7月 87.9% で相対的にマシ |
| 週次自動停止なし | 人が翌日判断（R5） |
| オフライン既定は据え置き | 効果を「当日送信」で切り分け |

---

## 11. 承認チェックリスト（実装開始前）

- [ ] R1（プロフィール反転見送り）を Phase1 で入れてよい  
- [ ] R2 は最初 **observe（ログのみ）** でよい  
- [ ] R3 は最初 **observe** でよい  
- [ ] オフライン BT の既定ロジックは変えない  
- [ ] 実装後、スナップリプレイ or 2開催で効果を見る  

（ユーザーが「実装して」と言ったら、このチェックを満たした前提でコーディングする）

---

## 12. 参照

- `scripts/analyze_july2026.py`
- `r_analysis/scripts/10_july2026_review.R`
- `r_analysis/output/reports/july2026_logic_guidance.md`
- `src/predictor/race_day_notify.py`（S+ / P6）
- `src/predictor/upset_p6_rules.py` / `upset_high_bet_gate.py`
- `src/predictor/snapshot_compare.py`
