# Villa 六空間任務還原

使用者將優先順序調整為完成六個空間，人物沿用已可運作的參考角色。
本次把保留的 Home 任務家具、細部接觸與事件控制器接到 Villa，並保留兩層樓、
樓梯與戶外場景。原始 Home 與已發佈場景均為唯讀來源。

| 空間 | Villa 位置 | 還原內容 |
| --- | --- | --- |
| 玄關 | 一樓入口與樓梯旁 | 出口門、穿鞋椅、帶回鑰匙／手機的到達判定 |
| 客廳 | 一樓西側 | 沙發、茶几、鑰匙、拖鞋、電視與立燈 |
| 廚房／餐廳 | 一樓北側 | 杯、水壺、雙手鍋具、餐桌、爐火、可開啟冰箱與收納 |
| 臥室 | 二樓西側 | 床、床頭櫃／抽屜、手機、四扇衣櫃門、背包穿脫 |
| 書房 | 二樓中央 | 桌椅、電腦、雙門收納櫃、梯子、雙手高處取箱 |
| 浴室／洗衣 | 二樓東側 | 浴缸與面盆水龍頭、水位／溢流、馬桶、衣籃、洗衣機門與衣物流程 |

43 個具名互動物件使用原有 `HomeLabel` 與 entity ID，另有三個執行時危害標記。
家具採等比例平移，保存手部接觸面、座位、收納容量與梯階尺寸；六扇通道門使用
個別的樞軸與旋轉。新門洞有實際碰撞和門楣。臥室背包掛架移離入口，走廊盆栽
移至二樓較寬處；其他盆栽幾何與材質保留。玄關椅往西移 250 cm，
讓樓梯底部有完整的角色通行寬度。

`AHomeActionsCharacter` 重用 Villa 的角色外觀與行走資產。只有具有
`VistaSixSpaces` 標記的地圖啟用 Villa 外觀／動作；既有 Home 保留原本的資產選擇。
Home 狀態機負責室內操作，原 Villa 的獨立倒水示範不會與 Home 同時控制手持物。
另案 PR #20 的連續倒水中斷尚未併入此模式。

房間判定現在包含 Z 範圍，樓上的走廊不會提前被判成玄關。水面、水流、爐火、
溢流危害、梯階與扶手接觸點隨房間位置移動。室內動作仍保留原有接觸、碰撞、
回復、所有權和容量檢查。
庭院門也檢查玩家的垂直距離，避免樓上臥室的 E 鍵操作被正下方庭院門攔截。

## 事件語意

七個事件的 `initial_operations`、公開目標、成功／失敗條件及時間限制保持原內容：

- `mmg_001`：開出口門以前關爐火。
- `mmg_013`：拿起拖鞋；不是清理水漬。
- `mmg_021`：關閉浴缸水龍頭。
- `mmg_040`：檢查梯子；坐上滾輪椅是失敗條件，不把高處取箱替換成金標目標。
- `mmg_044`：把鑰匙實體帶到玄關。
- `mmg_045`：把手機實體帶到玄關。
- `mmg_070`：洗衣機運作。

舊場景的 `set_transform` 仍遵守原有替代場景 baseline 政策；不重寫 canonical dataset。
玩家持物時不能使用換房捷徑。跨房間驗證透過實際 WASD、碰撞與持物 constraint，
沒有在拿起物品後重新設定角色位置。

## 重建與驗證工具

- `tools/runtime/vista_six_spaces/layout.py`：房間範圍、門樞軸與 contract 轉換。
- `tools/ue/vista_six_spaces/restore_rooms.py`：在私人專案中另存地圖，建立家具與門洞，
  並設定該專案的預設地圖；輸出來源 hash、替換清單和 contract。
- `tools/ue/vista_six_spaces/export_gallery_plant.py` 與
  `tools/blender/vista_six_spaces/clear_gallery.py`：移動合併模型中的單一走廊盆栽，
  輸出獨立 GLB 和幾何變更紀錄。原有 UE 材質在匯入時重新綁定。
- `tools/ue/vista_six_spaces/verify_saved.py`：讀回磁碟中的地圖，驗證 43 個唯一標籤、
  GameMode、場景標記，以及門板是否直立。
