# Villa R1：可操作的兩層住宅 demo

在 Moonlight 選 **VISTA Villa R1**。新版使用凍結的獨立專案；原本 **VISTA Home R5** 仍保留。這次把生成圖的挑高、淺木／石材、黑色細框、二樓迴廊和主要房間配置做進 Unreal，並接好一段廚房操作。

![Unreal 實機：挑高客廳與二樓迴廊](/data/sysx/vista-world/runs/vista-villa-r1-20260910b/native-h/user/Saved/VillaProof/09_architecture.png)

[進度簡報 PPTX](/data/sysx/vista-world/runs/vista-villa-r1-20260910b/progress-deck-b/VISTA-Villa-progress.zh-TW.pptx) · [簡報 PDF](/data/sysx/vista-world/runs/vista-villa-r1-20260910b/progress-deck-b/VISTA-Villa-progress.zh-TW.pdf) · [14 張生成設計圖冊](/data/sysx/vista-world/runs/vista-villa-r1-20260910a/design-review-a/index.html)

## 現在可以操作

| 按鍵 | 功能 |
| --- | --- |
| WASD、滑鼠 | 在兩層空間走動、觀看 |
| Tab | 第一／第三人稱切換 |
| E | 對準近處杯壺拿取；持物時對支撐面放回 |
| P | 拿壺、靠近杯子後倒水 |
| F | 在水槽旁開關龍頭 |
| H | 廚房示範、獨立上樓測試、多視角巡覽 |
| R | 重設道具和水量，回到角色鏡頭 |

H 會先把角色放到廚房起點，樓梯測試另設起點；樓梯上升使用實際角色移動與碰撞。自由走動可自行探索房間。第一人稱空手能看到雙手，低頭可見衣服、腹部、腿和鞋。

## 這版的四項進度

- **人物與動作：**沿用 MakeHuman CC0 骨架與皮膚，增加眼睛／角膜、綁定髮絲和衣物幾何。三段 CMU 步行轉成 203 個姿勢樣本，修正 A／T pose，選片後接 IK。尚非完整 Epic Motion Matching 資料庫。
- **住宅：**16 × 12 m 外框、3.2 m 二樓、6.4 m 挑高、20 階樓梯；客餐廳、廚房、洗衣房、兩間臥室、書房、浴室。60 組幾何使用實際材質槽和照片 PBR；木櫃、石材中島、薄壁杯壺與水槽已有近距離檢查。
- **連續操作：**走近、抓壺、倒入杯中、放回、走到水槽、開關水、上樓。原生流程拿取／放回各 1 次，無取消。
- **液體：**水量守恆帳本、容器液面、重力細水柱與粗網格 FLIP。關源後已流出的部分繼續運動。本次杯中 218.9 ml，帳本殘差 0.0 ml；此數字不是 FLIP 粒子質量的量測。

## 驗證與界線

Editor、Game Development 和 Shipping 外掛編譯通過；73 項 Python 檢查、原 Home 的 12 個姿勢／拿放案例通過。新版以 GPU 1 原生執行並保存 15 張截圖，無材質編譯失敗；角色可上樓。實測 frame time 中位數 **45.7 ms**、p95 **85.1 ms**，包含自動截圖，不代表穩定 30 fps。

目前未達完整 GTA 或生成圖的照片品質。細部手指、臉部、衣物、家具與花園還需精修；FLIP 有粗顆粒／青色表面瑕疵，液體材質仍需改善。原 Home 六個空間的事件保留在 R5，**尚未全部移植到這棟新 Villa**。自然語言規劃、世界還原與 VISTA／EgoArgus 助理閉環尚待接入。

[設計圖與各空間的對照及驗收方向](quality-plan.zh-TW.md) · [來源、雜湊與失敗嘗試](implementation-manifest.json)

## 可重現流程與交付

1. Blender 的 `build_villa.py` 由共同尺寸建立空間；`build_character.py` 與 `retarget_mocap.py` 準備人物及步行資料。
2. UE 的 `import_villa.py`、`refine_native.py`、`update_geometry.py`、`finish_materials_and_source.py`、`finish_kitchen.py` 與 `finish_water.py` 逐步保存資產、材質、碰撞和出水源；每次使用獨立輸出與紀錄。
3. `run_native.py` 檢查 renderer、實際動作、地圖／外掛雜湊及水量；再看實機畫面。所有大型資產留在本機 run，不放 Git。
4. 測過的 2,763 個檔案已複製並逐檔比對至 `/data/sysx/vista-world/runs/vista-villa-r1-20260910b/demo-project-a`。Sunshine 新入口只會在你選它時啟動；R5 的地圖、外掛和遊戲／輸入程序維持原狀。

可重用的 [skill 原始碼](../../../skills/vista-blender-ue-workflow/SKILL.md) 已同步至 [本機 skill](/home/yhliu/.codex/skills/vista-blender-ue-workflow/SKILL.md)。其中記錄了材質保存、骨架校正、Niagara 綁定、GPU 檢查及失敗恢復的具體流程；未宣稱較小模型的端到端能力已做實驗驗證。

設計圖的生成工具沒有回報模型版本，因此沒有標成已驗證的 GPT Image 2.5。本輪未呼叫付費影像、影片或 OpenRouter 模型。研究筆記與老師推薦論文已在私人 VISTA-Web 的 PR #2 合併到 dev；錄影審查頁 PR #1 也已合併到 dev，未部署 production。
