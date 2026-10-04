// TargetDesign-workbench - double-click launcher.
//
// Starts the local web workbench (webapp/app.py) hidden, waits until it answers,
// opens the default browser and keeps a small control window so the server can be
// stopped again.  Build with tools/launcher/build_launcher.ps1.
//
// Command line:
//   --port N          listen port (default 5000)
//   --host ADDR       bind address (default 0.0.0.0, all interfaces)
//   --install         create .venv and pip install the requirements, then start
//   --requirements P  requirements file for --install (default requirements-windows.txt)
//   --timeout S       seconds to wait for the server (default 240)
//   --repo PATH       repository root (default: found relative to this exe)
//   --no-browser      start the server but do not open a browser
//   --check           headless self test; writes a status file and returns
//   --check-file P    status file for --check (default logs/launcher_check.txt)
//   --stop            stop a running workbench server and exit
//   --help            show usage
//
// --check exit codes: 0 ready, 2 no Python 3, 3 start failed, 4 not ready,
//                     5 packages missing, 6 dependency install failed.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Net.NetworkInformation;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace CrisprWorkbench
{
    internal sealed class Options
    {
        public int Port = 5000;
        public string Host = "0.0.0.0";
        public bool Install = false;
        public string Requirements = null;
        public bool OpenBrowser = true;
        public bool Check = false;
        public bool StopOnly = false;
        public bool Help = false;
        public int TimeoutSeconds = 240;
        public string RepoRoot = null;
        public string CheckFile = null;
    }

    internal sealed class PythonInfo
    {
        public string Exe;
        public string PrefixArgs = "";
        public string Description;
    }

    internal sealed class ServerHost
    {
        public string RepoRoot;
        public int Port;
        public string Host = "0.0.0.0";
        public string LogPath;
        public PythonInfo Python;
        public Process Child;
        public bool Attached;
        public int AttachedPid;

        private readonly Queue<string> recent = new Queue<string>();

        public event Action<string> Logged;

        public string Url
        {
            get { return "http://127.0.0.1:" + this.Port.ToString(CultureInfo.InvariantCulture) + "/"; }
        }

        /// <summary>Address handed to the web app; 0.0.0.0 exposes every interface.</summary>
        public string BindAddress
        {
            get { return string.IsNullOrEmpty(this.Host) ? "127.0.0.1" : this.Host; }
        }

        public bool LocalOnly
        {
            get
            {
                return this.BindAddress == "127.0.0.1" || this.BindAddress == "localhost";
            }
        }

        /// <summary>IPv4 URLs other machines can use, loopback excluded.</summary>
        public List<string> LanUrls()
        {
            List<string> urls = new List<string>();
            string port = this.Port.ToString(CultureInfo.InvariantCulture);
            try
            {
                foreach (NetworkInterface nic in NetworkInterface.GetAllNetworkInterfaces())
                {
                    if (nic.OperationalStatus != OperationalStatus.Up)
                    {
                        continue;
                    }
                    foreach (UnicastIPAddressInformation info in nic.GetIPProperties().UnicastAddresses)
                    {
                        IPAddress address = info.Address;
                        if (address.AddressFamily != AddressFamily.InterNetwork
                            || IPAddress.IsLoopback(address))
                        {
                            continue;
                        }
                        urls.Add("http://" + address.ToString() + ":" + port + "/");
                    }
                }
            }
            catch (Exception)
            {
            }
            return urls;
        }

        /// <summary>Loopback URL, plus the shareable LAN URLs when the bind is not local-only.</summary>
        public string AdvertisedUrlsText()
        {
            if (this.LocalOnly)
            {
                return this.Url;
            }
            List<string> lan = this.LanUrls();
            if (lan.Count == 0)
            {
                return this.Url + "\r\n(no LAN address found)";
            }
            StringBuilder builder = new StringBuilder(this.Url);
            foreach (string url in lan)
            {
                builder.Append("\r\n").Append(url);
            }
            return builder.ToString();
        }

        public void Log(string message)
        {
            string line = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture) + "  " + message;
            try
            {
                File.AppendAllText(this.LogPath, line + Environment.NewLine, new UTF8Encoding(true));
            }
            catch (Exception)
            {
            }
            lock (this.recent)
            {
                this.recent.Enqueue(line);
                while (this.recent.Count > 40)
                {
                    this.recent.Dequeue();
                }
            }
            Action<string> handler = this.Logged;
            if (handler != null)
            {
                handler(line);
            }
        }

        public string RecentLog(int count)
        {
            StringBuilder builder = new StringBuilder();
            lock (this.recent)
            {
                int skip = this.recent.Count - count;
                int index = 0;
                foreach (string line in this.recent)
                {
                    if (index++ < skip)
                    {
                        continue;
                    }
                    builder.AppendLine(line);
                }
            }
            return builder.ToString().TrimEnd();
        }

        // ------------------------------------------------------------ discovery

        public static string FindRepoRoot(string hint)
        {
            if (!string.IsNullOrEmpty(hint) && File.Exists(Path.Combine(hint, "webapp", "app.py")))
            {
                return Path.GetFullPath(hint);
            }
            string env = Environment.GetEnvironmentVariable("CRISPR_WORKBENCH_ROOT");
            if (!string.IsNullOrEmpty(env) && File.Exists(Path.Combine(env, "webapp", "app.py")))
            {
                return Path.GetFullPath(env);
            }
            string dir = Path.GetDirectoryName(Application.ExecutablePath);
            string current = dir;
            for (int i = 0; i < 5 && !string.IsNullOrEmpty(current); i++)
            {
                if (File.Exists(Path.Combine(current, "webapp", "app.py")))
                {
                    return current;
                }
                DirectoryInfo parent = Directory.GetParent(current);
                current = (parent == null) ? null : parent.FullName;
            }
            return Path.GetFullPath(dir);
        }

        public static PythonInfo FindPython(string repoRoot)
        {
            List<PythonInfo> candidates = PythonCandidates(repoRoot);
            foreach (PythonInfo info in candidates)
            {
                if (IsUsablePython(info))
                {
                    return info;
                }
            }
            LastRejected = candidates.Count > 0 ? candidates[0] : null;
            return null;
        }

        /// <summary>First candidate that failed the Python 3 probe, for diagnostics.</summary>
        public static PythonInfo LastRejected;

        /// <summary>Top-level modules the web app needs before it can serve.</summary>
        public static readonly string[] RequiredModules = new string[] { "numpy", "Bio", "pyfaidx" };

        /// <summary>Run the interpreter with the given arguments and capture stdout.</summary>
        /// <returns>The exit code and stdout, or null when the process could not run.</returns>
        public static string RunPythonCapture(PythonInfo info, string arguments, int timeoutMs)
        {
            if (info == null || string.IsNullOrEmpty(info.Exe))
            {
                return null;
            }
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                string prefix = string.IsNullOrEmpty(info.PrefixArgs) ? "" : (info.PrefixArgs + " ");
                psi.FileName = info.Exe;
                psi.Arguments = prefix + arguments;
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;
                psi.StandardOutputEncoding = new UTF8Encoding(false);
                psi.StandardErrorEncoding = new UTF8Encoding(false);
                using (Process probe = Process.Start(psi))
                {
                    string stdout = probe.StandardOutput.ReadToEnd();
                    probe.StandardError.ReadToEnd();
                    if (!probe.WaitForExit(timeoutMs))
                    {
                        try
                        {
                            probe.Kill();
                        }
                        catch (Exception)
                        {
                        }
                        return null;
                    }
                    return probe.ExitCode == 0 ? stdout : null;
                }
            }
            catch (Exception)
            {
                return null;
            }
        }

        /// <summary>Required modules the interpreter cannot import.</summary>
        /// <returns>The missing names, or null when the interpreter could not be probed.</returns>
        public static List<string> MissingModules(PythonInfo info)
        {
            if (info == null)
            {
                return null;
            }
            string names = "'" + string.Join("','", RequiredModules) + "'";
            string code = "import importlib.util as u; print(','.join(m for m in ["
                + names + "] if u.find_spec(m) is None))";
            string output = RunPythonCapture(info, "-c \"" + code + "\"", 60000);
            if (output == null)
            {
                return null;
            }
            List<string> missing = new List<string>();
            foreach (string part in output.Trim().Split(','))
            {
                if (part.Trim().Length > 0)
                {
                    missing.Add(part.Trim());
                }
            }
            return missing;
        }

        /// <summary>Interpreter inside the repository virtualenv (created by --install).</summary>
        public string VenvPythonPath
        {
            get { return Path.Combine(this.RepoRoot, ".venv", "Scripts", "python.exe"); }
        }

        public static PythonInfo NewPythonInfo(string exe, string description)
        {
            PythonInfo info = new PythonInfo();
            info.Exe = exe;
            info.Description = description;
            return info;
        }

        /// <summary>Requirements file for the install step; explicit path wins.</summary>
        public static string ResolveRequirements(string repoRoot, string requested)
        {
            if (!string.IsNullOrEmpty(requested))
            {
                return Path.IsPathRooted(requested) ? requested : Path.Combine(repoRoot, requested);
            }
            string windows = Path.Combine(repoRoot, "requirements-windows.txt");
            if (File.Exists(windows))
            {
                return windows;
            }
            return Path.Combine(repoRoot, "requirements.txt");
        }

        /// <summary>Create the repository virtualenv when needed, then pip install.</summary>
        /// <remarks>Blocking; run it on a worker thread. ``progress`` receives one line per step.</remarks>
        public bool InstallDependencies(PythonInfo basePython, string requirementsFile,
            Action<string> progress, out string error)
        {
            error = "";
            if (basePython == null)
            {
                error = "no Python 3 to build the virtualenv from";
                return false;
            }
            if (!File.Exists(requirementsFile))
            {
                error = "requirements file not found: " + requirementsFile;
                return false;
            }
            if (!IsUsablePython(NewPythonInfo(this.VenvPythonPath, this.VenvPythonPath)))
            {
                string venvDir = Path.Combine(this.RepoRoot, ".venv");
                if (progress != null)
                {
                    progress("creating virtualenv: " + venvDir);
                }
                if (!RunAndStream(basePython, "-m venv \"" + venvDir + "\"", 900, progress, out error))
                {
                    return false;
                }
            }
            PythonInfo venv = NewPythonInfo(this.VenvPythonPath, this.VenvPythonPath + " (repository venv)");
            if (!IsUsablePython(venv))
            {
                error = "virtualenv interpreter is not usable: " + this.VenvPythonPath;
                return false;
            }
            if (progress != null)
            {
                progress("installing packages: " + requirementsFile);
            }
            return RunAndStream(venv, "-m pip install -r \"" + requirementsFile + "\"",
                3600, progress, out error);
        }

        /// <summary>Run a child process, streaming stdout and stderr lines to ``progress``.</summary>
        private static bool RunAndStream(PythonInfo info, string arguments, int timeoutSeconds,
            Action<string> progress, out string error)
        {
            error = "";
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                string prefix = string.IsNullOrEmpty(info.PrefixArgs) ? "" : (info.PrefixArgs + " ");
                psi.FileName = info.Exe;
                psi.Arguments = prefix + arguments;
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;
                psi.StandardOutputEncoding = new UTF8Encoding(false);
                psi.StandardErrorEncoding = new UTF8Encoding(false);
                psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
                using (Process child = new Process())
                {
                    child.StartInfo = psi;
                    child.Start();
                    Thread reader = new Thread(new ThreadStart(delegate
                    {
                        try
                        {
                            string errLine;
                            while ((errLine = child.StandardError.ReadLine()) != null)
                            {
                                if (progress != null)
                                {
                                    progress(errLine);
                                }
                            }
                        }
                        catch (Exception)
                        {
                        }
                    }));
                    reader.IsBackground = true;
                    reader.Start();
                    string outLine;
                    while ((outLine = child.StandardOutput.ReadLine()) != null)
                    {
                        if (progress != null)
                        {
                            progress(outLine);
                        }
                    }
                    reader.Join(5000);
                    if (!child.WaitForExit(timeoutSeconds * 1000))
                    {
                        try
                        {
                            child.Kill();
                        }
                        catch (Exception)
                        {
                        }
                        error = "timed out after " + timeoutSeconds.ToString(CultureInfo.InvariantCulture) + "s";
                        return false;
                    }
                    if (child.ExitCode != 0)
                    {
                        error = "exit code " + child.ExitCode.ToString(CultureInfo.InvariantCulture);
                        return false;
                    }
                    return true;
                }
            }
            catch (Exception exc)
            {
                error = exc.Message;
                return false;
            }
        }

        public static bool IsUsablePython(PythonInfo info)
        {
            if (info == null || string.IsNullOrEmpty(info.Exe) || !File.Exists(info.Exe))
            {
                return false;
            }
            try
            {
                string prefix = string.IsNullOrEmpty(info.PrefixArgs) ? "" : (info.PrefixArgs + " ");
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = info.Exe;
                psi.Arguments = prefix + "-c \"import sys; sys.stdout.write(str(sys.version_info[0]))\"";
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;
                using (Process probe = Process.Start(psi))
                {
                    string output = probe.StandardOutput.ReadToEnd();
                    probe.WaitForExit(20000);
                    return probe.HasExited && probe.ExitCode == 0 && output.Trim() == "3";
                }
            }
            catch (Exception)
            {
                return false;
            }
        }

        public static List<PythonInfo> PythonCandidates(string repoRoot)
        {
            List<PythonInfo> candidates = new List<PythonInfo>();

            string custom = Environment.GetEnvironmentVariable("CRISPR_WORKBENCH_PYTHON");
            if (!string.IsNullOrEmpty(custom))
            {
                PythonInfo customInfo = new PythonInfo();
                customInfo.Exe = custom;
                customInfo.Description = custom + " (CRISPR_WORKBENCH_PYTHON)";
                candidates.Add(customInfo);
            }

            string[] venvs = new string[]
            {
                Path.Combine(repoRoot, ".venv", "Scripts", "python.exe"),
                Path.Combine(repoRoot, ".venv310", "Scripts", "python.exe")
            };
            foreach (string venv in venvs)
            {
                if (File.Exists(venv))
                {
                    PythonInfo info = new PythonInfo();
                    info.Exe = venv;
                    info.Description = venv + " (repository venv)";
                    candidates.Add(info);
                }
            }

            string fromPath = FindOnPath("python.exe");
            if (fromPath != null)
            {
                PythonInfo info = new PythonInfo();
                info.Exe = fromPath;
                info.Description = fromPath + " (PATH)";
                candidates.Add(info);
            }

            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string programs = Path.Combine(local, "Programs", "Python");
            if (Directory.Exists(programs))
            {
                List<string> found = new List<string>(
                    Directory.GetFiles(programs, "python.exe", SearchOption.AllDirectories));
                found.Sort();
                found.Reverse();
                foreach (string exe in found)
                {
                    PythonInfo info = new PythonInfo();
                    info.Exe = exe;
                    info.Description = exe + " (user install)";
                    candidates.Add(info);
                }
            }

            string pyLauncher = FindOnPath("py.exe");
            if (pyLauncher != null)
            {
                PythonInfo info = new PythonInfo();
                info.Exe = pyLauncher;
                info.PrefixArgs = "-3";
                info.Description = pyLauncher + " -3 (py launcher)";
                candidates.Add(info);
            }
            return candidates;
        }

        public static string FindOnPath(string fileName)
        {
            string path = Environment.GetEnvironmentVariable("PATH");
            if (string.IsNullOrEmpty(path))
            {
                return null;
            }
            string[] parts = path.Split(Path.PathSeparator);
            foreach (string part in parts)
            {
                if (string.IsNullOrEmpty(part))
                {
                    continue;
                }
                try
                {
                    string candidate = Path.Combine(part.Trim(), fileName);
                    if (File.Exists(candidate))
                    {
                        return candidate;
                    }
                }
                catch (Exception)
                {
                }
            }
            return null;
        }

        // -------------------------------------------------------------- probing

        public static string HttpGet(string url, int timeoutMs)
        {
            try
            {
                HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
                request.Proxy = null;
                request.Timeout = timeoutMs;
                request.ReadWriteTimeout = timeoutMs;
                request.KeepAlive = false;
                using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                using (Stream stream = response.GetResponseStream())
                using (StreamReader reader = new StreamReader(stream, Encoding.UTF8))
                {
                    return reader.ReadToEnd();
                }
            }
            catch (Exception)
            {
                return null;
            }
        }

        public static bool IsWorkbench(int port)
        {
            string body = HttpGet("http://127.0.0.1:" + port.ToString(CultureInfo.InvariantCulture) + "/api/schema", 2500);
            return body != null && body.IndexOf("\"modes\"", StringComparison.Ordinal) >= 0;
        }

        public static bool PortListening(int port)
        {
            try
            {
                using (TcpClient client = new TcpClient())
                {
                    IAsyncResult result = client.BeginConnect(IPAddress.Loopback, port, null, null);
                    bool connected = result.AsyncWaitHandle.WaitOne(700);
                    if (!connected)
                    {
                        return false;
                    }
                    client.EndConnect(result);
                    return true;
                }
            }
            catch (Exception)
            {
                return false;
            }
        }

        public static int FindPidByPort(int port)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("netstat", "-ano -p TCP");
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardOutput = true;
                using (Process proc = Process.Start(psi))
                {
                    string text = proc.StandardOutput.ReadToEnd();
                    proc.WaitForExit(15000);
                    string needle = ":" + port.ToString(CultureInfo.InvariantCulture);
                    string[] lines = text.Split('\n');
                    foreach (string raw in lines)
                    {
                        string line = raw.Trim();
                        if (line.Length == 0 || line.IndexOf("LISTENING", StringComparison.OrdinalIgnoreCase) < 0)
                        {
                            continue;
                        }
                        string[] parts = line.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                        if (parts.Length < 5)
                        {
                            continue;
                        }
                        if (!parts[1].EndsWith(needle, StringComparison.Ordinal))
                        {
                            continue;
                        }
                        int pid;
                        if (int.TryParse(parts[parts.Length - 1], out pid) && pid > 0)
                        {
                            return pid;
                        }
                    }
                }
            }
            catch (Exception)
            {
            }
            return 0;
        }

        public static void KillTree(int pid)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("taskkill", "/PID " + pid.ToString(CultureInfo.InvariantCulture) + " /T /F");
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;
                using (Process proc = Process.Start(psi))
                {
                    proc.WaitForExit(20000);
                }
            }
            catch (Exception)
            {
            }
        }

        public static void OpenInBrowser(string url)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo(url);
                psi.UseShellExecute = true;
                Process.Start(psi);
            }
            catch (Exception)
            {
            }
        }

        // -------------------------------------------------------------- control

        public void AdoptRunning(int pid)
        {
            this.Attached = true;
            this.AttachedPid = pid;
        }

        public void Start()
        {
            if (this.Python == null)
            {
                throw new InvalidOperationException("Python interpreter not found.");
            }
            List<string> missing = MissingModules(this.Python);
            if (missing == null)
            {
                this.Log("environment probe failed; python=" + this.Python.Description);
            }
            else if (missing.Count == 0)
            {
                this.Log("environment ok; python=" + this.Python.Description
                    + "; packages=" + string.Join(", ", RequiredModules));
            }
            else
            {
                this.Log("missing packages: " + string.Join(", ", missing.ToArray())
                    + "; python=" + this.Python.Description);
            }
            ProcessStartInfo psi = new ProcessStartInfo();
            string script = Path.Combine(this.RepoRoot, "webapp", "app.py");
            string prefix = this.Python.PrefixArgs;
            if (!string.IsNullOrEmpty(prefix))
            {
                prefix = prefix + " ";
            }
            psi.FileName = this.Python.Exe;
            psi.Arguments = prefix + "\"" + script + "\" --host " + this.BindAddress
                + " --port " + this.Port.ToString(CultureInfo.InvariantCulture);
            psi.WorkingDirectory = this.RepoRoot;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.StandardOutputEncoding = new UTF8Encoding(false);
            psi.StandardErrorEncoding = new UTF8Encoding(false);
            // Keep child processes on UTF-8 so Chinese progress lines survive.
            psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";

            Process child = new Process();
            child.StartInfo = psi;
            child.EnableRaisingEvents = true;
            child.OutputDataReceived += this.OnChildOutput;
            child.ErrorDataReceived += this.OnChildOutput;
            child.Start();
            child.BeginOutputReadLine();
            child.BeginErrorReadLine();
            this.Child = child;
            this.Log("server started: " + psi.FileName + " " + psi.Arguments);
            this.Log("working directory: " + psi.WorkingDirectory);
        }

        private void OnChildOutput(object sender, DataReceivedEventArgs args)
        {
            if (!string.IsNullOrEmpty(args.Data))
            {
                this.Log("server> " + args.Data);
            }
        }

        public bool WaitUntilReady(TimeSpan timeout, Action<string> progress)
        {
            DateTime deadline = DateTime.UtcNow.Add(timeout);
            int waited = 0;
            while (DateTime.UtcNow < deadline)
            {
                if (IsWorkbench(this.Port))
                {
                    return true;
                }
                if (this.Child != null && this.Child.HasExited)
                {
                    this.Log("server process exited with code " + this.Child.ExitCode.ToString(CultureInfo.InvariantCulture));
                    return false;
                }
                if (progress != null)
                {
                    progress("等待服务就绪 / waiting for the server ... " + waited.ToString(CultureInfo.InvariantCulture) + "s");
                }
                Thread.Sleep(1000);
                waited++;
            }
            return false;
        }

        public void Stop()
        {
            if (this.Child != null && !this.Child.HasExited)
            {
                int pid = this.Child.Id;
                KillTree(pid);
                try
                {
                    this.Child.WaitForExit(15000);
                }
                catch (Exception)
                {
                }
                this.Log("server stopped (pid " + pid.ToString(CultureInfo.InvariantCulture) + ")");
            }
            else if (this.Attached && this.AttachedPid > 0)
            {
                KillTree(this.AttachedPid);
                this.Log("attached server stopped (pid " + this.AttachedPid.ToString(CultureInfo.InvariantCulture) + ")");
                this.AttachedPid = 0;
            }
            else
            {
                int pid = FindPidByPort(this.Port);
                if (pid > 0)
                {
                    KillTree(pid);
                    this.Log("server on port " + this.Port.ToString(CultureInfo.InvariantCulture)
                        + " stopped (pid " + pid.ToString(CultureInfo.InvariantCulture) + ")");
                }
            }
            this.Child = null;
        }

        public bool IsRunning()
        {
            if (this.Child != null && !this.Child.HasExited)
            {
                return true;
            }
            return IsWorkbench(this.Port);
        }
    }

    internal sealed class MainForm : Form
    {
        private readonly ServerHost host;
        private readonly Options options;
        private readonly bool openBrowser;
        private Label statusLabel;
        private LinkLabel urlLink;
        private CheckBox stopOnClose;
        private Button openButton;
        private Button stopButton;
        private volatile bool ready;

        public MainForm(ServerHost host, Options options)
        {
            this.host = host;
            this.options = options;
            this.openBrowser = options.OpenBrowser;

            this.Text = "TargetDesign-workbench";
            this.ClientSize = new Size(520, 262);
            this.MinimumSize = new Size(460, 242);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.Font = new Font("Segoe UI", 9F);

            Label title = new Label();
            title.Text = "TargetDesign-workbench";
            title.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
            title.Location = new Point(16, 14);
            title.AutoSize = true;
            this.Controls.Add(title);

            this.statusLabel = new Label();
            this.statusLabel.Location = new Point(18, 48);
            this.statusLabel.Size = new Size(484, 112);
            this.statusLabel.Text = "正在启动本地服务 ...";
            this.Controls.Add(this.statusLabel);

            this.urlLink = new LinkLabel();
            this.urlLink.Location = new Point(18, 170);
            this.urlLink.AutoSize = true;
            this.urlLink.Text = host.Url;
            this.urlLink.LinkClicked += this.OnLinkClicked;
            this.Controls.Add(this.urlLink);

            this.stopOnClose = new CheckBox();
            this.stopOnClose.Text = "关闭窗口时停止服务 (stop the server when closing)";
            this.stopOnClose.Location = new Point(18, 196);
            this.stopOnClose.Size = new Size(400, 24);
            this.stopOnClose.Checked = true;
            this.Controls.Add(this.stopOnClose);

            this.openButton = new Button();
            this.openButton.Text = "打开浏览器";
            this.openButton.Location = new Point(18, 224);
            this.openButton.Size = new Size(130, 28);
            this.openButton.Enabled = false;
            this.openButton.Click += this.OnOpenClicked;
            this.Controls.Add(this.openButton);

            this.stopButton = new Button();
            this.stopButton.Text = "停止服务";
            this.stopButton.Location = new Point(156, 224);
            this.stopButton.Size = new Size(110, 28);
            this.stopButton.Click += this.OnStopClicked;
            this.Controls.Add(this.stopButton);

            Button closeButton = new Button();
            closeButton.Text = "退出";
            closeButton.Location = new Point(400, 224);
            closeButton.Size = new Size(88, 28);
            closeButton.Click += this.OnCloseClicked;
            this.Controls.Add(closeButton);

            this.FormClosing += this.OnFormClosing;
            this.Load += this.OnLoad;
        }

        private void OnLoad(object sender, EventArgs e)
        {
            Thread worker = new Thread(new ThreadStart(this.StartServerThread));
            worker.IsBackground = true;
            worker.Start();
        }

        private void StartServerThread()
        {
            bool existing = ServerHost.IsWorkbench(this.host.Port);
            if (existing)
            {
                int pid = ServerHost.FindPidByPort(this.host.Port);
                this.host.AdoptRunning(pid);
                this.host.Log("existing server detected on port "
                    + this.host.Port.ToString(CultureInfo.InvariantCulture)
                    + (pid > 0 ? (" (pid " + pid.ToString(CultureInfo.InvariantCulture) + ")") : ""));
                this.SetStatus("服务已在运行，已附加。\r\nattached to the server that is already running.");
                this.FinishReady();
                return;
            }

            if (this.host.Python == null)
            {
                this.host.Log("no usable Python 3 found"
                    + (ServerHost.LastRejected != null
                        ? ("; rejected: " + ServerHost.LastRejected.Exe)
                        : "; no candidate found"));
                this.SetStatus("找不到可用的 Python 3 / no usable Python 3\r\n"
                    + "已查找：CRISPR_WORKBENCH_PYTHON、包内 .venv 与 .venv310、PATH、用户安装目录\r\n"
                    + "请安装 Python 3（勾选 Add python.exe to PATH），然后运行：\r\n"
                    + "  python -m pip install -r requirements-windows.txt");
                return;
            }

            List<string> missing = ServerHost.MissingModules(this.host.Python);
            bool depsMissing = missing != null && missing.Count > 0;
            if (this.options.Install || depsMissing)
            {
                if (!this.InstallMissing(depsMissing ? missing : new List<string>()))
                {
                    return;
                }
            }

            try
            {
                this.host.Start();
            }
            catch (Exception exc)
            {
                this.SetStatus("启动失败 / failed to start:\r\n" + exc.Message);
                this.host.Log("start failed: " + exc.Message);
                return;
            }

            this.SetStatus("正在启动本地服务 ...\r\nstarting the local server ...");
            bool ok = this.host.WaitUntilReady(TimeSpan.FromSeconds(600), new Action<string>(this.SetStatus));
            if (!ok)
            {
                this.SetStatus("服务没有就绪 / the server did not become ready.\r\n"
                    + this.host.RecentLog(6) + "\r\n日志 / log: " + this.host.LogPath);
                return;
            }
            this.host.Log("server is ready at " + this.host.AdvertisedUrlsText());
            this.SetStatus("服务已就绪。\r\nserver ready: " + this.host.AdvertisedUrlsText()
                + "\r\n日志 / log: " + this.host.LogPath);
            this.FinishReady();
        }

        /// <summary>Create .venv and pip install when packages are missing (or --install was given).</summary>
        private bool InstallMissing(List<string> missing)
        {
            string missingNames = missing.Count == 0
                ? "(none, refreshing)" : string.Join(", ", missing.ToArray());
            string requirements = ServerHost.ResolveRequirements(this.host.RepoRoot, this.options.Requirements);
            this.host.Log("missing Python packages: " + missingNames);
            this.host.Log("requirements file: " + requirements);
            this.host.Log("virtualenv: " + this.host.VenvPythonPath);
            if (!this.options.Install)
            {
                DialogResult answer = MessageBox.Show(
                    "缺少 Python 依赖 / missing packages: " + missingNames + "\r\n\r\n"
                    + "是否现在创建 .venv 并自动安装依赖？\r\n"
                    + "Create .venv and install the requirements now?\r\n"
                    + "(需要联网，首次可能十几分钟 / needs network, may take several minutes)",
                    "TargetDesign-workbench", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
                if (answer != DialogResult.Yes)
                {
                    this.host.Log("dependency install declined");
                    this.SetStatus("缺少依赖 / missing packages: " + missingNames + "\r\n"
                        + "已取消自动安装 / install cancelled\r\n"
                        + "手动安装 / install manually:\r\n"
                        + this.host.Python.Exe + " -m pip install -r requirements-windows.txt");
                    return false;
                }
            }
            this.SetStatus("正在创建 .venv 并安装依赖 ...\r\ninstalling dependencies ...");
            string error;
            bool installed = this.host.InstallDependencies(this.host.Python, requirements,
                new Action<string>(this.OnInstallLine), out error);
            if (!installed)
            {
                this.host.Log("dependency install failed: " + error);
                this.SetStatus("依赖安装失败 / install failed: " + error + "\r\n"
                    + this.host.RecentLog(8) + "\r\n日志 / log: " + this.host.LogPath);
                return false;
            }
            PythonInfo venv = ServerHost.NewPythonInfo(this.host.VenvPythonPath,
                this.host.VenvPythonPath + " (repository venv)");
            List<string> stillMissing = ServerHost.MissingModules(venv);
            if (stillMissing == null || stillMissing.Count > 0)
            {
                string list = stillMissing == null
                    ? "(probe failed)" : string.Join(", ", stillMissing.ToArray());
                this.host.Log("packages still missing after install: " + list);
                this.SetStatus("安装后仍缺依赖 / still missing: " + list
                    + "\r\n日志 / log: " + this.host.LogPath);
                return false;
            }
            this.host.Python = venv;
            this.host.Log("dependencies ready; using " + venv.Exe);
            return true;
        }

        private void OnInstallLine(string line)
        {
            if (string.IsNullOrEmpty(line))
            {
                return;
            }
            this.host.Log("install> " + line);
            this.SetStatus("正在安装依赖 / installing dependencies ...\r\n" + line);
        }

        private void FinishReady()
        {
            this.ready = true;
            this.SetStatus("服务已就绪。\r\nserver ready: " + this.host.AdvertisedUrlsText()
                + "\r\n日志 / log: " + this.host.LogPath);
            this.Invoke(new Action(delegate
            {
                this.openButton.Enabled = true;
            }));
            if (this.openBrowser)
            {
                ServerHost.OpenInBrowser(this.host.Url);
            }
        }

        private void SetStatus(string text)
        {
            if (this.IsDisposed)
            {
                return;
            }
            try
            {
                this.Invoke(new Action(delegate
                {
                    this.statusLabel.Text = text;
                }));
            }
            catch (Exception)
            {
            }
        }

        private void OnLinkClicked(object sender, LinkLabelLinkClickedEventArgs e)
        {
            if (this.ready)
            {
                ServerHost.OpenInBrowser(this.host.Url);
            }
        }

        private void OnOpenClicked(object sender, EventArgs e)
        {
            ServerHost.OpenInBrowser(this.host.Url);
        }

        private void OnStopClicked(object sender, EventArgs e)
        {
            this.host.Stop();
            this.ready = false;
            this.openButton.Enabled = false;
            this.SetStatus("服务已停止。\r\nserver stopped.");
        }

        private void OnCloseClicked(object sender, EventArgs e)
        {
            this.Close();
        }

        private void OnFormClosing(object sender, FormClosingEventArgs e)
        {
            if (this.stopOnClose.Checked)
            {
                this.host.Stop();
            }
        }
    }

    internal static class Program
    {
        private static Options ParseOptions(string[] args)
        {
            Options options = new Options();
            for (int i = 0; i < args.Length; i++)
            {
                string arg = args[i];
                switch (arg)
                {
                    case "--port":
                        options.Port = int.Parse(args[++i], CultureInfo.InvariantCulture);
                        break;
                    case "--host":
                        options.Host = args[++i];
                        break;
                    case "--install":
                        options.Install = true;
                        break;
                    case "--requirements":
                        options.Requirements = args[++i];
                        break;
                    case "--timeout":
                        options.TimeoutSeconds = int.Parse(args[++i], CultureInfo.InvariantCulture);
                        break;
                    case "--repo":
                        options.RepoRoot = args[++i];
                        break;
                    case "--check-file":
                        options.CheckFile = args[++i];
                        break;
                    case "--no-browser":
                        options.OpenBrowser = false;
                        break;
                    case "--check":
                        options.Check = true;
                        options.OpenBrowser = false;
                        break;
                    case "--stop":
                        options.StopOnly = true;
                        options.OpenBrowser = false;
                        break;
                    case "--help":
                    case "-h":
                    case "/?":
                        options.Help = true;
                        break;
                }
            }
            return options;
        }

        private static void WriteCheckFile(Options options, string repoRoot, string text)
        {
            string path = options.CheckFile;
            if (string.IsNullOrEmpty(path))
            {
                path = Path.Combine(repoRoot, "logs", "launcher_check.txt");
            }
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                File.WriteAllText(path, text + Environment.NewLine, new UTF8Encoding(true));
            }
            catch (Exception)
            {
            }
        }

        [STAThread]
        private static int Main(string[] args)
        {
            WebRequest.DefaultWebProxy = null;
            Options options = ParseOptions(args);

            if (options.Help)
            {
                MessageBox.Show(
                    "TargetDesign-workbench launcher\r\n\r\n"
                    + "  --port N        listen port (default 5000)\r\n"
                    + "  --host ADDR     bind address (default 0.0.0.0, all interfaces)\r\n"
                    + "  --install       create .venv + pip install the requirements, then start\r\n"
                    + "  --requirements P  requirements file (default requirements-windows.txt)\r\n"
                    + "  --timeout S     seconds to wait for the server (default 240)\r\n"
                    + "  --repo PATH     repository root\r\n"
                    + "  --no-browser    do not open a browser\r\n"
                    + "  --check         headless self test, writes logs/launcher_check.txt\r\n"
                    + "  --stop          stop a running server and exit\r\n"
                    + "  --help          this text",
                    "TargetDesign-workbench",
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
                return 0;
            }

            string repoRoot = ServerHost.FindRepoRoot(options.RepoRoot);
            PythonInfo python = ServerHost.FindPython(repoRoot);

            if (options.StopOnly)
            {
                int pid = ServerHost.FindPidByPort(options.Port);
                if (pid <= 0)
                {
                    if (!options.Check)
                    {
                        MessageBox.Show("端口 " + options.Port + " 上没有运行中的服务。",
                            "TargetDesign-workbench", MessageBoxButtons.OK,
                            MessageBoxIcon.Information);
                    }
                    WriteCheckFile(options, repoRoot, "stop: nothing listening on port "
                        + options.Port.ToString(CultureInfo.InvariantCulture));
                    return 0;
                }
                ServerHost.KillTree(pid);
                WriteCheckFile(options, repoRoot, "stop: killed pid "
                    + pid.ToString(CultureInfo.InvariantCulture));
                return 0;
            }

            if (options.Check)
            {
                return RunCheck(options, repoRoot, python);
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            ServerHost host = new ServerHost();
            host.RepoRoot = repoRoot;
            host.Port = options.Port;
            host.Host = options.Host;
            host.Python = python;
            Directory.CreateDirectory(Path.Combine(repoRoot, "logs"));
            host.LogPath = Path.Combine(repoRoot, "logs",
                "webapp_launcher_" + DateTime.Now.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture) + ".log");
            host.Log("launcher started; repo=" + repoRoot + "; host=" + options.Host
                + "; port=" + options.Port);

            Application.Run(new MainForm(host, options));
            return 0;
        }

        private static int RunCheck(Options options, string repoRoot, PythonInfo python)
        {
            StringBuilder report = new StringBuilder();
            int exitCode = 0;
            if (ServerHost.IsWorkbench(options.Port))
            {
                report.AppendLine("status: already-running");
                report.AppendLine("host: " + options.Host);
                report.AppendLine("url: http://127.0.0.1:" + options.Port + "/");
                int runningPid = ServerHost.FindPidByPort(options.Port);
                report.AppendLine("pid: " + runningPid);
                if (options.StopOnly)
                {
                    ServerHost.KillTree(runningPid);
                    report.AppendLine("stopped: pid " + runningPid);
                }
                WriteCheckFile(options, repoRoot, report.ToString().TrimEnd());
                return 0;
            }

            if (python == null)
            {
                report.AppendLine("status: python-missing");
                report.AppendLine("searched: CRISPR_WORKBENCH_PYTHON, repo .venv/.venv310, PATH, user installs");
                report.AppendLine("rejected: "
                    + (ServerHost.LastRejected != null ? ServerHost.LastRejected.Exe : "(no candidate)"));
                report.AppendLine("hint: install Python 3, then"
                    + " 'python -m pip install -r requirements-windows.txt'");
                WriteCheckFile(options, repoRoot, report.ToString().TrimEnd());
                return 2;
            }

            List<string> missing = ServerHost.MissingModules(python);
            ServerHost installer = new ServerHost();
            installer.RepoRoot = repoRoot;
            installer.Port = options.Port;
            installer.Host = options.Host;
            installer.Python = python;
            installer.LogPath = Path.Combine(repoRoot, "logs", "webapp_launcher_check.log");
            if (options.Install)
            {
                string requirements = ServerHost.ResolveRequirements(repoRoot, options.Requirements);
                Queue<string> tail = new Queue<string>();
                Action<string> collector = delegate(string line)
                {
                    if (string.IsNullOrEmpty(line))
                    {
                        return;
                    }
                    installer.Log("install> " + line);
                    tail.Enqueue(line);
                    while (tail.Count > 5)
                    {
                        tail.Dequeue();
                    }
                };
                report.AppendLine("install: " + requirements);
                string installError;
                bool installed = installer.InstallDependencies(python, requirements, collector, out installError);
                report.AppendLine("install result: " + (installed ? "ok" : ("failed: " + installError)));
                foreach (string line in tail)
                {
                    report.AppendLine("  " + line);
                }
                if (!installed)
                {
                    WriteCheckFile(options, repoRoot, report.ToString().TrimEnd());
                    return 6;
                }
                python = ServerHost.NewPythonInfo(installer.VenvPythonPath,
                    installer.VenvPythonPath + " (repository venv)");
            }

            if (missing != null && missing.Count > 0)
            {
                report.AppendLine("status: packages-missing");
                report.AppendLine("python: " + python.Description);
                report.AppendLine("missing packages: " + string.Join(", ", missing.ToArray()));
                report.AppendLine("hint: " + python.Exe
                    + " -m pip install -r requirements-windows.txt");
                WriteCheckFile(options, repoRoot, report.ToString().TrimEnd());
                return 5;
            }

            ServerHost host = new ServerHost();
            host.RepoRoot = repoRoot;
            host.Port = options.Port;
            host.Host = options.Host;
            host.Python = python;
            Directory.CreateDirectory(Path.Combine(repoRoot, "logs"));
            host.LogPath = Path.Combine(repoRoot, "logs", "webapp_launcher_check.log");
            try
            {
                host.Start();
            }
            catch (Exception exc)
            {
                report.AppendLine("status: start-failed");
                report.AppendLine("error: " + exc.Message);
                WriteCheckFile(options, repoRoot, report.ToString().TrimEnd());
                return 3;
            }

            bool ok = host.WaitUntilReady(TimeSpan.FromSeconds(options.TimeoutSeconds), null);
            report.AppendLine("status: " + (ok ? "ready" : "not-ready"));
            report.AppendLine("host: " + host.BindAddress);
            report.AppendLine("url: " + host.Url);
            if (!host.LocalOnly)
            {
                foreach (string lanUrl in host.LanUrls())
                {
                    report.AppendLine("lan url: " + lanUrl);
                }
            }
            report.AppendLine("pid: " + host.Child.Id.ToString(CultureInfo.InvariantCulture));
            report.AppendLine("python: " + python.Description);
            report.AppendLine("packages: ok (" + string.Join(", ", ServerHost.RequiredModules) + ")");
            report.AppendLine("repo: " + repoRoot);
            report.AppendLine("log: " + host.LogPath);
            if (!ok)
            {
                exitCode = 4;
            }
            host.Stop();
            report.AppendLine("stopped: true");
            WriteCheckFile(options, repoRoot, report.ToString().TrimEnd());
            return exitCode;
        }
    }
}
