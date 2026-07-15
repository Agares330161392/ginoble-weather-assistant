/**
 * 童鞋天气助手
 */
const WMO = {
  0: { label: "晴", icon: "☀️" },
  1: { label: "大部晴朗", icon: "🌤️" },
  2: { label: "局部多云", icon: "⛅" },
  3: { label: "阴", icon: "☁️" },
  45: { label: "雾", icon: "🌫️" },
  48: { label: "雾凇", icon: "🌫️" },
  51: { label: "毛毛雨", icon: "🌦️" },
  53: { label: "毛毛雨", icon: "🌦️" },
  55: { label: "毛毛雨", icon: "🌦️" },
  61: { label: "小雨", icon: "🌧️" },
  63: { label: "中雨", icon: "🌧️" },
  65: { label: "大雨", icon: "🌧️" },
  71: { label: "小雪", icon: "🌨️" },
  73: { label: "中雪", icon: "❄️" },
  75: { label: "大雪", icon: "❄️" },
  80: { label: "阵雨", icon: "🌦️" },
  81: { label: "阵雨", icon: "🌦️" },
  82: { label: "暴雨", icon: "⛈️" },
  95: { label: "雷暴", icon: "⛈️" },
};

const WEEK = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

const FAVORITES_KEY = "ginoble_favorite_cities";
const MAX_FAVORITES = 15;
const DEFAULT_FAVORITES = [
  { province: "浙江", name: "杭州", lat: 30.2741, lon: 120.1551 },
  { province: "浙江", name: "义乌", lat: 29.3068, lon: 120.0751 },
  { province: "上海", name: "上海", lat: 31.2304, lon: 121.4737 },
  { province: "广东", name: "广州", lat: 23.1291, lon: 113.2644 },
  { province: "广东", name: "深圳", lat: 22.5431, lon: 114.0579 },
  { province: "北京", name: "北京", lat: 39.9042, lon: 116.4074 },
];

let provinces = [];
let flatCities = [];
let favorites = [];
let currentCity = null;
let currentDays = 7;
let weatherCache = { 7: null, 16: null };
let provinceWeatherMap = {};
let chinaSvgLoaded = false;
let mapScale = 1;
let mapMode = "temp";

const $ = (sel) => document.querySelector(sel);

function cityKey(c) {
  return `${c.province}-${c.name}`;
}

function normalizeCity(c) {
  return {
    province: c.province,
    name: c.name,
    lat: c.lat,
    lon: c.lon,
    key: cityKey(c),
  };
}

function loadFavorites() {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY);
    if (raw) {
      const list = JSON.parse(raw);
      if (Array.isArray(list) && list.length) {
        favorites = list.map(normalizeCity);
        return;
      }
    }
  } catch (_) {
    /* ignore */
  }
  favorites = DEFAULT_FAVORITES.map(normalizeCity);
  saveFavorites();
}

function saveFavorites() {
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(favorites));
}

function isFavorite(city) {
  const k = cityKey(city);
  return favorites.some((f) => f.key === k);
}

function addFavorite(city) {
  const c = normalizeCity(city);
  if (isFavorite(c)) {
    showToast(`${c.name} 已在常用城市中`);
    return false;
  }
  if (favorites.length >= MAX_FAVORITES) {
    showToast(`最多添加 ${MAX_FAVORITES} 个常用城市，请先移除部分`);
    return false;
  }
  favorites.unshift(c);
  saveFavorites();
  renderFavorites();
  updateFavoriteButtons();
  showToast(`已添加 ${c.province} · ${c.name}`);
  return true;
}

function removeFavorite(key, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  favorites = favorites.filter((f) => f.key !== key);
  saveFavorites();
  renderFavorites();
  updateFavoriteButtons();
}

function renderFavorites() {
  const list = $("#favoriteList");
  const hint = $("#favoriteHint");
  if (!list) return;

  if (!favorites.length) {
    list.innerHTML = '<span class="favorites-empty">暂无常用，请搜索并添加</span>';
    hint?.classList.remove("hidden");
    return;
  }

  hint?.classList.add("hidden");
  list.innerHTML = favorites
    .map((c) => {
      const active =
        currentCity && currentCity.key === c.key;
      return `
        <span class="favorite-chip${active ? " active" : ""}" data-key="${c.key}"
          data-province="${c.province}" data-city="${c.name}" data-lat="${c.lat}" data-lon="${c.lon}">
          <span class="fav-name" title="${c.province} ${c.name}">${c.name}</span>
          <button type="button" class="fav-remove" aria-label="移除">×</button>
        </span>`;
    })
    .join("");

  list.querySelectorAll(".favorite-chip").forEach((chip) => {
    chip.addEventListener("click", (e) => {
      if (e.target.closest(".fav-remove")) return;
      selectCity({
        province: chip.dataset.province,
        name: chip.dataset.city,
        lat: parseFloat(chip.dataset.lat),
        lon: parseFloat(chip.dataset.lon),
      });
    });
    chip.querySelector(".fav-remove")?.addEventListener("click", (e) => {
      removeFavorite(chip.dataset.key, e);
    });
  });
}

function updateFavoriteButtons() {
  const btnAdd = $("#btnAddFavorite");
  const btnStar = $("#btnFavStar");

  if (currentCity) {
    const fav = isFavorite(currentCity);
    if (btnAdd) {
      btnAdd.disabled = fav;
      btnAdd.title = fav ? "已在常用城市中" : "将当前城市加入常用";
      btnAdd.textContent = fav ? "✓" : "＋";
    }
    if (btnStar) {
      btnStar.classList.remove("hidden");
      btnStar.classList.toggle("is-fav", fav);
      btnStar.textContent = fav ? "★ 已常用" : "☆ 常用";
    }
  } else {
    if (btnAdd) {
      btnAdd.disabled = true;
      btnAdd.textContent = "＋";
    }
    if (btnStar) btnStar.classList.add("hidden");
  }
}

function setupFavoriteControls() {
  $("#btnAddFavorite")?.addEventListener("click", () => {
    if (currentCity) addFavorite(currentCity);
  });
  $("#btnFavStar")?.addEventListener("click", () => {
    if (!currentCity) return;
    if (isFavorite(currentCity)) {
      removeFavorite(currentCity.key);
      showToast(`已移除 ${currentCity.name}`);
    } else {
      addFavorite(currentCity);
    }
  });
}

function bindCityFromElement(el) {
  return {
    province: el.dataset.province,
    name: el.dataset.city,
    lat: parseFloat(el.dataset.lat),
    lon: parseFloat(el.dataset.lon),
  };
}

function wmoInfo(code) {
  return WMO[code] || { label: "未知", icon: "🌡️" };
}

function formatDate(dateStr) {
  const d = new Date(dateStr + "T12:00:00");
  const m = d.getMonth() + 1;
  const day = d.getDate();
  return `${m}/${day}`;
}

function showToast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.add("hidden"), 3200);
}

function setLoading(show, text = "加载中…") {
  $("#loading").classList.toggle("hidden", !show);
  $("#loadingText").textContent = text;
}

async function loadCities() {
  const res = await fetch("/data/cities.json");
  const data = await res.json();
  provinces = data.provinces || [];
  flatCities = [];
  provinces.forEach((p) => {
    (p.cities || []).forEach((c) => {
      flatCities.push({
        province: p.name,
        name: c.name,
        lat: c.lat,
        lon: c.lon,
        key: `${p.name}-${c.name}`,
      });
    });
  });
  renderProvinceNav();
  renderFavorites();
  await loadProvinceWeatherOverview();
  renderChinaMap();
  const stats = $("#cityStats");
  if (stats) {
    stats.textContent = `已收录 ${flatCities.length} 个城市 · 常用 ${favorites.length} 个`;
  }
}

function renderProvinceNav() {
  const nav = $("#provinceNav");
  nav.innerHTML = provinces
    .map(
      (p) => `
    <div class="province-block">
      <p class="province-name">${p.name}</p>
      <div class="city-chips">
        ${(p.cities || [])
          .map(
            (c) =>
              `<button type="button" class="city-chip" data-province="${p.name}" data-city="${c.name}" data-lat="${c.lat}" data-lon="${c.lon}">${c.name}</button>`
          )
          .join("")}
      </div>
    </div>`
    )
    .join("");

  nav.querySelectorAll(".city-chip").forEach((btn) => {
    btn.addEventListener("click", () => selectCity(bindCityFromElement(btn)));
  });
}

