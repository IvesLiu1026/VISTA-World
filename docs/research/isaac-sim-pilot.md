# Isaac Sim 實測：VISTA 人形與物理協助

2026-09-16，server5090。這次有實際安裝、執行與檢查原生畫面。
使用獨立 Python 3.11 / Isaac Sim 5.1.0.0，RTX 5090 GPU 0；原六房間、
Sunshine、語音與對話服務同時保留。GPU 1、主機驅動與既有 UE 資產未修改。

## 對「我們的人物」的結論

**有可行的整合路徑，而且已把現有 VISTA 人物真正載入 Isaac。**
取用既有人形 `six-room-companion-face-b/companion.blend` 與目前六房間使用的
CMU 衍生步態，轉成含 USD Skeleton / Animation / 蒙皮的獨立資產。
保留 53 個關節、63 個蒙皮 mesh 與皮膚等貼圖；原生 RTX 畫面能播放走路，
角色前進約 2.86 m，腳部相對骨盆的位移也有變化，並非只平移整個靜態模型。

第一版轉換雖通過結構檢查，實際畫面仍有手部拉伸與初始幀異常，已標記不接受。
改成依骨骼本地 bind transform 計算動畫 basis，並暖機 skinning / temporal buffers，
第二版原生畫面通過人工檢查。這仍只證明 **角色資產及既有動畫可以共用**：
不是新學到的走路策略、動態平衡、避障、物理抓取，亦非寫實度已達標。
UE 的足部 IK、互動邏輯與語音沒有隨 USD 一起移植；眼鏡與材質外觀仍需校準。

NVIDIA 另有針對人類角色的 GoTo、Idle、LookAround、Sit 和自訂動畫命令；
自訂角色／動畫需要相應的骨架和動作重定向設定。文件也明確說明動態避障並非保證，
Sit 是固定動畫並需要座椅 offset。**本次沒有執行 IRA / Omni.Anim.People 控制器**，
不能把它們的文件能力當成這個 53 骨骼人物已完成的功能。
[Actor Control](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/action_and_event_data_generation/ext_replicator-agent/actor_control.html)，
[Customization](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/action_and_event_data_generation/ext_replicator-agent/customization.html)。

若目標是自然外觀的人類 NPC / 助手，建議先保留目前 UE 的呈現與輸入，將共用的
行為介面接到人物的走路、轉身、看向目標、伸手與物件操作。Isaac 可作物理／感測
對照與資料生成後端。若要人形本身依力矩站穩、拿重物與應對推擠，還需要身體
articulation、質量與關節模型、全身控制／訓練；一般 skeletal mesh 不等於機器人。

## 已跑的物理與感測案例

場景是新建的小房間／工作桌，不是完整六房間搬遷。PhysX 使用 CPU dynamics
（USD 中 `enableGPUDynamics = 0`），RTX 渲染使用 GPU 0。沒有付費 API／LLM。

| 案例 | 實測結果 | 能支持的結論 |
| --- | --- | --- |
| 桌面支撐、無支撐落下、牆阻擋／暢通對照 | 7 個物理／影像／GPU 設定檢查通過 | 可以建立幾何與物理驗證，不只能看圖片 |
| Franka 正常抓放，兩個起始位置 | 2/2 最終成功；平面誤差 2.52、2.61 mm | 接觸驅動的搬運能執行；未使用附著或瞬移 |
| 搬運中暫停兩秒再繼續 | 2/2 最終放置成功；但暫停高度檢查 **0/2 通過** | 暫停控制器 phase 不保證身體已穩定，需物理停靠條件 |
| 強制夾爪維持張開 | 2/2 物理失敗；控制器仍回報 done | 不能把流程跑完當作任務成功 |
| 六次操作的雙視角感測 | 3,144 張 RGB；深度、嚴格遞增時間與成對時間戳檢查通過 | 可做帶時間戳的研究串流；尚非長時序 benchmark |

抓放的成功條件在執行前定義：曾升到 z > 0.87 m，最後距目標平面 < 0.06 m、
高度誤差 < 0.02 m、速度 < 0.05 m/s。故障案例停留在原處，距目標約 0.849 m。
暫停另要求搬運高度全程 > 0.90 m；實際初始高度約 0.827–0.828 m，因此保留失敗，
沒有放寬門檻。這不是物件掉到地板，而是動畫／控制 phase 與實際到達姿勢不同步。

