# DS4 电量提示 · DS4 Battery Overlay

> **本项目的介绍整理与功能改造由 「DeepSeek v4.1 Flash」 修改整理**
> **Introduction and feature work by 「DeepSeek v4.1 Flash」**
>
> 当前版本 **v1.3.1** ｜ 版本号同时显示在程序启动日志、控制面板标题与 `--version` 输出中
> Current version **v1.3.1** · shown in the startup log, the control-panel title and `--version`
>
> **本版新增**：控制面板可一键切换 **中文 / 英文**，顶部电量横条与底部弹窗**同步**切换语言。
> **New in this version**: one-click **Chinese / English** switch in the control panel; the top
> battery bar and the bottom popup follow the selected language.
>
> **豆包AI生成**：项目最初由豆包（Doubao）AI 创作完成，后经多轮功能扩展与性能优化。

---

## English Introduction

**DS4 Battery Overlay** shows the battery level of a **DualShock 4** controller on screen.
Connect (or plug in) the controller and a rounded battery popup appears at the bottom centre
for **3 seconds**; the always-on-top bar can be toggled with a key combo.

### Features

| Feature | Description |
| --- | --- |
| Battery popup | Appears on connect / plug-in, shows the level for 3 s (fade in 0.15 s, fade out 0.35 s) |
| Charging status | "Charging" / "Fully charged" when on USB; wireless shows a plain percentage |
| Disconnect notice | Popup when the controller is unplugged |
| Power events | Bluetooth: plugging/unplugging the charge cable shows a short notice |
| Low-battery warning | Red highlight at ≤ 20 %; checked every ~30 s, warned once per drop |
| In-game level check | Double-press **PS** (within 500 ms) to show the level for 2 s |
| Top battery bar | **D-pad Down + PS** toggles a rounded bar at the top of the screen; refreshes every 2 s, colours by level (≤20 % red / 20–60 % amber / >60 % green) |
| **Overcharge guard** | Warns you to unplug once the battery reaches a threshold (default 90 %) — the controller's charging circuit is hardware, so software can only *remind* you |
| Control panel | GUI to start/stop/restart the resident program, toggle autostart, toggle the overcharge guard, view battery details and preview the UI |
| **Language switch** | **Chinese / English**, switchable in the control panel; both on-screen displays follow instantly |
| Battery details | Measured level, raw step (0–15), charging state, link type, estimated runtime and time-to-full |
| Runtime estimate | Estimated "time left" while discharging and "time to full" while charging (based on the measured rate; shows "Estimating" until a full 10 % step has been seen) |
| Autostart | Registry-based (`HKCU\...\Run`), one click in the panel or the bundled `.bat` files |
| Robustness | Single-instance guard, HID handle self-healing (survives screen-share / voice-chat apps), watchdog, crash log, resource self-monitoring |

### Usage

1. Unzip, then double-click **`Start-DS4-Battery-Overlay.bat`** (start the resident program).
2. Double-click **`Open-Control-Panel.bat`** (open the control panel) — here you can stop/restart the
   program, toggle autostart, toggle the overcharge guard, switch the language, view battery
   details and preview the UI.
3. In game: **double-press PS** to see the level, **D-pad Down + PS** to toggle the top bar.

> Please run games in *windowed / borderless* mode: a normal always-on-top window cannot be
> displayed over an exclusive-fullscreen game, and PS-key listening also fails when another app
> (Steam, DS4Windows…) holds the controller exclusively.

### Honest notes on accuracy

- The DS4 reports the battery in **10 % steps** (raw step 0–15); this is a hardware limitation,
  so values such as 0/10/20…100 % are expected.
- The hardware does **not** expose mAh capacity, cycle count or battery health (all ~50 HID
  FEATURE reports were enumerated, plus Windows battery devices and WMI). This project therefore
  does **not** display any fabricated mAh figure.
- Software **cannot cut the charging circuit**; the overcharge guard is a reminder, not a switch.

---

## 中文介绍


