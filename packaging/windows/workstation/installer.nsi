Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!ifndef STAGE
!error "Build with scripts/Build-Workstation.ps1."
!endif
!ifndef SOURCE_COMMIT
!error "CORE NEXT requires the frozen release source commit."
!endif
Name "DRAGONHYDRA CORE NEXT ${VERSION}"
OutFile "${OUTPUT}"
InstallDir "$PROGRAMFILES64\DRAGONHYDRA CORE NEXT"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
SetCompressorDictSize 64
VIProductVersion "${NUMERICVERSION}"
VIAddVersionKey "ProductName" "DRAGONHYDRA CORE NEXT Workstation"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${NUMERICVERSION}"
VIAddVersionKey "FileDescription" "Unsigned development complete workstation installer"
VIAddVersionKey "LegalCopyright" "DRAGONHYDRA contributors"
ShowInstDetails show
ShowUninstDetails show
Var StateRoot
Var ServiceName
Var ShortcutSuffix
Var Parameters
Var Result
Var PsExe
Var CheckScript
Var ProfilePath
Var SeedSnapshot
Var SeedSnapshotSha256
Var SeedArgs
Var ShortcutName
Var UninstallId
Var InstallationId
Var InitialInstallRoot
Var ProfileArgs
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Open DRAGONHYDRA CORE NEXT"
!define MUI_FINISHPAGE_RUN_FUNCTION "LaunchWorkstation"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

!macro Fail MESSAGE
    DetailPrint "${MESSAGE}"
    IfSilent +2
    MessageBox MB_OK|MB_ICONSTOP "${MESSAGE}"
    SetErrorLevel 1
    Abort
!macroend

!macro NormalizePath VARIABLE
    ; NSIS GetFullPathName can return empty for a not-yet-created target.
    ; The Windows API normalizes absolute paths without requiring them to exist.
    System::Call 'kernel32::GetFullPathNameW(w "${VARIABLE}", i ${NSIS_MAX_STRLEN}, w .r0, p 0) i.r1'
    ${If} $1 == 0
    ${OrIf} $1 >= ${NSIS_MAX_STRLEN}
        !insertmacro Fail "The selected product path could not be normalized safely."
    ${EndIf}
    StrCpy ${VARIABLE} $0
!macroend

