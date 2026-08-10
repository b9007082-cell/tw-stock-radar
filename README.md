# 台股起漲雷達

依公開可驗證的朱家泓技術分析原則，建立的台股盤後選股與回測平台。目前掃描：

- `多頭確認`：頭頭高、底底高、收盤站上 20 日線，且 5、10、20 日線多頭排列。
- `回後買上漲`：多頭趨勢中，回檔不跌破前低、守住 20 日線且回檔均量低於前段上漲均量；確認時需紅 K 收復 5 日線、突破前一日高點、轉強量大於回檔均量，且當日成交量大於 2000 張；若價格已突破但轉強量只有回檔均量 0.85～1.0 倍，先列觀察不視為確認買點。
- `底部起漲`：低位整理後的轉強訊號；今日成交量需大於 2000 張，股價距近 60 日低點不超過 45%，近 20 日整理區間不超過 30%，整理均量不高於前 20 日均量 1.05 倍，收盤站上 20MA 且 20MA 走平或轉上。確認時需紅 K 收盤突破近 20 日整理壓力、突破前一日高點，且今日量大於整理均量 1.2 倍；突破近 10 日短壓但尚未突破 20 日壓力者列轉強。
- `處置反彈`：以中探針型態作為價量版篩選模板；近 20 日高點回落至少 25%，近 5 日或 10 日急跌，近 30 日出現疑似跌停／重挫節奏，低檔爆出前一日 2 倍以上成交量並形成止跌 K。隔日上漲收盤突破止跌 K 高點列確認，跌破止跌 K 低點出場。此分類目前為價量推估版，正式處置與出關日仍以證交所／櫃買公告為準。
- `搶反彈`：近 20 日高點回落超過 15%，且具連續下跌或 5 日急跌特徵；低檔出現成交量大於前一日 2 倍以上的止跌 K（長下影、十字線或實體紅 K），等隔日上漲收盤突破前一日止跌 K 最高點才列確認買點，跌破前一日 K 低點出場。
- `布林收斂突破`：前一日 20 日布林通道寬度位於近 80 日低分位（≤20%），隔日需出現第一根收盤突破上通道且突破前一日高點的紅 K；同時成交量需放大至 20 日均量 1.5 倍以上、收盤位置在當日 K 棒高檔區，作為主力攻擊買盤的價量代理條件。
- `6060戰法`：用 Yahoo chart API 抓取最近 3 個月 60 分鐘 K 線；日成交量需大於 2000 張，60分K 收盤需貼近 60MA（距離 1.5% 內），且 60分60MA 必須向上。進場以放量突破 60分60MA 為確認，回踩 60分60MA 不破列為轉強觀察；不再把日線多頭排列、20日線向上或 MACD 零軸上作為硬性條件。
- `低檔高殖利率`：使用 TWSE / TPEx 官方本益比、殖利率與股價淨值比資料；殖利率需 ≥ 5%、日成交量大於 2000 張、近 100 日從高點回落至少 8%，且距近 100 日低點不超過 35%，P/B 高於 2.5 者排除。站回 20 日線且 20 日線不再轉弱者列確認，其餘列轉強或觀察。
- `Lorentzian ML`：依 AI Edge 官方 port repo 的 Lorentzian Classification 實作概念轉譯為每日選股版；Source 使用 `close`、Neighbors `8`、Max Bars Back `2000`、Feature Count `5`，使用 RSI、WaveTrend、CCI、ADX 與 RSI 快線做 0～1 正規化後的 Lorentzian distance ANN 投票，再搭配 Volatility / Regime 濾網、Kernel Lookback `8`、相對強度與 2000 張流動性門檻。ADX 濾網依預設保持關閉，只顯示 ADX 數值供判讀。此項為研究輔助訊號，不是朱家泓老師五字訣原始條件。
- `指標輔助`：KD 低檔黃金交叉向上、MACD 維持 0 軸之上會列入提示與排序理由；因指標常落後價格，暫作輔助檢查，不作為硬刪除門檻。
- `WATCH`（方向或條件觀察）、`TRIAL`（正在轉強但尚未確認）、`CONFIRMED`（買點確認）三級訊號。
- 只有 `CONFIRMED` 才會顯示可執行進場區；結構停損設在最近確認波谷。
- 每日另產生「回後買上漲 Top 10」、「底部起漲 Top 10」、「處置反彈 Top 10」、「搶反彈 Top 10」、「布林收斂突破 Top 10」、「6060戰法 Top 10」、「低檔高殖利率 Top 10」及「Lorentzian ML Top 10」；確認固定優先，底部起漲以離 60 日低點遠近、20 日整理區間、整理量縮、突破量能與結構風險排序，處置反彈以中探針型態相似度、急跌日、偏離20MA、低檔爆量與止跌 K 風險排序，搶反彈以跌幅、低檔爆量、止跌 K 風險與是否突破止跌 K 高點排序，布林收斂突破以收斂分位、突破上軌幅度、主力攻擊量與收盤位置排序，6060戰法以距60分60MA遠近、60分60MA上彎、放量突破或回踩不破排序，低檔高殖利率以殖利率、離低點遠近、從高點回落、P/B 與成交張數排序，Lorentzian ML 以 AI Edge port 對齊後的近鄰投票、信心、Kernel 斜率、相對強度與結構風險排序。
- Top 10 會排除風險過高的股票；回後買上漲維持結構風險 ≤ 8% 且到前高至少保有 1.5R 空間，底部起漲因屬早期低位佈局，允許整理區停損風險放寬到 30%，但排序會優先把風險較低、量縮後放量、接近突破確認的股票排前面。兩套榜單都套用量縮與 2000 張流動性硬條件。

