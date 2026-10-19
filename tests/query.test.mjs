import test from 'node:test';
import assert from 'node:assert/strict';
import { query, presetRange, makeDate, daysInMonth, filterRows, tabCounts } from '../dist/query.mjs';

const data = {
  dates: ['2026-10-17', '2026-10-16', '2026-10-15'],
  drivers: [{id:'a', name:'王师傅'}, {id:'b', name:'李师傅'}],
  records: [
    {driverId:'a', date:'2026-10-17', amountCents:12629},
    {driverId:'a', date:'2026-10-16', amountCents:0},
    {driverId:'a', date:'2026-10-15', amountCents:null},
    {driverId:'b', date:'2026-10-17', amountCents:20000},
    {driverId:'b', date:'2026-10-16', amountCents:100},
    {driverId:'b', date:'2026-10-15', amountCents:300},
  ],
};
test('姓名与单日边界同时过滤', () => {
  const result = query(data, {search:'王', from:'2026-10-17', to:'2026-10-17'});
  assert.equal(result.rows.length, 1);
  assert.equal(result.total, 12629);
  assert.equal(result.days.length, 1);
});
test('起止日期都包含在查询范围', () => {
  assert.equal(query(data, {from:'2026-10-15', to:'2026-10-16'}).total, 400);
});
test('零值算作已记录，空白算作未记录', () => {
  const result = query(data, {search:'王'});
  assert.equal(result.rows[0].recorded, 2);
  assert.equal(result.rows[0].missing, 1);
  assert.equal(result.rows[0].daily[1].amountCents, 0);
});
test('最近七天按数据最新日期计算，跨月准确', () => {
  assert.deepEqual(presetRange(['2026-09-24','2026-10-02'], 7), {from:'2026-09-26',to:'2026-10-02'});
});
test('空搜索结果与错误日期范围明确处理', () => {
  assert.equal(query(data, {search:'不存在'}).rows.length, 0);
  assert.throws(() => query(data, {from:'2026-10-17',to:'2026-10-16'}));
});
test('统计使用整数分，排序后合计保持一致', () => {
  const result = query(data);
  assert.equal(result.total, 33029);
  assert.equal(result.rows[0].id, 'b');
  assert.equal(query(data, {sort:'name'}).total, result.total);
});

test('最近一天、三天和自定义五天都包含最新数据日', () => {
  assert.deepEqual(presetRange(data.dates, 1), {from:'2026-10-17',to:'2026-10-17'});
  assert.deepEqual(presetRange(data.dates, 3), {from:'2026-10-15',to:'2026-10-17'});
  assert.deepEqual(presetRange(data.dates, 5), {from:'2026-10-13',to:'2026-10-17'});
  assert.throws(() => presetRange(data.dates, 0.5));
  assert.throws(() => presetRange(data.dates, 366));
});
test('固定2026年，最近范围不跨入2025年', () => {
  const dates = ['2025-12-31','2026-01-02','2027-01-01'];
  assert.deepEqual(presetRange(dates, 7), {from:'2026-01-01',to:'2026-01-02'});
  assert.deepEqual(presetRange(dates, 0), {from:'2026-01-02',to:'2026-01-02'});
  assert.deepEqual(query({...data, dates}).days, ['2026-01-02']);
  assert.throws(() => query(data, {from:'2025-12-31'}));
  assert.throws(() => presetRange(['2025-12-31'], 1));
});
test('月日选择器正确处理二月和三十天月份', () => {
  assert.equal(daysInMonth(2), 28);
  assert.equal(daysInMonth(9), 30);
  assert.equal(makeDate(2, 28), '2026-02-28');
  assert.throws(() => makeDate(2, 29));
  assert.throws(() => query(data, {from:'2026-02-31'}));
});
test('0流水预警随司机和日期筛选变化，空白不触发', () => {
  const all = query(data);
  assert.equal(all.zeroDrivers, 1);
  assert.equal(all.zeroRecords, 1);
  assert.equal(all.rows.find(driver => driver.id === 'a').zeroDays, 1);
  assert.equal(query(data, {search:'李'}).zeroRecords, 0);
  assert.equal(query(data, {from:'2026-10-17',to:'2026-10-17'}).zeroRecords, 0);
  const blank = query(data, {search:'王',from:'2026-10-15',to:'2026-10-15'});
  assert.equal(blank.missing, 1);
  assert.equal(blank.zeroRecords, 0);
});

