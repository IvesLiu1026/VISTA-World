# 第一／第三人稱與抓取動畫：技術調查

調查日期：2026-09-06。基準：`26be8b7c`，UE 5.7.3，整屋展示 `project-g`。
本次交付是來源核查、現有程式與資產差距分析，以及可執行的下一版範圍；尚未把新的角色、視角切換或抓取功能接入 Sunshine。

## 結論

不需要先生成圖片或影片才能開始。先建立有完整手指、軀幹與雙腿的角色，把第一／第三人稱、動畫、接觸點與物理物件接成同一套系統。圖片可決定外觀，影片可輔助動作節奏；可重定向的骨架動畫、物件局部握點與真實接觸才是實作輸入。

建議沿用已完成的六房住宅資產，在角色／互動分支實作。第一個完整操作選擇餐桌上的杯子：走近、伸手、握住、拿起、持物行走、放回與鬆手掉落。之後增加冰箱把手與雙手端鍋。這個順序是本專案的工程判斷，並非論文保證的交付效果。

## 目前專案已具備什麼

| 檢查對象 | 實際狀態 | 對下一版的影響 |
| --- | --- | --- |
| `VistaPhotorealReview/Private/PhotorealReview.cpp` | `ACharacter` 膠囊、移動與一個相機；沒有設定可見的 Skeletal Mesh 或 AnimInstance | 要加入真正的人體、動畫與另一個相機，不能只把相機往後移 |
| `VistaPlayableHome/Private/VistaPlayableHomeCharacter.cpp:719` | 舊版已有視角切換；進入第一人稱時呼叫 `SetNearCameraVisualHidden(true)` | 可參考相機狀態保存，但不能照搬隱藏整個身體的呈現方式 |
| `materialize_makehuman_cc0_animation_runtime.py` | 已定義 53 骨架，含左右手各五指三節及雙腳；有 idle、walk、pickup、place、drop 的來源契約 | 優先盤點現有角色與相容動畫；契約存在不代表全部動畫已在整屋版可用或品質已被接受 |
| `VistaActionExecutorComponent.cpp`、`VistaAnimationComponent.cpp` | 已有手部 CarryAnchor、接觸／完成訊號、動作取消與物件狀態恢復程式 | 可重用這些概念與經驗；整屋展示插件尚未接上這些執行元件 |
| R15 動作說明 | 旋鈕、按鈕、抽屜、坐下與倒水等已有來源配方；文件明確保留 runtime／人體動作品質驗證工作 | 不把來源或匯入成功當作現成自然動畫 |
| `model-b/model-manifest.json` | `kitchen_mug`、`kitchen_pot` 為 `complex_as_simple`；杯子 pivot 為 Blender `(4, -2, 0)`，幾何在其偏移位置 | 動態杯子需獨立的局部原點、凸碰撞與握點，並保持現有世界位置不變 |

本機 UE 5.7.3 的 `CameraComponent.h` 與 `PrimitiveComponent.h` 已確認具有 First Person FOV／Scale 和 `EFirstPersonPrimitiveType`。這是本機 API 的核查，不是新角色渲染的實機驗證。

## 參考素材怎麼用

| 素材 | 適合用途 | 本輪選擇 |
| --- | --- | --- |
| 生成圖片 | 角色衣服、膚色、袖口、鞋款、近距離材質方向 | 外觀有明確需求再做；不拿來判定骨骼、重量或接觸 |
| 生成影片 | 動作分鏡、速度與氣氛探索 | 非前置依賴；任何姿勢或接觸都要回到 3D 場景核對 |
| 真人參考影片 | 伸手路徑、肩肘協調、握杯前的手指張開、放下後鬆手的時機 | 比較動作時優先選擇完整手足可見、物件尺度清楚的素材 |
| 可用的 MoCap／骨架動畫 | 走路、轉身、起停等基礎動作 | 先核對現有來源，再做重定向與腳底接地；不要把缺少手指資料的片段當成精細抓取 |
| 同一 UE 場景的多視角錄影 | 第一／第三人稱一致性、手指穿透、腳滑、物件是否被提早帶走 | 作為最後驗收證據 |

