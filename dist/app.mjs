import { query, presetRange, daysInMonth, makeDate, filterRows, tabCounts } from './query.mjs';

const $ = id => document.getElementById(id);
const money = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const formatMoney = cents => money.format(cents / 100);
const formatDate = iso => iso.replaceAll('-', '/');
let data;
let dataVersion = null;
let refreshing = false;
let activeDays = 0;
let warningDays = 7;
let viewMode = 'cards';
let activeTab = 'all';
let selectedDriverId = null;
let lastDialogFocus = null;
let filtersCollapsed = false;
const isMobile = () => matchMedia('(max-width: 700px)').matches;
const standardDays = new Set([0, 1, 3, 7, 14]);
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

function updateDayOptions(prefix, preferredDay) {
  const month = Number($(`${prefix}-month`).value);
  const selectedDay = Math.min(Number(preferredDay || $(`${prefix}-day`).value || 1), daysInMonth(month));
  $(`${prefix}-day`).replaceChildren();
  for (let day = 1; day <= daysInMonth(month); day++) {
    const option = el('option', '', `${day} 日`);
    option.value = String(day);
    $(`${prefix}-day`).append(option);
  }
  $(`${prefix}-day`).value = String(selectedDay);
}

for (const prefix of ['from', 'to']) {
  for (let month = 1; month <= 12; month++) {
    const option = el('option', '', `${month} 月`);
    option.value = String(month);
    $(`${prefix}-month`).append(option);
  }
  updateDayOptions(prefix, 1);
}

function getDate(prefix) {
  return makeDate(Number($(`${prefix}-month`).value), Number($(`${prefix}-day`).value));
}

function setDates(range) {
  for (const prefix of ['from', 'to']) {
    const [, month, day] = range[prefix].split('-').map(Number);
    $(`${prefix}-month`).value = String(month);
    updateDayOptions(prefix, day);
  }
}

function applyRecent(count) {
  if (!data) return;
  setDates(presetRange(data.dates, count));
  activeDays = count;
  $('manual-range').open = false;
  $('custom-days-error').hidden = true;
  render();
}

function dailyTable(driver) {
  const table = el('table');
  const caption = el('caption', 'sr-only', `${driver.name}的每日流水明细，金额单位为元`);
  table.append(caption);
  const thead = el('thead');
  const header = el('tr');
  for (const text of ['日期', '流水（元）']) {
    const th = el('th', '', text);
    th.scope = 'col';
    header.append(th);
  }
  thead.append(header);
  table.append(thead);
  const body = el('tbody');
  for (const record of driver.daily) {
    const row = el('tr');
    if (record.zeroWarning) row.classList.add('zero-row');
    const amount = el('td', record.amountCents === null ? 'unrecorded' : '', record.amountCents === null ? '未记录' : formatMoney(record.amountCents));
    if (record.zeroWarning) amount.append(el('span', 'daily-zero-label', '0 流水'));
    row.append(el('td', '', formatDate(record.date)), amount);
    body.append(row);
  }
  table.append(body);
  return table;
}

function driverView(driver, days) {
  const detail = el('details', 'driver');
  if (driver.hasZeroWarning) detail.classList.add('has-zero');
  detail.dataset.driverId = driver.id;
  const summary = el('summary');
  summary.append(el('span', 'avatar', driver.name.slice(0, 1)));
  summary.firstElementChild.setAttribute('aria-hidden', 'true');
  const info = el('div');
  info.append(el('div', 'driver-name', driver.name), el('div', 'driver-days', `已记录 ${driver.recorded} / ${days} 天`));
  if (driver.hasZeroWarning) info.append(el('span', 'zero-badge', `连续 ${warningDays} 天 0 流水`));
  const totalClass = driver.hasZeroWarning && driver.recorded > 0 && driver.zeroDays === driver.recorded ? 'driver-total zero-amount' : 'driver-total';
  summary.append(info, el('span', totalClass, driver.recorded ? formatMoney(driver.total) : '未记录'));
  const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  icon.setAttribute('viewBox', '0 0 20 20');
  icon.setAttribute('aria-hidden', 'true');
  icon.classList.add('chevron');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'm5 7 5 5 5-5');
  icon.append(path);
  summary.append(icon);
  const daily = el('div', 'daily');
  daily.append(el('h3', '', `${driver.name}的每日流水`), dailyTable(driver));
  detail.append(summary, daily);
  return detail;
}

