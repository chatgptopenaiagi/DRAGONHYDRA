using System;
using System.IO;
using System.Text;
using System.Threading;

namespace Dragonhydra.Workstation
{
    // Keep File.Replace's nullable backup argument entirely in typed C#.
    // Windows PowerShell 5.1 otherwise coerces $null into an empty filename.
    public static class AtomicFile
    {
        public static void Commit(string temporary, string destination)
        {
            Commit(temporary, destination, null);
        }
        public static void Commit(string temporary, string destination, string backup)
        {
            temporary=Path.GetFullPath(temporary);
            destination=Path.GetFullPath(destination);
            if(String.Equals(temporary,destination,StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("Temporary and destination must differ.");
            if(!String.Equals(Path.GetDirectoryName(temporary),Path.GetDirectoryName(destination),StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("Atomic temporary files must be siblings of the destination.");
            if(String.IsNullOrEmpty(backup)) backup=null;
            else
            {
                backup=Path.GetFullPath(backup);
                if(String.Equals(backup,temporary,StringComparison.OrdinalIgnoreCase) || String.Equals(backup,destination,StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("Backup must be a separate file.");
            }
            for(int attempt=0;;attempt++)
            {
                try
                {
                    if(File.Exists(destination)) File.Replace(temporary,destination,backup);
                    else File.Move(temporary,destination);
                    return;
                }
                catch(IOException error)
                {
                    int code=error.HResult & 0xffff;
                    // Get-Content, antivirus and other readers may briefly deny
                    // delete sharing. Retry only sharing/lock violations and an
                    // existence-check race, never permission or data errors.
                    bool retry=code==32 || code==33 || ((code==80 || code==183) && File.Exists(temporary) && File.Exists(destination));
                    if(!retry || attempt>=39) throw;
                    Thread.Sleep(25);
                }
            }
        }
        public static string Read(string path)
        {
            for(int attempt=0;;attempt++)
            {
                try
                {
                    using(var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete))
                    using(var reader=new StreamReader(stream,new UTF8Encoding(false,true),true)) return reader.ReadToEnd();
                }
                catch(IOException error)
                {
                    int code=error.HResult & 0xffff;
                    if((code!=32 && code!=33) || attempt>=39) throw;
                    Thread.Sleep(25);
                }
            }
        }
        public static void Write(string destination, string text)
        {
            destination=Path.GetFullPath(destination);
            string temporary=destination+".next."+Guid.NewGuid().ToString("N");
            try
            {
                byte[] bytes=new UTF8Encoding(false,true).GetBytes(text);
                using(var stream=new FileStream(temporary,FileMode.CreateNew,FileAccess.Write,FileShare.None,4096,FileOptions.WriteThrough))
                {
                    stream.Write(bytes,0,bytes.Length);
                    stream.Flush(true);
                }
                Commit(temporary,destination);
            }
            finally { if(File.Exists(temporary)) File.Delete(temporary); }
        }
    }
}
