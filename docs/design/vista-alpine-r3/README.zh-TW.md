# Alpine Villa R3：湖景、自然採光與戶外跑跳

本版沿用 Villa R2 的別墅、二樓、樓梯與室內操作，新增可走出的露台、湖岸、草坡、樹林與步道。開門、行走、跑步、跳躍與落地在 Unreal 中執行。遠處阿爾卑斯山使用 8K 實拍全景，近處地形、樹木、岩石、露台與湖面是場景資產。

這是朝寫實方向推進的可操作研究原型，尚未達 GTA 成品品質。遠坡幾何、植物遠距細節、人物皮膚／衣服變形和動作過渡仍有改善空間。遠景照片中的山峰不是可以爬上的地形；湖面尚未實作游泳、浮力或完整體積流體。

## Demo 操作

Sunshine 已註冊獨立入口 **VISTA Alpine Villa R3**，畫面左上顯示 **ALPINE VILLA R3**。在 Moonlight 重新整理應用程式清單後選取它。交付與驗證紀錄見 [implementation-manifest.json](implementation-manifest.json)。原有九個入口完整保留；註冊後 R1 的遊戲與輸入程序 PID 未變。本次沒有選取 R3，也沒有在 Moonlight 客戶端實測串流。

| 操作 | 按鍵 |
| --- | --- |
| 移動、觀看 | WASD、滑鼠 |
| 跑步 | 按住左 Shift |
| 跳躍 | Space；在地面且未進行物品操作時 |
| 第一／第三人稱切換 | Tab |
| 餐廳湖景落地門開關、拿取／放回物品 | 靠近並看向目標，按 E |
| 拿起水壺後倒水 | P |
| 水槽龍頭 | 靠近水槽按 F |
| 室內示範與巡覽 | H |
| 重設 | R |

從客廳走向餐廳，靠近通往湖景露台的滑門，對準門把附近按 E，待門打開後走出去。門關閉時有碰撞，角色佔據門口時會阻止關門。空手平視保留垂手；低頭看得到軀幹、腿和鞋，向側下方看可見手臂。戶外仍使用同一個完整角色。

## 實作內容

- **景觀：** 共用公尺尺度高度場，近處 2.5 m 網格與較遠 25 m 網格銜接；湖盆、湖岸、2.4 m 步道、露台與階梯有一致座標。樹幹有獨立碰撞，葉片／草不阻擋玩家，岩石保留表面碰撞。
- **資產：** Poly Haven CC0 實拍地表、針葉樹、幼樹、岩石、草叢與 HDR 全景。修復來源模型以 CORNER FLOAT_VECTOR 儲存的 UV，再驗證 glTF `TEXCOORD_0`。遠岸補上成片樹林，草叢集中在玩家路線旁。
- **採光：** 同時平衡日光、HDR 環境光、曝光與室內光源，保留 R2 的樓梯天窗及跨樓層採光窗。最終日光設定 20,000 lux、EV100 範圍 10–12.5；這些是引擎參數，非實地照度測量。
- **材質：** 草地使用多尺度實拍細節與連續大範圍色差，減少遠距鋪貼感。露台重新按世界尺度鋪設霧面石材與接縫；湖水使用 SingleLayerWater 光學深度及低幅度波紋。
- **動作：** 取用本機 Epic mannequin 的八向走路、八向跑步、起跳、落下與落地共 19 段，重定向到原 53 骨骼角色。以移動距離推進週期，同時調整步幅與腳部位移；空中停用接地 IK、落地重建支撐點。步行約 1.25 m/s，跑步約 3.5 m/s。
- **人物：** 保留原角色比例，依連通的衣物網格區分上衣與褲子；縮減鞋子所含襪筒穿出褲管的範圍，第一與第三人稱使用相同骨架與對應材質。極端側移姿勢仍可見少量襪筒／褲管交疊。

既有倒水示範仍是 Niagara FLIP 視覺、容器液面／水柱，以及獨立的守恆帳本。湖水光學材質、Niagara 粒子和帳本是不同層次；本版沒有把它們宣稱為經驗證的物理反事實模擬。

