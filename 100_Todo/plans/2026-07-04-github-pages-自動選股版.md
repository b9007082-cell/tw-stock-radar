# 台股起漲雷達 GitHub Pages 自動選股版

> 建立時間：2026-07-04 15:03
> 類型：改善現有專案
> 狀態：待執行

---

## 你要做的事（一句話版）

將現有台股起漲雷達改造成可部署於公開 GitHub repository `tw-stock-radar` 的靜態網站，由 GitHub Actions 每個交易日台北時間 19:30 自動抓取官方盤後資料、保留最近六個月行情、計算訊號並安全發布到 GitHub Pages。

## 背景和動機

目前系統使用 Next.js 前端、FastAPI 與 SQLite/PostgreSQL 後端，適合本機或伺服器部署，但 GitHub Pages 只能提供靜態檔案，不能常駐執行 FastAPI 或資料庫。

GitHub 版本採「離線計算、靜態發布」：

```text
GitHub Actions 排程
        |
        v
TWSE / TPEx 官方行情
        |
        v
六個月壓縮歷史資料
        |
        v
Python 策略與回測引擎
        |
        v
靜態 JSON + Next.js export
        |
        v
GitHub Pages
```

現有 FastAPI 保留供本機研究與測試；公開網站完全不依賴常駐後端。

## 已確認設定

- Repository 名稱：`tw-stock-radar`
- Repository 可見性：Public
- 網站服務：GitHub Pages
- 自動更新：週一至週五台北時間 19:30，即 UTC 11:30
- 歷史資料：最近六個月
- 資料來源：TWSE、TPEx 官方公開行情
- 策略狀態：預設研究版，未通過樣本外驗證不得顯示為已核准
- 手動操作：保留 GitHub Actions `workflow_dispatch`

## 靜態資料結構

```text
data/
  raw/
    YYYY-MM-DD.json.gz
  state/
    manifest.json

frontend/public/data/
  manifest.json
  summary.json
  signals.json
  bars/
    2330.json
    ...
  backtests/
    2330.json
    ...
```

### 原始資料保存規則

- 每個交易日一個 gzip JSON，內容為當日上市、上櫃普通股 OHLCV 與成交金額。
- 僅保留最近六個月，超出保留期的檔案由資料工作流程移除。
- 每日檔案包含資料日期、來源網址、擷取時間、筆數與 SHA-256。
- 上市與上櫃資料日期不同、總筆數異常或必要欄位缺失時，當次工作失敗。

### 網站資料發布規則

- `manifest.json` 包含資料日期、策略版本、研究／核准狀態、生成時間與各檔案雜湊。
- `signals.json` 只保存最新選股結果與命中理由。
- `bars/` 只輸出候選股最近六個月 K 線，避免網站下載全市場資料。
- `backtests/` 只輸出候選股摘要，不公開龐大逐筆交易紀錄。
- 所有檔案先寫入 staging 目錄，完整驗證後再原子替換正式輸出。

## 具體步驟

### Step 1：重構資料來源與六個月回補

- 做什麼：將 TWSE、TPEx 資料來源拆成可測試 adapter；加入依交易日抓取市場全量歷史行情的回補命令，以及交易日、欄位與筆數驗證。
- 產出：`backfill`、`update-latest` CLI，以及六個月 gzip 日檔。
- 注意：只接受官方來源；遇到限流採指數退避與快取，不以第三方資料靜默補缺。

### Step 2：建立靜態網站匯出器

- 做什麼：重用現有指標、策略、相對強度與回測模組，從六個月日檔產生 summary、signals、候選 K 線及回測摘要。
- 產出：可重跑且結果一致的 `export-static` CLI 與 JSON schema。
- 注意：輸出前檢查至少 65 個交易日、資料新鮮度、價格合理性、重複資料及策略版本。

### Step 3：將 Next.js 改為 GitHub Pages 靜態輸出

- 做什麼：設定 `output: "export"`、`basePath: "/tw-stock-radar"`、`assetPrefix` 與 `trailingSlash`；前端改讀同站靜態 JSON，不再呼叫 localhost API。
- 產出：可由 `npm run build` 生成 `frontend/out/` 的靜態網站。
- 注意：本機開發模式仍可切換 API 與靜態資料，不能破壞目前 FastAPI 工作流。

### Step 4：建立資料更新 GitHub Actions