async function loadProvinceWeatherOverview() {
  const targets = [
    { province: "北京", name: "北京", lat: 39.9042, lon: 116.4074 },
    { province: "天津", name: "天津", lat: 39.3434, lon: 117.3616 },
    { province: "上海", name: "上海", lat: 31.2304, lon: 121.4737 },
    { province: "重庆", name: "重庆", lat: 29.563, lon: 106.5516 },
    { province: "河北", name: "石家庄", lat: 38.0428, lon: 114.5149 },
    { province: "山西", name: "太原", lat: 37.8706, lon: 112.5489 },
    { province: "内蒙古", name: "呼和浩特", lat: 40.8414, lon: 111.7519 },
    { province: "辽宁", name: "沈阳", lat: 41.8057, lon: 123.4315 },
    { province: "吉林", name: "长春", lat: 43.8171, lon: 125.3235 },
    { province: "黑龙江", name: "哈尔滨", lat: 45.8038, lon: 126.535 },
    { province: "江苏", name: "南京", lat: 32.0603, lon: 118.7969 },
    { province: "浙江", name: "杭州", lat: 30.2741, lon: 120.1551 },
    { province: "安徽", name: "合肥", lat: 31.8206, lon: 117.2272 },
    { province: "福建", name: "福州", lat: 26.0745, lon: 119.2965 },
    { province: "江西", name: "南昌", lat: 28.6820, lon: 115.8582 },
    { province: "山东", name: "济南", lat: 36.6512, lon: 117.1201 },
    { province: "河南", name: "郑州", lat: 34.7466, lon: 113.6254 },
    { province: "湖北", name: "武汉", lat: 30.5928, lon: 114.3055 },
    { province: "湖南", name: "长沙", lat: 28.2282, lon: 112.9388 },
    { province: "广东", name: "广州", lat: 23.1291, lon: 113.2644 },
    { province: "广西", name: "南宁", lat: 22.8170, lon: 108.3669 },
    { province: "海南", name: "海口", lat: 20.0440, lon: 110.1999 },
    { province: "四川", name: "成都", lat: 30.5728, lon: 104.0668 },
    { province: "贵州", name: "贵阳", lat: 26.6470, lon: 106.6302 },
    { province: "云南", name: "昆明", lat: 25.0406, lon: 102.7123 },
    { province: "陕西", name: "西安", lat: 34.3416, lon: 108.9398 },
    { province: "甘肃", name: "兰州", lat: 36.0611, lon: 103.8343 },
    { province: "青海", name: "西宁", lat: 36.6171, lon: 101.7782 },
    { province: "宁夏", name: "银川", lat: 38.4872, lon: 106.2309 },
    { province: "新疆", name: "乌鲁木齐", lat: 43.8256, lon: 87.6168 },
    { province: "西藏", name: "拉萨", lat: 29.6520, lon: 91.1721 },
    { province: "台湾", name: "台北", lat: 25.0330, lon: 121.5654 },
  ];
  const results = await Promise.allSettled(targets.map(async (t) => {
    const res = await fetch(`/api/weather?lat=${t.lat}&lon=${t.lon}&days=1`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "天气加载失败");
    const daily = data.daily || {};
    const current = data.current || {};
    return {
      ...t,
      temp: Math.round(current.temperature_2m ?? daily.temperature_2m_max?.[0] ?? 0),
      rain: Number((daily.precipitation_sum?.[0] ?? 0).toFixed ? (daily.precipitation_sum?.[0] ?? 0).toFixed(1) : daily.precipitation_sum?.[0] ?? 0),
      wind: Math.round(current.wind_speed_10m ?? daily.wind_speed_10m_max?.[0] ?? 0),
      code: current.weather_code ?? daily.weather_code?.[0] ?? 0,
    };
  }));
  provinceWeatherMap = {};
  results.forEach((r) => {
    if (r.status === "fulfilled") provinceWeatherMap[r.value.province] = r.value;
  });
  renderChinaMap();
  updateMapSummary();
}

function updateActiveChip() {
  const k = currentCity ? cityKey(currentCity) : "";
  document.querySelectorAll(".city-chip").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.province + "-" + btn.dataset.city === k);
  });
  document.querySelectorAll(".favorite-chip").forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.key === k);
  });
  document.querySelectorAll(".province-tile").forEach((tile) => {
    tile.classList.toggle("active", tile.dataset.province === (currentCity?.province || ""));
  });
}

function tempColor(temp) {
  if (temp >= 30) return "#e4572e";
  if (temp >= 24) return "#f08a24";
  if (temp >= 18) return "#f6b93b";
  if (temp >= 10) return "#4aa3df";
  if (temp >= 0) return "#3466c2";
  return "#1f3b73";
}

function rainColor(rain) {
  if (rain >= 20) return "#3a86ff";
  if (rain >= 8) return "#4cc9f0";
  if (rain >= 1) return "#73c0ff";
  return "#8ecae6";
}

function blendColor(temp, rain) {
  const t = tempColor(temp);
  const r = rainColor(rain);
  return `linear-gradient(135deg, ${t}, ${r})`;
}

function trendLabel(item) {
  if (!item) return "暂无数据";
  if (item.rain >= 30) return "暴雨";
  if (item.rain >= 15) return "大雨";
  if (item.rain >= 5) return "中雨";
  if (item.rain > 0) return "小雨";
  if (item.temp >= 36) return "极端高温";
  if (item.temp >= 32) return "高温";
  if (item.temp >= 28) return "偏热";
  if (item.temp >= 22) return "舒适";
  if (item.temp >= 15) return "偏凉";
  if (item.temp >= 5) return "寒冷";
  return "严寒";
}


function renderLegend() {
  const el = $("#mapLegend");
  if (!el) return;
  const chips = mapMode === "temp"
    ? [["低温", "#081d58"], ["寒冷", "#253494"], ["偏凉", "#2c7fb8"], ["舒适", "#a1dab4"], ["偏暖", "#fee08b"], ["高温", "#d73027"]]
    : [["无雨", "#f4f8ff"], ["微量", "#dbeeff"], ["小雨", "#a8d4ff"], ["中雨", "#73bdf5"], ["大雨", "#2563eb"], ["暴雨", "#163a8a"]];
  el.innerHTML = chips.map(([label, color]) => `<span class="legend-chip"><span class="legend-dot" style="background:${color}"></span>${label}</span>`).join("");
}

function updateMapSummary() {
  const values = Object.values(provinceWeatherMap);
  if (!values.length) return;
  const avgTemp = values.reduce((a, b) => a + (b.temp || 0), 0) / values.length;
  const avgRain = values.reduce((a, b) => a + (b.rain || 0), 0) / values.length;
  const hotCount = values.filter((v) => v.temp >= 30).length;
  const rainCount = values.filter((v) => v.rain >= 1).length;
  const trend = hotCount > values.length / 3 ? "偏热" : rainCount > values.length / 3 ? "偏湿" : "总体平稳";
  const tempEl = $("#mapStatTemp");
  const rainEl = $("#mapStatRain");
  const trendEl = $("#mapStatTrend");
  if (tempEl) tempEl.textContent = `全国平均气温 ${avgTemp.toFixed(1)}°C`;
  if (rainEl) rainEl.textContent = `全国平均降水 ${avgRain.toFixed(1)}mm`;
  if (trendEl) trendEl.textContent = `整体趋势 ${trend}`;
  renderLegend();
  styleChinaSvgMap();
}

function renderChinaMap() {
  const el = $("#chinaMap");
  if (!el) return;
  el.innerHTML = `
    <div class="china-map-stage" style="transform: scale(${mapScale}); transform-origin: center center;">
      <svg viewBox="0 0 1000 738" class="china-svg-map" role="img" aria-label="中国省级天气地图">
        <g id="chinaSvgFeatures"></g>
        <g id="chinaSvgLabels"></g>
      </svg>
    </div>
  `;
  fetch("/static/cn.svg")
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.text();
    })
    .then((svg) => {
      const parser = new DOMParser();
      const doc = parser.parseFromString(svg, "image/svg+xml");
      const featureGroup = doc.querySelector("#features");
      const labelGroup = doc.querySelector("#label_points");
      const mountFeatures = $("#chinaSvgFeatures");
      const mountLabels = $("#chinaSvgLabels");
      if (mountFeatures && featureGroup) mountFeatures.innerHTML = featureGroup.innerHTML;
      if (mountLabels && labelGroup) mountLabels.innerHTML = labelGroup.innerHTML;
      styleChinaSvgMap();
      bindChinaSvgEvents();
      chinaSvgLoaded = true;
      updateMapSummary();
    })
    .catch((err) => {
      console.error("地图加载失败", err);
      el.innerHTML = '<div class="map-placeholder">中国地图加载失败，请检查 `static/cn.svg` 是否可访问</div>';
    });
}

