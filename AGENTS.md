# WebIncome 交接说明（给 CODEX）

最后更新：2026-10-20。上一轮 CODEX 会话在推送 GitHub 后因用量上限中断，本文件记录之后完成的工作和当前状态。继续修改前请先读完。

## 项目是什么

Flask 只读司机流水查询站：管理员上传 `.xlsx`，网站读取 `Sheet2!A:Y`，排除红色姓名，逐格核对 SUMIF 结果后保存查询数据；手机和电脑用查询密码登录后按司机、日期查看。原始 Excel 不会被修改，业务数据不进入 Git。

## 当前状态（已完成）

- 功能：登录/权限、Excel 上传与校验、查询筛选、连续 0 流水预警、三种排序、卡片/紧凑双视图、手机/深色模式、本机自动同步。
- 查看权限：线上已取消查看密码（`WEBINCOME_PUBLIC_VIEW=1`），打开网址即可查询；上传 Excel 仍需管理员密码。任何拿到网址的人都能看到流水数据。
- 测试：17 项 Python 测试、16 项前端测试全部通过。
  - `python -m unittest discover -s tests -v`
  - `node --test tests/query.test.mjs`
- Git：`main` 分支，私有仓库 `CandyTea/WebIncome`。
- 线上部署：已完成，服务器为腾讯云 OpenCloudOS 9.6，Python 3.11。
  - 代码：`/opt/webincome`
  - 数据：`/var/lib/webincome/current.json`
  - 配置：`/etc/webincome.env`（含密码和同步令牌，权限 600，不提交）
  - 服务：`webincome.service`，gunicorn 监听 `0.0.0.0:8765`
  - 服务器上另有 Docker 项目「讯览」占用 80/8088，Node 服务占用 3000，**不要动它们**。
  - 本机已上传一份真实流水表做验收：26 名司机、593 个数值格、31 个空白、196 个零值，合计 113,538.98 元，与本地核对一致。
  - 服务器登录信息、管理员/查看密码、同步令牌保存在本机 `.local/server-credentials.txt`（Git 忽略）。
  - 本机已生成专用部署密钥并安装到服务器 root 的 `authorized_keys`，日常用 `ssh -i ~/.ssh/webincome_deploy root@124.221.0.127`；不再依赖密码。
  - 本轮改动已推送到 GitHub：`106e597`（远程同步）、`e2f2923`（部署记录）、`782522b`（公开查看）。

## 本轮新增/修改

1. `app.py`
   - 新增 `SYNC_TOKEN` 配置，对应环境变量 `WEBINCOME_SYNC_TOKEN`。
   - 新增 `POST /api/sync`：用 `X-Sync-Token` 或 `Authorization: Bearer` 认证，只接受 `.xlsx`，复用同一套导入校验；未配置令牌时返回 404，令牌错误返回 401。
   - 抽出 `parse_workbook()`，上传与同步共用；失败时保留上一份有效数据。
2. `local_sync.py`
   - 回调增加 `contents` 参数；新增 `SyncRejected` / `RetryableSyncError`，网络或服务器临时故障会自动重试，不必等下一次保存。
3. `remote_sync.py`（新增）
   - 监测本地 Excel，核验后通过 `/api/sync` 推送到远程网站；支持 `--once`、配置文件、重试间隔。
4. `tests/test_remote_sync.py`（新增，5 项）
   - 令牌上传、错误令牌/损坏文件保留旧数据、Bearer 认证、未配置令牌时关闭接口、临时失败自动重试、真实 HTTP 推送。
5. `远程自动同步.cmd`（新增）
   - 读取 `.local/remote-sync.txt`（`url=`、`token=`、`watch=`）并运行 `remote_sync.py`。
6. 文档：`README.md`、`部署说明.md`、`.env.example` 增加远程同步说明和 `WEBINCOME_SYNC_TOKEN`。
7. 公开查看：`app.py` 新增 `WEBINCOME_PUBLIC_VIEW`；为 `1` 时查看页和查询接口无需登录，管理员上传仍需密码。`本地自动同步.cmd` 和线上 `/etc/webincome.env` 已设为 `1`。
8. 查询页新增卡片/紧凑双视图（`dist/`）：紧凑视图一行一个司机，点行从底部弹出每日明细，顶部有“全部 / 预警 / 未记录”分类；视图和分类写入网址并记住选择。手机紧凑模式默认收起筛选区，原卡片视图保留。

## 尚未完成 / 下一步

1. **腾讯云安全组放行 TCP 8765**。当前只有 22、80、3000 放行，外网访问 `http://服务器IP:8765` 会超时；服务器本机 `127.0.0.1:8765` 正常。放行后即可从手机/电脑访问。
2. 目前是 HTTP 直连（无域名、无 HTTPS），密码和流水明文经过公网，适合临时自用。后续有域名时按 `部署说明.md` 接入 Nginx/HTTPS，并把 gunicorn 改回监听 `127.0.0.1`。
3. iPhone Safari / Mac Safari 真机验收（月日选择框、快捷范围、横屏、深色模式）。
4. 服务器目前用打包上传部署，没有配置 GitHub Deploy Key；以后若要 `git pull` 更新，需要生成只读 Deploy Key 并加到仓库。
5. 服务器目前用打包上传部署，没有配置 GitHub Deploy Key；服务器访问 GitHub 不稳定，暂不建议改为 `git pull`。需要时再生成只读 Deploy Key 并加到仓库。

## 验证记录（2026-10-20）

- Python 17 项、前端 15 项测试通过。
- 服务器本机 `/login` 返回 200。
- `POST /api/sync`：错误令牌 401，正确令牌 200，导入统计与本地一致。
- 本机 `remote_sync.py --once` 推送成功，服务器 `current.json` 的 `source.kind` 为 `remote-sync`。
- 公开查看：`/` 和 `/data/sheet2.json` 未登录返回 200；`/admin` 返回 302；未登录上传 401；管理员登录后 `/admin` 返回 200。
- 紧凑视图：390/375/360 像素无横向溢出；卡片/紧凑切换、预警/未记录标签、底部弹层（手机）和居中弹窗（桌面）、筛选展开收起均通过无头 Chrome 验证。
- GitHub 推送成功（`ae67fe9..106e597`）。
- 外网 `http://124.221.0.127:8765` 仍被腾讯云安全组拦截，待放行后即可访问。

## 操作命令

```bash
# 服务器
systemctl status webincome
systemctl restart webincome
journalctl -u webincome -n 100 --no-pager

# 本机测试
python -m unittest discover -s tests -v
node --test tests/query.test.mjs

# 本机运行（本地网站 + 监测）
本地自动同步.cmd

# 远程自动同步
远程自动同步.cmd
```

## 约束

- 不要提交 `.local/`、`.venv/`、`*.xlsx`、密码或令牌。
- 不要修改或回写用户的原始 Excel。
- 不要改动服务器上「讯览」和 3000 端口的现有服务。
- 新增导入规则时，保持“失败保留上一份有效数据”的行为，并补充使用虚构工作簿的测试。
