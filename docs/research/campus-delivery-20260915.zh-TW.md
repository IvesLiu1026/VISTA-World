# 交大校園探索、材質與動作交付

私人專案為 `projects/vista-campus/payload/PhotorealHome.uproject`，預設 `/Game/VISTA/CampusR13/Maps/Campus`。保留原有六個室內空間，新增光復校園、北門路口、大學路街區的近似場景、可駕駛汽車與可騎乘機車。共享 Sunshine 選取未變動；這份記錄不代表 Windows／Mac 串流驗收。

## 已實作

- Esc 開啟可點選的四個場景；Q 顯示眼前可用動作、室內活動與房間捷徑。WASD＋滑鼠移動／觀看，E 執行主要動作，Tab 切換視角。車上 W/S 控制前進／倒退、A/D 轉向、Space 煞車、停穩後 E 下車。選單開啟時車輛煞停。場景切換會重新開始探索；攜物、任務未結束、坐著或車上時會阻擋切換。
- 校園道路、穿越道、兩側行人號誌、固定路線車流與停放車輛。號誌為可控的實驗時序，不是現場交通號誌資料。車輛採掃掠碰撞與地面支撐；車輪、方向盤與把手隨運動更新。
- 九組 CC0 來源共 27 張 2K 貼圖，形成 14 組 PBR 表面：磚、混凝土、灰泥、外牆磁磚、花崗岩、鋪面、柏油、金屬、皮革、橡膠、車漆與玻璃。建築採公分尺度世界投影；車輛紋理採物件投影。車漆有 clear coat，車窗另用明確的透明材質。
- 汽車有可開合的駕駛座車門與環形方向盤；機車有獨立把手與較低座墊。汽車的上車、入座、握持、轉向、油門／煞車腳部動作與下車，以及機車的上下車、握持、轉向、停車落腳、起步收腳均接到操作流程。期間鎖住駕駛輸入，下車檢查出口是否可站立。
- 雙手以 IK 配合車輛接觸點，指節採保留骨長的關節調整，指尖以既有皮膚標記近似貼合實際把手圓管。接觸數值在骨架更新完成後量測。這是程序化動畫，並非動作捕捉、力回饋、輪胎動力學或軟組織接觸模擬。

## 資料與驗證

所有路徑均相對 workspace；外部資產、UE 套件、影片與執行記錄不進 Git。

| 項目 | 記錄 |
|---|---|
| 最終程式 | `runs/campus-build-n/package`；Editor、Game Development、Shipping 均成功 |
| 原有契約／compiler 與移動證據測試 | `runs/campus-source-tests-d.log`：34 項通過；`runs/campus-config-tests-a.log`：3 項舊版設定／缺圖回歸通過 |
| PBR 來源 | `runs/campus-pbr-a/acquisition.json`；公開 URL、實際尺寸與 SHA-256 另列 `campus-pbr-sources.json` |
| 幾何 | `runs/campus-geometry-e/geometry.json`；汽車／機車 GLB 結構檢查通過 |
| 表面與車輛作者記錄 | `runs/campus-surfaces-d.json`、`campus-articulated-d.json` |
| 精確戶外網格參照與材質覆寫 | `runs/campus-material-bindings-a.json`；R13 使用原 R4 網格資產，改動 actor 的材質槽 |
| 全新程序讀取驗證 | `runs/campus-surface-readback-d.json`、`campus-saved-g.json`：27 張貼圖、32 個戶外網格 actor、46 個材質槽變更；原室內 68 個帶 HomeLabel 的 actor 與契約相同 |
| 動作與握持 | `runs/campus-n-animations-d/process.json`：20 項原生檢查通過；兩部連續上下車影片；`runs/campus-contact-review-b.json` 含靜止／轉向接觸摘要 |


最終六組原生檢查共 **63 項通過**，全部使用 build-n 與相同 R13 地圖／設定，均正常退出：場景巡覽 7、車輛 19、穿越道 4、室內 5、材質 8、動作 20。記錄為 `runs/campus-n-{tour,vehicles,crossing,home,animations}-d` 與 `runs/campus-n-surfaces-c`。

可直接開啟 `runs/campus-review-ready-20260915/index.html`，內含原生畫面、汽車與機車連續操作影片，以及研究提案副本。`summary.json` 記錄各組結果和來源雜湊。最終私人 payload 清單為 `runs/campus-payload-r13.json`：4,190 個檔案、4,440,013,266 bytes，清單 SHA-256 `90385895a9ab3684439efe97d8fcc4e92d13ac64b46872c7077e98db9a487267`。它包含原有依賴與歷史資產；不是重新發布的研究資料集。

