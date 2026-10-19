const form = document.getElementById('upload-form');
const button = document.getElementById('upload-button');
const status = document.getElementById('upload-status');
const error = document.getElementById('upload-error');
function showAudit(audit) {
  const current = document.getElementById('current-info');
  current.replaceChildren();
  for (const text of [`${audit.dateFrom} 至 ${audit.dateTo}`, `${audit.included_drivers} 名司机，${audit.dateColumns} 天，合计 ${(audit.total_amount_cents / 100).toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2})} 元`, `已排除 ${audit.excluded_red_drivers} 名红色姓名司机。`]) {
    const p = document.createElement('p');
    p.textContent = text;
    current.append(p);
  }
}
form.addEventListener('submit', async event => {
  event.preventDefault();
  const file = document.getElementById('workbook').files[0];
  if (!file) return;
  error.hidden = true;
  if (!file.name.toLowerCase().endsWith('.xlsx') || file.size > 10 * 1024 * 1024) {
    error.textContent = '请选择不超过 10 MB 的 .xlsx 文件。';
    error.hidden = false;
    return;
  }
  button.disabled = true;
  button.textContent = '正在读取并核验 Excel…';
  status.hidden = false;
  status.textContent = '正在上传，网站将自动过滤红色姓名并核验流水。';
  try {
    const response = await fetch('/api/upload', { method: 'POST', headers: { 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content }, body: new FormData(form) });
    if (response.status === 401) { location.assign('/login?next=/admin'); return; }
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '上传未成功，请重试。');
    const audit = result.audit;
    status.textContent = `上传成功。已更新 ${audit.included_drivers} 名司机、${audit.dateColumns} 天的流水，排除 ${audit.excluded_red_drivers} 名红色姓名司机。`;
    showAudit(audit);
    form.reset();
  } catch (reason) {
    status.hidden = true;
    error.textContent = reason.message === 'Failed to fetch' ? '网络连接中断，请检查后重新上传。原有数据不会因上传失败而删除。' : reason.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = '上传并更新流水';
  }
});

let checkingSync = false;
let syncVersion;
async function checkSync() {
  if (!document.getElementById('sync-status') || checkingSync || document.hidden) return;
  checkingSync = true;
  try {
    const response = await fetch('/api/local-sync', {cache:'no-store'});
    if (!response.ok) return;
    const state = await response.json();
    if (!state.sync.enabled) return;
    const status = document.getElementById('sync-status');
    status.textContent = state.sync.message;
    status.classList.toggle('error', state.sync.state === 'error');
    document.getElementById('sync-time').textContent = state.sync.lastSyncedAt ? `上次检查：${new Date(state.sync.lastSyncedAt).toLocaleString('zh-CN')}` : '';
    if (state.audit && state.version !== syncVersion) {
      showAudit(state.audit);
      syncVersion = state.version;
    }
  } catch { /* The watcher keeps running even if this page loses connectivity. */ }
  finally { checkingSync = false; }
}
checkSync();
setInterval(checkSync, 4000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) checkSync(); });