Function .onInit
    ${IfNot} ${IsNativeAMD64}
        !insertmacro Fail "This build requires AMD64 Windows. ARM64 and 32-bit Windows are not tested targets."
    ${EndIf}
    ${IfNot} ${AtLeastWin10}
        !insertmacro Fail "DRAGONHYDRA Workstation requires Windows 10 or later."
    ${EndIf}
    SetRegView 64
    ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" "Release"
    ${If} $0 < 528040
        !insertmacro Fail "Install Microsoft .NET Framework 4.8 before running this installer."
    ${EndIf}
    SetShellVarContext all
    StrCpy $StateRoot ""
    StrCpy $ServiceName ""
    ${GetParameters} $Parameters
    ${GetOptions} $Parameters "/PROFILE=" $ProfilePath
    ${GetOptions} $Parameters "/SEED=" $SeedSnapshot
    ${GetOptions} $Parameters "/SEEDHASH=" $SeedSnapshotSha256
    StrCpy $SeedArgs ""
    ${If} $SeedSnapshot != ""
        StrCpy $SeedArgs '-SeedSnapshot "$SeedSnapshot" -SeedSnapshotSha256 "$SeedSnapshotSha256"'
    ${EndIf}
    ${GetOptions} $Parameters "/STATE=" $0
    ${If} $0 != ""
        StrCpy $StateRoot $0
    ${EndIf}
    ${GetOptions} $Parameters "/SERVICE=" $0
    ${If} $0 != ""
        StrCpy $ServiceName $0
    ${EndIf}
    StrCpy $ShortcutSuffix ""
    ${If} $ServiceName != "DragonhydraWorkstation"
        StrCpy $ShortcutSuffix " - $ServiceName"
    ${EndIf}
    ; This NSIS stub is 32-bit. Sysnative selects 64-bit PowerShell from both
    ; the UI and installation worker threads, without per-thread redirection.
    StrCpy $PsExe "$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
    InitPluginsDir
    SetOutPath "$PLUGINSDIR"
    File /oname=Installer-Checks.ps1 "${STAGE}\workstation\Installer-Checks.ps1"
    File /oname=CoreNextProfile.ps1 "${STAGE}\workstation\CoreNextProfile.ps1"
    StrCpy $CheckScript "$PLUGINSDIR\Installer-Checks.ps1"
    StrCpy $ProfileArgs ""
    ${If} $ProfilePath != ""
        StrCpy $ProfileArgs '-ProfilePath "$ProfilePath"'
    ${EndIf}
    nsExec::ExecToLog '"$PsExe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$CheckScript" -Action SelectProfile $ProfileArgs -ReleaseVersion "${VERSION}" -ReleaseSourceCommit "${SOURCE_COMMIT}" -OutputBindings "$PLUGINSDIR\core-next-selected.ini"'
    Pop $Result
    ${If} $Result != 0
        !insertmacro Fail "The CORE NEXT installation profile could not be selected safely. No product service was changed."
    ${EndIf}
    StrCpy $InitialInstallRoot $INSTDIR
    ReadINIStr $INSTDIR "$PLUGINSDIR\core-next-selected.ini" "Profile" "InstallRoot"
    ${If} $InitialInstallRoot != "$PROGRAMFILES64\DRAGONHYDRA CORE NEXT"
    ${AndIf} $InitialInstallRoot != $INSTDIR
        !insertmacro Fail "The requested binary directory differs from the selected CORE NEXT profile."
    ${EndIf}
    ReadINIStr $ProfilePath "$PLUGINSDIR\core-next-selected.ini" "Profile" "ProfilePath"
    ReadINIStr $0 "$PLUGINSDIR\core-next-selected.ini" "Profile" "StateRoot"
    ${If} $StateRoot != ""
    ${AndIf} $StateRoot != $0
        !insertmacro Fail "The requested state directory differs from the selected CORE NEXT profile."
    ${EndIf}
    StrCpy $StateRoot $0
    ReadINIStr $0 "$PLUGINSDIR\core-next-selected.ini" "Profile" "ServiceName"
    ${If} $ServiceName != ""
    ${AndIf} $ServiceName != $0
        !insertmacro Fail "The requested service differs from the selected CORE NEXT profile."
    ${EndIf}
    StrCpy $ServiceName $0
    ReadINIStr $ShortcutName "$PLUGINSDIR\core-next-selected.ini" "Profile" "ShortcutName"
    ReadINIStr $UninstallId "$PLUGINSDIR\core-next-selected.ini" "Profile" "UninstallId"
    ReadINIStr $InstallationId "$PLUGINSDIR\core-next-selected.ini" "Profile" "InstallationId"
FunctionEnd

Function CheckWebView
    ReadRegStr $0 HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
    ${If} $0 == ""
        ReadRegStr $0 HKCU "SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
    ${EndIf}
    ${If} $0 == ""
    ${OrIf} $0 == "0.0.0.0"
        DetailPrint "Installing missing WebView2 using the verified Microsoft online bootstrapper."
        InitPluginsDir
        SetOutPath "$PLUGINSDIR"
        File "${PREREQUISITES}\MicrosoftEdgeWebview2Setup.exe"
        ExecWait '"$PLUGINSDIR\MicrosoftEdgeWebview2Setup.exe" /silent /install' $Result
        ${If} $Result != 0
            !insertmacro Fail "WebView2 installation failed. Check connectivity to Microsoft, install WebView2, and retry."
        ${EndIf}
        ReadRegStr $0 HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
        ${If} $0 == ""
            !insertmacro Fail "WebView2 was not detected after setup; the workstation was not installed."
        ${EndIf}
    ${EndIf}
FunctionEnd