function renderCompact(result) {
  const counts = tabCounts(result.rows);
  $('count-all').textContent = counts.all;
  $('count-warning').textContent = counts.warning;
  $('count-missing').textContent = counts.missing;
  for (const button of document.querySelectorAll('[data-tab]')) {
    const selected = button.dataset.tab === activeTab;
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
  }
  const rows = filterRows(result.rows, activeTab);
  const list = $('compact-list');
  list.replaceChildren();
  const days = result.days.length;
  for (const driver of rows) {
    const row = el('button', 'compact-row');
    row.type = 'button';
    row.dataset.driverId = driver.id;
    if (driver.hasZeroWarning) row.classList.add('has-zero');
    const main = el('span', 'compact-main');
    main.append(el('span', 'compact-name', driver.name));
    const sub = el('span', 'compact-sub');
    sub.append(document.createTextNode(driver.recorded ? `已记录 ${driver.recorded} / ${days} 天` : '范围内未记录'));
    if (driver.hasZeroWarning) sub.append(el('span', 'compact-warn', `连续 ${warningDays} 天 0 流水`));
    main.append(sub);
    const total = el('span', driver.recorded ? 'compact-total' : 'compact-total unrecorded', driver.recorded ? formatMoney(driver.total) : '未记录');
    if (driver.hasZeroWarning && driver.recorded > 0 && driver.zeroDays === driver.recorded) total.classList.add('zero-amount');
    row.append(main, total, el('span', 'compact-chevron', '›'));
    row.setAttribute('aria-label', `${driver.name}，${driver.recorded ? `已记录 ${driver.recorded} / ${days} 天，合计 ${formatMoney(driver.total)} 元` : '范围内未记录'}，点开查看每日明细`);
    row.addEventListener('click', () => openDriver(driver, days));
    list.append(row);
  }
  if ($('driver-dialog').open && selectedDriverId) {
    const driver = result.rows.find(item => item.id === selectedDriverId);
    if (driver) updateDialog(driver, days);
    else closeDialog();
  }
}

function openDriver(driver, days) {
  selectedDriverId = driver.id;
  lastDialogFocus = document.activeElement;
  updateDialog(driver, days);
  const dialog = $('driver-dialog');
  if (!dialog.open) dialog.showModal();
}

function updateDialog(driver, days) {
  $('dialog-title').textContent = driver.name;
  const meta = $('dialog-meta');
  meta.replaceChildren(document.createTextNode(driver.recorded ? `已记录 ${driver.recorded} / ${days} 天 · 合计 ${formatMoney(driver.total)} 元` : '范围内未记录'));
  if (driver.hasZeroWarning) meta.append(el('span', 'zero-badge', `连续 ${warningDays} 天 0 流水`));
  const daily = el('div', 'daily dialog-daily');
  if (driver.daily.length) daily.append(dailyTable(driver));
  else daily.append(el('p', 'dialog-empty', '此范围内没有记录。'));
  $('dialog-body').replaceChildren(daily);
}

function closeDialog() {
  const dialog = $('driver-dialog');
  if (dialog.open) dialog.close();
  selectedDriverId = null;
}

function applyViewMode() {
  document.body.classList.toggle('view-compact', viewMode === 'compact');
  $('classic-view').hidden = viewMode === 'compact';
  $('compact-view').hidden = viewMode !== 'compact';
  for (const button of document.querySelectorAll('[data-view]')) {
    button.setAttribute('aria-pressed', String(button.dataset.view === viewMode));
  }
  if (viewMode === 'cards') closeDialog();
}

function setView(mode) {
  if (mode !== 'cards' && mode !== 'compact') return;
  viewMode = mode;
  try { localStorage.setItem('webincome.view', mode); } catch { /* Private mode can reject storage. */ }
  applyViewMode();
  setFiltersCollapsed(mode === 'compact' && isMobile());
  if (data) render();
}

function setFiltersCollapsed(collapsed) {
  filtersCollapsed = collapsed;
  const mobile = isMobile();
  const isCollapsed = collapsed && mobile;
  document.querySelector('.filters').classList.toggle('is-collapsed', isCollapsed);
  const toggle = $('filter-toggle');
  toggle.setAttribute('aria-expanded', String(!isCollapsed));
  toggle.textContent = isCollapsed ? '展开筛选' : '收起筛选';
  $('filter-summary').hidden = !isCollapsed;
}

