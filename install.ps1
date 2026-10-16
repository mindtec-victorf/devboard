# devboard installer for Windows (PowerShell 5.1+ or 7):
#   irm https://raw.githubusercontent.com/mindtec-victorf/devboard/main/install.ps1 | iex
# Puts `devboard` on your user PATH, links the skill for the agents found here (Codex, Copilot) and writes
# the instruction blocks for Codex and Gemini. Claude Code users: install the plugin instead
# (/plugin marketplace add mindtec-victorf/devboard, then /plugin install devboard@devboard).
$ErrorActionPreference = "Stop"
function Pick($value, $default) { if ($value) { $value } else { $default } }
$Repo = Pick $env:DEVBOARD_REPO "https://github.com/mindtec-victorf/devboard"
$App  = Pick $env:DEVBOARD_APP  (Join-Path $env:LOCALAPPDATA "devboard\app")
$Bin  = Pick $env:DEVBOARD_BIN  (Join-Path $env:LOCALAPPDATA "devboard\bin")

$check = "import sys; sys.exit(sys.version_info < (3, 10))"
$hasPython = $false
if (Get-Command py -ErrorAction SilentlyContinue) { py -3 -c $check 2>$null; $hasPython = ($LASTEXITCODE -eq 0) }
if (-not $hasPython -and (Get-Command python -ErrorAction SilentlyContinue)) { python -c $check 2>$null; $hasPython = ($LASTEXITCODE -eq 0) }
if (-not $hasPython) { throw "devboard needs Python 3.10+ (python.org or the Microsoft Store)" }

New-Item -ItemType Directory -Force -Path (Split-Path $App) | Out-Null
if ($env:DEVBOARD_SRC) {                      # a local checkout (development, CI)
  if (Test-Path $App) { Remove-Item -Recurse -Force $App }
  New-Item -ItemType Junction -Path $App -Target $env:DEVBOARD_SRC | Out-Null
} elseif (Test-Path (Join-Path $App ".git")) {
  git -C $App pull --ff-only -q
} elseif (Get-Command git -ErrorAction SilentlyContinue) {
  git clone -q --depth 1 $Repo $App
} else {                                      # no git: download the main branch as a zip
  $zip = Join-Path $env:TEMP "devboard-main.zip"
  Invoke-WebRequest "$Repo/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing
  $tmp = Join-Path $env:TEMP "devboard-main"
  if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
  Expand-Archive $zip -DestinationPath $tmp
  if (Test-Path $App) { Remove-Item -Recurse -Force $App }
  Move-Item (Join-Path $tmp "devboard-main") $App
}

New-Item -ItemType Directory -Force -Path $Bin | Out-Null
$shim = Join-Path $Bin "devboard.cmd"
Set-Content -Path $shim -Encoding oem -Value "@call `"$App\bin\devboard.cmd`" %*"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not (($userPath -split ";") -contains $Bin)) {
  [Environment]::SetEnvironmentVariable("Path", (($userPath, $Bin) | Where-Object { $_ }) -join ";", "User")
  Write-Host "devboard: added $Bin to your user PATH (open a new terminal)"
}
$env:Path = "$Bin;$env:Path"
Write-Host "devboard: CLI at $shim"

foreach ($agentHome in @((Join-Path $HOME ".codex"), (Join-Path $HOME ".copilot"))) {
  if (-not (Test-Path $agentHome)) { continue }
  $skills = Join-Path $agentHome "skills"
  New-Item -ItemType Directory -Force -Path $skills | Out-Null
  $link = Join-Path $skills "devboard"
  if (Test-Path $link) { Remove-Item -Recurse -Force $link }
  New-Item -ItemType Junction -Path $link -Target (Join-Path $App "skills\devboard") | Out-Null
  Write-Host "devboard: skill linked into $link"
}
if (Test-Path (Join-Path $HOME ".codex"))  { & $shim setup-agent codex }
if (Test-Path (Join-Path $HOME ".gemini")) { & $shim setup-agent gemini }
Write-Host "devboard: done. Per project: 'devboard setup-agent cursor|copilot|agents', then 'devboard init <id> --title ... --repo .'"
