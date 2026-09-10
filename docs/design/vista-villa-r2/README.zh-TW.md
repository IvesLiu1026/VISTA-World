# Villa R2：採光、步態與自然垂手

Moonlight 入口：**VISTA Villa R2**。畫面左上角顯示 **VILLA R2**。原 Villa R1 與 Home R5 的專案保留。若清單還未更新，重新整理 Moonlight 的主機應用程式清單，再選 R2；本次沒有自動切換正在保留的 R1 畫面。

![Unreal 實機：樓梯天窗與跨樓層採光窗](/data/sysx/vista-world/runs/vista-villa-r1-20260910c/native-d/user/Saved/VillaProof/14_architecture.png)

## 這次改了什麼

| 使用者看到的問題 | R2 的處理 |
| --- | --- |
| 室外太亮、窗外泛白 | 直射光從 30,000 調至 9,000 lux，固定曝光 EV100 10，重新平衡室內光源。這是引擎設定，非實地照度測量。 |
| 樓梯與二樓採光不足 | 樓梯上方 2.2 × 5.2 m 天窗、東側跨兩層長窗、南側走廊高窗；實際重做屋頂及牆面開口、窗框與窗台，保留 20 階樓梯和樓板動線。窗邊面光源近似間接反射。 |
| 手在身旁還彎得很怪 | 重新校準垂手姿勢；空手時保留動畫的肘部方向，不再套固定肘部極向量的手腕 IK；手指略微彎曲。 |
| 走路動作不協調 | 改用按時間順序的完整 CMU 步行週期，按身形與移動距離校準，取消重複擺手／步態層，加入支撐腳鎖定，縮小擺臂幅度。 |
| Ego view 空手一直舉起 | 關閉空手 ready pose。站立時可左右自由看至約 85°，轉得更多時身體跟上；轉頭／低頭使用同一骨架。側下看另有最多 6 cm 的相機前傾，避免肩膀擋住垂下的前臂，仍檢查相機碰撞。 |

![Unreal 實機：側看時自然垂下的前臂](/data/sysx/vista-world/runs/vista-villa-r1-20260910c/movement-native-f/user/Saved/VillaMotionProof/02_ego_left_002.png)

## 操作

WASD 移動、滑鼠觀看、Tab 切換第一／第三人稱。E 拿取／放回，P 倒水，F 開關龍頭，H 自動示範與巡覽，R 重設。空手平視不會把雙手舉到畫面中央；向側下方看可見垂手，低頭可見軀幹、腿和鞋。H 會另設廚房與樓梯起點，之後使用實際角色移動；不是全屋自主導航。

## 骨架判斷與驗證

目前 53 根骨骼已包含肩、肘、腕、五指、脊椎、頸、髖、膝、踝與腳趾。這次主要問題是姿勢校準、重複動畫層及相機設定。若要進一步改善皮膚扭轉、肩肘變形與表情，可再加入 twist bones、修正形狀及臉部控制；單純增加關節數不會消除步態問題。

R2 使用固定 1/30 秒模擬取樣；12 組原生檢查包含站立、左右看、低頭、走動、停步、後退、側移與切換視角。空手肘部彎曲約 12.36°，手腕在肩下約 44.5 cm；受測骨段長度保持不變，平地完整支撐期間的腳踝位移另以逐幀與整段支撐累積量檢查，最大約 1.43 cm（限值 3 cm），包含起步前幾步。相機與肢體數值之外，另看實際 PNG 排除肩膀遮住手的情形。

廚房示範拿取／放回各成功一次，無取消；杯中約 219.4 ml，帳本殘差 0，角色到達二樓。這些水量是既有守恆帳本的數值，不是 FLIP 粒子質量。原 Home 的 12 個姿勢與拿放回歸案例也通過。Editor、Linux Game Development／Shipping 建置，以及 28 個合約／編譯器測試與 7 個聚焦測試通過。

步行仍是有限動捕片段加上方向修正、接地 IK；尚不是完整的轉身、上下樓、跑步、停步動捕資料庫。衣物邊緣及腳踝仍有資產瑕疵，人物、花園與流體也未達 GTA 成品品質。這輪 GPU 1 同時有其他運算負載，原生自動截圖的幀時間不作即時幀率驗收。

## 參考與重現

[Rockstar 的 GTA V 第一人稱介紹](https://blog.playstation.com/2014/11/04/grand-theft-auto-v-on-ps4-introducing-all-new-first-person-mode/) 說明了配套動畫與控制的必要性；未以此推斷 GTA 6 的內部骨架。[Epic IK Retargeting](https://dev.epicgames.com/documentation/en-us/unreal-engine/ik-rig-animation-retargeting-in-unreal-engine?application_version=5.7) 與 [Pose Warping](https://dev.epicgames.com/documentation/unreal-engine/pose-warping-in-unreal-engine?application_version=5.7) 作為姿勢／步幅對齊的技術參考。實作為本專案 C++ 流程，並未宣稱安裝了 Epic Pose Search。動捕源自 [CMU 官方資料庫](https://mocap.cs.cmu.edu/subjects.php) 的步行資料。

Blender：`build_walk_cycle.py` 與 `build_daylight.py`；UE：`apply_daylight.py` 與 `add_daylight_views.py`；原生驗證：`run_native.py --mode motion/villa/poses`、`verify_motion.py`。詳細參數與本機路徑記在 [既有工作流程 skill](../../../skills/vista-blender-ue-workflow/SKILL.md) 的 runbook；資產、來源雜湊與測試收據見 [交付清單](implementation-manifest.json)。大型資產保留在 run 目錄，沒有新增付費模型呼叫。