function updateFilterSummary() {
  const search = $('search').value.trim();
  let range;
  if (activeDays === null) range = `${formatDate(getDate('from'))} 至 ${formatDate(getDate('to'))}`;
  else if (activeDays === 0) range = '全部数据';
  else range = `最近 ${activeDays} 天`;
  const sortText = { amount: '合计从高到低', 'amount-asc': '合计从低到高', name: '按姓名' }[$('sort').value] || '';
  $('filter-summary').textContent = `${search ? `司机“${search}”` : '全部司机'} · ${range} · ${sortText}`;
}

function render() {
  if (!data) return;
  const state = { search: $('search').value, from: getDate('from'), to: getDate('to'), sort: $('sort').value, warningDays };
  $('range-preview').textContent = `${formatDate(state.from)} 至 ${formatDate(state.to)}`;
  let result;
  try { result = query(data, state); }
  catch (error) {
    $('filter-error').textContent = error.message;
    $('filter-error').hidden = false;
    $('results').hidden = true;
    return;
  }
  $('filter-error').hidden = true;
  $('results').hidden = false;
  const openDrivers = new Set([...document.querySelectorAll('.driver[open]')].map(node => node.dataset.driverId));
  $('driver-list').replaceChildren();
  for (const driver of result.rows) {
    if (!result.days.length) continue;
    const node = driverView(driver, result.days.length);
    node.open = openDrivers.has(driver.id) || result.rows.length === 1;
    $('driver-list').append(node);
  }
  $('total-amount').textContent = formatMoney(result.total);
  const recordedCount = result.rows.reduce((count, driver) => count + driver.recorded, 0);
  $('total-amount').classList.toggle('zero-overview', recordedCount > 0 && result.zeroRecords === recordedCount && result.warningDrivers === result.rows.length);
  $('selected-range').textContent = `${formatDate(state.from)} 至 ${formatDate(state.to)}`;
  $('driver-count').textContent = result.days.length ? result.rows.length : 0;
  $('day-count').textContent = result.days.length;
  $('result-count').textContent = result.days.length ? `共 ${result.rows.length} 名司机，点开查看每日明细` : '所选范围没有数据';
  const visibleRows = viewMode === 'compact' ? filterRows(result.rows, activeTab) : result.rows;
  const hasVisibleRows = result.days.length > 0 && visibleRows.length > 0;
  $('empty').hidden = hasVisibleRows;
  const emptyHeading = $('empty').querySelector('h3');
  const emptyText = $('empty').querySelector('p');
  if (!result.days.length) {
    emptyHeading.textContent = '所选范围没有数据';
    emptyText.textContent = '请调整查询时间，或让管理员上传新的 Excel。';
  } else if (viewMode === 'compact' && activeTab !== 'all') {
    emptyHeading.textContent = activeTab === 'warning' ? '没有预警司机' : '没有未记录的司机';
    emptyText.textContent = activeTab === 'warning' ? `当前范围内没有连续 ${warningDays} 天 0 流水的司机。` : '当前范围内所有司机都有流水记录。';
  } else {
    emptyHeading.textContent = '没有匹配的流水';
    emptyText.textContent = '试试其他司机姓名，或调整查询时间。';
  }
  $('data-note').textContent = result.rows.length && result.days.length ? `已核验的范围内流水${result.missing ? `，其中 ${result.missing} 项未记录` : ''}。` : '';
  $('zero-alert').hidden = result.warningDrivers === 0 || result.days.length === 0;
  $('zero-alert-text').textContent = result.warningRange ? `${result.warningDrivers} 名司机最近连续 ${warningDays} 天每天流水均为 0（${formatDate(result.warningRange.from)} 至 ${formatDate(result.warningRange.to)}）。` : '';
  $('warning-hint').textContent = result.warningRange ? `当前规则：最近连续 ${warningDays} 天每天均为 0 才报红。预警范围 ${formatDate(result.warningRange.from)} 至 ${formatDate(result.warningRange.to)}，与查询时间独立。` : '按最新数据往前判断；缺少记录不报红。';
  document.querySelector('.list-heading').hidden = !$('empty').hidden;
  renderCompact(result);
  updateFilterSummary();
  for (const button of document.querySelectorAll('[data-days]')) {
    button.setAttribute('aria-pressed', String(activeDays === Number(button.dataset.days)));
  }
  $('custom-toggle').setAttribute('aria-pressed', String(activeDays !== null && !standardDays.has(activeDays)));
  const url = new URL(location.href);
  for (const key of ['q', 'from', 'to', 'sort', 'days', 'warnDays', 'view', 'tab']) url.searchParams.delete(key);
  if (state.search.trim()) url.searchParams.set('q', state.search.trim());
  if (activeDays !== null && activeDays > 0) url.searchParams.set('days', String(activeDays));
  else if (activeDays === null) {
    url.searchParams.set('from', state.from);
    url.searchParams.set('to', state.to);
  }
  if (state.sort !== 'amount') url.searchParams.set('sort', state.sort);
  if (warningDays !== 7) url.searchParams.set('warnDays', String(warningDays));
  if (viewMode === 'compact') url.searchParams.set('view', 'compact');
  if (activeTab !== 'all') url.searchParams.set('tab', activeTab);
  history.replaceState(null, '', url);
}