插入 / 连接 **DualShock 4 (DS4)** 手柄时，屏幕底部居中弹出电量提示，稳定显示 **3 秒**后自动淡出。
支持 **USB** 与 **蓝牙** 两种连接方式，也支持「手柄一直插着、程序后启动」的情况（启动时会先弹一次）。

---

## 一、功能总览（当前全部可用功能）

### 1. 电量提示与充电状态
- **接入即弹窗**：插入 / 连接手柄后弹出电量窗，显示 3 秒后淡出（淡入 0.15s + 淡出 0.35s）
- **充电状态**：插线充电显示绿色「充电中」（进度 0/10…100%）；充满显示「已充满」（100%）；无线使用只显示百分比
- **拔出提示**：手柄断开时弹出「手柄已断开」
- **接入 / 拔出电源提示**：蓝牙连接时插拔充电线会弹出「接入电源 / 拔出电源」（1.5 秒）

### 2. 低电量提醒
- 电量 **≤ 20%** 时红色高亮弹窗
- 连接期间每约 **30 秒**自动检查一次，跌破阈值主动提醒；提示过只报一次，恢复到阈值以上才重新计时

### 3. 游戏内随时看电量（双击 PS 键）
- 游戏中 **500ms 内双击 PS 键**，立即弹出当前电量窗（显示 2 秒）
- 窗口始终置顶、不抢游戏焦点

### 4. 常驻电量横条（十字键下 + PS）
- **十字键下 + PS** 组合键：在屏幕正上方显示 / 隐藏电量横条
- 美术风格：左右两端**圆角胶囊**外框；左上深色**状态标签**（DS4 / 充电中 / 已充满 / 未连接）
- 大号百分比居中并与细进度条重叠，**数字加粗 + 白色描边**，叠在任何壁纸上都清晰
- 进度条颜色随电量：**≤20% 红 / 20–60% 黄 / >60% 绿**；未连接显示「未连接」
- 显示期间每 **2 秒**自动刷新；唤出时**立即上屏**（先用已知电量渲染，不再等读取）

### 5. 防过充（插线达阈值提醒拔线）
- 插着充电线且电量达到阈值（默认 **90%**，可配置）时，弹出 **「请拔掉充电线」** 提示
- 同一轮充电只提醒一次，并带 **60 秒冷却**；拔线或电量回落后自动重置，下次达标可再提醒
- 控制面板可**一键开关**；阈值写入程序目录的 `ds4_config.json`
- ⚠️ **物理限制**：手柄插上 USB 后充电是硬件直连，**软件无法切断充电电路**，DS4 也没有充电阈值接口。
  本功能是**提醒你拔线**，不是自动断电。

### 6. 可视化控制面板（免 Python，自包含）
双击 **`Open-Control-Panel.bat`** 打开图形界面（所有启停逻辑都在面板内，不再依赖其它程序）：

| 功能 | 说明 |
| --- | --- |
| 状态指示 | 绿 / 红圆点 + 「运行中 / 未运行」+ 常驻程序 PID + 开机自启状态 |
| 一键操作 | **启动 / 停止 / 重启 / 刷新状态** |
| 开机自启开关 | 按钮文案随当前状态变化 |
| **防过充开关** | 显示当前阈值（如 `关闭防过充(90%)`），点击即开 / 关 |
| **电池详情** | 查看实测数据 + **预计续航** / **预计充满时长**（见下） |
| 预览外观 | 无需手柄即可预览电量弹窗与顶部横条效果 |
| **语言切换（本版新增）** | 一键在 **中文 / 英文** 间切换；面板、顶部电量横条与底部弹窗**同步**切换，设置保存到 `ds4_config.json` |

> **语言切换怎么生效**：面板写配置的同时会写一个 `_lang.signal` 通知文件，常驻程序在轮询
> 中检测到变化后**立即**用新语言重绘弹窗与顶部横条 —— **无需重启程序**。