## 驗證與研究使用

原生檢查分開執行：戶外連續 30 Hz 移動／跳躍、12 種角色視角／步態案例、室內拿取／倒水／放回／樓梯，以及原 Home 姿勢回歸。10 Hz 的快速畫面預覽不能當成移動驗收。數值、實際 PNG、完整來源雜湊與程序退出狀態記在交付清單。

| 最終檢查 | 實際結果 |
| --- | --- |
| 戶外連續移動 | 850 幀；實際開門走出露台，跑速 3.5 m/s，22 幀在空中並完成落地 |
| 角色視角與步態 | 12 種案例、650 幀；完整支撐期腳踝最大位移 0.61 cm，空手保持垂手 |
| 室內互動與二樓 | 拿取、倒水、放回、水龍頭、樓梯完成；接收容器 207.34 mL，帳本殘差 0 mL |
| 原生畫面 | 48 張 PNG 已逐張檢視；不是生成參考圖 |
| 建置 | UE Editor、Linux Game Development／Shipping 成功 |
| Python | 本輪共 47 個不同案例通過：28 個基礎合約／編譯器、8 個模擬服務生命週期、11 個 R3 驗證案例 |
| 凍結交付 | 3,556 個檔案、3,836,331,985 bytes；完整雜湊驗證通過 |
| 凍結專案讀回 | 新程序檢查碰撞、材質、日光、草木數量；外置 VT 快取後 0 錯誤、0 警告 |

原 Home 的 12 個姿勢／互動回歸案例在較早的 build-d 通過；其後僅修改 Villa 的鏡頭與步態，沒有聲稱用最終 build-f 重跑該組案例。最終三組 Villa 原生檢查使用相同的插件、地圖、兩份動作資料與人物外觀雜湊。

固定 30 Hz 是動作驗證的模擬取樣率，不代表串流能跑 30 FPS。此次共用 GPU 並包含截圖停頓，廚房記錄的幀時間中位數約 207 ms；尚未取得獨占 GPU 下的即時效能基準。

實際 Unreal 畫面：

![湖岸望向別墅](/data/sysx/vista-world/runs/vista-villa-r3-20260910a/kitchen-native-a/user/Saved/VillaProof/19_architecture.png)

![二樓天窗與採光](/data/sysx/vista-world/runs/vista-villa-r3-20260910a/kitchen-native-a/user/Saved/VillaProof/15_architecture.png)

![空手第三人稱姿勢](/data/sysx/vista-world/runs/vista-villa-r3-20260910a/kitchen-native-a/user/Saved/VillaProof/02_walk_and_stop.png)

目前可作為 VISTA／EgoArgus 後續具身互動與風險情境研究的可操作展示環境；本輪新增的是呈現和操作能力，沒有新增經標註的 benchmark，也沒有驗證 NL agent 的策略或因果結論。生成腳本、種子、隱藏標籤、評審紀錄與研究答案不可流入受限 assist-step 模型輸入。

## 重現

請讀 [Blender／Unreal skill](../../../skills/vista-blender-ue-workflow/SKILL.md) 與 [戶外操作參考](../../../skills/vista-blender-ue-workflow/references/alpine-outdoors.md)。原始來源、GLB、Blender、UE 專案、動捕與 PNG 都留在 Git 外的 run 目錄；Git 保存重現腳本、C++、測試與文件。Editor 與 Linux Game Development／Shipping 需分別建置。凍結交付的所有檔案都必須符合 manifest，才能由 launcher 選取。

免費來源：[Poly Haven CC0 授權](https://polyhaven.com/license)、[Alps Field](https://polyhaven.com/a/alps_field)、[Fir Tree](https://polyhaven.com/a/fir_tree_01)、[Pine Sapling](https://polyhaven.com/a/pine_sapling_medium)、[Rock Moss Set](https://polyhaven.com/a/rock_moss_set_01)、[Grass](https://polyhaven.com/a/grass_medium_01)、[Rocky Terrain](https://polyhaven.com/a/rocky_terrain_02)。本輪沒有呼叫付費圖片／影片模型，也沒有購買資產。
