# 台股起漲雷達

依公開可驗證的朱家泓技術分析原則，建立的台股盤後選股與回測平台。第一版掃描：

- 盤整約兩個月、量縮且接近箱頂的股票。
- 多頭強勢股跌破 5 日線後，重新站回或突破確認的股票。
- `WATCH`（觀察）、`TRIAL`（試單）、`CONFIRMED`（確認）三級訊號。
- 每日依最新均線、量能與支撐重新計算建議進場區、確認價及防守價。
- 現價離 5 日線超過 3% 時等待回測，超過 8% 標示過熱勿追。

> 跌破 5 日線本身不是買點。平台只會先列入觀察，待重新轉強才產生可執行訊號。

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

### 本機產生 Pages 資料

```powershell
cd backend
python -m app.cli backfill-history --days 183
python -m app.cli export-static

cd ..\frontend
npm run build:pages
```

靜態輸出位於 `frontend/out/`。Pages 使用 `/tw-stock-radar` base path；本機 FastAPI 模式仍可使用原本的 `npm run dev`。

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
- 跌破停損、收盤跌破 MA20 或持有 20 個交易日出場。

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
frontend/out/                     GitHub Pages build artifact
```

網站只發布候選股 K 線，不把全市場原始行情放入 Pages artifact；原始壓縮資料保留在 repository 供 Actions 重算與稽核。

## 規則來源與責任邊界

老師公開原則與平台自訂量化門檻分開處理：

- 公開原則：頭頭高、底底高；站上 MA20；均線走平或上彎；回後買上漲；盤整突破。
- 平台參數：40 日箱型、20% 振幅、1.2／1.5 倍量能、相對強度前 20% 等。

平台參數不是老師原始公式，必須通過樣本外回測才可升級為正式訊號。本工具不自動下單，也不構成投資建議。

系統預設 `STRATEGY_APPROVED=false`，因此即使出現 `CONFIRMED`，API 仍會標為研究訊號。只有在完整歷史資料的樣本外結果同時達到 200 筆交易、Profit Factor 1.2、正期望值及最大回撤不超過 25% 後，才可由維護者把該策略版本改為已核准；不得只因單一個股或示範資料表現良好而開啟。