### 7. 电池详情与时长估算（v1.2.8 起两个时间常显；v1.2.9 起不再显示容量估算）
面板点 **「电池详情」** 查看 —— **预计续航** 与 **预计充满** 会同时显示：

```
电池详情（实测）
  真实电量  ：80%
  原始档位  ：8 / 15  ← 硬件按 10% 一档上报，这是精度上限
  充电状态  ：充电中
  连接方式  ：USB 有线
  预计续航  ：还能用 约 2 小时 40 分钟   ← 按上次无线速率推算
  预计充满  ：还需 约 30 分钟
  数据时间  ：2026-10-08 17:00:00
```

- **预计续航**：无线放电时按实测放电速率估算；**插线时沿用最近一次无线速率**结合当前电量继续给出估算
  （并标注"按上次无线速率推算"），所以插着线也能看到还能用多久
- **预计充满**：插线充电时按实测充电速率估算「还要充多久」
- 速率由常驻程序自动累积历史读数计算（样本至少间隔 30 秒、电量变化约一档）
- 若从未有过放电样本（例如一直插线），续航会显示"估算中"，**用过一次无线即可出数**

> **本面板只展示可实测的数据**：电量 / 原始档位 / 充电状态 / 连接方式 / 时长估算。
> DS4 硬件**不提供 mAh 容量、循环次数或健康度**（已实测枚举其全部约 50 个 HID FEATURE 报告，
> 并检查 Windows 电池类设备与 WMI，均无容量字段），因此**不做容量估算、也不显示任何 mAh 数字**。
> 其中**原始档位（0–15）**能直接看出硬件量化精度。

### 8. 开机自启
- 开启：双击 **`Enable-Autostart.bat`** ｜ 取消：双击 **`Disable-Autostart.bat`**
- 也可在控制面板里一键开关
- 通过注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 实现，指向主程序，开机后台常驻

### 9. 稳定性与性能（长期运行保障）
- **单实例保护**：全局互斥体，重复启动只保留一个实例，不会重复弹窗
- **句柄自愈**：自检手柄句柄健康（帧心跳 + `is_plugged()` 主动探测 + 报告静默判定），
  被屏幕共享 / 语音开黑软件抢占或快速拔插后**自动重开**，无需重启程序
- **看门狗**：主循环超过 30 秒无心跳（界面假死）自动原地重启
- **崩溃防护**：`faulthandler` 原生崩溃转储；顶层异常写日志并自愈重启；
  资源自监控每 5 分钟记录内存 / 线程 / 句柄，内存超阈值自动重启
- **CPU 优化（本版重点）**：实测常驻占用从 **3.28% 降到 1.67%（占单核，降 49%）**，
  占 16 核总量仅 **0.105%**。详见下方「CPU 优化记录」

### 10. CPU 优化记录（本版）
用「逐个组件消元 + 进程 CPU 时间精确计量」定位并修掉了三处真实浪费：

| 优化项 | 问题 | 修法 | 效果 |
| --- | --- | --- | --- |
| **枚举结果缓存** | HID 枚举 `get_devices()` 单次约 27 ms，同一秒内会被调用多次（设备轮询 + 句柄维护） | 加 0.8 秒 TTL 缓存；真正要打开句柄时才 `force=True` 绕过 | 每秒枚举次数压到 1 次 |
| **零成本存活检查**（最关键） | `dev.is_opened()` / `reader.is_active()` 看似廉价，实测**内部会走 SetupAPI，单次 0.7~3 ms**；每秒调用即占单核约 3% | 改为纯内存判断：帧心跳时间戳（回调每 200 帧 ≈ 1 秒推进一次）+ 打开宽限期；读取线程一停，心跳即停 | **每秒路径成本降到 < 1 微秒** |
| **回调热路径** | 187 帧/秒的回调里每帧都做 `is_bt_device()`（含 `.upper()` 字符串分配）与 `time.monotonic()` | 改为按报告 ID 分支；心跳时间戳每 200 帧才取一次 | 单帧 50 µs → 0.8 µs |
| **消除重复探测** | 看门狗与主循环**各自**每秒/每 5 秒做一次健康探测 | 统一由 `_poll_devices` 按 5 秒节流，主循环只做零成本检查 | 去掉一份重复开销 |

