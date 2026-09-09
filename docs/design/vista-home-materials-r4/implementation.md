# Home R4 材質進度與保留的 Demo

今天的操作入口仍是 Sunshine **VISTA Photoreal Home**，使用 Home R3
`fc68a26236f53245b242283097576e93fa9a61c4` 的 project-x。
R4 在獨立工作目錄製作，沒有更換 Sunshine 入口或向使用者的視角送出操作。

R3 完整備份在 `/data/sysx/vista-world/home/demo-r3-20260908`：
2,318 個專案檔案、約 1.35 GB，另有原始碼 tar。
`demo-lock.json` 記錄逐檔 SHA-256、啟動設定、服務 PID 和來源 commit。
影片、14 頁簡報和 8 分鐘操作腳本仍在
`/data/sysx/vista-world/presentations/vista-home-r3-progress-20260908/final`。

## 本輪實作

| 範圍 | 現在的修改 |
| --- | --- |
| 沙發、床單、窗簾 | 實拍亞麻與棉布的顏色、粗糙度、法線，依真實紋理尺寸設定重複比例 |
| 木地板、門、家具 | 沿用舊 SimWorld + VISTA 的白橡木來源，校正原先過大的紋理尺度與家具色調 |
| 牆面、天花板、櫥櫃漆面 | 補入實拍牆漆的表面變化；依用途降低法線及色差強度 |
| 廚房與玄關地坪 | 加入磨石子實拍表面 |
| 不鏽鋼、鍍鉻、陶瓷、釉面 | 保留原有表面圖，調整粗糙度、金屬性和適用表面的方向性反光 |
| 人物 | 沿用現有皮膚及衣物圖、骨架和權重；增加預積分皮膚散射，調整衣料、頭髮及鞋面反光 |

21 個照片材質設定共用 18 張貼圖，另有 ABS 和橡膠材質。
新材質套用到 130 個材質槽；77 個既有表面槽另有反光調整。
電腦按鍵保留 ABS，洗衣機軟管使用橡膠，洗衣籃保留原編織幾何表面。

全部操作只調整材質槽，沒有替換 StaticMesh、變更碰撞、增加物件、
移動角色或改寫動作契約。158 個靜態物件的前後狀態檢查通過。
兩套人物網格的骨架和材質槽數保持相同，眼睛的透明材質保留。

## 已交付與驗證範圍

執行紀錄：`/data/sysx/vista-world/runs/vista-home-materials-r4-20260908a`。
選定副本：`project-e/PhotorealHome.uproject`；匯入紀錄：`import-e.json`。

- 35 項契約、編譯計畫和材質對應測試通過。
- Blender 已保存可重建的場景與人物材質預覽；六張畫面包含三個房間、兩張材質近景和人物。
- UE 以 NullRHI 在獨立副本匯入並保存，沒有啟動額外 GPU 視窗；匯入行程正常結束。
- 保存後的 UE 讀回驗證 `verify-saved-e.json` 通過：207 個材質槽、21 個實際連接至顏色／粗糙度／法線輸出的照片材質、18 張貼圖、UV 通道與校正參數，以及兩套人物的原有皮膚圖片和散射接線。
- `integrity-final-e.json` 通過：2,318 個來源與備份檔案雜湊一致，Sunshine 設定、服務 PID 及啟動時間一致。R4 副本僅修改 Home 地圖、兩套人物的材質槽和自己的 DDC 設定；全部既有 StaticMesh 與插件檔案保持逐位元相同。

匯入器會明確指定貼圖角色。亞麻的藍色 albedo 會被 UE 自動誤判為法線圖；
已改為先設定普通色彩壓縮，再設定 sRGB，並在保存和讀回時檢查。
最終副本使用上述修正；早期匯入副本與失敗紀錄保留供追溯，沒有切入 demo。

這些 Blender 圖是**材質製作預覽，不是 Sunshine 畫面**。房間預覽採用既有
R1 Blender 幾何；實際 UE 材質修改以完整 R3 project-x 備份為基底。
Blender 的布料 sheen 與皮膚散射，是對材質方向的預覽；UE 目前使用 Default Lit
照片材質與 Preintegrated Skin，兩個引擎的輸出不保證完全相同。

為保留正在操作的 demo，本輪沒有做新版 UE 畫面、全屋動作或 FPS 驗收。
R4 尚未取代 R3；人物毛髮形狀、形體、衣物變形與第一人稱遮擋仍需下一輪精修。
未新增正式 VISTA 標籤或模型可見案例。

[六張預覽與 Demo 入口說明](/data/sysx/vista-world/runs/vista-home-materials-r4-20260908a/R4材質進度.md)。
`world_packs/vista_home_materials_r4/delivery.json` 保存本輪輸出與驗證紀錄的雜湊索引。

## 素材來源

舊 SimWorld + VISTA 的實拍素材包仍在
`/mnt/NAS2/yhliu/SimWorldStudio/vista-playable-home-realism/runs/20260816T073747Z/external-assets/attempt-01-poly-haven-cc0`。
本輪直接沿用其中的白橡木與毛料；缺少的表面另外下載四組免費貼圖，共 55,681,375 bytes。
所有下載都經既有下載器核對公開大小與 MD5，另外保存 SHA-256。

來源：[白橡木](https://polyhaven.com/a/white_oak_veneer)、
[毛料](https://polyhaven.com/a/poly_wool_herringbone)、
[棉布](https://polyhaven.com/a/cotton_jersey)、
[亞麻](https://polyhaven.com/a/rough_linen)、
[牆漆](https://polyhaven.com/a/beige_wall_001)、
[磨石子](https://polyhaven.com/a/terrazzo_tiles)。
素材採用 [Poly Haven CC0 授權](https://polyhaven.com/license)。
人物沿用已保存的 MakeHuman CC0 來源，沒有生成新人物照片。

沒有複製 City Sample／HSSD 受限資產，沒有付費模型、圖片／影片生成或上傳。

## 重建

從本工作目錄使用 `uv`，先以 `prepare_materials.py` 合併原有與新增貼圖來源；
再用 `prepare_project.py` 從保留的 demo 建立新的專案目錄。
兩個腳本都要求新輸出，避免覆寫先前成果。

`tools/blender/vista_home_materials_r4/build_previews.py` 接收
`--source`、`--plan`、`--out`；加 `--character` 產生人物預覽。
使用 Blender 4.5.8，`--background --threads 4 --python-exit-code 1`，Cycles CPU。

`tools/ue/vista_home_materials_r4/import_overlay.py` 透過
`VISTA_HOME_MATERIALS_R4_CONFIG` 讀取匯入設定；
`verify_saved.py` 透過 `VISTA_HOME_MATERIALS_R4_VERIFY` 讀取讀回設定。
兩者都要求 `-NullRHI` 和符合設定的專案路徑。
實際設定保存在執行紀錄目錄的 `import-config-e.json` 與 `verify-config-e.json`。
UE 使用網路隔離、獨立 UserDir、獨立 DDC、低優先序及兩個 CPU 核心。

原有 demo 仍運行時，不執行 R4 的 Sunshine 切換或第二個 GPU 預覽。
