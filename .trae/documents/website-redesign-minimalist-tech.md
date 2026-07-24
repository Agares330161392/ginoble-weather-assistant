# 网站改版方案 · 简约科技风首页 + 天气二级页

## 概述

基于站酷「简约科技风企业网站」的视觉分析结果，将基诺浦场景小助手从"侧栏+地图"单页布局改版为**菱形四模块首页 + 天气趋势二级页**架构。首页采用菱形布局展示四大功能入口，天气页改为七大地理分区筛选模式。

## 当前状态分析

### 现有架构
- 单页应用：左侧栏（品牌+搜索+常用城市+功能按钮+省份导航）+ 右侧主区（全国地图/城市详情）
- 四个功能入口（小红书/抖音/热榜/全国天气）全部挤在侧栏的按钮中
- 天气功能与内容分析功能混合在同一页面层级

### 现有文件
| 文件 | 行数 | 核心内容 |
|------|------|----------|
| `static/index.html` | 459行 | HTML结构：`.app` > `.sidebar` + `.main` + 3个modal |
| `static/css/style.css` | 2037行 | 完整样式，CSS变量`--accent:#e85d3a`已接近目标珊瑚橙 |
| `static/js/app.js` | 2784行 | init()入口 + 城市数据/地图/天气/AI/小红书/抖音/热榜/日历 |
| `server.py` | ~1130行 | 26个API路由，后端无需改动 |