- 做什麼：建立週一至週五 UTC 11:30 排程及手動執行 workflow；安裝 Python 依賴、下載當日行情、保留六個月、產生靜態 JSON、執行測試後提交資料變更。
- 產出：`.github/workflows/update-data.yml`。
- 注意：加入 concurrency lock、最小權限、無變更不 commit、失敗不覆蓋舊資料；提交訊息包含資料日期與策略版本。

### Step 5：建立 GitHub Pages 部署 Actions

- 做什麼：在資料更新成功或 `main` 前端變更時執行 lint、測試與 Next.js export，再使用 GitHub Pages 官方 artifact 流程部署。
- 產出：`.github/workflows/deploy-pages.yml` 與 Pages build artifact。
- 注意：使用 `contents: read`、`pages: write`、`id-token: write` 最小權限；同一時間只允許一個部署。

### Step 6：加入失敗保護與自動測試

- 做什麼：測試官方資料 parser、六個月裁切、重複執行一致性、靜態 JSON schema、base path、候選股 K 線與失敗時保留前一版。
- 產出：後端單元／整合測試、前端 build 測試、workflow fixture 測試。
- 注意：資料日期落後、上市／上櫃日期不一致、候選結果空白但市場資料異常時，工作流程必須失敗並保留舊網站。

### Step 7：建立 Public repository 並發布

- 做什麼：初始化有效 Git repository、建立 `tw-stock-radar` Public repository、提交並推送程式；在 GitHub 啟用 Pages 的 GitHub Actions source，手動執行六個月回補與首次部署。
- 產出：公開原始碼 repository、GitHub Pages 網址與成功的 Actions 執行紀錄。
- 注意：建立 repository、推送與啟用 Pages 都是 GitHub 外部狀態變更，執行前再次確認登入帳號與發布內容。

### Step 8：正式驗收

- 做什麼：比對 GitHub Pages 與本機匯出結果；檢查桌機、手機、篩選、搜尋、K 線、部位試算、資料日期、研究版標示及隔日增量更新。
- 產出：部署驗收紀錄與維護說明。
- 注意：畫面不得將示範資料當成真實訊號；資料不足或回測未通過時必須明確顯示研究狀態。

## 預計成果

- 可公開瀏覽的 `tw-stock-radar` GitHub Pages 網站。
- 每個交易日台北時間 19:30 自動更新。
- 首次部署即具備最近六個月官方歷史行情。
- 不需伺服器、資料庫、API token 或付費服務。
- 資料與策略結果具來源、日期、版本及 checksum，可重現與稽核。
- Actions 失敗時保留前一版可用網站。
- 可手動執行資料更新、回補與重新部署。

## 不包含在這次的範圍

- 盤中即時行情或分鐘 K。
- LINE、Telegram、Email 推播。
- 自動下單與券商帳戶串接。
- 五年以上全市場資料倉庫。
- Supabase、Render、Vercel Functions 等外部後端服務。
- 自訂網域與付費 CDN。
- 將研究版策略直接標成正式投資訊號。

## 可能遇到的風險

- 官方網站限流或格式變更：使用快取、退避、fixture 測試與嚴格 schema；失敗時不發布。
- GitHub Actions 排程延遲：排程設於 19:30 並保留手動 workflow，不承諾精確到分鐘。
- Repository 持續膨脹：僅保存六個月 gzip 日檔，網站只發布候選股資料。
- GitHub Pages base path 錯誤：在 CI 檢查所有靜態資源與 JSON URL 均包含 `/tw-stock-radar`。
- 假日或資料未更新：依實際資料日期判斷；無新交易日不產生重複 commit。
- 六個月資料不足以完成完整策略驗證：維持研究版標示，不因網站上線而解除驗證閘門。
- 公開 repository 暴露策略參數：這是 Public 方案的既定結果，不放入帳號資料、token 或其他秘密。

## 執行完成定義

- Public repository 名稱為 `tw-stock-radar`。
- GitHub Pages 可從公開網址載入，無 localhost API 請求。
- 六個月官方行情回補成功，至少包含 65 個交易日。
- 手動與排程 workflow 均可重複執行，無新資料時不產生 commit。
- 任一資料品質檢查失敗時，前一版 Pages 維持可用。
- 本機與 Pages 的 summary、signals、K 線及策略版本一致。
- 後端測試、前端 lint/build、安全掃描及瀏覽器桌機／手機驗收通過。