function reset() {
  if (!data) return;
  $('search').value = '';
  setDates(presetRange(data.dates, 0));
  activeDays = 0;
  $('manual-range').open = false;
  $('custom-days-panel').hidden = true;
  $('custom-toggle').setAttribute('aria-expanded', 'false');
  $('custom-days-error').hidden = true;
  $('sort').value = 'amount';
  warningDays = 7;
  $('warning-days').value = '7';
  $('warning-days').removeAttribute('aria-invalid');
  $('warning-rule-error').hidden = true;
  activeTab = 'all';
  closeDialog();
  render();
}

async function load(initial = true) {
  try {
    const previous = initial ? null : { search: $('search').value, from: getDate('from'), to: getDate('to'), sort: $('sort').value, activeDays };
    const response = await fetch('./data/sheet2.json', { cache: 'no-store' });
    if (response.status === 401) { location.assign('/login'); return; }
    if (!response.ok) {
      const message = await response.json();
      throw new Error(message.error || '流水数据暂时无法读取。');
    }
    data = await response.json();
    if (data.schemaVersion !== 1 || !data.dates?.length || !Array.isArray(data.drivers) || !Array.isArray(data.records)) throw new Error('数据格式不正确');
    const range = presetRange(data.dates, 0);
    dataVersion = response.headers.get('X-Data-Version');
    if (previous) {
      $('search').value = previous.search;
      $('sort').value = previous.sort;
      activeDays = previous.activeDays;
      setDates(activeDays === null ? previous : presetRange(data.dates, activeDays));
    } else {
      const params = new URLSearchParams(location.search);
      $('search').value = params.get('q') || '';
      const ruleDays = Number(params.get('warnDays'));
      warningDays = Number.isInteger(ruleDays) && ruleDays >= 1 && ruleDays <= 365 ? ruleDays : 7;
      $('warning-days').value = String(warningDays);
      const count = Number(params.get('days'));
      if (params.has('days') && Number.isInteger(count) && count >= 1 && count <= 365) {
        activeDays = count;
        setDates(presetRange(data.dates, count));
        if (!standardDays.has(count)) {
          $('custom-days-panel').hidden = false;
          $('custom-toggle').setAttribute('aria-expanded', 'true');
          $('custom-days').value = String(count);
        }
      } else if (params.has('from') || params.has('to')) {
        const selected = {from: params.get('from') || range.from, to: params.get('to') || range.to};
        try {
          query(data, selected);
          activeDays = null;
          setDates(selected);
          $('manual-range').open = true;
        } catch { activeDays = 0; setDates(range); }
      } else { activeDays = 0; setDates(range); }
      if (['name', 'amount-asc'].includes(params.get('sort'))) $('sort').value = params.get('sort');
    }
    $('coverage').textContent = `数据截至 ${formatDate(range.to)}`;
    $('load-status').hidden = true;
    $('load-error').hidden = true;
    render();
  } catch (error) {
    if (!initial && data) return;
    $('load-status').hidden = true;
    $('load-error').hidden = false;
    $('load-error-text').textContent = /尚未上传|尚无 2026/.test(error.message) ? error.message : '流水数据暂时无法读取。请检查网络后重试。';
    console.error('流水读取失败', error);
  }
}

