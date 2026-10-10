<#
  prune_internal.ps1  --  shrink the Flandre pet runtime (_internal)

  WHAT IT DOES
    Moves Qt / Python components that the app NEVER loads at runtime out of
    _internal into .tmp\_pruned_backup. Fully reversible, nothing is deleted.

  WHY THESE ARE SAFE TO REMOVE
    src/ only imports PySide6.QtCore, QtGui, QtWidgets and PIL (PNG only).
    Verified by: DLL dependency-closure check (LoadLibrary on every kept DLL,
    plus a negative control), two offscreen runs of the packaged exe, and one
    real visible launch. Runtime loads only:
      Qt6Core / Qt6Gui / Qt6Widgets / QtCore.pyd / QtGui.pyd / QtWidgets.pyd
      Shiboken.pyd / shiboken6.abi3.dll  (+ qwindows, qmodernwindowsstyle, qico)

  RESULT (measured on this project)
    _internal 125.06 MB -> 57.16 MB     (~68 MB saved, 54%)

  USAGE
    powershell -ExecutionPolicy Bypass -File prune_internal.ps1
    powershell -ExecutionPolicy Bypass -File prune_internal.ps1 -ListOnly
    powershell -ExecutionPolicy Bypass -File prune_internal.ps1 -Restore

  IMPORTANT
    A PyInstaller rebuild puts everything back. Re-run this script after
    every rebuild, then start the exe once to confirm it still works.
#>
param(
    [switch]$Restore,
    [switch]$ListOnly
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path -LiteralPath (Join-Path $scriptDir "_internal")) {
    $root = $scriptDir
} else {
    $root = Split-Path -Parent $scriptDir
}
$internal = Join-Path $root "_internal"
$backup = Join-Path $root ".tmp\_pruned_backup"

if (-not (Test-Path -LiteralPath $internal)) {
    throw "Cannot find _internal under: $root"
}

# ---- paths relative to _internal ----
$files = @(
    # unused Qt modules (never imported by src/)
    "PySide6\Qt6Quick.dll",
    "PySide6\Qt6Qml.dll",
    "PySide6\Qt6QmlModels.dll",
    "PySide6\Qt6QmlMeta.dll",
    "PySide6\Qt6QmlWorkerScript.dll",
    "PySide6\Qt6Pdf.dll",
    "PySide6\Qt6Network.dll",
    "PySide6\QtNetwork.pyd",
    "PySide6\Qt6OpenGL.dll",
    "PySide6\Qt6VirtualKeyboard.dll",
    # Mesa software OpenGL: this app uses no OpenGL at all
    "PySide6\opengl32sw.dll",
    # alternative platform plugin; the default qwindows.dll is kept
    "PySide6\plugins\platforms\qdirect2d.dll",
    # image formats never used (app only opens PNG / ICO / JPG)
    "PySide6\plugins\imageformats\qwebp.dll",
    "PySide6\plugins\imageformats\qtiff.dll",
    "PySide6\plugins\imageformats\qicns.dll",
    "PySide6\plugins\imageformats\qtga.dll",
    "PySide6\plugins\imageformats\qwbmp.dll",
    "PySide6\plugins\imageformats\qpdf.dll",
    # OpenSSL runtime + ssl/hash modules: no network, no hashlib anywhere
    "libcrypto-3-x64.dll",
    "libssl-3-x64.dll",
    "_ssl.pyd",
    "_hashlib.pyd",
    # Pillow AVIF codec: only PNG is ever opened
    "PIL\_avif.cp312-win_amd64.pyd"
)

$dirs = @(
    # Qt UI translations; the app never installs a QTranslator
    "PySide6\translations",
    "PySide6\plugins\tls",
    "PySide6\plugins\networkinformation",
    "PySide6\plugins\platforminputcontexts",
    "PySide6\plugins\generic"
)

