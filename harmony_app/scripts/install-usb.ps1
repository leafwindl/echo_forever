[CmdletBinding()]
param(
    [string]$DeviceId = '',
    [string]$HapPath = '',
    [string]$HdcPath = $env:HDC_PATH,
    [switch]$NoLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $HdcPath) {
    $hdcCommand = Get-Command hdc -ErrorAction SilentlyContinue
    if ($hdcCommand) {
        $HdcPath = $hdcCommand.Source
    } elseif ($env:DEVECO_SDK_HOME -and (Test-Path -LiteralPath (Join-Path $env:DEVECO_SDK_HOME 'openharmony/toolchains/hdc.exe'))) {
        $HdcPath = Join-Path $env:DEVECO_SDK_HOME 'openharmony/toolchains/hdc.exe'
    } else {
        $HdcPath = 'D:/Devstudio/DevEco Studio/sdk/default/openharmony/toolchains/hdc.exe'
    }
}
$hdcExecutable = (Resolve-Path -LiteralPath $HdcPath).Path
if (-not $HapPath) {
    $HapPath = Join-Path $PSScriptRoot '../entry/build/default/outputs/default/entry-default-signed.hap'
}
$resolvedHap = (Resolve-Path -LiteralPath $HapPath).Path
if ([System.IO.Path]::GetExtension($resolvedHap) -ne '.hap') {
    throw 'Choose the signed HAP file produced by this project.'
}

# Read identity/version from the actual artifact, not from possibly newer source settings.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($resolvedHap)
try {
    $moduleEntry = $archive.GetEntry('module.json')
    if (-not $moduleEntry) { throw 'HAP does not contain module.json.' }
    $reader = [System.IO.StreamReader]::new($moduleEntry.Open())
    try { $moduleInfo = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
} finally {
    $archive.Dispose()
}
$bundleName = [string]$moduleInfo.app.bundleName
$versionName = [string]$moduleInfo.app.versionName
$versionCode = [int]$moduleInfo.app.versionCode
if ($bundleName -ne 'cn.echoaiforever.echo_app.dev') {
    throw "Unexpected bundle: $bundleName. No installation was attempted."
}

$targetOutput = & $hdcExecutable list targets 2>&1
$targets = @($targetOutput | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ -and $_ -notmatch '^\[' })
if (-not $DeviceId) {
    if ($targets.Count -ne 1) { throw 'Connect and authorize exactly one phone, or specify -DeviceId.' }
    $DeviceId = $targets[0]
} elseif ($targets -notcontains $DeviceId) {
    throw 'The selected device is not connected or authorized.'
}

$installArguments = @('-t', $DeviceId, 'install', '-r', $resolvedHap)
$installOutput = (& $hdcExecutable @installArguments 2>&1 | Out-String)
$installExitCode = $LASTEXITCODE
Write-Host $installOutput.Trim()
# hdc can exit zero even when it prints [Fail], so verify its actual result as well.
if ($installExitCode -ne 0 -or $installOutput -notmatch 'install bundle successfully' -or $installOutput -match '\[Fail\]') {
    throw 'USB replacement install failed. The script will never uninstall or clear app data.'
}
$dumpOutput = (& $hdcExecutable -t $DeviceId shell bm dump -n $bundleName 2>&1 | Out-String)
if ($dumpOutput -notmatch ('"versionCode"\s*:\s*' + $versionCode + '\b')) {
    throw 'Installation returned success, but the expected version was not confirmed on the phone.'
}
Write-Host "Verified $bundleName $versionName ($versionCode). Existing app data was retained."
if (-not $NoLaunch) {
    $launchOutput = (& $hdcExecutable -t $DeviceId shell aa start -b $bundleName -a EntryAbility 2>&1 | Out-String)
    Write-Host $launchOutput.Trim()
    if ($launchOutput -notmatch 'start ability successfully') {
        throw 'The app was installed, but automatic launch was not confirmed.'
    }
}
