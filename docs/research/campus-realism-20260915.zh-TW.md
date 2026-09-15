# 校園寫實度更新：CampusR25

這一輪在既有六房間、光復校區、北門與大學路上加入實體立面細節，重新製作汽車／機車的外觀網格，並細化原有人物的衣物及皮膚材質。地圖仍是近似搭建；人物臉部、頭髮、車輛造型與遠方街區仍有明顯簡化，不能稱為 GTA 等級美術或測量重建。

## 變更與保留的契約

- 31 棟可見街廓建築增加窗框深度、窗台、百葉、排水管、冷氣格柵、欄杆和入口分件。新增立面網格不承擔互動碰撞。
- 汽車改為弧面車頂、傾斜玻璃、前後門分件、座椅、儀表與燈具；機車補入踏板紋、煞車拉桿、懸吊與排氣管。輪胎、輪圈和輪轂重新建模。
- 前門鉸鏈、方向盤／握把、車輪與座位的操作基準沿用既有版本。53 根骨架的順序與綁定保留；原始皮膚頂點和權重的 SHA-256 未變更。
- 黑色上衣及工裝褲細分後增加毫米級皺褶，衣料材質加入經距離過濾的細紋。頭髮保留原有髮束，稍微調整側分和髮尾。
- 皮膚使用原有 CC0 膚色貼圖，加入 Subsurface Profile、粗糙度變化與較弱的微法線；並非新的臉部掃描。原有第一人稱身體刻意不包含頭髮和頭部。
- 六房間的物件、姿態、材質綁定與任務事件同原版本逐項比較；原有道路、車輛互動代理、樹木碰撞與邊界保留。室外維持 R21 的單一太陽、天空擷取與曝光設定。

## 原生驗證與失敗記錄

來源測試 57 項、原生檢查 75 項通過；七組原生程序皆正常結束（exit 0）。四張地圖、人物材質與骨架、16 個新靜態網格，以及原有室內契約都經過新的 Unreal 程序讀回。原生測試的實際完成狀態、截圖、影片和輸入雜湊記於 `runs/campus-realism-r25-*`；最終清單記於同輪交付收據。

實際近景發現初版的部分門板與輪胎內外面朝向相反；已修正，Blender 產生時另檢查 26,984 個封閉幾何元件的有向體積。R22／R23 的探索性錄影保留，不作為最終版本驗收。R24 再修正車艙比例、後柱、門板倒角與儀表；最後結構檢查發現 profile 倒角前未更新面法線，造成少量重疊退化面。R25 修正法線並清理重疊頂點後，16 個輸出網格的非流形邊與退化面均為 0。

初版效能探針誤把剛建立的空 CSV 檔案當成測量完成；修正後等待 Unreal 的結尾標記，再使用檔尾完整欄名讀取。第一次儲存驗證要求第一人稱身體也有頭髮，與既有設計不符；修正為分別驗證 world／owner 的實際材質契約。失敗收據保留。駕駛回歸另發現固定時間輸入可能讓車停在路燈旁；保留出口碰撞拒絕，探針增加一個有界分支：遇到該提示時，用真正倒車與煞車移開，再嘗試一次下車。最終 R25 通過的駕駛測試未觸發此分支，不能把分支存在當作這次已量測到復原成功。

`run_native.py` 檢查同一版四張地圖、設定、程式、人物／動作輸入與新增命名空間內每個資產的 SHA-256。六組既有回歸加上一組近景／效能探針使用私有 X11、實際 Vulkan 和實際 GPU 0。上下車錄影保留完整連續流程；接觸數值仍是骨骼附著的皮膚標記近似，不能代替全面穿模檢查或動作捕捉。

## 重現

主機上的相對路徑均以 `~/vista-world-5090/workspace` 為根。實際工作樹為 `worktrees/campus-realism`，作者專案為 `projects/vista-campus/payload/PhotorealHome.uproject`。

