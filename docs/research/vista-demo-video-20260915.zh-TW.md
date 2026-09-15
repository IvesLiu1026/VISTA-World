# 六房間與校園的字幕 Demo

使用者要求錄製六房間、校園與目前可展示的各種互動，並用字幕解釋正在做什麼。影片必須來自實際 Unreal 運作，保留動作與物件狀態的原生收據，不把腳本示例當成模型實驗結果。

## 錄製與剪輯

- 輸入為獨立凍結的 `projects/campus-realism-r25`，非使用者正在操作的 R13。每次啟動前校驗凍結清單，使用私有 Xvfb、GPU 0 和獨立 UserDir。GPU 1、Sunshine 和共用輸入不變。
- `demo_capture.py` 透過 native Home typed bridge 或真實鍵鼠操作。相機與空手人物的起點在鏡頭前設定；攜帶物品的跨房間移動使用碰撞路徑，不傳送物品。
- `demo_plan.py` 定義六房間、人物動作、七個事件和戶外的中文分鏡；每個動作的字幕起點與真正發出指令的時間同步，終點延續到下一操作。錄影時間使用 X11 第一個輸入影格的 epoch，避免編碼器緩衝造成字幕超前。
- 每段是 1920×1080、30 fps 原生連續錄影，輸出 H.264/yuv420p。沒有補幀、生成式影片或旁白。章節之間有明確取景剪接，保留完整原始片段與操作回覆。
- `render_demo.py` 僅採用成功片段；驗證凍結版本、檔案雜湊、影片規格、動作種類及章節／事件覆蓋，再產生各章、完整影片、精華及 SRT/VTT。繁體中文字幕使用本機 Noto Sans CJK TC，直接燒入影片。
- `publish_demo.py` 產生全新的私有影片頁和下載連結，只發佈清單內的 MP4、字幕、海報與摘要。`serve_review.py` 限定明確的 Tailscale IPv4，支援瀏覽器影片 Range/HEAD；不提供工作區目錄。

## 動作涵蓋的定義

必須覆蓋 Home 設定的 40 個 action ID 與 `step_down`、`unequip` 兩個延伸 ID。這是 42 種指令，其中含共用動作和別名，不表示 42 套獨立 motion-capture 動畫，也不是每個物件與動作的笛卡兒積。

43 個非 hazard 物件／家具控制綁定須出現在導覽或互動的分鏡清單；七個事件須各有成功的原生片段。另加入錯誤順序的失敗示例、戶外場景切換、汽機車進出／轉向／煞停、車流與綠燈過街。動作成功回覆與畫面美術品質分開判斷。

研究事件只示範現有事件契約的條件與結果。例如 `mmg_040` 的保留成功條件為檢視梯子，不能把該結果擴大為已完成高處取物規劃實驗。身體的滑倒、跌倒、受撞示例是動作原型，不代表已驗證的真實碰撞物理。

## 重現入口

在 `worktrees/campus-realism` 執行 `workspace/bin/uv run tools/runtime/vista_campus/demo_capture.py --help`；以 `xvfb-run -a -n 241 -s '-screen 0 1920x1080x24 -nolisten tcp'` 包住命令。提供凍結專案、UE 5.7.3、cache、原始座標 donor、全新輸出目錄及 `--group rooms|body|events|campus`。各組依序執行，不可同時使用同一展示專案。`--only` 可僅重錄實際失敗的分鏡。

保留 `recording.json`、`source/` 腳本快照、`raw/` 影片、native.log 和 bridge 回覆。將已正常退出的錄製收據傳給 `render_demo.py --recording ... --contract ... --out NEW_DIR`。不要將 `--allow-partial` 的字幕試片當作完整交付。完成後 `publish_demo.py --gallery ACCEPTED_REVIEW --release demo.json --out NEW_GALLERY`。

交付的實際檔案清單、總長、瀏覽器播放與字幕檢查，以本輪生成的 demo 收據及 `.agent/handoffs/20260915-campus-realism.md` 最後狀態為準。

## 本次交付

- 原生凍結版本：CampusR25，manifest SHA-256 `caee7f26f2a5e2d43155b1a53e064338815200264f89d97295796661e7dddbaf`。84 個採用片段，包含 42 個動作指令、43 個非 hazard 綁定、1 個潑灑標記和 7 個事件。
- 13 章共 18 分 22 秒；正常速度精華版 3 分 44 秒。15 個 MP4 均為 1920×1080、H.264/yuv420p、30 fps，繁體中文字幕已燒入；另附各片 SRT/VTT。總 MP4 大小 890,580,800 bytes。
- 完整影片收據：`runs/campus-realism-demo-final-r25/demo.json`；媒體解碼與字幕時間驗證：`runs/campus-realism-delivery-r25/video-validation.json`。全 15 片完整解碼通過，完整版含 13 個 MP4 章節。
- 網址：`http://100.114.231.122:48995/` 與 `/demo.html`；圖片在 `/realism.html`。依使用者最後要求，頁面沒有說明段落或效能表；名稱和時長浮在畫面內，動作文字在影片字幕中，僅留播放／下載／字幕與媒體切換控制。細節保留於研究文件和 JSON 收據。
- 全 15 片在本機 Chromium 實際播放、拖曳至第 5 秒成功；13 個海報、16 張圖片可解碼。桌面 1440 px 和手機 390 px 無水平溢出。這是伺服器端瀏覽器檢查，不代替 MacBook／Moonlight 客戶端的實際回報。

採用的錄製收據：`campus-realism-demo-rooms-a`（43 段）、`rooms-b`（1 段）、`body-a`（12 段）、`events-b`（4 段）、`campus-a`（16 段）、`campus-b`（2 段），以及 `campus-realism-delivery-r25/events-a-selected.json`（6 段）。上述縮寫皆位於 `workspace/runs/campus-realism-demo-*`。每個原生程序正常退出 0。

原 `rooms-a` 的拉椅子片段因站位超過可達範圍失敗，調整空手起點後僅重錄該片段。原 `events-a` 的鑰匙／手機事件功能通過，但朝地面觀看時衣服穿模，因此保留原始收據，另存可追溯的 6 段選用清單，將兩個事件重錄為「拿取」與「正常前視角的攜帶路線」。兩段之間只改相機，不傳送人物或手持物件；場景碰撞和成功條件仍由原生回覆確認。穿模本身仍是待修的角色缺陷，不能以鏡頭選擇宣稱已修好。

六房間／校園錄影在獨立 Xvfb 完成。錄製期間使用者的共用選擇從原 R13 程序變為另一 R13 程序，再到 Alpine Villa R3；本工作未送入共用鍵鼠、切換遊戲或重啟 Sunshine。最後伺服器確認的 Sunshine PID 為 364102，Alpine Villa 遊戲 PID 為 476478；執行下一次操作前仍需重新讀取真實狀態，不能只依過期的 `workspace/state/dev-selection.json`。