### 设计风格参考（来自站酷分析报告）
- 色彩：60%白 + 30%黑灰 + 10%珊瑚橙(#FF6B35)
- 字体：大号几何无衬线粗体标题 + 系统无衬线正文
- 间距：8pt基础网格，60-70%留白
- 组件：圆角卡片(8-12px)、药丸按钮、微妙阴影(0 2px 8px rgba(0,0,0,0.08))
- 风格：简约科技风 / 扁平设计2.0

## 提议变更

### 变更1：index.html — 新增首页结构 + 重构天气页侧栏

**首页区（新增，放在 `.app` 之前）**：
```
div#homePage.home-page
├── header.home-hero (深色渐变背景)
│   ├── h1 (品牌大标题)
│   ├── p.home-subtitle (副标题)
│   └── div.home-accent-bar (珊瑚橙装饰条)
└── div.diamond-layout (菱形四模块容器)
    ├── div.diamond-item.diamond-top → 小红书内容抓取分析
    ├── div.diamond-item.diamond-right → 抖音内容抓取分析
    ├── div.diamond-item.diamond-bottom → 童装童鞋热榜
    └── div.diamond-item.diamond-left → 全国天气趋势
```

**天气页区（改造现有 `.app`）**：
- 给 `.app` 添加 `id="weatherPage"` 和 `class="hidden"`（默认隐藏）
- 在 `.sidebar-fixed` 中：
  - 删除 `#btnXhsAnalyze`、`#btnDyAnalyze`、`#btnDyHot` 三个按钮
  - 新增 `div.region-selector`（七大地理分区按钮组）
  - 新增 `button#btnBackHome`（返回首页按钮）
- `.main` 部分保持不变（地图/城市面板/AI分析）

**菱形布局方案**（CSS Grid实现）：
```
        [小红书]
[天气]            [抖音]
        [热榜]
```
使用 3×3 grid，四个模块分别放在上中、左中、右中、下中位置，四角留空形成菱形。

### 变更2：style.css — 首页样式 + 地理分区样式 + 风格对齐

**首页样式**：
- `.home-page`：全屏深色渐变背景（`linear-gradient(135deg, #1a1a1a, #2d2d2d)`）
- `.home-hero`：居中品牌区，大标题(2.5-3rem) + 副标题 + 珊瑚橙装饰条
- `.diamond-layout`：`display:grid; grid-template-columns:repeat(3,1fr); grid-template-rows:repeat(3,1fr); gap:1.5rem; max-width:800px; margin:0 auto;`
- `.diamond-item`：圆角卡片(12px)，白色半透明背景(`rgba(255,255,255,0.08)`)，悬停珊瑚橙边框+上浮效果
- 四个位置类：`.diamond-top`(grid-area:1/2)、`.diamond-left`(grid-area:2/1)、`.diamond-right`(grid-area:2/3)、`.diamond-bottom`(grid-area:3/2)

**地理分区样式**：
- `.region-selector`：7个按钮的垂直列表，每个按钮含分区名+省份数
- `.region-btn`：药丸形按钮，选中态珊瑚橙实心
- `.region-btn.active`：珊瑚橙背景+白字

**风格对齐调整**：
- CSS变量微调：`--accent: #FF6B35`（对齐站酷分析报告的珊瑚橙）
- 卡片阴影统一为：`0 2px 8px rgba(0,0,0,0.08)`
- 标题字重梯度：Display 800 / Heading 700 / Body 400

### 变更3：app.js — 页面导航 + 地区分区筛选

**页面导航逻辑**：
```js
function showHomePage() {
  $("#homePage").classList.remove("hidden");
  $("#weatherPage").classList.add("hidden");
}
function showWeatherPage() {
  $("#homePage").classList.add("hidden");
  $("#weatherPage").classList.remove("hidden");
}
```

**菱形模块点击事件**（在 `init()` 或独立 `setupHomePage()` 中绑定）：
- 小红书卡片 → `openXhsModal()`
- 抖音卡片 → `openDyModal()`
- 热榜卡片 → `openDyHotModal()` + `initHotModal()`
- 天气卡片 → `showWeatherPage()`
- `#btnBackHome` → `showHomePage()`

**七大地理分区筛选逻辑**：
```js
const GEO_REGIONS = {
  "华北": ["北京", "天津", "河北", "山西", "内蒙古"],
  "东北": ["辽宁", "吉林", "黑龙江"],
  "华东": ["上海", "江苏", "浙江", "安徽", "福建", "江西", "山东"],
  "华中": ["河南", "湖北", "湖南"],
  "华南": ["广东", "广西", "海南"],
  "西南": ["重庆", "四川", "贵州", "云南", "西藏"],
  "西北": ["陕西", "甘肃", "青海", "宁夏", "新疆"],
};
```
- 修改 `renderProvinceNav()` 增加 `filterRegion` 参数
- 点击分区按钮时过滤 `provinces` 数组，只显示该分区的省份
- "全部"按钮恢复显示所有省份
- 选中分区时同时高亮地图上对应区域（通过SVG省份元素class控制）

### 变更4：init() 调整

- 新增 `setupHomePage()` 调用（绑定菱形模块点击）
- 新增 `setupRegionSelector()` 调用（绑定分区按钮）
- 删除侧栏中已移除的按钮相关绑定（但保留modal打开函数供首页调用）
- `loadCities()` 完成后渲染地理分区按钮

## 涉及文件

| 文件 | 操作 | 改动量 |
|------|------|--------|
| `static/index.html` | 编辑 | 新增首页结构(~40行) + 侧栏改造(删3按钮+加分区+加返回按钮) |
| `static/css/style.css` | 编辑 | 新增首页样式(~120行) + 分区样式(~30行) + 变量微调(~5行) |
| `static/js/app.js` | 编辑 | 新增导航+分区逻辑(~80行) + 修改init+renderProvinceNav(~20行) |
| `server.py` | 不改动 | 后端API完全复用 |

## 假设与决策

1. **首页不设侧栏**：首页为全屏沉浸式入口，天气页才显示侧栏+地图
2. **modal复用**：小红书/抖音/热榜的modal结构完全保留，首页点击直接打开对应modal
3. **天气页侧栏**：保留搜索框和常用城市（天气场景需要），仅移除三个功能按钮、增加分区选择
4. **分区筛选范围**：仅影响侧栏省份导航列表的显示，不影响地图本身（地图始终显示全国）
5. **地图高亮**（可选增强）：选中分区时在地图上高亮对应省份（通过已有的SVG class控制）
6. **移动端适配**：菱形布局在窄屏下退化为2×2网格
7. **视觉风格**：对齐站酷分析报告的简约科技风——深色hero+大字标题+珊瑚橙强调+大量留白

## 验证步骤

1. 启动本地服务 `python server.py`
2. 打开浏览器访问首页，确认菱形四模块布局正确渲染
3. 点击"小红书内容抓取分析"卡片，确认弹窗正常打开
4. 点击"抖音内容抓取分析"卡片，确认弹窗正常打开
5. 点击"童装童鞋热榜"卡片，确认弹窗正常打开
6. 点击"全国天气趋势"卡片，确认切换到天气页
7. 在天气页侧栏确认：无小红书/抖音/热榜按钮，有七大分区选择器
8. 点击"华北"分区，确认省份导航仅显示北京/天津/河北/山西/内蒙古
9. 点击"全部"或取消选中，确认恢复全部省份
10. 点击"返回首页"按钮，确认回到首页
11. 在移动端宽度(375px)下确认菱形布局退化为2×2网格
12. 确认CSS风格对齐简约科技风：深色hero+珊瑚橙强调+大字标题