控制器是 NVIDIA PickPlaceController + RMPflow 的**特權狀態腳本基線**，直接知道
物件位置，不是 VLM 感知或 learned planning。輸出的 observation 與 evaluator trace
分開存放，但本次沒有建立或聲稱安全隔離的模型評測服務。
[官方抓放範例](https://github.com/isaac-sim/IsaacSim/blob/47d886f2858d1ceed556b21c88927aa67bc81c12/source/standalone_examples/api/isaacsim.robot.manipulators/franka_pick_up.py)。

## 最值得接回 VISTA / EgoArgus 的研究問題

1. **人形助手在長時序串流中何時、如何介入。** 人在講電話，同時水快滿、物件
   要拿取；助手不只排優先級，還要選擇可中斷的姿勢、移動／操作並恢復舊任務。
   比較立即搶占、不可搶占、依物理狀態選中斷點，量測 deadline miss、介入成本、
   真實操作成功、恢復率及延遲。此次暫停高度失敗提供工程動機，不是論文結論。
2. **以觀察驗證協助結果。** 指令完成但手中沒有物件時，助手能否察覺並修正？
   同時評估感知錯誤與執行失敗，避免只憑事件腳本判成功。
3. **小模型 NL → 可驗證場景／行為。** 以受限 schema 產生位置、支撐、可通行
   空間與動作，再用幾何和物理回饋修正。比較純生成、schema 約束、加入物理回饋。
   本次只驗證底層檢查能力，未跑 NL 模型或生成品質實驗。

上述題目是結合本地測試提出的研究設計，尚未做相關工作的完整 novelty 審查。
下一個人物里程碑宜限縮為：**走到人旁邊 → 注視／提醒 → 操作一件物件 → 被打斷 → 恢復**。
先建立人形動作的可達性、接觸與成功驗證，再擴充多人、六房間和長時間重疊事件。

## 相容性、效能及限制

- 主機 Ubuntu 24.04.4、驅動 580.173.02。選 5.1 是因該版官方 Linux 測試驅動
  為 580.65.06，且可在不改主機驅動下實测。目前 5.1 文件已標示不再支援；
  這個 pilot 不是最新 6.1／其全部 skills 的驗證。
  [5.1 需求](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html)。
- 抓放期間 GPU 0 全部程序合計峰值約 22,550 MiB；開始時 18,582 MiB，新增約
  3,968 MiB。是每兩秒取樣的觀察值，並非獨立精準顯存 profiler。
- 六次抓放共 104.70 s 模擬，用了 151.24 s 迴圈時間，含兩個 640×360 相機、
  15 fps PNG 寫檔及深度輸出。這個約 0.69 倍實時的數字不能外推到完整校園、
  六房間、多人或高解析串流；也沒有做人形 RL 訓練或 GPU dynamics 壓測。
- 指定單一 NVIDIA Vulkan ICD 排除主機重複 ICD；僅子程序環境改動。
  CUDA mask 排除 GPU 1；實際 RTX active device UUID 對應 GPU 0。
- 碰到 camera acquisition clock 在 world reset 後停住，已補 sensor post-reset。
  原先取回影像與相機 metadata 不同 callback 的問題也改成同一 snapshot。
- Kit 正常清理曾卡住；保留該次退出紀錄，改用有結果／error 檔檢查的 fast shutdown。
  退出碼 0 本身不能當成成功。原生人形 A 版的結構檢查也不能取代人工看圖。
- 原始角色／外部資產的既有授權範圍未擴大；這些是 review 資產和工程證據，
  不宣稱可以直接發布為 paper dataset。

## 可重現資料

工作區根目錄：`/home/yhliu/vista-world-5090/workspace`。

- 程式：`worktrees/isaac-pilot/tools/isaac/`；安裝環境 `services/isaac-pilot/venv`。
- 套件版本、安裝與 28 個既有 contract/compiler 測試：`runs/isaac-pilot-setup-a/`。
- 接受的物理資料：`runs/isaac-pilot-physics-c/data/`。
- 六次操作（含暫停高度失敗）：`runs/isaac-pilot-manipulation-c/data/`。
- 抓放比較影片：`runs/isaac-pilot-review-b/isaac-pilot-demo.mp4`，英文標示、無語音。
- 接受的人形轉換：`runs/isaac-pilot-avatar-export-b/`；原生證據
  `runs/isaac-pilot-avatar-native-b/`；影片
  `runs/isaac-pilot-avatar-review-a/vista-avatar-in-isaac.mp4`。
- 早期試驗 A/B 均保留，尤其 `avatar-native-a/manual-review.json` 明確拒收。

每次 native run 有啟動參數、來源 SHA-256、GPU 記錄與退出紀錄。輸出資料不進 Git。
以上測試只在独立程序執行，沒有替換現在 Moonlight 的六房間版本。
