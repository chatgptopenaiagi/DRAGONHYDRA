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
    private static void ValidateState()
    {
        var binding=Read("launcher.json");
        string id=Convert.ToString(binding["installation_id"]);
        if(!System.Text.RegularExpressions.Regex.IsMatch(id,@"^core-next-[a-f0-9]{32}$")) throw new InvalidOperationException("CORE NEXT identity required");
        string expected=Path.Combine(@"C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\profiles",id,"state");
        if(!String.Equals(Path.GetFullPath(state),expected,StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("CORE NEXT state required");
        foreach(string path in new[]{state,Convert.ToString(binding["browser_user_data"])}) {
            for(string walk=path;!String.IsNullOrEmpty(walk);walk=Path.GetDirectoryName(walk)) {
                if(Directory.Exists(walk) && (File.GetAttributes(walk)&FileAttributes.ReparsePoint)!=0) throw new InvalidOperationException("CORE NEXT ordinary state required");
            }
        }
    }
    [STAThread] public static void Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        state=null;
        bool administration=false;
        for(int i=0;i<args.Length;i++)
        {
            if(args[i]=="--state" && i+1<args.Length) state=Path.GetFullPath(args[++i]);
            else if(args[i]=="--administration") administration=true;
            else { MessageBox.Show("Unsupported launcher option.","DRAGONHYDRA");return; }
        }
        if(String.IsNullOrEmpty(state)) { MessageBox.Show("An explicit CORE NEXT installation state is required.","DRAGONHYDRA CORE NEXT");return; }
        try
        {
            ValidateState();
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
                            string profile=Convert.ToString(info["browser_user_data"]);
                            string installation=Convert.ToString(info["installation_id"]);
                            string expectedRoot=Path.Combine(@"C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\profiles",installation);
                            if(!installation.StartsWith("core-next-") || !String.Equals(Path.GetFullPath(state),Path.Combine(expectedRoot,"state"),StringComparison.OrdinalIgnoreCase) || !String.Equals(Path.GetFullPath(profile),Path.Combine(expectedRoot,"browser"),StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("CORE NEXT profile binding mismatch");
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
