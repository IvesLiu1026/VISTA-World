# Villa R1：設計與即時品質樣板

目標是人物、物件與操作都可信的住宅環境。本次版本從 Home R5 分出獨立工作副本，原本 Sunshine 的 **VISTA Home R5** 保留。

先看 [14 張別墅設計圖冊](/data/sysx/vista-world/runs/vista-villa-r1-20260910a/design-review-a/設計圖冊.md) 或 [HTML 圖冊](/data/sysx/vista-world/runs/vista-villa-r1-20260910a/design-review-a/index.html)。包含客餐廳、廚房、入口樓梯、二樓迴廊、臥室、浴室、書房、洗衣間、外觀、兩層平面概念與材質近景。生成工具沒有回報模型版本，因此沒有把它標成已驗證的 GPT Image 2.5。

![近距離物件樣板；Blender Cycles 渲染](/data/sysx/vista-world/runs/vista-villa-r1-20260910a/hero-props-d/hero-props.png)

這組托盤、陶瓷杯、玻璃壺是實際建模／PBR 的 Blender 預覽。托盤沿用已取得的 Poly Haven CC0 照片木紋、roughness 和 normal；杯壺有內壁、圓唇與封閉底部。模型已匯入獨立 UE 材質檢查場景，保存後重新載入，尺寸、材質和靜態碰撞設定吻合。這三件新樣板尚未接成可抓握的 Home 道具。

## 本次完成與界線

| 項目 | 本次結果 | 後續驗收 |
| --- | --- | --- |
| 設計 | 14 張選定概念圖、提示詞、修訂與 SHA-256 圖冊 | 使用者選定設計後，統一尺寸、樓梯與開口；目前不是可施工平面圖 |
| 人物動作 | 共用五次曲線、步伐／身體小動作、手指依序閉合；12 項原生相機／姿勢／拿放檢查通過，3 張 Blender 表面可見性預覽通過 | 新角色、臉／眼／頭髮、動捕資料與 Motion Matching 尚未整套導入；不宣稱達到 GTA 品質 |
| 物件 | 3 個 GLB、Blender 原檔、照片木紋；閉合壁面與底部射線檢查；UE 匯入及重載檢查 | 原生近看材質、可動碰撞與新抓握錨點 |
| 流體 | Niagara 3D FLIP 校準場景、參數型別／名稱檢查、獨立 GPU 執行與原生截圖流程 | 出水源控制、倒入杯中、溢出與 Home ml／事件狀態仍需連動與量測 |
| 流程 | 已建立並安裝可重用 skill，含 GLB 檢查工具與本機執行範例 | 不代表較小模型的端到端能力已做實驗驗證 |

詳細方向見 [接近 GTA 的品質方案](quality-plan.zh-TW.md)。流體各次嘗試與最終檢查結論見 `implementation-manifest.json`；不能只看程序回傳 0 或粒子數為正就認定畫面通過。

## 可重現來源

- 模型與渲染：`tools/blender/vista_villa_r1/build_hero_props.py`。
- UE 資產與校準：`tools/ue/vista_villa_r1/`。兩個獨立地圖為 `/Game/VISTA/VillaR1/Maps/PropsLab` 和 `/Game/VISTA/VillaR1/Maps/FluidLabR2`。
- 原生檢查：`tools/runtime/vista_villa_r1/run_native.py`，使用自己的網路 namespace、虛擬顯示器和 user directory；記錄實際 NVIDIA renderer。
- Skill 原始碼：[SKILL.md](../../../skills/vista-blender-ue-workflow/SKILL.md)；已安裝至 [本機 skill](/home/yhliu/.codex/skills/vista-blender-ue-workflow/SKILL.md)。
- 大型／生成檔案保留於 `/data/sysx/vista-world/runs/vista-villa-r1-20260910a`，不進 Git。

基礎 contract/compiler 的 28 項測試及本次 8 項動作曲線、GLB 與 Home 合約測試通過。新外掛以 UnrealEditor Linux Development 編譯；原生姿勢檢查是 NullRHI，身體表面預覽是 Blender，流體截圖才是 Vulkan 原生畫面。

## 研究銜接

[VISTA](https://arxiv.org/html/2605.10579v2) 負責情境生成與稽核，[EgoArgus](https://arxiv.org/html/2608.25561v1) 提供證據關係與介入判斷；後者已使用 VISTA。新的切入點是固定起始世界後，執行不同提醒與人物反應，量測後果差異。世界還原、人物語言反應及完整助理閉環仍需獨立實作與驗證。