場景選單曾因作者重試留下 R10 路徑而切到中途版本；已改成按場景 ID 明確選取 R13，新增缺圖／重複 ID／歷史設定回歸，原生啟動及讀回亦檢查選單與地圖一致。停車出道路檢查改為在 8 秒界限內用真實按鍵依車頭方向與位置回饋控制，保持連續移動和道路到達斷言；舊固定時長失敗記錄保留。

貼圖替換曾觸發 Nanite 複製網格重建後的招牌邊界差異；最終改以原網格參照配合 actor 材質覆寫，新的讀取驗證逐一比較網格路徑、變換、碰撞和標籤。先前中途失敗的輸出保留，不列為完成證據。私人 UE 的診斷回報維持停用，原生執行確認有效設定；不宣稱網路隔離。

## 重建順序

以含 `/Game/VISTA/SixSpacesR5/Maps/Villa` 的獨立 `vista-campus` 專案為輸入，使用記錄的 UE 5.7.3、Blender 4.5.8 與 workspace `bin/uv`。每個輸出位置必須全新，作者程序與原生遊戲不可同時開啟同一私人專案。

1. `tools/blender/vista_campus/build.py --out NEW_GEOMETRY` 建立幾何；既有戶外幾何可用 `--vehicles-only-from` 保留並單獨重建車輛。
2. `tools/ue/vista_campus/author.py` 以 `VISTA_CAMPUS_ROOT=/Game/VISTA/CampusR4` 建立原始場景；`VISTA_CAMPUS_SOURCE` 指向幾何，`VISTA_CAMPUS_OUT` 指向作者記錄目錄。
3. `tools/runtime/vista_campus/acquire_materials.py --out NEW_PBR` 預設使用提交的 `docs/research/campus-pbr-sources.json`，逐張驗證 URL、位元組數與 SHA-256。
4. `tools/ue/vista_campus/surfaces.py` 使用 `VISTA_SURFACE_ROOT=/Game/VISTA/CampusR8`、`VISTA_MATERIAL_PACKAGE` 與全新 `VISTA_CAMPUS_OUT` JSON。
5. 安裝已建好的插件。`tools/ue/vista_campus/vehicles.py` 使用 `VISTA_VEHICLE_ROOT=/Game/VISTA/CampusR12`、幾何、`VISTA_SURFACE_REPORT` 與新作者 JSON。
6. `configure.py` 按場景 ID 明確更新四張地圖、室內契約地圖與預設地圖，避免重試後沿用中途版本。`tools/ue/vista_campus/rebind_surfaces.py` 以 `VISTA_FINAL_ROOT=/Game/VISTA/CampusR13`、表面與車輛作者記錄產出最終地圖。它使用精確的原始戶外網格參照。
7. 新的 UE 程序分別執行 `verify_surfaces.py` 與 `verify_saved.py`，再以 `run_native.py` 的 `animations / surfaces / vehicles / tour / crossing / home` 六組檢查驗證。全程沿用私人診斷回報停用旗標與獨立 X11／GPU 0。

## 實際限制

建築尺寸、位置與外型仍是近似搭建，植栽與車體造型明顯簡化；真實貼圖不等於完成校園數位孿生或 GTA 等級美術。上下車是程序化姿勢，門把抓取細節、過渡步態與更多鏡頭下的自碰撞仍可再打磨。自動車流目前沒有完整人物駕駛演出。

道路邊界／重生、完整繁體中文與控制器 UI、跨地圖持續任務、真實交通行為與模型觀察／動作介面尚未完成。這些場景可用於系統開發；成為正式研究資料前仍須選定實驗契約、觀察限制、資產使用範圍、訓練／測試切分與可重播驗證。

研究方向另見 [VISTA 下一篇研究提案](vista-next-paper-20260914.zh-TW.md)：12 個方向，優先比較真正介入效果、小模型生成可執行世界，以及 Ask/Look/Act 的主動證據選擇；沒有把本次工程檢查當作模型實驗結果。

## 原始碼保存

來源位於 `worktrees/campus-gameplay` 的 `codex/campus-gameplay`，基於 PR #22 的 `1696f99`。這次未建立遠端 PR：GitHub app 的 Create Tree 回傳 403（Resource not accessible by integration），HTTPS Git 無 CLI 憑證，SSH 嚴格主機金鑰檢查未通過。未變更憑證或 known_hosts。保留本機提交與 `runs/campus-source-review.patch`，目標仍為 `codex/vista-home-villa-integration`；不得把它當作已合併或已發布版本。