const weekDates = ['2026-10-11','2026-10-12','2026-10-13','2026-10-14','2026-10-15','2026-10-16','2026-10-17'];
const weekData = {
  dates: weekDates,
  drivers: [{id:'zero',name:'连续零流水'}, {id:'six',name:'六天零流水'}, {id:'blank',name:'缺一天记录'}],
  records: [
    ...weekDates.map(date => ({driverId:'zero',date,amountCents:0})),
    ...weekDates.map((date,index) => ({driverId:'six',date,amountCents:index === 0 ? 100 : 0})),
    ...weekDates.map(date => ({driverId:'blank',date,amountCents:date === '2026-10-15' ? null : 0})),
  ],
};

test('默认连续七天每天为零才预警，六天和空白均不报红', () => {
  const result = query(weekData);
  assert.equal(result.warningDays, 7);
  assert.equal(result.warningDrivers, 1);
  assert.equal(result.rows.find(row => row.id === 'zero').hasZeroWarning, true);
  assert.equal(result.rows.find(row => row.id === 'six').hasZeroWarning, false);
  assert.equal(result.rows.find(row => row.id === 'blank').hasZeroWarning, false);
  assert.equal(query(data).warningDrivers, 0);
});

test('预警天数独立于查询区间，最新一天仍检查完整七天', () => {
  const result = query(weekData, {from:'2026-10-17',to:'2026-10-17'});
  assert.equal(result.days.length, 1);
  assert.equal(result.warningDrivers, 1);
  assert.deepEqual(result.warningRange, {from:'2026-10-11',to:'2026-10-17'});
  assert.equal(result.rows.find(row => row.id === 'zero').daily[0].zeroWarning, true);
  assert.equal(result.rows.find(row => row.id === 'six').daily[0].zeroWarning, false);
});

test('自定义连续三天改变预警而不改变查询金额与日期', () => {
  const standard = query(weekData);
  const custom = query(weekData, {warningDays:3});
  assert.equal(custom.warningDrivers, 2);
  assert.equal(custom.total, standard.total);
  assert.deepEqual(custom.days, standard.days);
  const zeros = custom.rows.find(row => row.id === 'zero');
  assert.equal(zeros.daily.filter(record => record.zeroWarning).length, 3);
  assert.equal(zeros.daily.find(record => record.date === '2026-10-14').zeroWarning, false);
  assert.throws(() => query(weekData, {warningDays:0}));
  assert.throws(() => query(weekData, {warningDays:1.5}));
  assert.throws(() => query(weekData, {warningDays:366}));
});

test('缺少自然日期或记录不足不触发，金额相抵为零也不误报', () => {
  assert.equal(query({...weekData,dates:weekDates.filter(day => day !== '2026-10-14')}).warningDrivers, 0);
  assert.equal(query(weekData, {warningDays:8}).warningDrivers, 0);
  const cancellation = {
    dates:weekDates,
    drivers:[{id:'a',name:'金额相抵'}],
    records:weekDates.map((date,index) => ({driverId:'a',date,amountCents:index === 0 ? 100 : index === 1 ? -100 : 0})),
  };
  const result = query(cancellation);
  assert.equal(result.total, 0);
  assert.equal(result.warningDrivers, 0);
});

test('金额从低到高排序，未记录排最后，保留真实零值', () => {
  const source = {
    ...data,
    drivers:[...data.drivers,{id:'empty',name:'没有记录'},{id:'real-zero',name:'真实零值'}],
    records:[...data.records,{driverId:'empty',date:'2026-10-17',amountCents:null},{driverId:'real-zero',date:'2026-10-17',amountCents:0}],
  };
  const result = query(source, {sort:'amount-asc'});
  assert.deepEqual(result.rows.map(row => row.id), ['real-zero','a','b','empty']);
  assert.equal(result.total, query(source).total);
  assert.deepEqual(query(source).rows.map(row => row.id), ['b','a','real-zero','empty']);
});

test('紧凑视图分类筛选与计数', () => {
  const rows = [
    {recorded: 2, hasZeroWarning: true},
    {recorded: 0, hasZeroWarning: false},
    {recorded: 1, hasZeroWarning: false},
  ];
  assert.deepEqual(tabCounts(rows), {all: 3, warning: 1, missing: 1});
  assert.equal(filterRows(rows, 'warning').length, 1);
  assert.equal(filterRows(rows, 'missing')[0].recorded, 0);
  assert.equal(filterRows(rows, 'all').length, 3);
  assert.equal(filterRows(rows, 'unknown').length, 3);
});