function weatherFill(temp, rain) {
  return mapMode === "rain" ? rainScaleColor(rain) : tempScaleColor(temp);
}

function hexToRgb(hex) {
  const m = hex.replace("#", "").match(/.{1,2}/g)?.map((x) => parseInt(x, 16));
  return m ? { r: m[0], g: m[1], b: m[2] } : { r: 0, g: 0, b: 0 };
}

function rgbToHex(r, g, b) {
  return `#${[r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("")}`;
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function mixColor(a, b, t) {
  const c1 = hexToRgb(a);
  const c2 = hexToRgb(b);
  return rgbToHex(lerp(c1.r, c2.r, t), lerp(c1.g, c2.g, t), lerp(c1.b, c2.b, t));
}

function scaleColor(value, stops) {
  const clamped = Math.max(stops[0].v, Math.min(stops[stops.length - 1].v, value));
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i];
    const b = stops[i + 1];
    if (clamped >= a.v && clamped <= b.v) {
      const t = (clamped - a.v) / (b.v - a.v || 1);
      return mixColor(a.c, b.c, t);
    }
  }
  return stops[stops.length - 1].c;
}

function tempScaleColor(temp) {
  return scaleColor(temp, [
    { v: -20, c: "#081d58" },
    { v: -10, c: "#253494" },
    { v: 0, c: "#2c7fb8" },
    { v: 8, c: "#41b6c4" },
    { v: 15, c: "#a1dab4" },
    { v: 22, c: "#fff7bc" },
    { v: 28, c: "#fee08b" },
    { v: 32, c: "#fdae61" },
    { v: 36, c: "#f46d43" },
    { v: 40, c: "#d73027" },
  ]);
}

function rainScaleColor(rain) {
  return scaleColor(rain, [
    { v: 0, c: "#f4f8ff" },
    { v: 0.1, c: "#e7f1ff" },
    { v: 1, c: "#cfe6ff" },
    { v: 5, c: "#a8d4ff" },
    { v: 15, c: "#73bdf5" },
    { v: 30, c: "#3f95e6" },
    { v: 60, c: "#2563eb" },
    { v: 100, c: "#163a8a" },
  ]);
}

function styleChinaSvgMap() {
  const svg = $(".china-svg-map");
  if (!svg) return;
  const isTemp = mapMode === "temp";
  const baseStroke = isTemp ? "rgba(255,255,255,0.98)" : "rgba(255,255,255,0.96)";
  const glow = isTemp ? "drop-shadow(0 0 18px rgba(255,255,255,0.45))" : "drop-shadow(0 0 18px rgba(59,130,246,0.38))";
  svg.querySelectorAll("path[id], circle[id]").forEach((el) => {
    el.style.cursor = "pointer";
    el.style.transition = "fill 0.2s ease, opacity 0.2s ease, filter 0.2s ease, stroke 0.2s ease, stroke-width 0.2s ease";
    const province = mapSvgProvinceName(el.id);
    const data = province ? provinceWeatherMap[province] : null;
    const temp = data?.temp ?? 18;
    const rain = data?.rain ?? 0;
    const fill = isTemp ? tempScaleColor(temp) : rainScaleColor(rain);
    el.setAttribute("fill", fill);
    el.setAttribute("stroke", baseStroke);
    el.setAttribute("stroke-width", data ? 1.45 : 0.7);
    el.setAttribute("stroke-linejoin", "round");
    el.setAttribute("stroke-linecap", "round");
    el.style.filter = glow;
  });
}

function mapSvgProvinceName(id) {
  const map = {
    CNBJ: "北京", CNTJ: "天津", CNSH: "上海", CNCQ: "重庆", CNHE: "河北", CNSX: "山西",
    CNNM: "内蒙古", CNLN: "辽宁", CNJL: "吉林", CNHL: "黑龙江", CNJS: "江苏", CNZJ: "浙江",
    CNAH: "安徽", CNFJ: "福建", CNJX: "江西", CNSD: "山东", CNHA: "河南", CNHB: "湖北",
    CNHN: "湖南", CNGD: "广东", CNGX: "广西", CNHI: "海南", CNSC: "四川", CNGZ: "贵州",
    CNYN: "云南", CNSN: "陕西", CNGS: "甘肃", CNQH: "青海", CNNX: "宁夏", CNXJ: "新疆",
    CNXZ: "西藏", CNTW: "台湾", CNHK: "香港", CNMO: "澳门",
  };
  return map[id] || null;
}

function bindChinaSvgEvents() {
  const svg = $(".china-svg-map");
  if (!svg) return;

  const bindTarget = (el, province) => {
    if (!province) return;
    el.style.pointerEvents = "all";
    el.style.cursor = "pointer";
    el.addEventListener("mouseenter", (e) => {
      el.classList.add("map-region-hover");
      showSvgTooltip(e, province);
    });
    el.addEventListener("mousemove", (e) => showSvgTooltip(e, province));
    el.addEventListener("mouseleave", () => {
      el.classList.remove("map-region-hover");
      hideMapTooltip();
    });
    el.addEventListener("click", async () => {
      const first = flatCities.find((c) => c.province === province);
      if (first) await selectCity(first);
    });
  };

  svg.querySelectorAll("path[id], circle[id]").forEach((el) => bindTarget(el, mapSvgProvinceName(el.id)));
  svg.querySelectorAll("circle[class]").forEach((el) => {
    const cls = el.getAttribute("class") || "";
    const province = cls.includes("Tibet") ? "西藏" : cls.includes("Taiwan") ? "台湾" : null;
    if (!province) return;
    bindTarget(el, province);
  });
}

function setMapScale(next) {
  mapScale = Math.min(3, Math.max(0.8, Number(next.toFixed(2))));
  const stage = document.querySelector(".china-map-stage");
  if (stage) stage.style.transform = `scale(${mapScale})`;
}

function setMapMode(mode) {
  mapMode = mode === "rain" ? "rain" : "temp";
  $("#btnTempMode")?.classList.toggle("active", mapMode === "temp");
  $("#btnRainMode")?.classList.toggle("active", mapMode === "rain");
  document.querySelector(".china-map-frame")?.classList.toggle("mode-rain", mapMode === "rain");
  document.querySelector(".china-map-frame")?.classList.toggle("mode-temp", mapMode === "temp");
  renderLegend();
  styleChinaSvgMap();
}

function showSvgTooltip(e, province) {
  const data = provinceWeatherMap[province];
  const tooltip = $("#mapTooltip");
  if (!tooltip || !data) return;
  const metric = mapMode === "rain" ? `${data.rain}mm` : `${data.temp}°C`;
  const metricLabel = mapMode === "rain" ? "降水" : "气温";
  const trend = trendLabel(data);
  tooltip.innerHTML = `<strong>${province}</strong>${metricLabel}：${metric}<br/>风速：${data.wind}km/h<br/>等级：${trend}<br/>天气：${wmoInfo(data.code).label}`;
  tooltip.classList.remove("hidden");
  moveSvgTooltip(e);
}

function moveSvgTooltip(e) {
  const tooltip = $("#mapTooltip");
  if (!tooltip || tooltip.classList.contains("hidden")) return;
  const shell = document.querySelector(".china-map-shell");
  const x = Math.min((e?.offsetX || 0) + 18, shell.clientWidth - 260);
  const y = Math.max(16, (e?.offsetY || 0) + 16);
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;
}

function showMapTooltip(e, tile) {
  const province = tile.dataset.province;
  const data = provinceWeatherMap[province];
  const tooltip = $("#mapTooltip");
  if (!tooltip || !data) return;
  tooltip.innerHTML = `
    <strong>${province}</strong>
    气温：${data.temp}°C<br/>
    降水：${data.rain}mm<br/>
    风速：${data.wind}km/h<br/>
    趋势：${trendLabel(data)}<br/>
    天气：${wmoInfo(data.code).label}
  `;
  tooltip.classList.remove("hidden");
  moveMapTooltip(e);
}

function moveMapTooltip(e) {
  const tooltip = $("#mapTooltip");
  if (!tooltip || tooltip.classList.contains("hidden")) return;
  const x = Math.min(e.offsetX + 18, document.querySelector(".china-map-shell").clientWidth - 260);
  const y = Math.max(16, e.offsetY + 16);
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;
}