Epic 的 [Game Animation Sample](https://dev.epicgames.com/documentation/en-us/unreal-engine/game-animation-sample-project-in-unreal-engine?application_version=5.7) 提供 MoCap、Motion Matching 與角色移動範例，可用來評估走路與轉向。它的主要範圍是移動與跨越障礙，不能推定已提供本案的杯子抓取系統。本次只讀文件，未下載樣本資產。

## 核查的 skills

已保存七份固定 commit 的候選技能文件與 SHA-256。這些是社群提供的工作流程／API 參考；沒有查到能證明它們對 GPT-6-Astra 有專屬能力或品質保證的評測。未安裝全域 skill、MCP 或 UE 插件，也未執行下載文件中的命令。

| 候選 | 對本案的用途 | 採用判斷 |
| --- | --- | --- |
| [quodsoler / ue-animation-system](https://github.com/quodsoler/unreal-engine-skills/blob/231c8571be6f3335685edc566a28ec6f9621361d/skills/ue-animation-system/SKILL.md) | AnimInstance、Montage、動作通知、上下半身混合 | 適合當 C++ 動畫接線參考；下述委派順序矛盾需修正 |
| [quodsoler / ue-physics-collision](https://github.com/quodsoler/unreal-engine-skills/blob/231c8571be6f3335685edc566a28ec6f9621361d/skills/ue-physics-collision/SKILL.md) | 查詢、碰撞模式、質量與約束 | 適合補足動態物件；具體設定以本機版本與實物尺寸為準 |
| [arjun988 / rigging](https://github.com/arjun988/blender-skills/blob/8f778d2405a214b508d4c7d80742be8e43acdd52/.claude/skills/rigging/SKILL.md) | 骨架、權重、IK／FK、極端姿勢變形檢查 | 採用檢查方法；保留已有 `hand_r` 等骨名，不套用它的另一套命名 |
| [arjun988 / animation](https://github.com/arjun988/blender-skills/blob/8f778d2405a214b508d4c7d80742be8e43acdd52/.claude/skills/animation/SKILL.md) | 動作 blocking、曲線、循環接縫與輸出 | 適合修飾配方動畫；參考影片不必是生成影片，MCP 也不是本機 Blender Python 的必要依賴 |
| [arjun988 / collision-proxy](https://github.com/arjun988/blender-skills/blob/8f778d2405a214b508d4c7d80742be8e43acdd52/.claude/skills/collision-proxy/SKILL.md) | 簡單形狀、凸碰撞組合、正確局部原點 | 杯身與杯把分開規劃碰撞，不能用一個大凸包把杯把孔全部填滿 |
| [kevinpbuckley / control-rig-and-ik](https://github.com/kevinpbuckley/unreal-engine-skills/blob/1661d7d24325612b79b77b8808ca27797ba43ef4/skills/core/control-rig-and-ik/SKILL.md) | 手腳 IK、骨架重定向、Control Rig 的執行順序 | 範圍很貼合；原文以 UE 5.8 為準，先核對 5.7.3 API 與座標空間 |
| [game-development-constitution / unreal-control-rig-ik](https://github.com/adventuresincausality/game-development-constitution/blob/aee2c2831176c064cb8cb800fc7bbbff5e5fbdc7/skills/unreal-control-rig-ik/SKILL.md) | 定位動畫在哪個階段出錯、接觸與腳滑診斷 | 作為診斷參考；同樣針對 UE 5.8，未採納其整套專案規則 |

另外查到 [VibeUE 的 animation-blueprint skill](https://github.com/kevinpbuckley/VibeUE/blob/master/Content/Skills/animation-blueprint/SKILL.md)，其圖表編輯範例需要 VibeUE 的 `AnimGraphService` 等服務。本機沒有因此取得這些 API；目前不把它當成可直接執行的方案。

### 為什麼不能直接照抄

`ue-animation-system` 的 Montage 範例先播放再呼叫 `Montage_SetEndDelegate`，但尾端常見錯誤表卻寫成先綁定再播放。查本機 `AnimInstance.cpp:2826` 可知這個 setter 綁定的是已存在的 active montage instance；對新播放實例應採用前者。這個矛盾已記錄在本地調查，沒有修改上游文件。

本機 `UIKRigComponent::SetIKRigGoalPositionAndRotation` 明確使用 Skeletal Mesh 的 component space。由世界座標 trace 得到的手／腳目標必須轉換後再傳入，不能因為範例省略轉換就直接填值。FBIK 解的是姿勢約束；它本身不等於對手指摩擦力與抓取穩定性的物理模擬。

## 相關論文與適用邊界

| 論文 | 核心內容 | 本案可以借用什麼 |
| --- | --- | --- |
| [GRAB，ECCV 2020](https://grab.is.tue.mpg.de/) | 10 位受試者與 51 種日常物件的全身、手部、物件姿態與接觸資料；GrabNet 預測手部抓姿 | 參考杯把握法、手指接觸與全身配合；資料下載另有註冊與使用條件，本次未下載 |
| [Omnigrasp，NeurIPS 2024](https://www.zhengyiluo.com/Omnigrasp-Site/) | 模擬人形抓起不同形狀物件並沿目標軌跡搬運 | 適合將來研究跨物件抓取；[官方程式](https://github.com/ZhengyiLuo/Omnigrasp) 使用 Isaac Gym 與 SMPL 系列模型，需另做模擬器、骨架與控制整合 |
| [InterMimic，CVPR 2025 Highlight](https://sirui-xu.github.io/InterMimic/) | 教師／學生策略學習並修正不完美的人物與物件動作參考；結合接觸與物理模仿 | 借用「先驗證少數高品質接觸，再擴大動作」的工程思路；[論文方法與附錄](https://arxiv.org/html/2502.20390v1) 的控制與訓練使用 Isaac Gym，不能直接替換 UE AnimBP |
| [GVHMR，SIGGRAPH Asia 2024](https://zju3dv.github.io/gvhmr/) | 從單眼影片估計人體姿勢與世界軌跡 | 若現成動畫缺少某個全身動作，可研究由影片取出身體動作再重定向；其公開輸出是 SMPL 人體參數，精細手指、物件姿態與接觸仍需另外處理 |

選擇這四篇是依本案問題的相關性，不是宣稱它們是 2026 年最新排名或已在本機重現。沒有啟動推論、訓練、下載權重或付費 API。

## 下一版實作設計

### 1. 同一角色的兩種視角

同一份全身骨架與動作狀態驅動兩種視角。第三人稱使用帶碰撞回縮的相機臂；第一人稱使用平穩的眼高相機，低頭可見軀幹、腿與腳，伸手／持物時可見雙手。手臂自然下垂時不強迫它們一直出現在畫面中央。

第一人稱可配置不渲染頭部內側的本地身體表示，同步完整世界身體的姿勢；第三人稱顯示完整角色。陰影與反射需要保留世界身體。頭部動畫的所有旋轉不直接傳給鏡頭，避免強烈晃動。

Epic 的 [First Person Rendering](https://dev.epicgames.com/documentation/en-us/unreal-engine/first-person-rendering?application_version=5.7) 提供本地身體與世界表示的設定。腳底與抓取接觸優先保留世界座標的一致性；若使用第一人稱 FOV／縮放，要另驗證手與杯子的投影是否仍對齊，且不改變碰撞與物件的實際位置。反射、陰影與材質能力依實際渲染設定驗證，不只檢查開關。

新視角鍵建議 `Tab`，保留目前 `V` 的房間另一角度用途。切換過程應保持位置、持物狀態與動畫進度；不得重新生成杯子或重播抓取。

### 2. 動作底層與姿勢修正

先核對角色比例、手指權重、掌心朝向、綁定姿勢與 feet／hand bones。沿用符合來源要求的現有角色作為功能基線，近距離手部的模型與皮膚／指甲材質再獨立改善。

動畫順序以基礎移動、上半身操作、平滑混合，最後手腳接觸修正為起點。手靠近目標使用手臂 IK；俯身或雙手端鍋才擴充到多目標的 [Full Body IK](https://dev.epicgames.com/documentation/en-us/unreal-engine/ik-rig-solvers-in-unreal-engine?application_version=5.7)。手指採用按物件設定的抓姿與接觸修正，不能只把手腕定位成功就算握住。

需要跨一步或轉身對位時，才考慮 [Motion Warping](https://dev.epicgames.com/documentation/en-us/unreal-engine/motion-warping-in-unreal-engine)，它調整的是 root motion。既有零 root-motion 的配方不會因為加上這個插件就自動走到握點；近距離杯子先用受碰撞約束的站位與手臂 IK。

### 3. 抓取必須有接觸與物件狀態

操作流程：

```text
目標可見且可達 → 伸手與手指預張開 → 接觸驗證 → 握住
                                              ↓
                         放開掉落 ← 持物行走 → 放到支撐面 → 鬆手
```

每個物件建立局部握點、接近方向、允許手別、手指姿勢、質量、碰撞與放置支撐面。視線命中只負責選物件，仍需檢查手與身體的可達距離及中間障礙。

動作通知僅表示動畫進入接觸窗口；確認實際距離、姿態與目標仍有效後，才建立握持約束。取消、目標被移走或不可達時，要有恢復流程。持物時應保留與房屋的碰撞，不能靠對相機做每幀位置指派穿越牆面。

首版評估 [Physics Handle／Constraint](https://dev.epicgames.com/documentation/en-us/unreal-engine/physics-components-in-unreal-engine?application_version=5.7) 保持杯子為物理物件。手部 IK 跟隨實際物件／握點；碰撞造成過大距離或伸手路徑被阻擋時，限制目標或解除握持。放開時恢復自由剛體運動。這是動畫配合物理約束的抓取，尚不等同於逐指施力學到的靈巧操作。

單手杯子完成後，再加入沿冰箱門鉸鏈移動的把手目標，最後加入雙手端鍋的雙握點、肩肘協調與重量感。冰箱現有 `F` 全域開關動作不能作為手已碰到把手的證據。

## 可檢視的第一版與驗收

建議在 `26be8b7c` 的獨立角色／互動分支建立新的 UE 專案副本，重用整屋資產與房間布局。保留已接受的 `project-g` 供比較；本次調查尚未建立或啟動該副本。

第一版交付範圍：全身角色、第一／第三人稱切換、自然起停與低頭見腳、單手杯子拿起／搬運／放置／掉落。雙手端鍋、冰箱把手與後續日常動作分開檢視，避免同時改掉所有操作。

以下數字是擬定的工程驗收目標，不是已完成的測試或人體標準：

- 兩種視角各自走完五處門洞；第三人稱相機貼牆時回縮，不能看到牆外。
- 第一人稱低頭、走路、俯身時可見合理的身體部位；手臂不反折，腳底支撐期間的滑移目標小於 2 cm。
- 杯子接觸窗口內，掌心／握點位置誤差目標小於 1 cm，方向誤差小於 10°；再逐幀檢查手指是否穿透，不能用掌心數字代替手指檢查。
- 杯子以多個位置、把手朝向與 70／85／100 cm 支撐高度測試；不可達或被牆擋住要拒絕，不拉長手臂。
- 伸手、持物、放置中途切換視角；不得改變物件持有者或重啟動作。
- 走向門框時持物碰撞有效；掉落後可再次拿取；連續拿放 20 次沒有重複物件、殘留約束或永遠無法互動的狀態。
- 保存第一／第三人稱的實機動作錄影與接觸／狀態記錄，另量測幀時間。原有 30 fps 上限不代表新角色一定能穩定達到該速度。

來源雜湊與本機程式位置記錄在 [調查清單](embodied-interaction-research-manifest.json)。