> 手柄蓝牙扩展报告为 **547 字节 × 185 帧/秒**（这是"游戏内实时监听 PS 键"的固有成本），
> 因此本项目不追求"零占用"，而是把**可控的软件开销**压到最低。

---

## 二、使用（打包版）

本目录已打包为**免 Python 环境**的可执行程序，日常使用只需双击：

1. 双击 **`Start-DS4-Battery-Overlay.bat`** —— 后台启动常驻程序
2. 双击 **`Open-Control-Panel.bat`** —— 图形界面管理（启停 / 自启 / 防过充 / 电池详情 / 预览）
3. 之后每次插入 / 连接 DS4 都会弹窗；游戏中**双击 PS 键**弹电量；**十字键下 + PS** 切换顶部横条
4. 无需手柄预览界面效果：
   ```
   ds4_battery_overlay.exe --preview 66        预览电量弹窗（66%）
   ds4_battery_overlay.exe --preview-bar 66    预览顶部电量横条
   ds4_battery_overlay.exe --version           查看版本
   ```

**目录结构**（v1.2.7 起精简为两个程序；**文件名已全部英文化**）：
```
ds4_battery_overlay.exe   常驻主程序（无窗口）  Resident overlay (no window)
ds4_overlay_data\         主程序运行库（不要删除）
ds4_panel.exe             可视化控制面板（自包含）  Control panel (self-contained)
ds4_panel_data\           面板运行库（不要删除）
Start-DS4-Battery-Overlay.bat   启动常驻程序 / start the resident program
Open-Control-Panel.bat          打开控制面板 / open the control panel
Enable-Autostart.bat            设置开机自启 / enable autostart
Disable-Autostart.bat           取消开机自启 / disable autostart
*.py                      源码（可选保留）
README.md                 本文档（中文 + English）
ds4_config.json           设置（防过充开关、阈值、语言；首次运行自动生成）
ds4_battery_info.json     电池详情与时长估算数据（运行时生成）
ds4_battery_state.json    电量记忆（运行时生成）
_lang.signal              语言变更通知（运行时生成）
*.log                     运行日志 / 崩溃日志（运行时生成）
```

> **v1.2.7 精简说明**：原 `ds4_manager.exe`（命令行管理，独占约 15 MB）已移除 ——
> 它的启动 / 停止 / 重启 / 状态功能已全部由控制面板覆盖。

---

## 三、退出程序

- 右键点击弹出的电量窗 → 立即退出；
- 或打开 **控制面板** 点「停止」；
- 或打开任务管理器结束 `ds4_battery_overlay.exe`。

---

## 四、常见问题