> 多頭方向成立、跌破後站回 5 日線，或盤中突破，都不單獨視為買點；必須等各策略的收盤確認條件完整成立。

## GitHub Pages 版本

本專案可完全在 GitHub 上運作，不需要常駐伺服器：

- Public repository：`tw-stock-radar`
- GitHub Pages：Next.js 靜態輸出
- 自動更新：週一至週五台北時間 19:30（UTC 11:30）
- 資料來源：TWSE、TPEx 官方歷史與盤後行情；低檔高殖利率另使用官方本益比、殖利率與股價淨值比 OpenAPI
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

每日推薦榜單位於 `frontend/public/data/recommendations.json`，會隨每日排程及網站「立即更新資料」一併重算。若嚴格條件下不足 10 檔，網站只顯示實際符合數量，不放寬風險門檻湊數；搶反彈屬逆勢交易，未突破止跌 K 高點前只列觀察。

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
frontend/public/data/recommendations.json  每日六套 Top 10
frontend/out/                     GitHub Pages build artifact
```

網站只發布候選股 K 線，不把全市場原始行情放入 Pages artifact；原始壓縮資料保留在 repository 供 Actions 重算與稽核。

## 規則來源與責任邊界

老師公開原則與平台自訂量化門檻分開處理：

- 公開原則：頭頭高、底底高；站上 MA20；均線走平或上彎；回後買上漲；低位整理後突破；跌破 MA20 防守。
- 平台量化轉譯：多頭確認需 5MA > 10MA > 20MA；回檔需相對前段量縮，轉強量大於回檔均量才算確認，若轉強量達回檔均量 0.85～1.0 倍且收盤突破前高則列觀察；底部起漲不要求多頭排列，改看股價距近 60 日低點不超過 45%、近 20 日整理區間不超過 30%、整理量不高於前段 1.05 倍、收盤站上 20MA、20MA 走平或轉上，並以突破近 10/20 日壓力搭配 1.0～1.2 倍以上量能分級；處置反彈需近 20 日高點回落至少 25%、近 30 日有疑似跌停／重挫節奏、低檔止跌 K 爆出前一日 2 倍以上成交量，並以上漲收盤突破止跌 K 高點確認；搶反彈需近 20 日跌幅超過 15%、低檔止跌 K 爆出前一日 2 倍以上成交量，並以上漲收盤突破止跌 K 高點確認；突破與收復條件以收盤價確認。
- 開源輔助：Lorentzian ML 來自 jdehorty 的 `Machine Learning: Lorentzian Classification v2.0` 概念，原始碼授權為 Mozilla Public License 2.0。本平台只轉譯每日掃描所需的特徵、Lorentzian distance 近鄰投票與 Kernel 趨勢濾網，並標示為研究輔助訊號。

這些數值是平台為了讓電腦可重複執行所做的量化轉譯，不是老師公布的唯一公式，也不代表老師本人背書。策略必須通過樣本外回測才可升級為正式訊號。本工具不自動下單，也不構成投資建議。

系統預設 `STRATEGY_APPROVED=false`，因此即使出現 `CONFIRMED`，API 仍會標為研究訊號。只有在完整歷史資料的樣本外結果同時達到 200 筆交易、Profit Factor 1.2、正期望值及最大回撤不超過 25% 後，才可由維護者把該策略版本改為已核准；不得只因單一個股或示範資料表現良好而開啟。
