# 台股起漲雷達

依公開可驗證的朱家泓技術分析原則，建立的台股盤後選股與回測平台。目前掃描：

- `多頭確認`：頭頭高、底底高、收盤站上 20 日線，且 5、10、20 日線多頭排列。
- `回後買上漲`：多頭趨勢中，回檔守住 20 日線且回檔均量低於前段上漲均量，再收復 5 日線；確認時需突破前一日高點，且轉強量大於回檔均量。
- `盤整突破`：多頭趨勢中，最近 20 日整理均量低於前 20 日均量，收盤突破最近確認波峰，且突破量大於整理均量 1.2 倍。
- `WATCH`（方向或條件觀察）、`TRIAL`（正在轉強但尚未確認）、`CONFIRMED`（買點確認）三級訊號。
- 只有 `CONFIRMED` 才會顯示可執行進場區；結構停損設在最近確認波谷。
- 每日另產生「回後買上漲 Top 10」及「盤整突破 Top 10」；納入轉強與確認訊號，但確認固定優先。
- Top 10 排除結構風險超過 8%的股票；回後買上漲另要求到前高至少保有 1.5R 空間，且兩套榜單都套用量縮硬條件。

> 多頭方向成立、跌破後站回 5 日線，或盤中突破，都不單獨視為買點；必須等各策略的收盤確認條件完整成立。

## GitHub Pages 版本

本專案可完全在 GitHub 上運作，不需要常駐伺服器：

- Public repository：`tw-stock-radar`
- GitHub Pages：Next.js 靜態輸出
- 自動更新：週一至週五台北時間 19:30（UTC 11:30）
- 資料來源：TWSE、TPEx 官方歷史與盤後行情
- 保存範圍：最近六個月壓縮日行情
- 失敗保護：任一市場缺資料、資料日期不一致或筆數異常時停止發布

GitHub Actions：

- `Update market data`：回補／追加行情、執行策略、提交靜態 JSON。
- `Deploy GitHub Pages`：測試、lint、靜態建置並部署 Pages。
- 兩個 workflow 均支援手動執行；首次可勾選 `backfill` 回補六個月。

### 一鍵手動更新

網站可透過 Cloudflare Access 保護的 Worker 安全觸發
`Update market data`，不會把 GitHub Token 暴露在 Pages：

```powershell
cd trigger-worker
npm install
npm test
npm run typecheck
npm run deploy
```

Worker 開發與部署需要 Node.js 22 以上。

Worker 需要以下 Secret：

- `GITHUB_TOKEN`：僅限本儲存庫且只有 `Actions: write` 的 Fine-grained PAT。
- `ACCESS_TEAM_DOMAIN`：Cloudflare Access team domain。
- `ACCESS_AUD`：Access application audience。
- `ALLOWED_EMAIL`：唯一允許觸發更新的 Email。

部署後在 GitHub repository variable 設定
`UPDATE_WORKER_URL=https://<worker>.<account>.workers.dev/`。Pages
重新建置後會在資料日期旁顯示「立即更新資料」按鈕。Worker
會拒絕未通過 Access、Email 不符、已有工作執行中或五分鐘內重複觸發的請求。

### 本機產生 Pages 資料

```powershell
cd backend
python -m app.cli backfill-history --days 183
python -m app.cli export-static

cd ..\frontend
npm run build:pages
```

靜態輸出位於 `frontend/out/`。Pages 使用 `/tw-stock-radar` base path；本機 FastAPI 模式仍可使用原本的 `npm run dev`。

每日推薦榜單位於 `frontend/public/data/recommendations.json`，會隨每日排程及網站「立即更新資料」一併重算。若嚴格條件下不足 10 檔，網站只顯示實際符合數量，不放寬風險門檻湊數。

## 技術架構

- Backend：Python 3.11、FastAPI、SQLAlchemy、APScheduler。
- Frontend：Next.js 16、React 19、Tailwind CSS 4、Lightweight Charts 5。
- Database：本機預設 SQLite；Docker Compose 使用 PostgreSQL 16。
- Data：TWSE、TPEx 官方盤後與歷史行情；另支援標準 CSV 歷史資料匯入。

