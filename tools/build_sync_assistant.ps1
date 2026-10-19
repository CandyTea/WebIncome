param([string]$OutputPath)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -eq 'Core') {
    throw 'Run this build with Windows PowerShell (powershell.exe), not pwsh.'
}
$projectDirectory = Split-Path -Parent $PSScriptRoot
if (-not $OutputPath) {
    $OutputPath = Join-Path $projectDirectory ([string]::Concat([char]0x0045,[char]0x0078,[char]0x0063,[char]0x0065,[char]0x006C,[char]0x540C,[char]0x6B65,[char]0x52A9,[char]0x624B,'.exe'))
}
$sourcePath = Join-Path $projectDirectory 'desktop\SyncAssistant.cs'
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$buildDirectory = Join-Path $projectDirectory '.local\build'
[System.IO.Directory]::CreateDirectory($buildDirectory) | Out-Null
$compiledPath = Join-Path $buildDirectory (([Guid]::NewGuid().ToString('N')) + '.exe')
# Read the source explicitly as UTF-8, including Chinese UI labels.
$source = [System.IO.File]::ReadAllText($sourcePath, [System.Text.Encoding]::UTF8)
Add-Type -TypeDefinition $source -Language CSharp -ReferencedAssemblies 'System.dll','System.Core.dll','System.Drawing.dll','System.Windows.Forms.dll','System.Web.Extensions.dll' -OutputAssembly $compiledPath -OutputType WindowsApplication
[System.IO.File]::Copy($compiledPath, $OutputPath, $true)
$configuration = @'
<?xml version="1.0" encoding="utf-8" ?>
<configuration>
  <startup><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.8" /></startup>
  <System.Windows.Forms.ApplicationConfigurationSection>
    <add key="DpiAwareness" value="PerMonitorV2" />
  </System.Windows.Forms.ApplicationConfigurationSection>
</configuration>
'@
[System.IO.File]::WriteAllText(($OutputPath + '.config'), $configuration, [System.Text.UTF8Encoding]::new($false))
Write-Output ('Built: ' + $OutputPath)
