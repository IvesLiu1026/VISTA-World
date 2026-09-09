# Home R5：空手與低頭時的第一人稱身體

空手平視時，左右手留在畫面下緣。低頭時，雙手逐漸放低，讓玩家看到
衣服覆蓋的軀幹、腹部區域、腿和鞋子。既有 R3 Sunshine demo 保持運作，
R5 以完成的 R4 材質專案為基底，在獨立副本交付。

## 行為

| 情境 | R5 行為 |
| --- | --- |
| 空手平視 | 完整骨架的雙臂做低位準備姿勢，手指稍微放鬆彎曲；手掌出現在畫面下緣 |
| 步行 | 保留小幅擺動與原有腳步解算 |
| 低頭 | 放低待機手勢，減少被動軀幹前傾；深度低頭時視點最多向前微移 8 cm，保留相機碰撞限制 |
| 拿起物品 | 每隻手依自己的 reach 權重交給原有 IK、手指與精細接觸解算 |
| 放手 | 原有回手流程接回空手姿勢 |
| Tab 切換視角 | 保留 owner body／world body 分工，待機手勢以約 0.4 秒的平滑過渡切換 |
| 靠近牆面 | 空手姿勢放低，避免把手伸入前方障礙物 |

相機與 owner body 保持相同 FOV 和比例。第一人稱的身體仍跟隨完整人物的
同一套骨架。模型、權重、骨架、衣服和 R4 材質沒有替換。
低頭的視點微移在手部接觸、蹲姿、坐姿或跌倒時退回原有相機行為。

## 驗證

- Linux UnrealEditor、UnrealGame Development／Shipping 的 BuildPlugin 通過。
- 35 項既有契約、編譯計畫及材質對應測試通過。
- 在獨立專案以 NullRHI 執行 12 個實際遊戲情境，檢查空手、低頭、第三人稱、切回第一人稱、步行、貼牆、離牆、拿杯子及放手。
- 空手的左右掌部及末端手指關節投影通過；骨架同步、可見性、手／世界透視一致性、手臂長度和動作終態通過。
- 原有杯子實際完成拾取與放手，拾取提交時的精細指尖接觸檢查通過。
- 原本 demo 的 2,318 個來源與備份檔案保持一致；Sunshine 設定、服務 PID 及啟動時間一致。
- R5 的 2,357 個 Content 檔案與 R4 逐位元相同，打包的 20 個插件來源檔與這份程式碼一致。

只檢查骨架中心是否落在視錐中，無法判斷衣服是否遮住腿。因此最終視覺驗證
另以實際蒙皮後的表面投射 80×45 條射線，計入衣服及環境遮擋，要求雙手、
軀幹、左右腿與左右腳有可見表面，並人工檢查三張預覽。
射線使用渲染可見的集合與物件，排除 glTF 匯入器的隱藏骨架控制形狀。

## 交付

執行紀錄：`/data/sysx/vista-world/runs/vista-home-first-person-r5-20260908a`。

- 選定插件：`build-c`
- 選定專案：`project-c/PhotorealHome.uproject`
- 原生姿勢：`native-c/user/Saved/FirstPersonProof/poses.json`
- 原生檢查：`pose-check-c.json`
- 保留版檢查：`preservation-final.json`
- 圖片與 Blender 專案：`previews-d`
- 人工視覺檢查：`visual-review.json`
- [完整預覽](/data/sysx/vista-world/runs/vista-home-first-person-r5-20260908a/R5第一人稱預覽.md)
- [交付清單與檔案雜湊](../../../world_packs/vista_home_first_person_r5/delivery.json)

圖片使用 UE 實際算出的骨架姿勢與相機資料，在 Blender CPU 中渲染。
房間使用 R4 材質製作場景，人物使用既有的已驗證 GLB 與 R4 材質。
這些圖是**原生姿勢的 Blender 預覽，不是 UE／Sunshine 畫面**。

目前沒有切換 Sunshine，也沒有開啟第二個 GPU 遊戲視窗。
新版的 GPU 畫面、自陰影、完整場景回歸及 FPS 仍待實機驗收。
既有 demo、正式 VISTA 標籤與模型輸入資料都沒有更動。

## 重建

先以 `RunUAT.sh BuildPlugin` 打包 `unreal_plugins/VistaPhotorealReview`。
使用 `tools/runtime/vista_home_first_person_r5/prepare_project.py` 的
`--source`、`--plugin`、`--out`、`--ddc` 建立新副本。

`run_proof.py --project PROJECT --out FRESH_DIRECTORY` 啟動有時間上限的
NullRHI 原生遊戲檢查。此流程以網路隔離、兩個 CPU 核心、獨立 UserDir／bridge
執行，不使用顯示器輸入或服務管理。驗證用的啟動旗標在一般遊戲中不生效。

`verify_pose.py --proof POSES --bridge BRIDGE --out FRESH_JSON` 驗證原生姿勢和動作紀錄。
`tools/blender/vista_home_first_person_r5/render_pose.py` 接收
`--home-source`、`--character-materials`、`--body-dir`、`--proof`、`--out`。
使用 Blender 4.5.8、`--background --threads 4 --python-exit-code 1`，Cycles CPU。

`verify_preservation.py` 檢查保留版與繼承內容。所有輸出都要求新目錄或新紀錄，
先前嘗試保留在執行紀錄中。