Section "Complete workstation" SEC_MAIN
    DetailPrint "Selected binary directory: [$INSTDIR]"
    DetailPrint "Selected retained-data directory: [$StateRoot]"
    DetailPrint "Selected product service: [$ServiceName]"
    !insertmacro NormalizePath $INSTDIR
    !insertmacro NormalizePath $StateRoot
    DetailPrint "Resolved binary directory: [$INSTDIR]"
    DetailPrint "Resolved retained-data directory: [$StateRoot]"
    DetailPrint "Verifying the installation worker uses 64-bit Windows PowerShell."
    nsExec::ExecToLog '"$PsExe" -NoLogo -NoProfile -NonInteractive -Command "[Environment]::Is64BitProcess; if(-not [Environment]::Is64BitProcess){exit 1}"'
    Pop $Result
    ${If} $Result != 0
        !insertmacro Fail "The required 64-bit Windows PowerShell could not be started."
    ${EndIf}
    InitPluginsDir
    SetOutPath "$PLUGINSDIR"
    File /oname=Installer-Checks.ps1 "${STAGE}\workstation\Installer-Checks.ps1"
    File /oname=CoreNextProfile.ps1 "${STAGE}\workstation\CoreNextProfile.ps1"
    StrCpy $CheckScript "$PLUGINSDIR\Installer-Checks.ps1"
    nsExec::ExecToLog '"$PsExe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$CheckScript" -Action Validate -ReleaseVersion "${VERSION}" -ReleaseSourceCommit "${SOURCE_COMMIT}" -ProfilePath "$ProfilePath" -InstallRoot "$INSTDIR" -StateRoot "$StateRoot" -ServiceName "$ServiceName"'
    Pop $Result
    ${If} $Result != 0
        !insertmacro Fail "Installation ownership or path checks failed. Existing files, services, and shortcuts were preserved. See installation details."
    ${EndIf}
    IfFileExists "$INSTDIR\workstation-installed.json" 0 fresh
    nsExec::ExecToLog '"$PsExe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\workstation\Workstation.ps1" -Action Stop -ProfilePath "$ProfilePath" -InstallRoot "$INSTDIR" -StateRoot "$StateRoot" -ServiceName "$ServiceName"'
    Pop $Result
    ${If} $Result != 0
        !insertmacro Fail "The owned workstation service could not be stopped safely; no replacement files were copied."
    ${EndIf}
fresh:
    Call CheckWebView
    SetOutPath "$INSTDIR"
    DetailPrint "Extracting the private workstation payload."
    SetDetailsPrint textonly
    File /r /x "installer.ini" /x "CORE-NEXT-PAYLOAD.json" "${STAGE}\*"
    SetDetailsPrint both
    DetailPrint "Payload extracted; initializing the owned workstation service."
    WriteINIStr "$INSTDIR\workstation\installer.ini" "Product" "Identity" "DRAGONHYDRA CORE NEXT v1"
    WriteINIStr "$INSTDIR\workstation\installer.ini" "Product" "InstallRoot" "$INSTDIR"
    WriteINIStr "$INSTDIR\workstation\installer.ini" "Product" "StateRoot" "$StateRoot"
    WriteINIStr "$INSTDIR\workstation\installer.ini" "Product" "ServiceName" "$ServiceName"
    WriteINIStr "$INSTDIR\workstation\installer.ini" "Product" "Version" "${VERSION}"
    WriteINIStr "$INSTDIR\workstation\installer.ini" "Product" "InstallationId" "$InstallationId"
    WriteINIStr "$INSTDIR\workstation\installer.ini" "Product" "ProfilePath" "$ProfilePath"
    WriteINIStr "$INSTDIR\workstation\installer.ini" "Product" "ShortcutName" "$ShortcutName"
    WriteINIStr "$INSTDIR\workstation\installer.ini" "Product" "UninstallId" "$UninstallId"
    nsExec::ExecToLog '"$PsExe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\workstation\Workstation.ps1" -Action Install $SeedArgs -ProfilePath "$ProfilePath" -InstallRoot "$INSTDIR" -StateRoot "$StateRoot" -ServiceName "$ServiceName"'
    Pop $Result
    ${If} $Result != 0
        !insertmacro Fail "Workstation initialization failed. Inspect private diagnostics in $StateRoot and retry this installer. User data was retained."
    ${EndIf}
    WriteUninstaller "$INSTDIR\Uninstall-Workstation.exe"
    WriteRegStr HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$UninstallId" "DisplayName" "$ShortcutName"
    WriteRegStr HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$UninstallId" "DisplayVersion" "${VERSION}"
    WriteRegStr HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$UninstallId" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$UninstallId" "UninstallString" '$\"$INSTDIR\Uninstall-Workstation.exe$\"'
    WriteRegDWORD HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$UninstallId" "NoModify" 1
    CreateDirectory "$SMPROGRAMS\$ShortcutName"
    CreateShortcut "$DESKTOP\$ShortcutName.lnk" "$INSTDIR\workstation\DragonhydraLauncher.exe" '--state "$StateRoot"'
    CreateShortcut "$SMPROGRAMS\$ShortcutName\DRAGONHYDRA CORE NEXT.lnk" "$INSTDIR\workstation\DragonhydraLauncher.exe" '--state "$StateRoot"'
    CreateShortcut "$SMPROGRAMS\$ShortcutName\DRAGONHYDRA CORE NEXT Administration.lnk" "$INSTDIR\workstation\DragonhydraLauncher.exe" '--state "$StateRoot" --administration'
    SetErrorLevel 0