| 现象 | 说明 |
| --- | --- |
| 弹出窗口但显示 `--%` | 手柄被其它软件独占（Steam 大屏幕、DS4Windows 等）时读不到电量。关掉独占程序后重新插入即可。 |
| 游戏里双击 PS 键没反应 | ① 请用「窗口化 / 无边框全屏」，独占全屏下普通置顶窗口无法显示；② 被 Steam 等独占时读不到手柄，PS 键监听同样失效。 |
| 单击 PS 键没反应 | PS 键是**双击**触发（500ms 内连按两次），单击不弹窗是刻意设计，避免游戏误触。 |
| 电量只会显示 0/10/20…100% | DS4 电量以 **10% 为一档**上报（0–15 档），这是手柄自身精度。可在面板「电池详情」里看到原始档位。 |
| 插线后一直显示 90%（或 80%）不涨 | 已修复。根因：**插电档位 11 被误当成"满刻度假象"**，改显了"最近一次无线记忆电量"（如 90%），于是数字卡死、也永远等不到「已充满」。档位 11 实际就是「已充满」，现按 Linux hid-sony 的官方语义解析。 |
| 为什么"已充满"要等一会儿才显示 | 手柄按 **10% 一档**上报：0–9 档是充电进度（9 档=90–99%），到 10 档是"100% 仍在收尾充电"，到 **11 档**才报"已充满"。所以 90%→100% 之间有一段正常的收尾期。 |
| 「预计续航 / 预计充满」显示"估算中" | 正常现象：只有累计变化达到一档（≥10%）才可能算出可信速率。多用一个档位即可出数。 |
| 防过充没有自动断电 | 硬件限制：USB 充电为直连，软件无法切断充电电路。该功能仅**提醒拔线**。 |
| 改了 `ds4_config.json` 没生效 | 配置在常驻程序启动时读取，改完需重启程序（面板的防过充开关是即时写文件的）。 |
| 手柄插入后约 1 秒才弹窗 | 程序以 1 秒为周期轮询设备接入，属正常设计。 |
| 运行后没有任何反应 | 请确认是原装 DS4 或兼容 PID 的设备；其它型号（如 DualSense）不在支持范围。 |
| 蓝牙连接显示 `--%` | 程序会先读取校准数据激活完整报告模式。仍不行则检查是否被 Steam / DS4Windows 独占。 |
| 和其它屏幕共享 / 语音软件冲突 | 已修复（v1.1.1 起）：主线程不再做 HID 枚举，句柄被抢占会自动重开。 |
| 旧版的命令行管理入口 | 命令行管理程序（`ds4_manager.exe`）已在 v1.2.7 随包体精简移除，请改用 `Open-Control-Panel.bat`（功能相同且更直观）。 |
| 双击 `.bat` 出现两个控制面板窗口 | 已修复：面板新增**单实例保护**，重复双击只会把已有窗口置前，不会再开第二个。 |

---

## 五、技术说明

- **依赖**：`pywinusb`（纯 Python + Windows 系统 `hid.dll`，无需额外驱动）；界面为 tkinter
- **设备检测**：后台线程每 1 秒枚举 `VID=0x054C`、`PID=0x09CC/0x0BA0/0x05C4`；
  未连接时降频到 5 秒一次省 CPU；主线程只读缓存状态（避免被 HID 枚举阻塞）
- **读电量**：订阅输入报告（USB `0x01` 64 字节 / 蓝牙 `0x11` 547 字节扩展格式）。
  蓝牙需先读 FEATURE 报告 `0x02`（校准数据）激活完整报告模式
- **电量字节**：USB 在 **byte30**、蓝牙在 **byte32**（与 Linux hid-sony 一致）；
  低 4 位为档位、bit4 为线缆 / 充电状态。**档位语义取决于线缆位**：
  | 线缆位 | 档位 | 含义 |
  | --- | --- | --- |
  | 插电 | 0–9 | 充电进度 = 档×10%（0=0–9% … 9=90–99%） |
  | 插电 | 10 | 100%，仍在做收尾充电 |
  | 插电 | **11** | **已充满（100%）** |
  | 插电 | 14 | 电压/温度异常，暂停充电 → 不猜数字，显示 `--%` |
  | 插电 | 15 | 充电故障 → 不猜数字，显示 `--%` |
  | 未插电 | 0–9 | 档×10%（0=0–9% … 9=90–99%） |
  | 未插电 | 10+ | 100% |
- **充满判定**：插电档位 **11 就是「已充满」**（与 Linux hid-sony
  `dualshock4_parse_report()` 的官方注释一致），到 10 档则是"100% 仍在收尾充电"。
  早期版本曾把 11 档误判为"充电电压满刻度假象"而改显**最近一次无线记忆电量**（如 90%），
  这正是**电量冲到 90% 就再也不动**的根因 —— 现已改正。
  平台期判定（`_CHARGE_PLATEAU_SECONDS`，20 分钟 + 档位 ≥9）降级为极端异常时的兜底，
  不会再在正常充电的台阶之间误报「已充满」。