function Get-DirMB($p) {
    if (-not (Test-Path -LiteralPath $p)) { return 0 }
    $s = (Get-ChildItem -LiteralPath $p -Recurse -File -Force -ErrorAction SilentlyContinue |
          Measure-Object Length -Sum).Sum
    return [math]::Round($s / 1MB, 2)
}

function Move-One($rel) {
    $src = Join-Path $internal $rel
    if (-not (Test-Path -LiteralPath $src)) { return $false }
    $dest = Join-Path $backup $rel
    $parent = Split-Path -Parent $dest
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    # 上一轮 Prune 留下的同名备份目录：先清掉，否则 Move-Item 会报
    # 「Cannot create a file when that file already exists」并整体中断
    if (Test-Path -LiteralPath $dest -PathType Container) {
        Remove-Item -LiteralPath $dest -Recurse -Force
    }
    Move-Item -LiteralPath $src -Destination $dest -Force
    return $true
}

# ================= RESTORE =================
if ($Restore) {
    if (-not (Test-Path -LiteralPath $backup)) {
        Write-Output "Nothing to restore: $backup does not exist."
        exit 0
    }
    $n = 0
    Get-ChildItem -LiteralPath $backup -Recurse -File -Force | ForEach-Object {
        $rel = $_.FullName.Substring($backup.Length).TrimStart('\')
        $dest = Join-Path $internal $rel
        $parent = Split-Path -Parent $dest
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        Move-Item -LiteralPath $_.FullName -Destination $dest -Force
        $n++
    }
    # drop the now-empty backup tree
    Get-ChildItem -LiteralPath $backup -Recurse -Directory -Force |
        Sort-Object { $_.FullName.Length } -Descending |
        ForEach-Object { if (-not (Get-ChildItem -LiteralPath $_.FullName -Force)) { Remove-Item -LiteralPath $_.FullName -Force } }
    if (-not (Get-ChildItem -LiteralPath $backup -Force)) { Remove-Item -LiteralPath $backup -Force }

    Write-Output ("Restored $n files.")
    Write-Output ("_internal is now " + (Get-DirMB $internal) + " MB")
    exit 0
}

# ================= LIST ONLY =================
if ($ListOnly) {
    Write-Output "Would move out of _internal:"
    $total = 0
    foreach ($rel in $files) {
        $p = Join-Path $internal $rel
        if (Test-Path -LiteralPath $p) {
            $mb = [math]::Round((Get-Item -LiteralPath $p).Length / 1MB, 2)
            $total += $mb
            Write-Output ("  {0,8} MB  {1}" -f $mb, $rel)
        }
    }
    foreach ($rel in $dirs) {
        $p = Join-Path $internal $rel
        if (Test-Path -LiteralPath $p) {
            $mb = Get-DirMB $p
            $total += $mb
            Write-Output ("  {0,8} MB  {1}\" -f $mb, $rel)
        }
    }
    Write-Output ("  --------")
    Write-Output ("  {0,8} MB  total" -f [math]::Round($total, 2))
    Write-Output ("_internal currently " + (Get-DirMB $internal) + " MB")
    exit 0
}

# ================= PRUNE =================
$before = Get-DirMB $internal
Write-Output ("_internal before : " + $before + " MB")

$moved = 0
foreach ($rel in $files) { if (Move-One $rel) { $moved++; Write-Output ("  moved  " + $rel) } }
foreach ($rel in $dirs)  { if (Move-One $rel) { $moved++; Write-Output ("  moved  " + $rel + "\") } }

$after = Get-DirMB $internal
Write-Output ("_internal after  : " + $after + " MB")
Write-Output ("files moved      : " + $moved)
if ($moved -eq 0) {
    Write-Output "Already pruned (or the rebuild has not happened yet)."
} else {
    Write-Output ("saved            : " + [math]::Round($before - $after, 2) + " MB")
    Write-Output ""
    Write-Output "Now START the exe once to confirm it still runs."
    Write-Output ("Undo with: prune_internal.ps1 -Restore")
}