1. 用 `tools/blender/vista_campus/realism_geometry.py` 建立新的 GLB／Blend 輸出目錄。
2. 先用 `verify_realism_geometry.py` 讀回新幾何，再用 `tools/blender/vista_reference_avatar/refine_realism.py` 讀取 `runs/rooms-avatar-build-i`；輸出到全新目錄。
3. 用 `tools/ue/vista_campus/finish_realism.py` 匯入全新的 `VISTA_REALISM_ROOT`，指定 `VISTA_REALISM_GEOMETRY`、`VISTA_REALISM_AVATAR` 與 `VISTA_CAMPUS_OUT`。同時更新測試用 `layout.py` 的 ROOT。不得覆寫現有 R25 或凍結版本。
4. 作者程序退出後，以 `verify_realism.py` 讀回；指定這次 `VISTA_REALISM_REPORT` 及原 R21 `VISTA_DEMO_REPORT`。執行原有六組原生測試，再加 `--suite realism`。
5. 用 `summarize_performance.py` 解析完成的原生 CSV；用 `freeze_campus_demo.py` 驗證六組收據和當前輸入，再複製成獨立專案。
6. 用 `build_realism_review.py` 檢查凍結清單、原生截圖／影片雜湊，產生圖片分開載入的私有預覽。`serve_review.py` 只提供清單內檔案，綁定明確的 Tailscale IPv4。

同一作者專案的 author／readback／native 程序必須依序執行。原有 Moonlight 六房間在另一份凍結專案中；本輪不重啟 Sunshine、不改變使用者的輸入與目前選定場景，也不使用 GPU 1。

## 效能解讀

每個場景在 1920 × 1080、30 fps 上限下記錄 450 幀，包含短距離步行及固定視角。分析剔除頭尾各 30 幀，以餘下 390 幀計算平均與 nearest-rank P95。FrameTime 包含限幀等待，不能推算解除上限後的最大 FPS；GPUTime 和 CPU 執行緒時間另列。此時 GPU 0 也在執行原有六房間。Unreal 的其他記錄欄位可能同名；解析器要求四個目標計時欄位各自唯一，不以無關記錄欄位的重名否定整份量測。

四景平均 FrameTime 分別約 33.33 ms。Gate／Daxue／Campus／Home 的 P95 分別為 33.79／33.75／33.79／34.59 ms。全段監測的顯存峰值 11,365 / 32,607 MiB，最高 49°C；資料記於 `runs/campus-realism-r25-performance.json`。

私有測試不包含 Moonlight 編碼、Mac／Windows 解碼與網路延遲。原生回歸的連續動作影片以 15 fps 擷取，只是錄影取樣率；使用者追加的字幕 Demo 另以 30 fps 實機錄製。場景初始化及截圖會造成額外負載，因此整段 GPU 監測與無截圖的 CSV 測量分開標註。

## 資產與下一輪重點

本輪沒有購買或下載新的外部資產。原有來源／授權追蹤沿用 `campus-pbr-sources.json`、`campus-demo-sources.json` 及 `../design/vista-reference-avatar/asset-receipt.json`；新增網格為本地程序化建模。參考皮膚散射的官方說明：[Unreal Subsurface Profile](https://dev.epicgames.com/documentation/en-us/unreal-engine/subsurface-profile-shading-model-in-unreal-engine?application_version=5.7)。參數是美術設定，尚未做人體實測擬合。

下一輪優先處理臉部及髮束自然度、車身曲面／玻璃接縫與內裝精度、建築背面和重複街景、接觸時的全身過渡。完整城市人車行為、跨地圖持續任務、動作捕捉和經驗證的車輛物理仍未實作；這一輪沒有模型評測或 research paper 的實驗結果。

## 已封存交付

`projects/campus-realism-r25/payload.json` 記錄 4,853 個檔案、5,710,877,474 bytes；SHA-256 為 `caee7f26f2a5e2d43155b1a53e064338815200264f89d97295796661e7dddbaf`。獨立專案已通過啟動前檢查。私有比較頁由 `runs/campus-realism-review-r25` 提供，原有 Six Rooms 選取狀態、遊戲和 Sunshine 程序保持不變。新增字幕 Demo 的錄製、涵蓋清單和交付收據另記於同輪 handoff。