GitHub 版使用官方市場每日歷史行情回補六個月；更長期間的研究資料仍須使用具合法來源的標準 CSV。系統不會混入來源不明資料。

## 本機快速啟動

### 1. 後端

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m app.cli seed-demo
uvicorn app.main:app --reload --port 8000
```

API 文件：<http://localhost:8000/docs>

### 2. 前端

另開一個 PowerShell：

```powershell
cd frontend
npm install
npm run dev
```

儀表板：<http://localhost:3000>

### 3. 正式盤後快照

```powershell
cd backend
python -m app.cli fetch-latest
python -m app.cli scan
```

官方快照每天只能累積一個交易日。資料不足 65 個交易日以前，不會產生策略訊號。

## 匯入歷史資料

CSV 必須包含以下欄位：

```text
symbol,name,market,date,open,high,low,close,volume,turnover
```

日期格式為 `YYYY-MM-DD`，成交量單位為股，成交金額單位為新台幣元。範本在 `examples/history-template.csv`。

```powershell
cd backend
python -m app.cli import-csv ..\examples\history-template.csv
python -m app.cli scan
```

## 回測

```powershell
cd backend
python -m app.cli backtest 2330
```

目前回測採：

- 訊號產生後的下一交易日開盤進場，避免未來函數。
- 雙邊手續費各 0.1425%、賣出稅 0.3%、雙邊滑價各 0.1%。
- 觸及最近確認波谷停損，或收盤跌破 MA20 後的下一交易日開盤出場。
- 不使用固定持有天數；資料結束仍持有的部位，以最後一日收盤結算。

成本皆為保守的可調模型；正式使用前應依券商折扣與當時法規更新。

## 自動排程

```powershell
cd backend
python -m app.worker
```

worker 會在台北時區週一至週五 19:00 下載官方快照並掃描。同日成功任務不會重複執行。

這是常駐後端版本的排程；GitHub Pages 版改由 `.github/workflows/update-data.yml` 在 19:30 執行。

## Docker Compose

```powershell
docker compose up --build
docker compose exec api python -m app.cli seed-demo
```

啟動後：

- Web：<http://localhost:3000>
- API：<http://localhost:8000>
- API 文件：<http://localhost:8000/docs>

## 測試與建置

```powershell
cd backend
python -m pytest

cd ..\frontend
npm run lint
npm run build
npm run build:pages
npm audit --omit=dev
```

## GitHub 資料目錄

```text
data/raw/YYYY-MM-DD.json.gz       六個月官方行情日檔
data/state/manifest.json          日期、筆數與 checksum
frontend/public/data/             網站使用的最新訊號與候選 K 線
frontend/public/data/recommendations.json  每日兩套 Top 10
frontend/out/                     GitHub Pages build artifact
```

網站只發布候選股 K 線，不把全市場原始行情放入 Pages artifact；原始壓縮資料保留在 repository 供 Actions 重算與稽核。

## 規則來源與責任邊界

老師公開原則與平台自訂量化門檻分開處理：

- 公開原則：頭頭高、底底高；站上 MA20；均線走平或上彎；回後買上漲；盤整突破；跌破 MA20 防守。
- 平台量化轉譯：5MA > 10MA > 20MA；以左右各兩根 K 棒確認波峰波谷；MA20 高於五日前；盤整需最近 20 日量縮，突破量需大於整理均量 1.2 倍；回檔需相對前段量縮，轉強量需大於回檔均量；突破與收復條件以收盤價確認。

這些數值是平台為了讓電腦可重複執行所做的量化轉譯，不是老師公布的唯一公式，也不代表老師本人背書。策略必須通過樣本外回測才可升級為正式訊號。本工具不自動下單，也不構成投資建議。

系統預設 `STRATEGY_APPROVED=false`，因此即使出現 `CONFIRMED`，API 仍會標為研究訊號。只有在完整歷史資料的樣本外結果同時達到 200 筆交易、Profit Factor 1.2、正期望值及最大回撤不超過 25% 後，才可由維護者把該策略版本改為已核准；不得只因單一個股或示範資料表現良好而開啟。
