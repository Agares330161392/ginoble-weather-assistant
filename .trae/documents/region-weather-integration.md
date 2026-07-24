# 地理分区天气整合计划

## Summary

点击地理分区按钮时，不仅筛选侧边栏省份列表，还要在地图上自动高亮该区域的所有省份，并显示该区域的天气概览汇总（平均气温、平均降水、趋势描述），无需逐个点击城市查看天气。

## Current State Analysis

### 当前行为
点击地理分区（如"华东"）后，`setupRegionSelector` 仅调用 `renderProvinceNav(region)` 筛选侧边栏城市列表，地图完全不受影响。用户仍需逐个点击城市才能查看天气详情。

### 现有数据链路（均已具备，无需改动后端）
1. **区域 → 省份**：`GEO_REGIONS` 常量（app.js 第53行），如"华东"→["上海","江苏","浙江","安徽","福建","江西","山东"]
2. **省份 → 天气数据**：`provinceWeatherMap`（app.js 第300行），`loadProvinceWeatherOverview()` 已并发加载34个省会的当日天气（温度、降水、风速、天气代码）
3. **省份 → SVG元素**：`mapSvgProvinceName(id)`（app.js 第558行），SVG path id 与省份名的双向映射
4. **着色机制**：`styleChinaSvgMap()`（app.js 第535行）遍历所有省份 path 按 `provinceWeatherMap` 数据着色
5. **已有高亮样式**：`.map-region-hover`（style.css 第671行），brightness/saturate/描边

### 关键代码位置
| 功能 | 文件 | 行号 |
|------|------|------|
| 区域选择器事件 | app.js | 1094-1103 `setupRegionSelector` |
| 省份导航渲染 | app.js | 272-298 `renderProvinceNav` |
| 地图着色 | app.js | 535-556 `styleChinaSvgMap` |
| 全国统计汇总 | app.js | 417-433 `updateMapSummary` |
| SVG省份名映射 | app.js | 558-568 `mapSvgProvinceName` |
| 地图工具栏HTML | index.html | 125-129 `map-toolbar` |
| 区域高亮CSS | style.css | 671-679 `.map-region-hover` |

## Implementation Status

| 变更 | 状态 | 说明 |
|------|------|------|
| 变更1 setupRegionSelector | ✅ 已完成 | app.js:1157-1158 已调用 highlightRegionOnMap + updateRegionSummary |
| 变更2 highlightRegionOnMap | ✅ 已完成 | app.js:596-612 已实现，styleChinaSvgMap:591 末尾调用保持高亮 |
| 变更3 updateRegionSummary | ✅ 已完成 | app.js:435-468 已实现区域天气聚合统计 |
| 变更4 CSS 区域高亮样式 | ❌ 待实现 | style.css 仅剩 .map-region-hover，缺 .map-region-active / .map-region-dimmed |
| 变更5 bindChinaSvgEvents 悬停 | ❌ 待实现 | app.js:626-647 mouseenter/mouseleave 未尊重 dimmed 状态 |
| 验证 | ❌ 待执行 | 启动服务测试区域高亮+天气概览 |

## Proposed Changes

### 变更1：app.js — setupRegionSelector 增加地图高亮调用（✅ 已完成）

**文件**：`static/js/app.js`
**位置**：第 1094-1103 行 `setupRegionSelector`
**改什么**：在点击分区后的回调中，`renderProvinceNav(region)` 之后，新增调用 `highlightRegionOnMap(region)` 和 `updateRegionSummary(region)`
**为什么**：让分区点击同时影响地图显示和区域天气概览，实现"点击即看整个区域天气"
**怎么改**：
```js
function setupRegionSelector() {
  document.querySelectorAll(".region-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".region-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const region = btn.dataset.region;
      renderProvinceNav(region);
      highlightRegionOnMap(region);    // 新增：地图区域高亮
      updateRegionSummary(region);     // 新增：区域天气概览
    });
  });
}
```

### 变更2：app.js — 新增 highlightRegionOnMap 函数（✅ 已完成）

**文件**：`static/js/app.js`
**位置**：在 `styleChinaSvgMap` 函数附近（约第535行后）
**改什么**：新增函数，遍历所有省份 SVG path，属于选中区域的省份添加高亮、非该区域省份降低透明度
**为什么**：视觉聚焦到选中区域，用户一眼看出哪些省份属于该区域、各自天气如何
**怎么改**：
```js
let _activeRegion = "all";

function highlightRegionOnMap(region) {
  _activeRegion = region || "all";
  const svg = document.querySelector(".china-svg-map");
  if (!svg) return;
  const regionProvinces = (region && region !== "all" && GEO_REGIONS[region])
    ? new Set(GEO_REGIONS[region]) : null;
  svg.querySelectorAll("path[id], circle[id]").forEach((el) => {
    const province = mapSvgProvinceName(el.id);
    el.classList.remove("map-region-active", "map-region-dimmed");
    if (!regionProvinces) return; // "全部"时不做特殊处理
    if (province && regionProvinces.has(province)) {
      el.classList.add("map-region-active");
    } else {
      el.classList.add("map-region-dimmed");
    }
  });
}
```
在 `styleChinaSvgMap` 函数末尾也调用 `highlightRegionOnMap(_activeRegion)`，确保重新着色后高亮状态不丢失。

### 变更3：app.js — 新增 updateRegionSummary 函数（✅ 已完成）

