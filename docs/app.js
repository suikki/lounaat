'use strict';

const FI_WEEKDAYS = ['Maanantai', 'Tiistai', 'Keskiviikko', 'Torstai', 'Perjantai'];
const FI_WEEKDAYS_SHORT = ['Ma', 'Ti', 'Ke', 'To', 'Pe'];

const $ = (sel) => document.querySelector(sel);

function fmtDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return iso;
  return `${d}.${m}.`;
}

function fmtTimestamp(iso) {
  if (!iso) return '';
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  return dt.toLocaleString('fi-FI', {
    weekday: 'short', day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

function localIso(d) {
  // YYYY-MM-DD in the user's local timezone (Date.toISOString gives UTC,
  // which is off by one near local midnight — wrong for our use case).
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function todayIso() {
  return localIso(new Date());
}

function isCurrentWeek(dateIso, weekDates) {
  return weekDates.includes(dateIso);
}

function thisWeekDates() {
  const now = new Date();
  // Monday of current week (clamp to Mon..Fri if weekend)
  const day = now.getDay() === 0 ? 7 : now.getDay(); // Mon=1..Sun=7
  const monday = new Date(now);
  monday.setDate(now.getDate() - (day - 1));
  const out = [];
  for (let i = 0; i < 5; i++) {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    out.push(localIso(d));
  }
  return out;
}

function pickDefaultDayIndex(weekDates) {
  const today = todayIso();
  const idx = weekDates.indexOf(today);
  if (idx >= 0 && idx < 5) return idx;
  return 0;
}

function findDayForRestaurant(restaurant, targetIso, targetWeekdayName) {
  // 1. Exact ISO date match
  const byDate = (restaurant.days || []).find((d) => d.date === targetIso);
  if (byDate) return { day: byDate, matched: 'date' };
  // 2. Match by weekday name (covers cases where the source uses last week's dates)
  const byName = (restaurant.days || []).find((d) => d.weekday === targetWeekdayName);
  if (byName) return { day: byName, matched: 'weekday' };
  return { day: null, matched: 'none' };
}

function renderDish(li, dish) {
  // Wrap parenthesized fragments in a "dish-meta" span so they can be styled
  // smaller and dimmer (e.g. allergen codes, ingredient notes).
  const parts = dish.split(/(\([^)]*\))/g);
  for (const part of parts) {
    if (!part) continue;
    if (part.startsWith('(') && part.endsWith(')')) {
      const span = document.createElement('span');
      span.className = 'dish-meta';
      span.textContent = part;
      li.appendChild(span);
    } else {
      li.appendChild(document.createTextNode(part));
    }
  }
}

function appendBanner(parent, cls, text) {
  const b = document.createElement('div');
  b.className = cls;
  b.textContent = text;
  parent.appendChild(b);
}

function appendHeading(parent, restaurant) {
  const h2 = document.createElement('h2');
  if (restaurant.url) {
    const a = document.createElement('a');
    a.href = restaurant.url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = restaurant.name;
    h2.appendChild(a);
  } else {
    h2.textContent = restaurant.name;
  }
  parent.appendChild(h2);
}

function renderSection(sec) {
  const wrap = document.createElement('section');
  wrap.className = 'section';
  if (sec.name) {
    const h = document.createElement('h3');
    h.className = 'section-name';
    h.textContent = sec.name;
    wrap.appendChild(h);
  }
  const ul = document.createElement('ul');
  ul.className = 'dishes';
  for (const dish of sec.dishes) {
    const li = document.createElement('li');
    renderDish(li, dish);
    ul.appendChild(li);
  }
  wrap.appendChild(ul);
  return wrap;
}

function renderCard(restaurant, targetIso, targetWeekdayName, weekDates) {
  const el = document.createElement('section');
  el.className = 'card';
  appendHeading(el, restaurant);

  if (restaurant.error) {
    appendBanner(el, 'banner err', `Skrappaus epäonnistui: ${restaurant.error}`);
    return el;
  }

  const { day, matched } = findDayForRestaurant(restaurant, targetIso, targetWeekdayName);
  if (!day) {
    appendBanner(el, 'empty', 'Ei tietoja tälle päivälle.');
    return el;
  }

  if (day.date && !isCurrentWeek(day.date, weekDates)) {
    appendBanner(el, 'banner warn', `Tiedot näyttävät olevan vanhentuneita (lähde: ${fmtDate(day.date)}).`);
  } else if (matched === 'weekday' && day.date && day.date !== targetIso) {
    appendBanner(el, 'banner warn', `Lähteen päiväys: ${fmtDate(day.date)}.`);
  }

  if (day.note) {
    appendBanner(el, 'note', day.note);
  }

  const sections = day.sections || [];
  if (sections.length === 0) {
    if (!day.note) appendBanner(el, 'empty', 'Ei lounaslistaa tälle päivälle.');
    return el;
  }
  for (const sec of sections) {
    el.appendChild(renderSection(sec));
  }
  return el;
}

function renderTabs(weekDates, activeIdx, onPick) {
  const nav = $('#tabs');
  nav.innerHTML = '';
  for (let i = 0; i < 5; i++) {
    const b = document.createElement('button');
    const isToday = weekDates[i] === todayIso();
    b.className = 'tab' + (isToday ? ' tab-today' : '');
    b.innerHTML = `
      <span class="tab-long">${FI_WEEKDAYS[i]}</span>
      <span class="tab-short" aria-hidden="true">${FI_WEEKDAYS_SHORT[i]}</span>
      <span class="tab-date">${fmtDate(weekDates[i])}</span>
    `;
    b.setAttribute('aria-pressed', i === activeIdx ? 'true' : 'false');
    b.setAttribute('aria-label', `${FI_WEEKDAYS[i]} ${fmtDate(weekDates[i])}${isToday ? ' (tänään)' : ''}`);
    b.addEventListener('click', () => onPick(i));
    nav.appendChild(b);
  }
}

function renderApp(data, weekDates, activeIdx) {
  const main = $('#app');
  main.innerHTML = '';
  const targetIso = weekDates[activeIdx];
  const targetWeekdayName = FI_WEEKDAYS[activeIdx];
  for (const r of data.restaurants) {
    main.appendChild(renderCard(r, targetIso, targetWeekdayName, weekDates));
  }
}

function renderFooter(data) {
  const sources = $('#sources');
  const updated = $('#updated');
  sources.textContent = '';
  sources.append('Lähteet: ');
  const linkable = data.restaurants.filter((r) => r.url);
  linkable.forEach((r, i) => {
    const a = document.createElement('a');
    a.href = r.url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = r.name;
    sources.appendChild(a);
    if (i < linkable.length - 1) sources.append(' · ');
  });
  updated.textContent = `Päivitetty: ${fmtTimestamp(data.generated_at)}`;
}

async function main() {
  const sources = $('#sources');
  sources.textContent = 'Ladataan…';
  let data;
  try {
    const resp = await fetch('./data/menus.json', { cache: 'no-cache' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    data = await resp.json();
  } catch (e) {
    sources.innerHTML = `<span class="banner err">Tietoja ei voitu ladata: ${e.message}</span>`;
    return;
  }

  const weekDates = thisWeekDates();
  let activeIdx = pickDefaultDayIndex(weekDates);

  const onPick = (i) => {
    activeIdx = i;
    renderTabs(weekDates, activeIdx, onPick);
    renderApp(data, weekDates, activeIdx);
  };
  renderTabs(weekDates, activeIdx, onPick);
  renderApp(data, weekDates, activeIdx);
  renderFooter(data);

  // If the tab is left open across a day boundary, reload when it next
  // becomes visible so the selected day and menus.json are fresh.
  const loadedDate = todayIso();
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && todayIso() !== loadedDate) {
      location.reload();
    }
  });
}

main();
