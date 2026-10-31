using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.ServiceProcess;
using System.Threading;

// One SCM supervisor. Descendants are confined to a product-owned kill-on-close
// job; normal stops signal PowerShell to shut down kernel/web/database in order.
internal sealed class DragonhydraService : ServiceBase
{
    private readonly string state;
    private Process worker;
    private IntPtr job;
    private volatile bool stopping;

    private DragonhydraService(string statePath, string name)
    {
        state = Path.GetFullPath(statePath);
        ServiceName = name;
        CanStop = true;
        CanShutdown = true;
        // sc.exe does not create an EventLog source. A least-privilege identity
        // must never need registry write access simply to start this service.
        AutoLog = false;
    }
    private static string Quote(string value)
    {
        if (value.IndexOf('"') >= 0 || value.IndexOf('\n') >= 0) throw new ArgumentException("Invalid path");
        return "\"" + value.TrimEnd('\\') + "\"";
    }
    private void Log(string value)
    {
        try { File.AppendAllText(Path.Combine(state, "service-host.log"), DateTime.UtcNow.ToString("o") + " " + value + Environment.NewLine); }
        catch { }
    }
    protected override void OnStart(string[] args)
    {
        stopping = false;
        string script = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Workstation.ps1");
        string powershell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
        job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero) throw new System.ComponentModel.Win32Exception();
        var limits = new ExtendedLimits();
        limits.BasicLimitInformation.LimitFlags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        int size = Marshal.SizeOf(limits);
        IntPtr memory = Marshal.AllocHGlobal(size);
        try
        {
            Marshal.StructureToPtr(limits, memory, false);
            if (!SetInformationJobObject(job, 9, memory, (uint)size)) throw new System.ComponentModel.Win32Exception();
        }
        finally { Marshal.FreeHGlobal(memory); }
        worker = new Process();
        worker.StartInfo = new ProcessStartInfo(powershell,
            "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File " + Quote(script) + " -Action Run -StateRoot " + Quote(state))
        { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = state, RedirectStandardOutput = true, RedirectStandardError = true };
        worker.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e) { if(e.Data != null) { try { File.AppendAllText(Path.Combine(state,"supervisor.stdout.log"),e.Data+Environment.NewLine); } catch {} } };
        worker.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) { if(e.Data != null) { try { File.AppendAllText(Path.Combine(state,"supervisor.stderr.log"),e.Data+Environment.NewLine); } catch {} } };
        worker.Start();
        worker.BeginOutputReadLine();
        worker.BeginErrorReadLine();
        if (!AssignProcessToJobObject(job, worker.Handle)) throw new System.ComponentModel.Win32Exception();
        Log("Supervisor started pid=" + worker.Id);
        ThreadPool.QueueUserWorkItem(delegate
        {
            worker.WaitForExit();
            Log("Supervisor exited code=" + worker.ExitCode);
            if (!stopping) Environment.Exit(worker.ExitCode == 0 ? 1 : worker.ExitCode);
        });
    }
    protected override void OnStop()
    {
        stopping = true;
        RequestAdditionalTime(65000);
        File.WriteAllText(Path.Combine(state, "stop.request"), "stop");
        if (worker != null && !worker.HasExited && !worker.WaitForExit(55000)) Log("Graceful deadline expired; closing owned process job");
        if (job != IntPtr.Zero) { CloseHandle(job); job = IntPtr.Zero; }
        Log("Service stopped");
    }
    protected override void OnShutdown() { OnStop(); }
    public static void Main(string[] args)
    {
        string statePath = null, name = "DragonhydraWorkstation";
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--state" && i + 1 < args.Length) statePath = args[++i];
            else if (args[i] == "--name" && i + 1 < args.Length) name = args[++i];
            else throw new ArgumentException("Unsupported service argument");
        }
        if (statePath == null || !System.Text.RegularExpressions.Regex.IsMatch(name, "^Dragonhydra[A-Za-z0-9_-]{0,60}$")) throw new ArgumentException("Invalid service configuration");
        ServiceBase.Run(new DragonhydraService(statePath, name));
    }
    [StructLayout(LayoutKind.Sequential)] private struct BasicLimits
    {
        public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)] private struct IoCounters { public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount, ReadTransferCount, WriteTransferCount, OtherTransferCount; }
    [StructLayout(LayoutKind.Sequential)] private struct ExtendedLimits
    {
        public BasicLimits BasicLimitInformation;
        public IoCounters IoInfo;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] private static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool SetInformationJobObject(IntPtr job, int type, IntPtr information, uint length);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);
}
