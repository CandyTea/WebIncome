export const QUERY_YEAR = 2026;

export function yearDates(dates) {
  return dates.filter(day => day.startsWith(`${QUERY_YEAR}-`)).sort();
}

export function daysInMonth(month) {
  if (!Number.isInteger(month) || month < 1 || month > 12) throw new Error('请选择有效月份。');
  return new Date(Date.UTC(QUERY_YEAR, month, 0)).getUTCDate();
}

export function makeDate(month, day) {
  if (!Number.isInteger(day) || day < 1 || day > daysInMonth(month)) throw new Error('请选择有效日期。');
  return `${QUERY_YEAR}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function validQueryDate(value) {
  if (!/^2026-\d{2}-\d{2}$/.test(value)) return false;
  const [, month, day] = value.split('-').map(Number);
  try { return makeDate(month, day) === value; } catch { return false; }
}

export function query(data, { search = '', from = '', to = '', sort = 'amount', warningDays = 7 } = {}) {
  if (!Number.isInteger(warningDays) || warningDays < 1 || warningDays > 365) throw new Error('预警天数请输入 1 至 365 的整数。');
  if ((from && !validQueryDate(from)) || (to && !validQueryDate(to))) throw new Error('查询时间限定为 2026 年，请重新选择日期。');
  if (from && to && from > to) throw new Error('开始日期不能晚于结束日期。');
  const allDates = yearDates(data.dates);
  const days = allDates.filter(day => (!from || day >= from) && (!to || day <= to)).reverse();
  const availableDates = new Set(allDates);
  const warningDates = [];
  if (allDates.length) {
    const date = new Date(`${allDates[allDates.length - 1]}T00:00:00Z`);
    for (let index = 0; index < warningDays; index++) {
      warningDates.push(date.toISOString().slice(0, 10));
      date.setUTCDate(date.getUTCDate() - 1);
    }
  }
  const warningDateSet = new Set(warningDates);
  const completeWindow = warningDates.length === warningDays && warningDates.every(day => availableDates.has(day));
  const warningRange = warningDates.length ? {from: warningDates[warningDates.length - 1] < '2026-01-01' ? '2026-01-01' : warningDates[warningDates.length - 1], to: warningDates[0]} : null;
  const selectedDays = new Set(days);
  const keyword = search.trim().toLocaleLowerCase('zh-CN');
  const rows = data.drivers.filter(driver => driver.name.toLocaleLowerCase('zh-CN').includes(keyword)).map(driver => ({ ...driver, total: 0, recorded: 0, missing: 0, zeroDays: 0, daily: [], warningRecords: new Map(), hasZeroWarning: false }));
  const indexed = new Map(rows.map(row => [row.id, row]));
  for (const record of data.records) {
    const driver = indexed.get(record.driverId);
    if (!driver) continue;
    if (warningDateSet.has(record.date)) driver.warningRecords.set(record.date, record.amountCents);
    if (!selectedDays.has(record.date)) continue;
    driver.daily.push({...record});
    if (record.amountCents === null) driver.missing += 1;
    else {
      driver.recorded += 1;
      driver.total += record.amountCents;
      if (record.amountCents === 0) driver.zeroDays += 1;
    }
  }
  for (const driver of rows) {
    driver.hasZeroWarning = completeWindow && warningDates.every(day => driver.warningRecords.get(day) === 0);
    delete driver.warningRecords;
    driver.daily.sort((a, b) => b.date.localeCompare(a.date));
    for (const record of driver.daily) record.zeroWarning = driver.hasZeroWarning && warningDateSet.has(record.date) && record.amountCents === 0;
  }
  rows.sort((a, b) => {
    const byName = a.name.localeCompare(b.name, 'zh-CN');
    if (sort === 'name') return byName;
    if (Boolean(a.recorded) !== Boolean(b.recorded)) return a.recorded ? -1 : 1;
    return (sort === 'amount-asc' ? a.total - b.total : b.total - a.total) || byName;
  });
  return { days, rows, total: rows.reduce((sum, row) => sum + row.total, 0), missing: rows.reduce((sum, row) => sum + row.missing, 0), zeroDrivers: rows.filter(row => row.zeroDays > 0).length, zeroRecords: rows.reduce((sum, row) => sum + row.zeroDays, 0), warningDays, warningRange, completeWarningWindow: completeWindow, warningDrivers: rows.filter(row => row.hasZeroWarning).length };
}

export function shanghaiToday(now = new Date()) {
  return new Date(now.getTime() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

export function rangeDates(from, to) {
  if (!validQueryDate(from) || !validQueryDate(to) || from > to) throw new Error('请选择有效的 2026 年日期范围。');
  const days = [];
  const day = new Date(`${to}T00:00:00Z`);
  while (day.toISOString().slice(0, 10) >= from) {
    days.push(day.toISOString().slice(0, 10));
    day.setUTCDate(day.getUTCDate() - 1);
  }
  return days;
}

export function favoriteFirst(rows, favorites) {
  // Keep the selected amount/name ordering within each group.
  return rows.filter(row => favorites.has(row.id)).concat(rows.filter(row => !favorites.has(row.id)));
}

export function presetRange(dates, count = 0, today = shanghaiToday()) {
  const sorted = yearDates(dates);
  if (!sorted.length) throw new Error('尚无 2026 年的流水数据。');
  if (!Number.isInteger(count) || count < 0 || count > 365) throw new Error('最近天数请输入 1 至 365 的整数。');
  if (!count) return { from: sorted[0], to: sorted[sorted.length - 1] };
  const end = new Date(`${today}T00:00:00Z`);
  if (!Number.isFinite(end.getTime())) throw new Error('当前日期无效。');
  end.setUTCDate(end.getUTCDate() - 1);
  const to = end.toISOString().slice(0, 10) > `${QUERY_YEAR}-12-31` ? `${QUERY_YEAR}-12-31` : end.toISOString().slice(0, 10);
  if (to < `${QUERY_YEAR}-01-01`) throw new Error('2026 年尚无已结束的日期，请自选查询日期。');
  const start = new Date(`${to}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - count + 1);
  const from = start.toISOString().slice(0, 10);
  return { from: from < '2026-01-01' ? '2026-01-01' : from, to };
}

export function driverDetail(data, driverId, { warningDays = 7, today = shanghaiToday() } = {}) {
  const identity = data.drivers.find(driver => driver.id === driverId);
  if (!identity) return null;
  const range = presetRange(data.dates, 14, today);
  const driver = query({ ...data, drivers: [identity] }, { ...range, warningDays }).rows[0];
  const daily = new Map(driver.daily.map(record => [record.date, record]));
  driver.daily = rangeDates(range.from, range.to).map(date => daily.get(date) || { driverId, date, amountCents: null, zeroWarning: false });
  driver.missing = driver.daily.length - driver.recorded;
  return driver;
}