- **时长估算**：按历史样本（至少间隔 30 秒、且电量变化 ≥8%）线性估算速率；
  样本只保留最近 3 小时；数据不足时返回"估算中"
- **PS 键 / 十字键**：常驻手柄句柄，输入报告 bit0 为 PS 键；十字键 POV 低 4 位 = 4 表示「下」
- **进程识别**：只认进程名为 `ds4_battery_overlay(.exe)`，
  或进程名为 `python(w).exe` 且命令行以本程序脚本全文结尾（避免误判 / 误杀）
- **配置**：`ds4_config.json` → `{"overcharge_enabled": true, "overcharge_pct": 90}`

---

## 六、版本记录（要点）

| 版本 | 主要内容 |
| --- | --- |
| v1.0.x | 初版：接入弹窗、充电状态、低电量提醒、PS 双击、顶部横条、开机自启 |
| v1.1.0 | 新增可视化控制面板（免 Python 的 `ds4_panel.exe`） |
| v1.1.1 | 修复与屏幕共享 / 语音开黑软件共用的兼容性（假死、PS 键失效、触发风暴） |
| v1.2.0 | 性能与稳定性优化（日志零冗余、常驻工作线程、横条惰性创建、崩溃防护） |
| v1.2.1 | 修复顶部电量条绘制错乱（"灰条"）与 DPI 裁切 |
| v1.2.5 | 面板新增「电池详情」；响应提速（首轮 50ms / 横条 2 秒刷新） |
| v1.2.6 | 新增防过充；修复管理程序误报实例数量 |
| v1.2.7 | 新增时长估算；精简包体（移除命令行管理程序）；面板自包含 |
| v1.2.8 | 预计续航 / 预计充满 两个时间常显（插线时沿用上次无线速率）；放宽估算门槛；包体再瘦身 -6 MB |
| v1.2.9 | 去掉「预估电池真实容量」功能（不再显示任何 mAh 数字） |
| v1.2.10 | 修复「只能充到 90%」：插电档位 11 = 已充满（10 = 100% 收尾中），14/15 = 异常不猜数字；电量条填充按电池框内壁对齐；窗口/任务栏图标换为手柄；弹窗标记工具窗口不再进任务栏；补齐 `_ctypes` 使任务栏图标生效 |
| v1.3 | **控制面板新增语言切换（中文 / 英文），顶部电量横条、底部弹窗与面板全部文案同步切换（无需重启程序）；面板顶部标题跟随语言；面板新增单实例保护（重复双击不再开出第二个窗口）；删掉指向已移除管理程序的死入口；文件名全部英文化；README 增加英文介绍；<br>**CPU 优化：常驻占用 3.28% → 1.67%（占单核，降 49%）** —— HID 枚举加 TTL 缓存、存活检查改零成本帧心跳（`is_opened()` 内部走 SetupAPI 单次 0.7~3ms 是主因）、回调热路径精简、消除重复健康探测** |

| **v1.3.1** | **修复 v1.3 引入的两处回归**：① **PS 双击无法唤出电量窗** —— 回调重构时残留 `bi, _ = offs` 引用了已删除的变量，导致每次双击都抛 `NameError` 并中断处理；② **顶部横条会出现在任务栏** —— 横条 `deiconify()` 映射窗口后工具窗口样式丢失（实测 `exstyle` 从 `0x88` 掉到 `0x08`），现改为**每次显示都重打样式**。同时新增两套回归测试（`test_ps_handler.py` 11 项、`test_popup_taskbar.py` 10 项）防止再次复发 |

> 版本号说明：v1.3 为语言切换 + CPU 优化版；v1.3.1 为其回归修复版。

---

## 七、说明

- 本项目介绍页面与前述功能改造，由 **DeepSeek v4.1 Flash** 修改整理
- 项目最初由 **豆包（Doubao）AI** 创建
- 版本号统一由源码中的 `__version__` 派生（发布标签、资产名、安装目录名、文档同步更新）