**文件**：`static/js/app.js`
**位置**：在 `updateMapSummary` 函数附近（约第417行后）
**改什么**：新增函数，聚合选中区域内省份的天气数据，计算平均气温/降水、趋势描述，更新地图工具栏显示
**为什么**：让用户点击分区后直接看到该区域整体天气概况，无需逐个城市点击
**怎么改**：
```js
function updateRegionSummary(region) {
  const statTemp = $("#mapStatTemp");
  const statRain = $("#mapStatRain");
  const statTrend = $("#mapStatTrend");
  if (!statTemp) return;

  if (!region || region === "all") {
    updateMapSummary(); // 恢复全国统计
    return;
  }

  const provinces = GEO_REGIONS[region] || [];
  const dataPoints = provinces
    .map((p) => provinceWeatherMap[p])
    .filter((d) => d && typeof d.temp === "number");

  if (dataPoints.length === 0) {
    statTemp.textContent = `${region}天气数据加载中…`;
    statRain.textContent = "";
    statTrend.textContent = "";
    return;
  }

  const avgTemp = dataPoints.reduce((s, d) => s + d.temp, 0) / dataPoints.length;
  const avgRain = dataPoints.reduce((s, d) => s + (d.rain || 0), 0) / dataPoints.length;
  const maxTemp = Math.max(...dataPoints.map((d) => d.temp));
  const minTemp = Math.min(...dataPoints.map((d) => d.temp));
  const hotProvince = dataPoints.find((d) => d.temp === maxTemp)?.province || "";
  const coldProvince = dataPoints.find((d) => d.temp === minTemp)?.province || "";

  statTemp.textContent = `${region}平均气温 ${avgTemp.toFixed(1)}°C`;
  statRain.textContent = `${region}平均降水 ${avgRain.toFixed(1)}mm`;
  statTrend.textContent = `最热：${hotProvince} ${maxTemp}°C · 最冷：${coldProvince} ${minTemp}°C`;
}
```

### 变更4：style.css — 新增区域高亮和淡化样式（❌ 待实现）

**文件**：`static/css/style.css`
**位置**：在 `.map-region-hover` 样式附近（约第671行后）
**改什么**：新增 `.map-region-active`（选中区域省份高亮）和 `.map-region-dimmed`（非选中区域省份淡化）样式
**为什么**：区分选中区域与未选区域，形成视觉聚焦
**怎么改**：
```css
.china-svg-map path.map-region-active,
.china-svg-map circle.map-region-active {
  filter: brightness(1.15) saturate(1.3) drop-shadow(0 0 6px rgba(255, 107, 53, 0.5));
  stroke: var(--accent);
  stroke-width: 2px !important;
  transition: filter 0.3s, opacity 0.3s;
}

.china-svg-map path.map-region-dimmed,
.china-svg-map circle.map-region-dimmed {
  opacity: 0.3;
  transition: opacity 0.3s;
}
```

### 变更5：app.js — bindChinaSvgEvents 悬停时尊重区域高亮状态（❌ 待实现）

**文件**：`static/js/app.js`
**位置**：第 570-600 行 `bindChinaSvgEvents`
**改什么**：悬停省份时，不要覆盖 `.map-region-active` 和 `.map-region-dimmed` 状态。mouseenter 时暂时移除 dimmed（让悬停的非区域省份也能看清），mouseleave 时恢复
**为什么**：避免悬停与区域高亮冲突导致样式混乱
**怎么改**：在现有的 mouseenter/mouseleave 回调中，增加对 dimmed 类的临时管理：
- mouseenter：如果元素有 `map-region-dimmed`，临时移除并记录
- mouseleave：如果之前是 dimmed，恢复

## Assumptions & Decisions

1. **使用省级天气数据（思路A）**：复用已有的 `provinceWeatherMap`（每省1个代表城市），不新增API请求。区域聚合基于省会城市数据，粒度足够满足"区域概览"需求。
2. **不做城市点叠加（不选思路B）**：区域内可能有50+城市，并发请求量大且需新增SVG城市点图层，复杂度过高。省级数据已能反映区域天气趋势。
3. **"全部"按钮恢复全国视图**：点击"全部"时清除所有区域高亮和淡化，恢复全国统一着色和全国统计。
4. **区域高亮与温度/降水切换兼容**：切换温度图/降水图时，通过在 `styleChinaSvgMap` 末尾调用 `highlightRegionOnMap(_activeRegion)` 保持高亮状态。
5. **区域概览显示位置**：复用现有 `map-toolbar` 的三个统计格子（`mapStatTemp`/`mapStatRain`/`mapStatTrend`），点击分区时替换为区域统计，点击"全部"时恢复全国统计。

## Verification Steps

1. 启动本地服务器，打开天气二级页
2. 等待地图加载完成（34个省份天气数据加载完毕）
3. 点击"华东"分区按钮，验证：
   - 侧边栏只显示华东7省的城市列表
   - 地图上华东7省高亮（橙色描边+亮度提升），其他省份淡化（opacity 0.3）
   - 地图工具栏显示"华东平均气温 X°C"、"华东平均降水 Ymm"、"最热：XX Z°C · 最冷：XX W°C"
4. 点击"全部"按钮，验证地图恢复全国统一着色、工具栏恢复全国统计
5. 在区域高亮状态下切换温度图/降水图，验证高亮状态保持
6. 悬停非选中区域的省份，验证能临时看清该省天气tooltip
7. 悬停选中区域的省份，验证高亮+tooltip正常显示
8. 移动端测试：确认区域高亮在小屏幕下正常显示
