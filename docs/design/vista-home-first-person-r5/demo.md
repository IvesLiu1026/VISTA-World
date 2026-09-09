# R5 獨立 Demo

Moonlight 連到原本的 Sunshine 主機，選 **VISTA Home R5**。
新版已完成首次著色器初始化，並在實際 UE 視窗中運作。

| Moonlight 入口 | 版本 |
| --- | --- |
| **VISTA Home R5** | R4 材質＋R5 第一人稱空手、低頭身體視點 |
| **VISTA Photoreal Home** | 原本保留的 R3 demo |

切換版本時，先在 Moonlight 結束目前 app，再選另一個入口。
兩版共用同一個 Home 顯示／輸入服務位置，選定時只執行其中一版。
退出 R5 串流後，R5 遊戲會繼續留在桌面，因此改連 **Low Res Desktop**
也會看到 R5。要回原版，請明確選 **VISTA Photoreal Home**。
專案、版本啟動設定、UserDir、bridge 操作紀錄及寫入快取分開。
原本六個 Sunshine app 定義及 R3 專案、備份都保留。

## 操作

| 按鍵 | 操作 |
| --- | --- |
| WASD＋滑鼠 | 移動與轉頭；向下看自己的身體 |
| Tab | 切換第一／第三人稱 |
| E | 執行準星下方顯示的操作，例如拿起物品 |
| 滾輪 | 切換目前物品可用操作 |
| G | 放手／取消 |
| R | 重設目前場景狀態 |
| 1～6 | 空手時切換玄關、客廳、廚房、臥室、書房、浴室 |
| F2 | 下一個 VISTA 情境 |

## 驗證範圍

R5 的 35 項既有測試與 12 個 NullRHI 原生情境已在實作交付時通過。
獨立 demo 另有 17 個啟動、隔離、串流退出保留及輸入擁有權測試通過。
也在實際主機啟動並終止一個串流啟動器，確認同一個 R5 遊戲 PID 保持運作，
沒有送出玩家按鍵。這避免退出 R5 入口時露出桌面背景的舊環境。

已確認 Sunshine 選中的 app ID 對應 R5，實際 UE 視窗正常渲染，
原生紀錄包含成功拾取與放置杯子。
自動按鍵檢查期間使用者連入，因輸入重疊而中止；該次檢查不列為通過。
後續檢查器會在每次輸入前確認 Moonlight 沒有擁有畫面。
完整 GPU 身體視覺、全部動作回歸與 R3 實際回切測試仍未完成，
目前保留使用者對 R5 的操作權。

## 本機交付

- [R5 Unreal 專案](/data/sysx/vista-world/runs/vista-home-first-person-r5-20260908a/project-c/PhotorealHome.uproject)
- [R5 啟動設定](/data/sysx/vista-world/runs/vista-home-first-person-r5-demo-20260908a/sunshine-profile.json)
- [執行確認](/data/sysx/vista-world/runs/vista-home-first-person-r5-demo-20260908a/live-confirmation.json)
- [原版保留檢查](/data/sysx/vista-world/runs/vista-home-first-person-r5-demo-20260908a/preservation.json)
- [桌面保留實測](/data/sysx/vista-world/runs/vista-home-first-person-r5-demo-20260908a/desktop-retention.json)
- [UE 實際畫面](/data/sysx/vista-world/runs/vista-home-first-person-r5-demo-20260908a/native-live.png)
- [原有 R3 操作腳本](/data/sysx/vista-world/presentations/vista-home-r3-progress-20260908/final/Demo操作腳本.md)

僅在沒有 Moonlight 選定 app 的時候，可用 `launch_demo.py --profile PROFILE --action start`
從主機端啟動。一般使用者直接選 Moonlight 入口即可。
若使用者明確要求把目前的 Low Res Desktop 畫面切到 R5，可額外帶
`--show-in-desktop`；此旗標只接受已核對的 Low Res Desktop app ID，
不允許接管其他已選定的 app，也不重啟 Sunshine。
`--action plan` 驗證插件雜湊與獨立路徑；`--action status` 顯示目前選定專案。
`--action stop` 僅停止仍屬於這份 R5 專案的 Home，不會關掉後來選定的 R3。

此次新增 app 後重新啟動 Sunshine 載入清單，沒有修改認證或配對檔案。
Sunshine 的 app 清單載入／重新整理行為依據
[安裝版本的官方來源](https://github.com/LizardByte/Sunshine/blob/v2026.516.143833/src/process.cpp)。