SectionEnd

Function LaunchWorkstation
    IfSilent done
    Exec '"$INSTDIR\workstation\DragonhydraLauncher.exe" --state "$StateRoot"'
done:
FunctionEnd

Function un.onInit
    SetRegView 64
    SetShellVarContext all
    StrCpy $PsExe "$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
    ReadINIStr $ProfilePath "$INSTDIR\workstation\installer.ini" "Product" "ProfilePath"
    ReadINIStr $StateRoot "$INSTDIR\workstation\installer.ini" "Product" "StateRoot"
    ReadINIStr $ServiceName "$INSTDIR\workstation\installer.ini" "Product" "ServiceName"
    ReadINIStr $ShortcutName "$INSTDIR\workstation\installer.ini" "Product" "ShortcutName"
    ReadINIStr $UninstallId "$INSTDIR\workstation\installer.ini" "Product" "UninstallId"
    ReadINIStr $InstallationId "$INSTDIR\workstation\installer.ini" "Product" "InstallationId"
    StrCpy $ShortcutSuffix ""
    ${If} $ServiceName != "DragonhydraWorkstation"
        StrCpy $ShortcutSuffix " - $ServiceName"
    ${EndIf}
FunctionEnd

Section "Uninstall"
    nsExec::ExecToLog '"$PsExe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\workstation\Installer-Checks.ps1" -Action ValidateUninstall -ReleaseVersion "${VERSION}" -ReleaseSourceCommit "${SOURCE_COMMIT}" -ProfilePath "$ProfilePath" -InstallRoot "$INSTDIR" -StateRoot "$StateRoot" -ServiceName "$ServiceName"'
    Pop $Result
    ${If} $Result != 0
        !insertmacro Fail "Uninstall ownership checks failed. No services or product files were removed."
    ${EndIf}
    nsExec::ExecToLog '"$PsExe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\workstation\Workstation.ps1" -Action Uninstall -ProfilePath "$ProfilePath" -InstallRoot "$INSTDIR" -StateRoot "$StateRoot" -ServiceName "$ServiceName"'
    Pop $Result
    ${If} $Result != 0
        !insertmacro Fail "The exact owned service could not be removed safely. Product files and user data were retained."
    ${EndIf}
    nsExec::ExecToLog '"$PsExe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\workstation\Installer-Checks.ps1" -Action RemoveShortcuts -ReleaseVersion "${VERSION}" -ReleaseSourceCommit "${SOURCE_COMMIT}" -ProfilePath "$ProfilePath" -InstallRoot "$INSTDIR" -StateRoot "$StateRoot" -ServiceName "$ServiceName"'
    Pop $Result
    ${If} $Result != 0
        !insertmacro Fail "Shortcut ownership checks failed; retained product files can be inspected safely."
    ${EndIf}
    DeleteRegKey HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$UninstallId"
    SetOutPath "$TEMP"
    ; ValidateUninstall has resolved the absolute owned target and state separation.
    ClearErrors
    RMDir /r "$INSTDIR"
    ${If} ${Errors}
        !insertmacro Fail "The owned service was removed, but some product files remain locked. Close the workstation, then retry cleanup. All user data was retained."
    ${EndIf}
    DetailPrint "User data retained at $StateRoot. Shared software and unrelated services were not removed."
    SetErrorLevel 0
SectionEnd
