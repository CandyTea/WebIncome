using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

[assembly: System.Runtime.Versioning.TargetFramework(".NETFramework,Version=v4.8", FrameworkDisplayName = ".NET Framework 4.8")]

namespace WebIncomeDesktop
{
    internal static class Config
    {
        public static Dictionary<string, string> Read(string file)
        {
            var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (!File.Exists(file)) return values;
            foreach (string line in File.ReadAllLines(file, Encoding.UTF8))
            {
                int split = line.IndexOf('=');
                if (split < 1 || line.TrimStart().StartsWith("#")) continue;
                values[line.Substring(0, split).Trim()] = line.Substring(split + 1).Trim();
            }
            return values;
        }

        public static string Get(Dictionary<string, string> values, string key, string fallback)
        {
            string value;
            return values.TryGetValue(key, out value) && !String.IsNullOrWhiteSpace(value) ? value : fallback;
        }

        public static void Write(string file, Dictionary<string, string> values)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(file));
            string temporary = file + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                var lines = new StringBuilder();
                foreach (var item in values)
                {
                    if (item.Key.IndexOfAny(new[] { '\r', '\n', '=' }) >= 0 || item.Value.IndexOfAny(new[] { '\r', '\n' }) >= 0)
                        throw new ArgumentException("设置中不能包含换行符。");
                    lines.Append(item.Key).Append('=').Append(item.Value).Append('\n');
                }
                File.WriteAllText(temporary, lines.ToString(), new UTF8Encoding(false));
                if (File.Exists(file)) File.Replace(temporary, file, null);
                else File.Move(temporary, file);
            }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
        }

        public static string Workbook(string value)
        {
            string file = value.Trim().Trim('"');
            if (String.IsNullOrWhiteSpace(file) || !File.Exists(file)) throw new ArgumentException("请先选择一个存在的 Excel 文件。");
            if (!String.Equals(Path.GetExtension(file), ".xlsx", StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("请选择 .xlsx 格式的工作簿。");
            if (new FileInfo(file).Length > 10 * 1024 * 1024) throw new ArgumentException("Excel 文件不能超过 10 MB。");
            return Path.GetFullPath(file);
        }

        public static string Url(string text)
        {
            Uri uri;
            if (!Uri.TryCreate(text.Trim(), UriKind.Absolute, out uri) || (uri.Scheme != "https" && uri.Scheme != "http") || String.IsNullOrEmpty(uri.Host))
                throw new ArgumentException("请填写完整网站地址，例如 https://你的网站域名。");
            if (!String.IsNullOrEmpty(uri.UserInfo) || !String.IsNullOrEmpty(uri.Query) || !String.IsNullOrEmpty(uri.Fragment))
                throw new ArgumentException("请填写网站首页地址，不带账号、密码或查询条件。");
            return uri.AbsoluteUri.TrimEnd('/');
        }
    }

    internal static class Theme
    {
        public static readonly Color Background = Color.FromArgb(245, 247, 251);
        public static readonly Color Text = Color.FromArgb(23, 41, 64);
        public static readonly Color Muted = Color.FromArgb(82, 99, 121);
        public static readonly Color Border = Color.FromArgb(207, 217, 230);
        public static readonly Color Blue = Color.FromArgb(23, 92, 211);
        public static readonly Color Error = Color.FromArgb(172, 35, 30);
        public static readonly Color Success = Color.FromArgb(25, 106, 66);
        public static Font Body { get { return new Font("Microsoft YaHei UI", 10F); } }

        public static Button Button(string text, bool primary)
        {
            var button = new Button { Text = text, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, MinimumSize = new Size(106, 40), Padding = new Padding(12, 5, 12, 5), Margin = new Padding(0, 0, 10, 8), FlatStyle = FlatStyle.Flat, UseVisualStyleBackColor = false };
            button.FlatAppearance.BorderColor = primary ? Blue : Border;
            button.BackColor = primary ? Blue : Color.White;
            button.ForeColor = primary ? Color.White : Text;
            button.FlatAppearance.MouseOverBackColor = primary ? Color.FromArgb(18, 74, 168) : Color.FromArgb(237, 243, 252);
            return button;
        }

        public static Label Label(string text, bool secondary)
        {
            return new Label { Text = text, AutoSize = true, ForeColor = secondary ? Muted : Text, Margin = new Padding(0, 0, 0, 8) };
        }
    }

    internal sealed class ServerForm : Form
    {
        private readonly TextBox address;
        private readonly TextBox token;
        public string ServerUrl { get; private set; }
        public string SyncToken { get; private set; }

        public ServerForm(string url, string secret)
        {
            Text = "服务器设置";
            Font = Theme.Body;
            AutoScaleDimensions = new SizeF(96, 96);
            AutoScaleMode = AutoScaleMode.Dpi;
            ClientSize = new Size(570, 300);
            MinimumSize = new Size(450, 330);
            StartPosition = FormStartPosition.CenterParent;
            BackColor = Theme.Background;
            MaximizeBox = false;
            MinimizeBox = false;
            var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(22), ColumnCount = 1, RowCount = 7, AutoScroll = true };
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            layout.Controls.Add(Theme.Label("网站地址", false));
            address = new TextBox { Text = url, Dock = DockStyle.Top, Margin = new Padding(0, 0, 0, 16) };
            layout.Controls.Add(address);
            layout.Controls.Add(Theme.Label("同步令牌", false));
            token = new TextBox { Text = secret, Dock = DockStyle.Top, UseSystemPasswordChar = true, Margin = new Padding(0, 0, 0, 8) };
            layout.Controls.Add(token);
            var show = new CheckBox { Text = "显示令牌", AutoSize = true, Margin = new Padding(0, 0, 0, 12) };
            show.CheckedChanged += delegate { token.UseSystemPasswordChar = !show.Checked; };
            layout.Controls.Add(show);
            var help = Theme.Label("沿用服务器上的同步令牌。它用于上传，不是管理员登录密码。", true);
            help.MaximumSize = new Size(510, 0);
            layout.Controls.Add(help);
            var actions = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Top, WrapContents = true };
            var save = Theme.Button("保存设置", true);
            var cancel = Theme.Button("取消", false);
            save.Click += delegate
            {
                try
                {
                    ServerUrl = Config.Url(address.Text);
                    SyncToken = token.Text.Trim();
                    if (String.IsNullOrEmpty(SyncToken) || SyncToken.IndexOfAny(new[] { '\r', '\n' }) >= 0) throw new ArgumentException("请填写有效的同步令牌。");
                    DialogResult = DialogResult.OK;
                }
                catch (ArgumentException error) { MessageBox.Show(this, error.Message, "请检查设置", MessageBoxButtons.OK, MessageBoxIcon.Information); }
            };
            cancel.DialogResult = DialogResult.Cancel;
            actions.Controls.Add(save);
            actions.Controls.Add(cancel);
            layout.Controls.Add(actions);
            Controls.Add(layout);
            AcceptButton = save;
            CancelButton = cancel;
        }
    }

    internal sealed class SyncForm : Form
    {
        private readonly string root;
        private readonly string runtimeRoot;
        private readonly string remotePath;
        private readonly string localPath;
        private Dictionary<string, string> remoteValues;
        private readonly TextBox workbook;
        private readonly RadioButton remote;
        private readonly RadioButton local;
        private readonly Label destination;
        private readonly Label status;
        private readonly TextBox log;
        private readonly Button browse;
        private readonly Button settings;
        private readonly Button start;
        private readonly Button stop;
        private readonly Button save;
        private readonly Button open;
        private readonly System.Windows.Forms.Timer timer;
        private Process worker;
        private Task<string> outputRead;
        private Task<string> errorRead;
        private bool stopping;
        private bool lastError;

        public SyncForm(string projectRoot, string codeRoot = null)
        {
            root = projectRoot;
            runtimeRoot = codeRoot ?? projectRoot;
            remotePath = Path.Combine(root, ".local", "remote-sync.txt");
            localPath = Path.Combine(root, ".local", "local-sync.txt");
            remoteValues = Config.Read(remotePath);
            var localValues = Config.Read(localPath);
            Text = "Excel 同步助手";
            Font = Theme.Body;
            ForeColor = Theme.Text;
            BackColor = Theme.Background;
            AutoScaleDimensions = new SizeF(96, 96);
            AutoScaleMode = AutoScaleMode.Dpi;
            ClientSize = new Size(760, 710);
            MinimumSize = new Size(600, 460);
            StartPosition = FormStartPosition.CenterScreen;
            KeyPreview = true;

            var shell = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 2, Padding = new Padding(22, 18, 22, 14) };
            shell.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            shell.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            shell.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            var body = new TableLayoutPanel { Dock = DockStyle.Fill, AutoScroll = true, ColumnCount = 1, RowCount = 4 };
            body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            body.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            body.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            body.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            body.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            var heading = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true, FlowDirection = FlowDirection.TopDown, WrapContents = false, Margin = new Padding(0, 0, 0, 12) };
            var title = Theme.Label("Excel 同步助手", false);
            title.Font = new Font("Microsoft YaHei UI", 17F, FontStyle.Bold);
            heading.Controls.Add(title);
            heading.Controls.Add(Theme.Label("选好流水表，保存 Excel 后自动更新网页。", true));
            body.Controls.Add(heading, 0, 0);

            var fileGrid = new TableLayoutPanel { Dock = DockStyle.Top, AutoSize = true, ColumnCount = 2, RowCount = 2, Padding = new Padding(12) };
            fileGrid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            fileGrid.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            workbook = new TextBox { Name = "workbook", ReadOnly = true, Multiline = true, WordWrap = true, ScrollBars = ScrollBars.Vertical, Height = 64, Dock = DockStyle.Fill, BackColor = Color.White, Margin = new Padding(0, 0, 12, 10) };
            string saved = Config.Get(localValues, "watch", Config.Get(remoteValues, "watch", Path.Combine(root, "全部流水表(1).xlsx")));
            if (!Path.IsPathRooted(saved.Trim('"'))) saved = Path.Combine(root, saved.Trim('"'));
            workbook.Text = saved.Trim('"');
            browse = Theme.Button("选择文件…", false);
            browse.Name = "browse";
            browse.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            browse.Click += delegate { ChooseFile(); };
            fileGrid.Controls.Add(workbook, 0, 0);
            fileGrid.Controls.Add(browse, 1, 0);
            var fileNote = Theme.Label("原始 Excel 只读：不会改名、移动、覆盖或回写。", true);
            fileGrid.Controls.Add(fileNote, 0, 1);
            fileGrid.SetColumnSpan(fileNote, 2);
            body.Controls.Add(Section("本地 Excel 文件", fileGrid), 0, 1);

            var targetGrid = new TableLayoutPanel { Dock = DockStyle.Top, AutoSize = true, ColumnCount = 2, RowCount = 2, Padding = new Padding(12) };
            targetGrid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            targetGrid.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            var modes = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true, WrapContents = true };
            remote = new RadioButton { Text = "同步到服务器", AutoSize = true, Margin = new Padding(0, 5, 20, 12) };
            local = new RadioButton { Text = "仅本地预览", AutoSize = true, Margin = new Padding(0, 5, 0, 12) };
            modes.Controls.Add(remote);
            modes.Controls.Add(local);
            settings = Theme.Button("服务器设置", false);
            settings.Click += delegate { EditServer(); };
            targetGrid.Controls.Add(modes, 0, 0);
            targetGrid.Controls.Add(settings, 1, 0);
            destination = Theme.Label("", true);
            targetGrid.Controls.Add(destination, 0, 1);
            targetGrid.SetColumnSpan(destination, 2);
            body.Controls.Add(Section("同步到哪里", targetGrid), 0, 2);

            var activity = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 1, Padding = new Padding(12), MinimumSize = new Size(0, 100) };
            activity.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            activity.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            status = Theme.Label("尚未启动", false);
            status.Font = new Font("Microsoft YaHei UI", 11F, FontStyle.Bold);
            log = new TextBox { Name = "activityLog", ReadOnly = true, Multiline = true, WordWrap = true, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Fill, BackColor = Color.White, BorderStyle = BorderStyle.FixedSingle, MinimumSize = new Size(0, 54) };
            activity.Controls.Add(log, 0, 0);
            var activityGroup = new GroupBox { Text = "运行记录", Dock = DockStyle.Fill, Padding = new Padding(0, 8, 0, 0), Margin = new Padding(0, 0, 0, 0), MinimumSize = new Size(0, 150) };
            activityGroup.Controls.Add(activity);
            body.Controls.Add(activityGroup, 0, 3);

            var footer = new TableLayoutPanel { AutoSize = true, Dock = DockStyle.Bottom, ColumnCount = 1, RowCount = 3, Padding = new Padding(0, 14, 0, 0) };
            var actions = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true, WrapContents = true };
            start = Theme.Button("开始同步", true);
            start.Name = "start";
            stop = Theme.Button("停止同步", false);
            stop.Name = "stop";
            stop.Enabled = false;
            save = Theme.Button("保存设置", false);
            open = Theme.Button("打开网页", false);
            start.Click += delegate { StartSync(); };
            stop.Click += delegate { StopSync(); };
            save.Click += delegate { try { SaveSettings(); SetStatus("设置已保存，尚未启动同步。", false); } catch (Exception error) { SetStatus(error.Message, true); } };
            open.Click += delegate { OpenPage(); };
            actions.Controls.Add(start);
            actions.Controls.Add(stop);
            actions.Controls.Add(save);
            actions.Controls.Add(open);
            footer.Controls.Add(status, 0, 0);
            footer.Controls.Add(actions, 0, 1);
            var footerNote = Theme.Label("保持本软件运行。关闭软件会停止同步；未启动时不会上传。", true);
            footerNote.Margin = new Padding(0);
            footer.Controls.Add(footerNote, 0, 2);
            shell.Controls.Add(body, 0, 0);
            shell.Controls.Add(footer, 0, 1);
            Controls.Add(shell);

            bool useRemote = Config.Get(localValues, "mode", "remote") == "remote" && !String.IsNullOrEmpty(Config.Get(remoteValues, "url", ""));
            remote.Checked = useRemote;
            local.Checked = !useRemote;
            remote.CheckedChanged += delegate { UpdateDestination(); };
            local.CheckedChanged += delegate { UpdateDestination(); };
            Resize += delegate
            {
                int width = Math.Max(230, ClientSize.Width - shell.Padding.Horizontal - 44);
                destination.MaximumSize = new Size(width, 0);
                fileNote.MaximumSize = new Size(width, 0);
                footerNote.MaximumSize = new Size(Math.Max(230, ClientSize.Width - shell.Padding.Horizontal), 0);
                status.MaximumSize = new Size(width, 0);
            };
            KeyDown += delegate(object sender, KeyEventArgs e)
            {
                if (e.Control && e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; if (worker == null) StartSync(); }
                if (e.KeyCode == Keys.Escape && worker != null) { e.SuppressKeyPress = true; StopSync(); }
            };
            timer = new System.Windows.Forms.Timer { Interval = 200 };
            timer.Tick += delegate { PollWorker(); };
            timer.Start();
            FormClosing += delegate { if (worker != null) { try { if (!worker.HasExited) { worker.Kill(); worker.WaitForExit(1200); } } catch (InvalidOperationException) { } } };
            FormClosed += delegate { timer.Dispose(); if (worker != null) worker.Dispose(); };
            Shown += delegate { Size workArea = Screen.FromControl(this).WorkingArea.Size; if (Width > workArea.Width - 20 || Height > workArea.Height - 30) Size = new Size(Math.Min(Width, workArea.Width - 20), Math.Min(Height, workArea.Height - 30)); browse.Select(); };
            UpdateDestination();
            AppendLog("选择 Excel 后点“开始同步”。也可以只保存选择，下次继续使用。");
        }

        private static GroupBox Section(string title, Control content)
        {
            var group = new GroupBox { Text = title, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, Dock = DockStyle.Top, Padding = new Padding(0, 8, 0, 0), Margin = new Padding(0, 0, 0, 12) };
            group.Controls.Add(content);
            return group;
        }

        private void ChooseFile()
        {
            using (var picker = new OpenFileDialog { Title = "选择要同步的流水表", Filter = "Excel 工作簿 (*.xlsx)|*.xlsx", CheckFileExists = true, CheckPathExists = true, Multiselect = false, RestoreDirectory = true })
            {
                string directory = Path.GetDirectoryName(workbook.Text);
                picker.InitialDirectory = Directory.Exists(directory) ? directory : root;
                if (picker.ShowDialog(this) != DialogResult.OK) return;
                try { workbook.Text = Config.Workbook(picker.FileName); SetStatus("文件已选好，点击开始同步或保存设置。", false); }
                catch (ArgumentException error) { SetStatus(error.Message, true); }
            }
        }

        private void EditServer()
        {
            using (var dialog = new ServerForm(Config.Get(remoteValues, "url", ""), Config.Get(remoteValues, "token", "")))
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                try
                {
                    var updated = new Dictionary<string, string>(remoteValues, StringComparer.OrdinalIgnoreCase);
                    updated["url"] = dialog.ServerUrl;
                    updated["token"] = dialog.SyncToken;
                    Config.Write(remotePath, updated);
                    remoteValues = updated;
                    UpdateDestination();
                    SetStatus("服务器设置已保存。", false);
                }
                catch (IOException) { SetStatus("服务器设置未能保存，请检查配置文件是否被占用。", true); }
                catch (UnauthorizedAccessException) { SetStatus("没有权限保存服务器设置。", true); }
            }
        }

        private void SaveSettings()
        {
            string selected = Config.Workbook(workbook.Text);
            if (remote.Checked)
            {
                Config.Url(Config.Get(remoteValues, "url", ""));
                if (String.IsNullOrWhiteSpace(Config.Get(remoteValues, "token", ""))) throw new ArgumentException("请先在服务器设置里填写同步令牌。");
            }
            var updated = new Dictionary<string, string>(remoteValues, StringComparer.OrdinalIgnoreCase);
            updated["watch"] = selected;
            // These fixed destinations can never be the selected .xlsx file.
            Config.Write(remotePath, updated);
            var localValues = Config.Read(localPath);
            localValues["watch"] = selected;
            localValues["mode"] = remote.Checked ? "remote" : "local";
            Config.Write(localPath, localValues);
            remoteValues = updated;
            workbook.Text = selected;
        }

        private void UpdateDestination()
        {
            string url = Config.Get(remoteValues, "url", "");
            destination.Text = local.Checked ? "更新本机网页：http://127.0.0.1:8765" : String.IsNullOrEmpty(url) ? "服务器尚未配置，请先点“服务器设置”。" : "更新服务器网页：" + url;
        }

        private void StartSync()
        {
            if (worker != null) return;
            try
            {
                SaveSettings();
                string python = Path.Combine(runtimeRoot, ".venv", "Scripts", "python.exe");
                if (!File.Exists(python)) throw new InvalidOperationException("找不到本地运行环境，请先按 README 安装项目依赖。");
                string config = remote.Checked ? remotePath : localPath;
                // The inherited environment may contain both PATH and Path.
                // Do not materialize .NET Framework's case-insensitive copy.
                var info = new ProcessStartInfo(python, "-X utf8 -u desktop_sync.py --mode " + (remote.Checked ? "remote" : "local") + " --config \"" + config + "\"") { WorkingDirectory = runtimeRoot, UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true, StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8 };
                worker = new Process { StartInfo = info };
                worker.Start();
                outputRead = worker.StandardOutput.ReadLineAsync();
                errorRead = worker.StandardError.ReadLineAsync();
                stopping = false;
                lastError = false;
                SetRunning(true);
                SetStatus("正在启动同步…", false);
            }
            catch (Exception error)
            {
                if (worker != null) { worker.Dispose(); worker = null; }
                SetRunning(false);
                SetStatus(error.Message, true);
            }
        }

        private void StopSync()
        {
            if (worker == null || stopping) return;
            try { stopping = true; SetStatus("正在停止同步…", false); if (!worker.HasExited) worker.Kill(); }
            catch (InvalidOperationException) { }
        }

        private void SetRunning(bool running)
        {
            browse.Enabled = settings.Enabled = remote.Enabled = local.Enabled = save.Enabled = start.Enabled = !running;
            start.BackColor = running ? Color.FromArgb(226, 232, 241) : Theme.Blue;
            start.ForeColor = running ? Theme.Muted : Color.White;
            stop.Enabled = running;
        }

        private void Pump(ref Task<string> pending, StreamReader stream, bool isError)
        {
            for (int count = 0; count < 40 && pending != null && pending.IsCompleted; count++)
            {
                string line = pending.GetAwaiter().GetResult();
                pending = line == null ? null : stream.ReadLineAsync();
                if (line == null) break;
                if (isError) { if (!String.IsNullOrWhiteSpace(line)) AppendLog(line); continue; }
                try
                {
                    var data = new JavaScriptSerializer().Deserialize<Dictionary<string, string>>(line);
                    string state = data["state"];
                    bool failed = state == "error";
                    SetStatus(data["message"], failed);
                    if (state == "synced") status.ForeColor = Theme.Success;
                }
                catch (ArgumentException) { AppendLog(line); }
                catch (KeyNotFoundException) { AppendLog(line); }
            }
        }

        private void PollWorker()
        {
            if (worker == null) return;
            try
            {
                Pump(ref outputRead, worker.StandardOutput, false);
                Pump(ref errorRead, worker.StandardError, true);
                if (worker.HasExited && outputRead == null && errorRead == null)
                {
                    int exitCode = worker.ExitCode;
                    worker.Dispose();
                    worker = null;
                    SetRunning(false);
                    if (stopping) SetStatus("已停止。之后保存 Excel 不会自动同步。", false);
                    else if (!lastError) SetStatus(exitCode == 0 ? "同步已结束。" : "同步进程已退出，请查看运行记录后重试。", exitCode != 0);
                }
            }
            catch (Exception) { SetStatus("读取运行状态失败。请停止同步后重试。", true); }
        }

        private string Redact(string message)
        {
            string secret = Config.Get(remoteValues, "token", "");
            return String.IsNullOrEmpty(secret) ? message : message.Replace(secret, "[令牌已隐藏]");
        }

        private void SetStatus(string message, bool failed)
        {
            lastError = failed;
            status.Text = Redact(message);
            status.ForeColor = failed ? Theme.Error : Theme.Text;
            AppendLog(message);
        }

        private void AppendLog(string message)
        {
            if (log.TextLength > 50000) log.Text = log.Text.Substring(log.TextLength - 25000);
            log.AppendText("[" + DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)).ToString("HH:mm:ss") + "] " + Redact(message) + Environment.NewLine);
        }

        private void OpenPage()
        {
            try { string url = local.Checked ? "http://127.0.0.1:8765" : Config.Url(Config.Get(remoteValues, "url", "")); Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); }
            catch (Exception) { SetStatus("无法打开网页，请先检查服务器设置或默认浏览器。", true); }
        }

        internal static void SelfTest(string output)
        {
            Directory.CreateDirectory(output);
            string testRoot = Path.Combine(output, "fixture-project");
            Directory.CreateDirectory(testRoot);
            string selected = Path.Combine(testRoot, "虚构测试流水表 仅用于界面验收.xlsx");
            if (!File.Exists(selected)) File.WriteAllText(selected, "UI fixture, not a business workbook.");
            var fixture = new Dictionary<string, string> { {"watch", selected}, {"url", "http://127.0.0.1:18765"}, {"token", "fictional-ui-test-token"} };
            Config.Write(Path.Combine(testRoot, ".local", "remote-sync.txt"), fixture);
            byte[] before = File.ReadAllBytes(selected);
            var results = new List<object>();
            foreach (float scale in new[] {1F, 1.25F, 1.5F, 2F})
            {
                using (var form = new SyncForm(testRoot))
                {
                    form.AutoScaleMode = AutoScaleMode.None;
                    form.Scale(new SizeF(scale, scale));
                    ScaleFonts(form, scale);
                    form.ClientSize = new Size((int)(760 * scale), (int)(710 * scale));
                    form.ShowInTaskbar = false;
                    form.StartPosition = FormStartPosition.Manual;
                    form.Location = new Point(-20000, -20000);
                    form.Show();
                    Application.DoEvents();
                    using (var image = new Bitmap(form.Width, form.Height)) { form.DrawToBitmap(image, new Rectangle(Point.Empty, form.Size)); image.Save(Path.Combine(output, "sync-assistant-" + (int)(scale * 100) + ".png")); }
                    if (!form.workbook.ReadOnly || form.worker != null) throw new InvalidOperationException("Unexpected workbook editing or worker startup");
                    if (form.start.Bounds.Width < TextRenderer.MeasureText(form.start.Text, form.start.Font).Width + 16) throw new InvalidOperationException("Start button text clipped");
                    var actionPosition = form.PointToClient(form.start.PointToScreen(Point.Empty));
                    var statusPosition = form.PointToClient(form.status.PointToScreen(Point.Empty));
                    if (actionPosition.Y + form.start.Height > form.ClientSize.Height || statusPosition.Y < 0) throw new InvalidOperationException("Actions or status are outside the visible window");
                    if (!form.start.Enabled || form.stop.Enabled) throw new InvalidOperationException("Idle controls incorrect");
                    form.SetRunning(true);
                    if (form.browse.Enabled || form.save.Enabled || !form.stop.Enabled) throw new InvalidOperationException("Running controls incorrect");
                    form.SetRunning(false);
                    if (form.Redact("fictional-ui-test-token") != "[令牌已隐藏]") throw new InvalidOperationException("Token redaction failed");
                    form.SaveSettings();
                    var saved = Config.Read(Path.Combine(testRoot, ".local", "remote-sync.txt"));
                    if (saved["watch"] != selected || saved["token"] != "fictional-ui-test-token") throw new InvalidOperationException("Configuration was not preserved");
                    results.Add(new { scale = scale, width = form.Width, height = form.Height, startWidth = form.start.Width, startTextWidth = TextRenderer.MeasureText(form.start.Text, form.start.Font).Width });
                    if (scale == 1F)
                    {
                        form.Size = form.MinimumSize;
                        Application.DoEvents();
                        var minimumPosition = form.PointToClient(form.start.PointToScreen(Point.Empty));
                        if (minimumPosition.Y + form.start.Height > form.ClientSize.Height) throw new InvalidOperationException("Minimum-size actions are clipped");
                        using (var image = new Bitmap(form.Width, form.Height)) { form.DrawToBitmap(image, new Rectangle(Point.Empty, form.Size)); image.Save(Path.Combine(output, "sync-assistant-minimum.png")); }
                        form.ClientSize = new Size(1280, 820);
                        Application.DoEvents();
                        using (var image = new Bitmap(form.Width, form.Height)) { form.DrawToBitmap(image, new Rectangle(Point.Empty, form.Size)); image.Save(Path.Combine(output, "sync-assistant-large.png")); }
                    }
                    form.Close();
                }
            }
            using (var settings = new ServerForm("https://example.com", "fictional-ui-test-token"))
            {
                settings.ShowInTaskbar = false;
                settings.StartPosition = FormStartPosition.Manual;
                settings.Location = new Point(-20000, -20000);
                settings.Show();
                Application.DoEvents();
                using (var image = new Bitmap(settings.Width, settings.Height)) { settings.DrawToBitmap(image, new Rectangle(Point.Empty, settings.Size)); image.Save(Path.Combine(output, "server-settings.png")); }
                settings.Close();
            }
            if (Convert.ToBase64String(before) != Convert.ToBase64String(File.ReadAllBytes(selected))) throw new InvalidOperationException("Workbook was changed");
            File.WriteAllText(Path.Combine(output, "results.json"), new JavaScriptSerializer().Serialize(new { ok = true, scaling = "simulated", windows = results, workbookUnchanged = true }), Encoding.UTF8);
        }

        private static void ScaleFonts(Control control, float scale)
        {
            Font original = control.Font;
            foreach (Control child in control.Controls) ScaleFonts(child, scale);
            control.Font = new Font(original.FontFamily, original.SizeInPoints * scale, original.Style);
        }

        internal static void IntegrationTest(string codeRoot, string testRoot, string output)
        {
            Directory.CreateDirectory(output);
            using (var form = new SyncForm(testRoot, codeRoot))
            {
                form.ShowInTaskbar = false;
                form.StartPosition = FormStartPosition.Manual;
                form.Location = new Point(-20000, -20000);
                form.Show();
                Application.DoEvents();
                byte[] original = File.ReadAllBytes(form.workbook.Text);
                form.StartSync();
                DateTime deadline = DateTime.UtcNow.AddSeconds(12);
                while (form.status.ForeColor != Theme.Success && DateTime.UtcNow < deadline)
                {
                    Application.DoEvents();
                    if (form.worker == null && form.lastError) break;
                    Thread.Sleep(50);
                }
                if (form.status.ForeColor != Theme.Success || form.worker == null) throw new InvalidOperationException("GUI did not receive a successful sync: " + form.log.Text);
                if (form.browse.Enabled || form.start.Enabled || !form.stop.Enabled) throw new InvalidOperationException("Running UI controls incorrect");
                using (var image = new Bitmap(form.Width, form.Height)) { form.DrawToBitmap(image, new Rectangle(Point.Empty, form.Size)); image.Save(Path.Combine(output, "sync-assistant-synced.png")); }
                form.StopSync();
                deadline = DateTime.UtcNow.AddSeconds(5);
                while (form.worker != null && DateTime.UtcNow < deadline) { Application.DoEvents(); Thread.Sleep(50); }
                if (form.worker != null || !form.start.Enabled || form.stop.Enabled) throw new InvalidOperationException("GUI did not stop its worker");
                if (Convert.ToBase64String(original) != Convert.ToBase64String(File.ReadAllBytes(form.workbook.Text))) throw new InvalidOperationException("Workbook changed");
                if (form.log.Text.Contains(Config.Get(form.remoteValues, "token", "not-a-real-token"))) throw new InvalidOperationException("Token appeared in the UI log");
                File.WriteAllText(Path.Combine(output, "integration.json"), new JavaScriptSerializer().Serialize(new { ok = true, started = true, synced = true, stopped = true, workbookUnchanged = true }), Encoding.UTF8);
                form.Close();
            }
        }
    }

    internal static class Program
    {
        [DllImport("shcore.dll")] private static extern int SetProcessDpiAwareness(int awareness);
        [DllImport("user32.dll")] private static extern bool SetProcessDPIAware();

        [STAThread]
        private static void Main(string[] args)
        {
            try { SetProcessDpiAwareness(2); } catch (DllNotFoundException) { SetProcessDPIAware(); } catch (EntryPointNotFoundException) { SetProcessDPIAware(); }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            if (args.Length == 2 && args[0] == "--self-test")
            {
                try { SyncForm.SelfTest(Path.GetFullPath(args[1])); }
                catch (Exception error) { Directory.CreateDirectory(args[1]); File.WriteAllText(Path.Combine(args[1], "failure.txt"), error.ToString()); Environment.ExitCode = 1; }
                return;
            }
            if (args.Length == 4 && args[0] == "--integration-test")
            {
                try { SyncForm.IntegrationTest(Path.GetFullPath(args[1]), Path.GetFullPath(args[2]), Path.GetFullPath(args[3])); }
                catch (Exception error) { Directory.CreateDirectory(args[3]); File.WriteAllText(Path.Combine(args[3], "failure.txt"), error.ToString()); Environment.ExitCode = 1; }
                return;
            }
            try
            {
                string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
                if (!File.Exists(Path.Combine(root, "desktop_sync.py"))) throw new InvalidOperationException("请把同步助手放在 WebIncome 项目目录中，再双击打开。");
                string name;
                using (var sha = SHA256.Create()) name = BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(root.ToLowerInvariant()))).Replace("-", "").Substring(0, 20);
                bool owner;
                using (var mutex = new Mutex(true, "Local\\WebIncomeSync-" + name, out owner))
                {
                    if (!owner) { MessageBox.Show("同步助手已经打开，请查看任务栏。", "Excel 同步助手"); return; }
                    try { Application.Run(new SyncForm(root)); }
                    finally { mutex.ReleaseMutex(); }
                }
            }
            catch (Exception error) { MessageBox.Show(error.Message, "同步助手无法启动", MessageBoxButtons.OK, MessageBoxIcon.Error); }
        }
    }
}
