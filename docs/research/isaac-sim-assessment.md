# Isaac Sim for VISTA / EgoArgus

Reviewed 2026-09-16. Upstream `develop` was pinned to
[`7c206f75bdadd9e05fc457f19863ca4c3f0cb693`](https://github.com/isaac-sim/IsaacSim/tree/7c206f75bdadd9e05fc457f19863ca4c3f0cb693).
This is a source/documentation assessment; Isaac Sim was not installed or run.

## 適合如何使用

可以採用，尤其適合研究助手決定介入之後的實際導航、抓取、放置和物理結果。
目前 UE 場景已經能呈現人的日常活動、語音和多個同時發生的需求；我建議先用
一個廚房／桌面案例建立 Isaac Sim 的物理執行對照，再決定要遷移多少場景。
這是依目前專案能力提出的整合建議，並未驗證 UE 與 Isaac 的即時同步。

NVIDIA 的 skills 是供 Codex 等 coding agent 使用的工作流程與輔助程式，
實際執行仍依赖 Isaac Sim、USD 資產、控制器和必要的模型。
[官方 skills 說明](https://docs.isaacsim.omniverse.nvidia.com/latest/development_tools/agent_skills.html)。

| 能力 | 可接到我們的工作 | 需要補上的部分 |
| --- | --- | --- |
| physics-simulation、USD articulation | 碰撞、剛體、關節、接觸結果 | 場景尺度、碰撞網格、機器人關節和物件配置 |
| manipulation-ik、motion-generation | 拿起物件、繞過障礙、放到桌上 | 適配機器人、抓取座標與成功／失敗驗證 |
| navigation-primitives、robot-navigation | 跟隨、走到房間、避開家具 | 房間地圖、足跡大小、導航控制與阻塞處理 |
| action-and-event-data-generation、incident events | 持續生成多人活動與事故事件 | VISTA 任務語意、正常對照與事件時序 |
| camera、sensor、data collection | 同步 RGB、深度、語意標記 | Ego 串流時間戳、評分端隔離與資料輸出規格 |
| behavior-tree-generation | 自然語言轉成行為樹 | 目前上游流程需要 NVIDIA API key；小模型本地版須另外實作 adapter |

上述能力對應上游 [skills 索引](https://github.com/isaac-sim/IsaacSim/blob/7c206f75bdadd9e05fc457f19863ca4c3f0cb693/skills/SKILLS.md)。
運動規劃 workflow 使用可替換的 controller，cuMotion / RMPflow 是其參考實作；
仍需配置障礙物和末端目標。
[motion-generation 原始碼](https://github.com/isaac-sim/IsaacSim/blob/7c206f75bdadd9e05fc457f19863ca4c3f0cb693/skills/motion-generation/SKILL.md)。

行為樹的自然語言產生流程目前明確要求 NVIDIA-hosted chat / embedding 的 API key，
沒有自動回退到本地小模型；範例 MoveTo 也仍有品質限制。因此不能把這個功能當作
「下載後小模型就能可靠地建立完整世界」的現成證據。
[behavior-tree-generation 原始碼](https://github.com/isaac-sim/IsaacSim/blob/7c206f75bdadd9e05fc457f19863ca4c3f0cb693/skills/behavior-tree-generation/SKILL.md)。

現在的人形角色是 UE skeletal mesh 和動畫／IK 的組合。要在 Isaac 中做可受力、
可抓取的人形助手，還需要機器人 articulation、關節限制、控制策略和接觸模型；
這些 skills 本身不會直接把現有角色變成具備可靠物理操作能力的機器人。

## 建議的研究切入點

1. **持續觀察、及時介入、完成物理協助。** 保留我們的 priority / interruption /
   resumption 問題，新增「規劃能否真的執行」。測試被電話中斷時，助手如何先處理
   即將逾時的需求，再回到先前任務；評分含實際接觸結果、deadline miss、打擾成本、
   計算延遲及恢復率。上游提供模擬工具，這個研究結論仍需實驗建立。
2. **小模型把 NL 轉成可驗證的場景與事件。** 先輸出受 schema 約束的物件、位置、
   affordance、事件與行為樹，再透過幾何／物理檢查回饋修正。比較直接生成程式、
   受限 DSL、加入驗證回饋三組。評分應包含可走通、無初始穿模、物件有支撐、任務
   可完成、語意符合程度及修正成本，不能只評圖片像不像。
3. **同一任務在不同模擬器的可靠度。** 共用事件／行動／observation contract，
   分別在 UE 與 Isaac 執行小案例，量化規劃和接觸結果對視覺、物理差異的敏感性。
   USD 幾何交換之外，材質、動畫、物理和事件綁定都需要明確轉換。

第一個有用的試驗範圍：一個房間、一位人類、一台可導航／操作的助手、一件可拿取
物件及兩個會重疊的需求。模型只讀當下可觀測 RGB／audio／proprioception；
隱藏事件排程、成功條件與精確世界狀態由評分端保管。先達到可重複完成與失敗案例，
再擴充到六房間與長時序評測。

## 本機條件

實際只讀檢查：Ubuntu 24.04.4、RTX 5090 32 GB、驅動 580.173.02。
GPU 0 在既有 UE／語音／對話服務運作時約使用 18.6 GB；GPU 1 有其他工作，未動用。
官方目前列出 Ubuntu 24.04、16 GB VRAM 起，並列出 Linux 測試驅動 595.58.03。
硬體與 OS 條件有希望，但現有驅動低於該測試版本，尚未建立這台主機跑當前 Isaac
版本的相容性或 FPS 證據。下一步需先選定版本、執行獨立 compatibility check。
[官方需求](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html)。

本次沒有安裝 Isaac、更改顯卡驅動或啟動 NVIDIA API。UE 場景的穿模與鏡頭修正
直接在現有引擎完成，與未來採用哪個模擬器分開驗證。