- `tools/runtime/vista_six_spaces/run_native.py`：使用獨立 X11 顯示、GPU 0、私有 bridge
  執行 `actions`、`details`、`sequences`、`protocol`、`tour`、`input`；保留失敗結果與截圖。
  `input` 實際按 E 拿手機、驗證持物換房受阻、G 放手，以及 1–6／Tab 操作。
- `tools/runtime/vista_six_spaces/make_review.py`：核對相同原生地圖、程式與設定的驗證結果，
  將原始截圖組成離線檢視頁。重試保留先前失敗紀錄與各自的測試程式 hash。

`restore_rooms.py` 需要 `VISTA_SIX_OUT`，可指定 `VISTA_SIX_SOURCE` 為保留的原始
Home contract，`VISTA_SIX_REVISION=R4` 與 `VISTA_SIX_PLANT` 為修訂後盆栽輸出目錄。
所有輸出路徑必須新建。二進位資產、原始人物照片、執行紀錄與畫面均不放入 Git。

R5 的背景收尾另由 `export_background_fixture.py`、`remove_stale_tap.py`、
`finish_background.py` 完成：舊水龍頭與欄杆在同一個金屬模型中，只移除水龍頭的
7,512 個頂點，保留其餘欄杆及原材質。FBX 匯出必須同時啟用 `export_source_mesh`
並停用 `collision`，才能取得完整來源幾何。另存 R5 後核對 43 個互動綁定完全相同，
功能契約只改版本與地圖路徑；保留 R4 作為完整功能驗證基準。欄杆新模型使用實際
三角網格碰撞，R5 補驗手機下樓、廚房操作與六空間取景。

檢視頁可用 `make_review.py --runs ... --background-cleanup .../cleanup.json --out ...`
合併基準與背景收尾的補驗。它驗證契約及綁定沒有功能差異，明列每一案例的來源版本；
不將 R4 的全部檢查宣稱為在 R5 重跑。HTML 內嵌原始 PNG，可單獨下載開啟。

Native runner 的必要參數為 `--project`、`--engine`、`--ddc`、`--source-contract`、
`--out`；由 `xvfb-run -a` 啟動，不能使用共享的 `:119`。
可用 `--only` 選定案例，`--suite sequences --timeouts` 加上兩個超時案例。
操作依舊是 WASD、滑鼠、E／左鍵、滾輪換動作、F 檢查、C 蹲下、B 背包、G 放下／取消、
Tab 換視角、1–6 換房、F2 換事件、R 重置。

## 證據邊界

地圖綁定、C++ 編譯、單項動作、完整任務序列與畫面檢查是不同層次的證據。
`tour` 以空手 fixture 取景，只證明六個房間的畫面，不算走路驗證。
`state.json`、接觸面和事件結果是 privileged review 資料，不能混入模型觀測。
此處液體仍為 Home 的容量／狀態模型與可見效果，並非流體力學實驗；角色、布料、
臉部與所有手指動畫也不宣稱達到 GTA 品質。具體通過數、版本 hash、未解問題與
實際啟動狀態記在工作區 handoff，不以設計文件取代驗收紀錄。

## 私人測試與當機回報

`-noexceptionhandler` 不會關閉這個 UE Linux 建置的自動當機回報。私人 runner 明確傳入
`-ini:Engine:[CrashReportClient]:bStartCRCFromEngineHandler=False` 與
`-ini:EditorSettings:[/Script/UnrealEd.CrashReportsPrivacySettings]:bSendUnattendedBugReports=False`。
`-VistaPrivateReview` 讓 native Home 啟動時讀取生效的 GEngineIni；若回報程序仍可啟動，
即退出測試。Harness 必須讀到 `VISTA_PRIVATE_REVIEW_CRC_DISABLED` 才開始操作。
私人專案的 DefaultEngine.ini 與 DefaultEditorSettings.ini 也保存對應停用設定；
執行該專案的 authoring commandlet 時同樣應使用上述 Engine 參數。

這不是網路 namespace 隔離。當 native 程序退出，GuardedHome 會拒絕其遺留 snapshot，
不把 stale bridge 的 ready=true 當成仍在運作。原生 GPU 驗證採逐次啟動，失敗嘗試保留。
