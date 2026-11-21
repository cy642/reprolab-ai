[CmdletBinding()]
param(
    [string]$StorageDir = (Join-Path $env:TEMP "reprolab-phase7-demo"),
    [ValidateRange(1, 65535)][int]$BackendPort = 18000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 15173
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
if ($BackendPort -eq $FrontendPort) {
    throw "Choose different ports for the backend and frontend."
}
if (-not [System.IO.Path]::IsPathRooted($StorageDir)) {
    $StorageDir = Join-Path $Root $StorageDir
}
$Storage = [System.IO.Path]::GetFullPath($StorageDir)
$DailyStorage = [System.IO.Path]::GetFullPath((Join-Path $Backend "storage"))
if ($Storage -eq $DailyStorage -or $Storage.StartsWith($DailyStorage + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Daily storage is forbidden: $DailyStorage. Choose an independent -StorageDir."
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Backend virtual-environment Python was not found: $Python"
}
$Vite = Join-Path $Frontend "node_modules\vite\bin\vite.js"
if (-not (Test-Path -LiteralPath $Vite -PathType Leaf)) {
    throw "Frontend dependencies are missing. Install the existing package.json dependencies in frontend first."
}
$Node = (Get-Command "node.exe" -ErrorAction Stop).Source
$null = New-Item -ItemType Directory -Path $Storage -Force

function Assert-PortFree([int]$Port) {
    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    if ($listeners.Port -contains $Port) {
        $owners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
        $ownerText = if ($owners.Count) { "; owning PID(s): $($owners -join ', ')" } else { "" }
        throw "Port $Port is already in use$ownerText. Choose another port; no existing process was stopped."
    }
}

function Start-OwnedProcess(
    [string]$FilePath,
    [string]$Arguments,
    [string]$WorkingDirectory,
    [hashtable]$Environment
) {
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $FilePath
    $info.Arguments = $Arguments
    $info.WorkingDirectory = $WorkingDirectory
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    foreach ($key in $Environment.Keys) {
        $info.EnvironmentVariables[$key] = [string]$Environment[$key]
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $info
    if (-not $process.Start()) {
        throw "Failed to start child process: $FilePath"
    }
    return $process
}

function Wait-Ready([System.Diagnostics.Process]$Process, [string]$Url, [string]$Name) {
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) {
            throw "$Name exited before becoming ready; exit code: $($Process.ExitCode)."
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch {
            # The listener may not have started yet; keep checking this owned process.
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not become ready within 45 seconds: $Url"
}

function Stop-OwnedProcessTree([System.Diagnostics.Process]$Process) {
    if ($null -eq $Process -or $Process.HasExited) { return }
    $rootPid = $Process.Id
    $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $queue = [System.Collections.Generic.Queue[int]]::new()
    $tree = [System.Collections.Generic.List[int]]::new()
    $queue.Enqueue($rootPid)
    while ($queue.Count) {
        $parentPid = $queue.Dequeue()
        $tree.Add($parentPid)
        foreach ($item in $allProcesses | Where-Object { $_.ParentProcessId -eq $parentPid }) {
            $queue.Enqueue([int]$item.ProcessId)
        }
    }
    $ordered = $tree.ToArray()
    [array]::Reverse($ordered)
    foreach ($ownedPid in $ordered) {
        Stop-Process -Id $ownedPid -Force -ErrorAction SilentlyContinue
    }
}

Assert-PortFree $BackendPort
Assert-PortFree $FrontendPort
$children = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()
$pidFile = Join-Path $Storage "phase7_demo_processes.json"
$pidFileCreated = $false

try {
    Write-Host "[Phase7] Initializing isolated demo: $Storage"
    $initializer = Start-OwnedProcess `
        -FilePath $Python `
        -Arguments "-m app.phase7_demo --storage-dir `"$Storage`"" `
        -WorkingDirectory $Backend `
        -Environment @{ REPROLAB_STORAGE_DIR = $Storage; REPROLAB_DISABLE_LLM = "1" }
    $children.Add($initializer)
    $initializer.WaitForExit()
    if ($initializer.ExitCode -ne 0) {
        throw "Phase7 initialization failed; exit code: $($initializer.ExitCode)"
    }

    $backendProcess = Start-OwnedProcess `
        -FilePath $Python `
        -Arguments "-m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort" `
        -WorkingDirectory $Backend `
        -Environment @{
            REPROLAB_STORAGE_DIR = $Storage
            REPROLAB_DISABLE_LLM = "1"
            FRONTEND_ORIGINS = "http://127.0.0.1:$FrontendPort,http://localhost:$FrontendPort"
        }
    $children.Add($backendProcess)
    Wait-Ready $backendProcess "http://127.0.0.1:$BackendPort/api/health" "Backend"

    $frontendProcess = Start-OwnedProcess `
        -FilePath $Node `
        -Arguments "`"$Vite`" --host 127.0.0.1 --port $FrontendPort --strictPort" `
        -WorkingDirectory $Frontend `
        -Environment @{ VITE_API_BASE_URL = "http://127.0.0.1:$BackendPort" }
    $children.Add($frontendProcess)
    Wait-Ready $frontendProcess "http://127.0.0.1:$FrontendPort/" "Vite frontend"

    @{
        backend_pid = $backendProcess.Id
        frontend_pid = $frontendProcess.Id
        backend_url = "http://127.0.0.1:$BackendPort"
        frontend_url = "http://127.0.0.1:$FrontendPort"
        storage_dir = $Storage
    } | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding UTF8
    $pidFileCreated = $true

    Write-Host "[Phase7] Frontend: http://127.0.0.1:$FrontendPort"
    Write-Host "[Phase7] Backend: http://127.0.0.1:$BackendPort/api/docs"
    Write-Host "[Phase7] Summary: $(Join-Path $Storage 'phase7_demo_summary.json')"
    Write-Host "[Phase7] Press Ctrl+C to stop only the child processes started by this script."
    while (-not $backendProcess.HasExited -and -not $frontendProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
    if ($backendProcess.HasExited) { throw "Backend exited; exit code: $($backendProcess.ExitCode)." }
    if ($frontendProcess.HasExited) { throw "Frontend exited; exit code: $($frontendProcess.ExitCode)." }
} finally {
    for ($index = $children.Count - 1; $index -ge 0; $index--) {
        Stop-OwnedProcessTree $children[$index]
        $children[$index].Dispose()
    }
    if ($pidFileCreated -and (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
        Remove-Item -LiteralPath $pidFile -Force
    }
}
