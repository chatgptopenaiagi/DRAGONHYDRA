using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class DragonhydraLauncher
{
    private static string state;
    private static Dictionary<string,object> Read(string name)
    {
        return new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(Dragonhydra.Workstation.AtomicFile.Read(Path.Combine(state,name)));
    }
    private static string Quote(string value) { if(value.Contains("\"") || value.Contains("\n")) throw new ArgumentException(); return "\""+value.TrimEnd('\\')+"\""; }
    private static void Open(string url) { Process.Start(new ProcessStartInfo(url) { UseShellExecute=true }); }
    [STAThread] public static void Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        state=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),"DRAGONHYDRA");
        bool administration=false;
        for(int i=0;i<args.Length;i++)
        {
            if(args[i]=="--state" && i+1<args.Length) state=Path.GetFullPath(args[++i]);
            else if(args[i]=="--administration") administration=true;
            else { MessageBox.Show("Unsupported launcher option.","DRAGONHYDRA");return; }
        }
        try
        {
            if(administration) { ShowAdministration();return; }
            using(var form=new Form { Text="Starting DRAGONHYDRA", Width=520, Height=185, StartPosition=FormStartPosition.CenterScreen, MaximizeBox=false })
            {
                var label=new Label { Left=20,Top=20,Width=460,Height=55,Text="Waiting for the local DRAGONHYDRA services…" };
                var retry=new Button { Left=20,Top=85,Width=110,Text="Retry",Enabled=false };
                var diagnostics=new Button { Left=145,Top=85,Width=140,Text="Open diagnostics" };
                diagnostics.Click+=delegate { Open(state); };
                form.Controls.AddRange(new Control[]{label,retry,diagnostics});
                DateTime deadline=DateTime.UtcNow.AddSeconds(100);
                var timer=new Timer { Interval=500 };
                retry.Click+=delegate { deadline=DateTime.UtcNow.AddSeconds(100);retry.Enabled=false;timer.Start(); };
                timer.Tick+=delegate
                {
                    try
                    {
                        var status=Read("status.json");
                        string stage=Convert.ToString(status["stage"]);
                        label.Text="Local services: "+stage;
                        if(stage=="ready")
                        {
                            timer.Stop();
                            string executable=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"..","client","DRAGONHYDRA-Client.exe"));
                            var info=Read("launcher.json");
                            string profile=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"DRAGONHYDRA",Convert.ToString(info["service_name"]),"WebView");
                            Process.Start(new ProcessStartInfo(executable,"--state "+Quote(Path.Combine(state,"client"))+" --profile "+Quote(profile)) { UseShellExecute=false });
                            form.Close();
                        }
                        else if(stage=="failed") { timer.Stop();retry.Enabled=true;label.Text="Services could not start. Open diagnostics for the recorded error, then retry after repair."; }
                    }
                    catch { label.Text="Waiting for first-run initialization. No additional server will be started."; }
                    if(DateTime.UtcNow>deadline) { timer.Stop();retry.Enabled=true;label.Text="Startup timed out. Open diagnostics or retry after the service is ready."; }
                };
                timer.Start(); Application.Run(form); timer.Dispose();
            }
        }
        catch(Exception ex) { MessageBox.Show("DRAGONHYDRA could not open its local installation ("+ex.GetType().Name+"). Check the installed service and data-directory permissions.","DRAGONHYDRA",MessageBoxButtons.OK,MessageBoxIcon.Error); }
    }
    private static void ShowAdministration()
    {
        var info=Read("first-run.json");
        using(var form=new Form { Text="DRAGONHYDRA Administration",Width=540,Height=280,StartPosition=FormStartPosition.CenterScreen,MaximizeBox=false })
        {
            var note=new Label{Left=20,Top=15,Width=480,Height=50,Text="Your local Joomla administrator account. Sign in and change its generated password. This information is private to the installation owner."};
            var user=new TextBox{Left=140,Top=80,Width=340,ReadOnly=true,Text=Convert.ToString(info["username"])};
            var password=new TextBox{Left=140,Top=115,Width=340,ReadOnly=true,UseSystemPasswordChar=true,Text=Convert.ToString(info["password"])};
            var show=new CheckBox{Left=140,Top=150,Width=210,Text="Show initial password"};show.CheckedChanged+=delegate{password.UseSystemPasswordChar=!show.Checked;};
            var launch=new Button{Left=140,Top=185,Width=170,Text="Open Joomla"};launch.Click+=delegate{Open(Convert.ToString(info["url"]));};
            form.Controls.AddRange(new Control[]{note,new Label{Left=20,Top=82,Text="Username"},new Label{Left=20,Top=117,Text="Password"},user,password,show,launch});
            Application.Run(form);
        }
    }
}
