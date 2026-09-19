# webapp Browse 弹层：点 OK 没反应

## 症状

网页版 Browse 弹层里选好路径后点 `OK` 没有任何反应（弹层不关、字段不变）。

## 复现

窗口高度不足时必现。用 headless Edge（CDP）在 1200x520 的窗口下测到：

```text
viewport 1174x427
#picker          top 43  bottom 384
.picker-list     top 239 bottom 499   h 260
.picker-foot     top 507 bottom 542
#picker-ok       top 507 bottom 542   <- 已经掉到窗口外
elementFromPoint(OK 中心) = null      <- 真鼠标点不到
点 OK 后：dirAfterOk.open = true，字段值不变
```

## 根因

`webapp/static/styles.css` 的 `.picker-list { min-height: 260px; }`：
弹层高度是 `min(80vh, 100vh - 60px)`，列表的 260px 硬下限比弹层里能容纳的还高时，
flex 列装不下，整个内容从弹层底部溢出，把 `OK` / `Use this folder` / `Cancel` 那一行
推到弹层外面；窗口再矮一点就连窗口也出去了，鼠标点不到任何东西。

`confirmPicker()` 在拿不到可确认对象时直接 `return`，所以既没有写回也没有提示，
表现就是“点了没反应”。

## 修复

- `webapp/static/styles.css`
  - `.picker-list` 的 `min-height: 260px` 改成 `min-height: 0`：只有列表会伸缩，
    并自带滚动。
  - `.picker` 加 `overflow: hidden`：固定行再也不会被挤出弹层。
  - `.picker-head` / `.picker-crumbs` / `.picker-toolbar` / `.picker-foot` /
    `#picker-roots` / `#picker-places` / `.picker > .row` 明确 `flex: 0 0 auto`。
- `webapp/static/app.js`
  - `confirmPicker()` 没有可确认对象时不再静默返回，把原因写进 `#picker-selected`
    （`dir` 类：`Pick a drive or a folder to confirm.`；文件类：`Select a file`）。
- `docs/WEBAPP.md`：补上述两条行为说明。

## 证据（修复后，同一探针）

```text
viewport 1174x427
#picker          top 43  bottom 384
.picker-list     top 240 bottom 329   h 89    <- 收缩并滚动
.picker-foot     top 337 bottom 371            <- 回到弹层内
elementFromPoint(OK 中心) = BUTTON#picker-ok.primary[OK]
点 OK：dirAfterOk.open = false，值写成 fixture\sub
```

窗口较高时（viewport 1254x667）同样正常：`#picker` 67-600，列表 264-545，
`OK` 553-587（在弹层内），真点击写回成功。

回归：`docs/handoff/webapp-file-picker/assets/probe_picker_explorer.js`（`windowErrors` 为空、
高亮/面包屑/历史/键盘/`Use this folder`/`Show hidden`/`strip` 全部照旧）、
`probe_picker_flow.js`（全部 `*Ok`/`*Works` 仍为 true）、
`test_webapp.py` 62 项全过。

## 已知但未改（规格内）

文件类字段（`fasta` / `bed` / `db` / `index` 等）没有选中行时 `OK` 是置灰的，
点它不会有任何反应，这是 round 2 的 D15 决定（`#picker-selected` 会显示
`Select a file`）。若希望「文件类字段也能用地址栏里手输的路径确认」，那是另一轮
规格改动。