function hideMapTooltip() {
  $("#mapTooltip")?.classList.add("hidden");
}

function setupSearch() {
  const input = $("#citySearch");
  const results = $("#searchResults");

  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    if (!q) {
      results.classList.add("hidden");
      return;
    }
    const matches = flatCities
      .filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.province.toLowerCase().includes(q)
      )
      .slice(0, 12);

    if (!matches.length) {
      results.innerHTML = '<li class="sub">未找到城市</li>';
    } else {
      results.innerHTML = matches
        .map((c) => {
          const fav = isFavorite(c);
          return `
            <li data-province="${c.province}" data-city="${c.name}" data-lat="${c.lat}" data-lon="${c.lon}">
              <span class="result-main">${c.name}<span class="sub"> · ${c.province}</span></span>
              <button type="button" class="btn-add-fav${fav ? " is-fav" : ""}" data-action="fav">${fav ? "已添加" : "＋常用"}</button>
            </li>`;
        })
        .join("");
    }
    results.classList.remove("hidden");

    results.querySelectorAll("li[data-city]").forEach((li) => {
      li.addEventListener("click", (e) => {
        if (e.target.closest(".btn-add-fav")) return;
        selectCity(bindCityFromElement(li));
        input.value = "";
        results.classList.add("hidden");
      });
      li.querySelector(".btn-add-fav")?.addEventListener("click", (e) => {
        e.stopPropagation();
        const city = bindCityFromElement(li);
        if (!isFavorite(city)) {
          addFavorite(city);
          e.target.classList.add("is-fav");
          e.target.textContent = "已添加";
        }
      });
    });
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-box")) {
      results.classList.add("hidden");
    }
  });
}

async function selectCity(city) {
  currentCity = normalizeCity(city);
  weatherCache = { 7: null, 16: null };
  updateActiveChip();
  updateFavoriteButtons();

  $("#mapSection").classList.add("hidden");
  $("#btnNationalWeather").classList.remove("hidden");
  $("#hero").classList.add("hidden");
  $("#cityPanel").classList.remove("hidden");
  $("#provinceLabel").textContent = city.province;
  $("#cityTitle").textContent = city.name;
  $("#aiBody").innerHTML =
    '<p class="ai-placeholder">点击「生成基诺浦营销方案」</p>';

  await loadWeather(currentDays);
}

async function loadWeather(days) {
  if (!currentCity) return;
  currentDays = days;

  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", parseInt(t.dataset.days, 10) === days);
  });

  if (weatherCache[days]) {
    renderWeather(weatherCache[days], days);
    return;
  }

  setLoading(true, `正在获取${currentCity.name}未来${days}天预报…`);
  try {
    const url = `/api/weather?lat=${currentCity.lat}&lon=${currentCity.lon}&days=${days}`;
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "天气加载失败");
    weatherCache[days] = data;
    renderWeather(data, days);
  } catch (err) {
    showToast(err.message);
  } finally {
    setLoading(false);
  }
}

function renderWeather(data, days) {
  const current = data.current || {};
  const code = current.weather_code ?? 0;
  const info = wmoInfo(code);
  $("#currentWeather").innerHTML = `
    <span class="icon">${info.icon}</span>
    <div>
      <div class="temp">${Math.round(current.temperature_2m ?? 0)}°C</div>
      <div class="meta">${info.label} · 湿度 ${current.relative_humidity_2m ?? "—"}% · 风速 ${current.wind_speed_10m ?? "—"} km/h</div>
    </div>`;

  const daily = data.daily || {};
  const times = daily.time || [];
  const grid = $("#forecastGrid");
  grid.classList.toggle("compact", days > 7);

  grid.innerHTML = times
    .map((t, i) => {
      const d = new Date(t + "T12:00:00");
      const w = wmoInfo(daily.weather_code?.[i] ?? 0);
      const max = daily.temperature_2m_max?.[i];
      const min = daily.temperature_2m_min?.[i];
      const precip = daily.precipitation_sum?.[i];
      const prob = daily.precipitation_probability_max?.[i];
      let precipHtml = "";
      if (precip > 0 || (prob && prob > 30)) {
        precipHtml = `<div class="precip">💧 ${precip ?? 0}mm ${prob ? `(${prob}%)` : ""}</div>`;
      }
      return `
        <article class="day-card">
          <div class="date">${formatDate(t)}</div>
          <div class="weekday">${WEEK[d.getDay()]}</div>
          <div class="weather-icon">${w.icon}</div>
          <div class="label" style="font-size:0.75rem;color:var(--text-muted)">${w.label}</div>
          <div class="temps">${Math.round(max)}° <span class="min">/ ${Math.round(min)}°</span></div>
          ${precipHtml}
        </article>`;
    })
    .join("");
}

async function runAnalysis() {
  if (!currentCity) return;
  if (!weatherCache[16]) {
    setLoading(true, "正在拉取完整预报供 AI 分析…");
    try {
      const res = await fetch(
        `/api/weather?lat=${currentCity.lat}&lon=${currentCity.lon}&days=16`
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "天气加载失败");
      weatherCache[16] = data;
    } catch (err) {
      showToast(err.message);
      setLoading(false);
      return;
    }
    setLoading(false);
  }

  const btn = $("#btnAnalyze");
  btn.disabled = true;
  $("#aiDeepActions").classList.add("hidden");
  $("#aiDeepBody").classList.add("hidden");
  $("#aiBody").innerHTML = '<div class="ai-loading"><div class="spinner"></div>通义千问正在生成基诺浦基础分析…</div>';

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        city: currentCity.name,
        province: currentCity.province,
        weather: weatherCache[16],
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || data.detail || "分析失败");

    const html = formatBaseAnalysis(data.analysis);
    $("#aiBody").innerHTML = html;
    $("#aiDeepActions").classList.remove("hidden");
    $("#btnDeepAnalyze").onclick = () => runDeepAnalysis(data.deep_prompt || "");
    showToast("基础策略已生成");
  } catch (err) {
    $("#aiBody").innerHTML = `<p class="ai-placeholder" style="color:#c44a2e">分析失败：${escapeHtml(err.message)}</p>`;
    showToast(err.message);
  } finally {
    btn.disabled = false;
  }
}

async function runDeepAnalysis() {
  if (!currentCity) return;
  const btn = $("#btnDeepAnalyze");
  btn.disabled = true;
  $("#aiDeepBody").classList.remove("hidden");
  $("#aiDeepBody").innerHTML = '<div class="ai-loading"><div class="spinner"></div>正在生成深度分析…</div>';

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        city: currentCity.name,
        province: currentCity.province,
        weather: weatherCache[16],
        deep: true,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || data.detail || "深度分析失败");

    $("#aiDeepBody").innerHTML = formatDeepAnalysis(data.analysis);
    showToast("深度分析已生成");
  } catch (err) {
    $("#aiDeepBody").innerHTML = `<p class="ai-placeholder" style="color:#c44a2e">深度分析失败：${escapeHtml(err.message)}</p>`;
    showToast(err.message);
  } finally {
    btn.disabled = false;
  }
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function formatBaseAnalysis(text) {
  return formatAnalysisBlocks(text);
}

function formatDeepAnalysis(text) {
  return formatAnalysisBlocks(text);
}

function formatAnalysisBlocks(text) {
  const lines = text.split("\n").filter((l) => l.trim());
  let html = '<div class="ai-report">';
  let inList = false;
  let inSection = false;

  const closeList = () => {
    if (inList) {
      html += "</ul>";
      inList = false;
    }
  };

  const closeSection = () => {
    if (inSection) {
      closeList();
      html += "</section>";
      inSection = false;
    }
  };

  lines.forEach((line) => {
    const t = line.trim();
    const isHeading = /^【.+】$/.test(t) || /^###\s+/.test(t) || /^##\s+/.test(t) || /^一、|^二、|^三、|^四、|^五、/.test(t);

    if (isHeading) {
      closeSection();
      const title = t.replace(/^###\s+|^##\s+/, "");
      html += `<section class="ai-block"><h3>${escapeHtml(title)}</h3>`;
      inSection = true;
      return;
    }

    if (/^[\d]+[.、)]/.test(t) || /^[-*•]/.test(t)) {
      if (!inList) {
        html += '<ul class="ai-list">';
        inList = true;
      }
      html += `<li>${escapeHtml(t.replace(/^[\d]+[.、)]\s*|^[-*•]\s*/, ""))}</li>`;
    } else if (t.startsWith("说明：") || t.startsWith("备注：") || t.startsWith("注意：")) {
      closeList();
      html += `<p class="ai-note">${escapeHtml(t)}</p>`;
    } else {
      closeList();
      html += `<p>${escapeHtml(t)}</p>`;
    }
  });
  closeSection();
  html += "</div>";
  return html || `<p>${escapeHtml(text)}</p>`;
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      loadWeather(parseInt(tab.dataset.days, 10));
    });
  });
}