$('filters').addEventListener('submit', event => event.preventDefault());
$('search').addEventListener('input', render);
$('sort').addEventListener('change', render);
for (const prefix of ['from', 'to']) {
  $(`${prefix}-month`).addEventListener('change', () => { updateDayOptions(prefix); activeDays = null; render(); });
  $(`${prefix}-day`).addEventListener('change', () => { activeDays = null; render(); });
}
$('filters').addEventListener('reset', event => { event.preventDefault(); reset(); });
for (const button of document.querySelectorAll('[data-days]')) button.addEventListener('click', () => {
  applyRecent(Number(button.dataset.days));
});
$('custom-toggle').addEventListener('click', () => {
  const show = $('custom-days-panel').hidden;
  $('custom-days-panel').hidden = !show;
  $('custom-toggle').setAttribute('aria-expanded', String(show));
  if (show) $('custom-days').focus();
});
function applyCustomDays() {
  const count = Number($('custom-days').value);
  if (!Number.isInteger(count) || count < 1 || count > 365) {
    $('custom-days-error').textContent = '请输入 1 至 365 的整数天数。';
    $('custom-days-error').hidden = false;
    $('custom-days').setAttribute('aria-invalid', 'true');
    return;
  }
  $('custom-days').removeAttribute('aria-invalid');
  applyRecent(count);
}
$('apply-days').addEventListener('click', applyCustomDays);
$('custom-days').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); applyCustomDays(); } });
function applyWarningDays() {
  const value = Number($('warning-days').value);
  if (!Number.isInteger(value) || value < 1 || value > 365) {
    $('warning-rule-error').textContent = '预警天数请输入 1 至 365 的整数。';
    $('warning-rule-error').hidden = false;
    $('warning-days').setAttribute('aria-invalid', 'true');
    return;
  }
  warningDays = value;
  $('warning-rule-error').hidden = true;
  $('warning-days').removeAttribute('aria-invalid');
  render();
}
$('apply-warning').addEventListener('click', applyWarningDays);
$('warning-days').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); applyWarningDays(); } });
$('empty-reset').addEventListener('click', reset);
$('retry').addEventListener('click', () => location.reload());
for (const button of document.querySelectorAll('[data-view]')) {
  button.addEventListener('click', () => setView(button.dataset.view));
}
for (const button of document.querySelectorAll('[data-tab]')) {
  button.addEventListener('click', () => { activeTab = button.dataset.tab; if (data) render(); });
  button.addEventListener('keydown', event => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    const tabs = [...document.querySelectorAll('[data-tab]')];
    const index = tabs.indexOf(button);
    const next = tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
    next.focus();
    next.click();
  });
}
$('filter-toggle').addEventListener('click', () => setFiltersCollapsed(!filtersCollapsed));
$('dialog-close').addEventListener('click', () => $('driver-dialog').close());
$('driver-dialog').addEventListener('click', event => { if (event.target === $('driver-dialog')) $('driver-dialog').close(); });
$('driver-dialog').addEventListener('close', () => {
  selectedDriverId = null;
  if (lastDialogFocus && document.contains(lastDialogFocus)) lastDialogFocus.focus();
  lastDialogFocus = null;
});
const initialParams = new URLSearchParams(location.search);
let storedView = null;
try { storedView = localStorage.getItem('webincome.view'); } catch { /* Ignore unavailable storage. */ }
viewMode = initialParams.get('view') === 'compact' || (initialParams.get('view') !== 'cards' && storedView === 'compact') ? 'compact' : 'cards';
if (initialParams.has('view')) {
  try { localStorage.setItem('webincome.view', viewMode); } catch { /* Ignore unavailable storage. */ }
}
activeTab = ['warning', 'missing'].includes(initialParams.get('tab')) ? initialParams.get('tab') : 'all';
applyViewMode();
setFiltersCollapsed(viewMode === 'compact' && isMobile());
matchMedia('(max-width: 700px)').addEventListener('change', event => {
  if (!event.matches) setFiltersCollapsed(false);
  else if (viewMode === 'compact') setFiltersCollapsed(true);
});
load();

async function checkForUpdates() {
  if (refreshing || document.hidden) return;
  refreshing = true;
  try {
    const response = await fetch('/api/data-status', { cache: 'no-store' });
    if (!response.ok) return;
    const state = await response.json();
    if (state.version && state.version !== dataVersion) await load(!data);
  } catch { /* Preserve the displayed data during temporary network failures. */ }
  finally { refreshing = false; }
}
setInterval(checkForUpdates, 4000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) checkForUpdates(); });