async function init() {
  loadFavorites();
  setupSearch();
  setupTabs();
  setupFavoriteControls();
  setupXhsAnalyze();
  $("#btnAnalyze").addEventListener("click", runAnalysis);
  $("#btnDeepAnalyze").addEventListener("click", runDeepAnalysis);
  $("#btnTempMode").addEventListener("click", () => setMapMode("temp"));
  $("#btnRainMode").addEventListener("click", () => setMapMode("rain"));
  $("#btnNationalWeather").addEventListener("click", () => {
    $("#mapSection").classList.remove("hidden");
    $("#btnNationalWeather").classList.add("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  $("#btnMapZoomIn").addEventListener("click", () => setMapScale(mapScale + 0.2));
  $("#btnMapZoomOut").addEventListener("click", () => setMapScale(mapScale - 0.2));
  $("#btnTempMode")?.addEventListener("click", () => setMapMode("temp"));
  $("#btnRainMode")?.addEventListener("click", () => setMapMode("rain"));

  try {
    await loadCities();
    const health = await fetch("/api/health").then((r) => r.json());
    if (!health.has_api_key) {
      showToast("未检测到千问 API Key，AI 分析将不可用");
    }
    if (!health.has_xhs_api_key) {
      showToast("未检测到小红书 API Key（XHS_API_KEY），小红书分析暂不可用");
    }
    if (health.brand_loaded === false) {
      showToast("未找到品牌资料文件，AI 将使用内置基诺浦知识库");
    }
  } catch (e) {
    showToast("初始化失败，请确认已启动本地服务");
  }
}

/* —— 小红书内容抓取分析 —— */
const XHS_TYPE_LABELS = {
  category_scene: "品类场景洞察",
  competitor_sentiment: "竞品舆情深挖",
  competitor_seeding: "竞品种草对比",
};
const XHS_TYPE_KEYS = {
  品类场景洞察: "category_scene",
  竞品舆情深挖: "competitor_sentiment",
  竞品种草对比: "competitor_seeding",
};
const XHS_NATIONAL = "__national__";

let xhsPresets = [];
let xhsLastSelection = null;
let xhsReportMd = "";
let xhsReportMeta = null;
let xhsReportFilename = "小红书分析报告.md";
let xhsJobId = null;
let xhsJobTimer = null;
let xhsAnalyzing = false;

function analysisTypeToDisplay(value) {
  if (!value) return "品类场景洞察";
  return XHS_TYPE_LABELS[value] || value;
}

function analysisTypeToStore(display) {
  const t = (display || "").trim();
  return XHS_TYPE_KEYS[t] || t || "品类场景洞察";
}

function parseWeatherCityValue(value) {
  if (!value || value === XHS_NATIONAL) {
    return { weather_city: "全国", weather_province: "", lat: null, lon: null, isNational: true };
  }
  const [province, name, lat, lon] = value.split("|");
  return {
    weather_city: name || "全国",
    weather_province: province || "",
    lat: lat ? Number(lat) : null,
    lon: lon ? Number(lon) : null,
    isNational: false,
  };
}

function weatherCityOptionValue(city) {
  return `${city.province}|${city.name}|${city.lat}|${city.lon}`;
}

function populateXhsWeatherCityOptions(selected) {
  const sel = $("#xhsWeatherCity");
  if (!sel) return;
  const parts = ['<option value="__national__">全国</option>'];
  if (favorites.length) {
    parts.push('<optgroup label="常用城市">');
    favorites.forEach((c) => {
      parts.push(`<option value="${escapeHtml(weatherCityOptionValue(c))}">${escapeHtml(c.province)} · ${escapeHtml(c.name)}</option>`);
    });
    parts.push("</optgroup>");
  }
  const byProvince = {};
  flatCities.forEach((c) => {
    if (!byProvince[c.province]) byProvince[c.province] = [];
    byProvince[c.province].push(c);
  });
  Object.keys(byProvince)
    .sort()
    .forEach((province) => {
      parts.push(`<optgroup label="${escapeHtml(province)}">`);
      byProvince[province].forEach((c) => {
        parts.push(`<option value="${escapeHtml(weatherCityOptionValue(c))}">${escapeHtml(c.name)}</option>`);
      });
      parts.push("</optgroup>");
    });
  sel.innerHTML = parts.join("");

  // 恢复选中：优先已存；勾选天气时默认全国
  let target = XHS_NATIONAL;
  if (selected?.weather_city && selected.weather_city !== "全国") {
    const hit = flatCities.find(
      (c) => c.name === selected.weather_city && (!selected.weather_province || c.province === selected.weather_province)
    );
    if (hit) target = weatherCityOptionValue(hit);
  }
  sel.value = target;
  if (sel.value !== target) sel.value = XHS_NATIONAL;
}

function syncXhsWeatherCityVisibility(forceNational = false) {
  const on = $("#xhsUseWeather").checked;
  $("#xhsWeatherCityWrap").classList.toggle("hidden", !on);
  if (!on) return;
  const current = parseWeatherCityValue($("#xhsWeatherCity").value || XHS_NATIONAL);
  populateXhsWeatherCityOptions(
    forceNational
      ? { weather_city: "全国", weather_province: "" }
      : { weather_city: current.weather_city, weather_province: current.weather_province }
  );
}

function buildNationalWeatherSummary() {
  const values = Object.values(provinceWeatherMap || {});
  if (!values.length) {
    return "范围：全国（省级概览暂未加载，请稍后再试或先打开全国天气图）";
  }
  let tempSum = 0;
  let rainSum = 0;
  let n = 0;
  const ranked = [];
  values.forEach((v) => {
    const t = Number(v.temp);
    const r = Number(v.rain);
    if (!Number.isFinite(t)) return;
    n += 1;
    tempSum += t;
    rainSum += Number.isFinite(r) ? r : 0;
    ranked.push({ province: v.province, t, r: Number.isFinite(r) ? r : 0 });
  });
  if (!n) return "范围：全国（暂无有效气温数据）";
  const hot = [...ranked].sort((a, b) => b.t - a.t);
  const cold = [...ranked].sort((a, b) => a.t - b.t);
  const rainy = [...ranked].sort((a, b) => b.r - a.r);
  return [
    "范围：全国（基于各省代表城市当日概览）",
    `全国平均气温：${(tempSum / n).toFixed(1)}℃`,
    `全国平均降水：${(rainSum / n).toFixed(1)}mm`,
    `偏热省份示例：${hot.slice(0, 5).map((x) => `${x.province}${x.t}℃`).join("、")}`,
    `偏冷省份示例：${cold.slice(0, 5).map((x) => `${x.province}${x.t}℃`).join("、")}`,
    `降水偏多示例：${rainy.slice(0, 5).map((x) => `${x.province}${x.r}mm`).join("、")}`,
  ].join("\n");
}

function getXhsFormValues() {
  const fetchCount = Math.max(1, Math.min(50, parseInt($("#xhsFetchCount").value, 10) || 20));
  const weather = parseWeatherCityValue($("#xhsWeatherCity")?.value || XHS_NATIONAL);
  return {
    preset_id: $("#xhsPresetSelect").value || "",
    analysis_type: analysisTypeToStore($("#xhsAnalysisType").value),
    keyword: ($("#xhsKeyword").value || "").trim(),
    sort_type: $("#xhsSortType").value,
    note_time: $("#xhsNoteTime").value,
    fetch_count: fetchCount,
    fetch_comments: $("#xhsFetchComments").checked,
    use_weather: $("#xhsUseWeather").checked,
    weather_city: weather.weather_city,
    weather_province: weather.weather_province,
    extra_prompt: ($("#xhsExtraPrompt").value || "").trim(),
  };
}

function fillXhsForm(data) {
  if (!data) return;
  if (data.preset_id) $("#xhsPresetSelect").value = data.preset_id;
  $("#xhsAnalysisType").value = analysisTypeToDisplay(data.analysis_type);
  if (data.keyword != null) $("#xhsKeyword").value = data.keyword;
  if (data.sort_type) $("#xhsSortType").value = data.sort_type;
  if (data.note_time) $("#xhsNoteTime").value = data.note_time;
  if (data.fetch_count != null) $("#xhsFetchCount").value = data.fetch_count;
  $("#xhsFetchComments").checked = !!data.fetch_comments;
  $("#xhsUseWeather").checked = !!data.use_weather;
  if (data.extra_prompt != null) $("#xhsExtraPrompt").value = data.extra_prompt;
  syncXhsWeatherCityVisibility(false);
  if (data.use_weather) {
    populateXhsWeatherCityOptions(data);
  }
}

function renderXhsPresetOptions(selectedId) {
  const sel = $("#xhsPresetSelect");
  sel.innerHTML = xhsPresets
    .map((p) => {
      const tag = p.system ? "系统" : "自定义";
      return `<option value="${escapeHtml(p.id)}">[${tag}] ${escapeHtml(p.name)}</option>`;
    })
    .join("");
  if (selectedId && xhsPresets.some((p) => p.id === selectedId)) {
    sel.value = selectedId;
  }
}

async function loadXhsPresets() {
  const res = await fetch("/api/xhs/presets");
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "加载预设失败");
  xhsPresets = data.presets || [];
  xhsLastSelection = data.last_selection || null;
  const selected = xhsLastSelection?.preset_id || xhsPresets[0]?.id;
  renderXhsPresetOptions(selected);
  fillXhsForm(xhsLastSelection || xhsPresets[0]);
}

function currentXhsPreset() {
  const id = $("#xhsPresetSelect").value;
  return xhsPresets.find((p) => p.id === id) || null;
}

function applySelectedPreset() {
  const p = currentXhsPreset();
  if (!p) return;
  fillXhsForm({ ...p, preset_id: p.id });
}

function openXhsModal() {
  $("#xhsModal").classList.remove("hidden");
  switchXhsPane("report");
  if (xhsAnalyzing) {
    setXhsProgress(Number($("#xhsProgressPct")?.textContent) || 5, "分析仍在后台进行中…", true);
    $("#btnXhsRun").disabled = true;
  }
  loadXhsPresets().catch((err) => showToast(err.message));
}

function closeXhsModal() {
  $("#xhsModal").classList.add("hidden");
}

function switchXhsPane(pane) {
  const isHistory = pane === "history";
  $("#btnXhsTabReport").classList.toggle("active", !isHistory);
  $("#btnXhsTabHistory").classList.toggle("active", isHistory);
  $("#xhsResultBody").classList.toggle("hidden", isHistory);
  $("#xhsHistoryBody").classList.toggle("hidden", !isHistory);
  if (isHistory) {
    loadXhsHistory().catch((err) => showToast(err.message));
  }
}

function inlineMarkdown(text) {
  let s = escapeHtml(text);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  s = s.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  s = s.replace(/_([^_\n]+)_/g, "<em>$1</em>");
  return s;
}

function isTableSeparator(line) {
  return /^\|?[\s:\-|]+\|[\s:\-|]*\|?$/.test(line.trim()) && line.includes("-");
}

function parseTableBlock(lines, start) {
  const rows = [];
  let i = start;
  while (i < lines.length) {
    const t = lines[i].trim();
    if (!t.includes("|")) break;
    if (isTableSeparator(t)) {
      i += 1;
      continue;
    }
    const cells = t
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((c) => c.trim());
    if (cells.length) rows.push(cells);
    i += 1;
  }
  if (rows.length < 1) return { html: "", next: start + 1 };
  const head = rows[0];
  const body = rows.slice(1);
  let html = '<div class="xhs-table-wrap"><table class="xhs-table"><thead><tr>';
  head.forEach((c) => {
    html += `<th>${inlineMarkdown(c)}</th>`;
  });
  html += "</tr></thead><tbody>";
  body.forEach((row) => {
    html += "<tr>";
    row.forEach((c) => {
      html += `<td>${inlineMarkdown(c)}</td>`;
    });
    html += "</tr>";
  });
  html += "</tbody></table></div>";
  return { html, next: i };
}

function renderMarkdownToHtml(md) {
  const lines = String(md || "").replace(/\r\n/g, "\n").split("\n");
  let html = '<article class="xhs-article">';
  let inList = false;
  let listTag = "ul";
  let inQuote = false;

  const closeList = () => {
    if (inList) {
      html += `</${listTag}>`;
      inList = false;
    }
  };
  const closeQuote = () => {
    if (inQuote) {
      html += "</blockquote>";
      inQuote = false;
    }
  };

  let i = 0;
  while (i < lines.length) {
    const raw = lines[i];
    const t = raw.trim();

    if (!t) {
      closeList();
      closeQuote();
      i += 1;
      continue;
    }

    if (/^---+$/.test(t) || /^\*\*\*+$/.test(t)) {
      closeList();
      closeQuote();
      html += "<hr />";
      i += 1;
      continue;
    }

    if (t.includes("|") && i + 1 < lines.length && isTableSeparator(lines[i + 1].trim())) {
      closeList();
      closeQuote();
      const parsed = parseTableBlock(lines, i);
      html += parsed.html;
      i = parsed.next;
      continue;
    }

    if (/^>\s?/.test(t)) {
      closeList();
      if (!inQuote) {
        html += "<blockquote>";
        inQuote = true;
      }
      html += `<p>${inlineMarkdown(t.replace(/^>\s?/, ""))}</p>`;
      i += 1;
      continue;
    }
    closeQuote();

    if (/^######\s+/.test(t)) {
      closeList();
      html += `<h6>${inlineMarkdown(t.replace(/^######\s+/, ""))}</h6>`;
    } else if (/^#####\s+/.test(t)) {
      closeList();
      html += `<h5>${inlineMarkdown(t.replace(/^#####\s+/, ""))}</h5>`;
    } else if (/^####\s+/.test(t)) {
      closeList();
      html += `<h4>${inlineMarkdown(t.replace(/^####\s+/, ""))}</h4>`;
    } else if (/^###\s+/.test(t)) {
      closeList();
      html += `<h3>${inlineMarkdown(t.replace(/^###\s+/, ""))}</h3>`;
    } else if (/^##\s+/.test(t)) {
      closeList();
      html += `<h2>${inlineMarkdown(t.replace(/^##\s+/, ""))}</h2>`;
    } else if (/^#\s+/.test(t)) {
      closeList();
      html += `<h1>${inlineMarkdown(t.replace(/^#\s+/, ""))}</h1>`;
    } else if (/^[-*•]\s+/.test(t)) {
      if (!inList || listTag !== "ul") {
        closeList();
        html += "<ul>";
        inList = true;
        listTag = "ul";
      }
      html += `<li>${inlineMarkdown(t.replace(/^[-*•]\s+/, ""))}</li>`;
    } else if (/^\d+[.\u3001)]\s+/.test(t)) {
      if (!inList || listTag !== "ol") {
        closeList();
        html += "<ol>";
        inList = true;
        listTag = "ol";
      }
      html += `<li>${inlineMarkdown(t.replace(/^\d+[.\u3001)]\s+/, ""))}</li>`;
    } else if (/^[一二三四五六七八九十]+[、.．]\s*/.test(t) && t.length < 40) {
      closeList();
      html += `<h2 class="xhs-cn-heading">${inlineMarkdown(t)}</h2>`;
    } else {
      closeList();
      html += `<p>${inlineMarkdown(t)}</p>`;
    }
    i += 1;
  }
  closeList();
  closeQuote();
  html += "</article>";
  return html;
}

function reportPreviewStyles() {
  return `
    :root { --text:#1f2430; --muted:#667085; --line:#e8ecf2; --accent:#e85d3a; --bg:#f7f8fb; }
    * { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font-family:"Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif; }
    .wrap { max-width:880px; margin:0 auto; padding:2rem 1.25rem 3rem; }
    .meta { color:var(--muted); font-size:0.9rem; margin-bottom:1.25rem; }
    .xhs-article { background:#fff; border:1px solid var(--line); border-radius:16px; padding:1.6rem 1.8rem 2rem; box-shadow:0 10px 30px rgba(20,24,40,.06); }
    .xhs-article h1 { font-size:1.7rem; margin:0 0 1rem; line-height:1.35; }
    .xhs-article h2 { font-size:1.2rem; margin:1.6rem 0 .7rem; padding-bottom:.35rem; border-bottom:1px solid var(--line); color:#121826; }
    .xhs-article h3,.xhs-article h4,.xhs-article h5,.xhs-article h6 { margin:1.15rem 0 .45rem; line-height:1.4; }
    .xhs-article h3 { font-size:1.05rem; }
    .xhs-article p, .xhs-article li { font-size:0.98rem; line-height:1.85; color:#2a3142; }
    .xhs-article p { margin:.55rem 0; }
    .xhs-article ul, .xhs-article ol { padding-left:1.3rem; margin:.5rem 0 .9rem; }
    .xhs-article li { margin:.28rem 0; }
    .xhs-article strong { color:#121826; }
    .xhs-article code { background:#f2f4f8; padding:.1rem .35rem; border-radius:5px; font-size:.9em; }
    .xhs-article blockquote { margin:1rem 0; padding:.7rem 1rem; border-left:4px solid var(--accent); background:#fff7f4; color:#5c453d; border-radius:0 10px 10px 0; }
    .xhs-article hr { border:none; border-top:1px solid var(--line); margin:1.4rem 0; }
    .xhs-table-wrap { overflow:auto; margin:1rem 0; border:1px solid var(--line); border-radius:12px; }
    .xhs-table { width:100%; border-collapse:collapse; font-size:.92rem; }
    .xhs-table th, .xhs-table td { padding:.65rem .75rem; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
    .xhs-table th { background:#f6f8fc; color:#344054; font-weight:700; }
    .xhs-table tr:last-child td { border-bottom:none; }
  `;
}

function buildReadableReportHtml(reportMd, meta, filename) {
  const weatherBit = meta?.use_weather ? ` · 天气 ${meta.weather_city || "全国"}` : "";
  const metaText = meta
    ? `${meta.created_at ? meta.created_at + " · " : ""}${meta.analysis_type_name || ""} · 关键词「${meta.keyword || ""}」 · 样本 ${meta.sample_count || 0} 条${weatherBit}`
    : "";
  return `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(filename || "小红书分析报告")}</title>
<style>${reportPreviewStyles()}</style></head><body><div class="wrap">
<p class="meta">${escapeHtml(metaText)}</p>
${renderMarkdownToHtml(reportMd)}
</div></body></html>`;
}

function setXhsReport(reportMd, meta) {
  xhsReportMd = reportMd || "";
  xhsReportMeta = meta || null;
  xhsReportFilename = (meta?.filename || "小红书分析报告.md").replace(/\.md$/i, "") + ".md";
  const weatherBit = meta?.use_weather ? ` · 天气 ${meta.weather_city || "全国"}` : "";
  const metaText = meta
    ? `${meta.created_at ? meta.created_at + " · " : ""}${meta.analysis_type_name || ""} · 关键词「${meta.keyword || ""}」 · 样本 ${meta.sample_count || 0} 条${weatherBit}`
    : "尚未生成";
  $("#xhsResultMeta").textContent = metaText;
  $("#xhsResultBody").innerHTML = xhsReportMd
    ? renderMarkdownToHtml(xhsReportMd)
    : '<p class="ai-placeholder">报告将显示在这里，支持预览、下载与历史回看。</p>';
  const has = !!xhsReportMd;
  $("#btnXhsPreview").disabled = !has;
  $("#btnXhsDownload").disabled = !has;
  $("#btnXhsDownloadHtml").disabled = !has;
}

async function loadXhsHistory() {
  const box = $("#xhsHistoryList");
  box.innerHTML = '<div class="ai-loading"><div class="spinner"></div>加载历史记录…</div>';
  let res;
  try {
    res = await fetch("/api/xhs/reports?limit=100");
  } catch (err) {
    box.innerHTML = `<p class="ai-placeholder" style="color:#c44a2e">无法连接服务：${escapeHtml(err.message)}</p>`;
    throw err;
  }
  const raw = await res.text();
  let data;
  try {
    data = JSON.parse(raw);
  } catch (_) {
    box.innerHTML =
      '<p class="ai-placeholder" style="color:#c44a2e">历史接口不可用（服务可能未重启）。请关闭后重新运行 server.py，再点刷新。</p>';
    throw new Error("历史接口返回非 JSON，请重启 server.py");
  }
  if (!res.ok) throw new Error(data.error || "加载历史失败");
  const reports = data.reports || [];
  if (!reports.length) {
    box.innerHTML = '<p class="ai-placeholder">暂无历史报告。完成一次分析后会自动保存在这里。</p>';
    return;
  }
  box.innerHTML = reports
    .map((r) => {
      const sub = [
        r.created_at || "",
        r.analysis_type_name || "",
        r.keyword ? `关键词「${r.keyword}」` : "",
        r.sample_count ? `${r.sample_count} 条样本` : "",
      ]
        .filter(Boolean)
        .join(" · ");
      return `<article class="xhs-history-item" data-id="${escapeHtml(r.id)}">
        <div class="xhs-history-main">
          <h4>${escapeHtml(r.title || r.keyword || r.id)}</h4>
          <p>${escapeHtml(sub)}</p>
        </div>
        <div class="xhs-history-item-actions">
          <button type="button" class="btn-secondary btn-sm" data-action="open">查看</button>
          <button type="button" class="btn-secondary btn-sm danger" data-action="delete">删除</button>
        </div>
      </article>`;
    })
    .join("");
}

async function openXhsHistoryReport(reportId) {
  const res = await fetch(`/api/xhs/reports/${encodeURIComponent(reportId)}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "打开报告失败");
  setXhsReport(data.report_md, data.meta);
  switchXhsPane("report");
  showToast("已打开历史报告");
}

async function deleteXhsHistoryReport(reportId) {
  if (!window.confirm("确认删除这份历史报告？此操作不可恢复。")) return;
  const res = await fetch(`/api/xhs/reports/${encodeURIComponent(reportId)}`, { method: "DELETE" });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "删除失败");
  if (xhsReportMeta?.id === reportId) {
    setXhsReport("", null);
  }
  await loadXhsHistory();
  showToast("历史报告已删除");
}

async function saveXhsPresetAsNew() {
  const values = getXhsFormValues();
  if (!values.keyword) {
    showToast("请先填写关键词");
    return;
  }
  const name = window.prompt("新预设名称", `${values.keyword}分析`);
  if (name == null) return;
  const res = await fetch("/api/xhs/presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...values, name: name.trim() || values.keyword }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "保存预设失败");
  await loadXhsPresets();
  $("#xhsPresetSelect").value = data.preset.id;
  fillXhsForm({ ...data.preset, preset_id: data.preset.id });
  showToast("已新增预设");
}

async function updateCurrentXhsPreset() {
  const p = currentXhsPreset();
  if (!p) {
    showToast("请先选择预设");
    return;
  }
  const values = getXhsFormValues();
  const name = window.prompt("预设名称", p.name);
  if (name == null) return;
  const res = await fetch(`/api/xhs/presets/${encodeURIComponent(p.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...values, name: name.trim() || p.name }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "更新失败");
  await loadXhsPresets();
  $("#xhsPresetSelect").value = data.preset.id;
  fillXhsForm({ ...data.preset, preset_id: data.preset.id });
  showToast(p.system ? "系统预设已更新" : "预设已更新");
}

async function deleteCurrentXhsPreset() {
  const p = currentXhsPreset();
  if (!p) return;
  if (p.system) {
    showToast("系统预设不可删除");
    return;
  }
  if (!window.confirm(`确认删除预设「${p.name}」？`)) return;
  const res = await fetch(`/api/xhs/presets/${encodeURIComponent(p.id)}`, { method: "DELETE" });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "删除失败");
  await loadXhsPresets();
  showToast("预设已删除");
}

function setXhsProgress(percent, message, visible = true) {
  const wrap = $("#xhsProgressWrap");
  if (!wrap) return;
  wrap.classList.toggle("hidden", !visible);
  const pct = Math.max(0, Math.min(100, Math.round(percent || 0)));
  $("#xhsProgressBar").style.width = `${pct}%`;
  $("#xhsProgressPct").textContent = `${pct}%`;
  if (message) $("#xhsProgressText").textContent = message;
  $("#xhsRunningDot")?.classList.toggle("hidden", !xhsAnalyzing);
}

function stopXhsJobPolling() {
  if (xhsJobTimer) {
    clearInterval(xhsJobTimer);
    xhsJobTimer = null;
  }
}

function finishXhsJobUi(ok, message) {
  xhsAnalyzing = false;
  stopXhsJobPolling();
  $("#btnXhsRun").disabled = false;
  $("#xhsRunningDot")?.classList.add("hidden");
  setXhsProgress(100, message || (ok ? "分析完成" : "分析失败"), true);
}

async function pollXhsJobOnce(jobId) {
  const res = await fetch(`/api/xhs/analyze/status/${encodeURIComponent(jobId)}`);
  const raw = await res.text();
  let data;
  try {
    data = JSON.parse(raw);
  } catch (_) {
    throw new Error("进度接口异常，请重启 server.py");
  }
  if (!res.ok) throw new Error(data.error || "查询进度失败");

  setXhsProgress(data.percent || 0, data.message || "进行中…", true);
  $("#xhsStatusHint").textContent = data.message || "分析进行中…";
  if ($("#xhsResultBody") && xhsAnalyzing) {
    $("#xhsResultBody").innerHTML = `<div class="ai-loading"><div class="spinner"></div>${escapeHtml(
      data.message || "分析进行中…"
    )}（${Math.round(data.percent || 0)}%）</div>`;
  }

  if (data.status === "done") {
    const result = data.result || {};
    setXhsReport(result.report_md, result.meta);
    switchXhsPane("report");
    finishXhsJobUi(true, "分析完成");
    const savedHint = result.meta?.id ? "已写入历史记录。" : "";
    $("#xhsStatusHint").textContent = `完成：共分析 ${result.meta?.sample_count || 0} 条笔记。${savedHint}可预览、下载或到「历史记录」回看。`;
    showToast(result.meta?.id ? "分析完成，已保存到历史" : "小红书分析完成");
    return true;
  }
  if (data.status === "error") {
    finishXhsJobUi(false, data.error || "分析失败");
    $("#xhsResultBody").innerHTML = `<p class="ai-placeholder" style="color:#c44a2e">分析失败：${escapeHtml(
      data.error || "未知错误"
    )}</p>`;
    $("#xhsStatusHint").textContent = "分析失败，请检查 API Key、关键词或稍后重试。";
    showToast(data.error || "分析失败");
    return true;
  }
  return false;
}

function startXhsJobPolling(jobId) {
  stopXhsJobPolling();
  xhsJobId = jobId;
  xhsJobTimer = setInterval(() => {
    pollXhsJobOnce(jobId).catch((err) => {
      finishXhsJobUi(false, err.message);
      $("#xhsStatusHint").textContent = err.message;
      showToast(err.message);
    });
  }, 800);
  pollXhsJobOnce(jobId).catch((err) => {
    finishXhsJobUi(false, err.message);
    showToast(err.message);
  });
}

async function runXhsAnalyze() {
  if (xhsAnalyzing) {
    showToast("已有分析任务在进行中");
    return;
  }
  const values = getXhsFormValues();
  if (!values.keyword) {
    showToast("请填写关键词");
    return;
  }
  if (!(values.analysis_type || "").trim()) {
    showToast("请填写分析类型");
    return;
  }

  $("#btnXhsRun").disabled = true;
  xhsAnalyzing = true;
  setXhsProgress(3, "提交任务…", true);
  $("#xhsStatusHint").textContent = "已开始分析；关闭弹窗也不会中断。";
  setXhsReport("", null);
  switchXhsPane("report");
  $("#xhsResultBody").innerHTML = '<div class="ai-loading"><div class="spinner"></div>任务启动中…</div>';

  const payload = { ...values };
  if (values.use_weather) {
    const picked = parseWeatherCityValue($("#xhsWeatherCity").value);
    payload.city = picked.weather_city;
    payload.province = picked.weather_province;
    try {
      if (picked.isNational) {
        if (!Object.keys(provinceWeatherMap || {}).length) {
          await loadProvinceWeatherOverview();
        }
        payload.weather_summary = buildNationalWeatherSummary();
      } else {
        const wres = await fetch(`/api/weather?lat=${picked.lat}&lon=${picked.lon}&days=7`);
        const wdata = await wres.json();
        if (!wres.ok) throw new Error(wdata.error || "天气加载失败");
        payload.weather = wdata;
        payload.weather_summary = "";
      }
    } catch (err) {
      finishXhsJobUi(false, err.message);
      showToast(err.message);
      $("#xhsStatusHint").textContent = "天气数据获取失败，可取消「结合天气」后重试。";
      return;
    }
  }

  try {
    const res = await fetch("/api/xhs/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "启动分析失败");
    // 兼容：旧服务可能仍返回整份报告；新服务返回 job_id
    if (data.job_id) {
      setXhsProgress(5, "任务已启动…", true);
      startXhsJobPolling(data.job_id);
      return;
    }
    if (data.report_md) {
      setXhsReport(data.report_md, data.meta);
      switchXhsPane("report");
      finishXhsJobUi(true, "分析完成");
      $("#xhsStatusHint").textContent = `完成：共分析 ${data.meta?.sample_count || 0} 条笔记。`;
      showToast("小红书分析完成（当前仍是旧服务，建议重启 server.py）");
      return;
    }
    throw new Error("未返回任务 ID。请先关闭所有旧的 server.py 窗口，再重新运行一次。");
  } catch (err) {
    finishXhsJobUi(false, err.message);
    $("#xhsResultBody").innerHTML = `<p class="ai-placeholder" style="color:#c44a2e">分析失败：${escapeHtml(err.message)}</p>`;
    $("#xhsStatusHint").textContent = "分析失败，请检查 API Key、关键词或稍后重试。";
    showToast(err.message);
  }
}

function downloadXhsReport() {
  if (!xhsReportMd) return;
  const blob = new Blob([xhsReportMd], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = xhsReportFilename || "小红书分析报告.md";
  a.click();
  URL.revokeObjectURL(url);
}

function downloadXhsReportHtml() {
  if (!xhsReportMd) return;
  const htmlName = (xhsReportFilename || "小红书分析报告.md").replace(/\.md$/i, "") + ".html";
  const html = buildReadableReportHtml(xhsReportMd, xhsReportMeta, htmlName);
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = htmlName;
  a.click();
  URL.revokeObjectURL(url);
}

function previewXhsReport() {
  if (!xhsReportMd) return;
  const w = window.open("", "_blank");
  if (!w) {
    showToast("浏览器拦截了预览窗口");
    return;
  }
  w.document.write(buildReadableReportHtml(xhsReportMd, xhsReportMeta, xhsReportFilename));
  w.document.close();
}

function setupXhsAnalyze() {
  $("#btnXhsAnalyze").addEventListener("click", openXhsModal);
  $("#btnXhsClose").addEventListener("click", closeXhsModal);
  $("#xhsModal").addEventListener("click", (e) => {
    if (e.target === $("#xhsModal")) closeXhsModal();
  });
  $("#xhsPresetSelect").addEventListener("change", applySelectedPreset);
  $("#xhsUseWeather").addEventListener("change", () => {
    syncXhsWeatherCityVisibility($("#xhsUseWeather").checked);
  });
  $("#btnXhsSavePreset").addEventListener("click", () => {
    saveXhsPresetAsNew().catch((err) => showToast(err.message));
  });
  $("#btnXhsUpdatePreset").addEventListener("click", () => {
    updateCurrentXhsPreset().catch((err) => showToast(err.message));
  });
  $("#btnXhsDeletePreset").addEventListener("click", () => {
    deleteCurrentXhsPreset().catch((err) => showToast(err.message));
  });
  $("#btnXhsRun").addEventListener("click", runXhsAnalyze);
  $("#btnXhsDownload").addEventListener("click", downloadXhsReport);
  $("#btnXhsDownloadHtml").addEventListener("click", downloadXhsReportHtml);
  $("#btnXhsPreview").addEventListener("click", previewXhsReport);
  $("#btnXhsTabReport").addEventListener("click", () => switchXhsPane("report"));
  $("#btnXhsTabHistory").addEventListener("click", () => switchXhsPane("history"));
  $("#btnXhsRefreshHistory").addEventListener("click", () => {
    loadXhsHistory().catch((err) => showToast(err.message));
  });
  $("#xhsHistoryList").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-action]");
    const item = e.target.closest(".xhs-history-item");
    if (!item) return;
    const id = item.dataset.id;
    if (!id) return;
    if (btn?.dataset.action === "delete") {
      deleteXhsHistoryReport(id).catch((err) => showToast(err.message));
      return;
    }
    if (btn?.dataset.action === "open" || !btn) {
      openXhsHistoryReport(id).catch((err) => showToast(err.message));
    }
  });
}

init();
