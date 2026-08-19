# Build a release of Blackboard and package it for the other computer.
#
# Run from the repository root:
#     powershell -ExecutionPolicy Bypass -File tools\release.ps1
#
# What it does, in order:
#   1. refuses to run unless the repository is clean and on the bvref branch
#   2. reads the version from beeref/constants.py
#   3. checks style and tests against the known baseline
#   4. builds the executable with PyInstaller
#   5. packages Install.cmd + the executable into dist\Blackboard-<version>.zip
#   6. installs that same package here, so this PC runs what was shipped
#   7. tags the commit as v<version>
#
# The zip is the only file that needs to reach the other computer.

$ErrorActionPreference = 'Stop'

# --- expected test baseline -------------------------------------------------
# Nine tests fail on unmodified upstream code too (see CLAUDE.md). Anything
# beyond that is a real regression and stops the release.
$ExpectedPassed    = 1393
$MaxAllowedFailed  = 9

function Fail($message) {
    Write-Host "RELEASE STOPPED: $message" -ForegroundColor Red
    exit 1
}

function Step($message) {
    Write-Host ""
    Write-Host "== $message" -ForegroundColor Cyan
}

# --- 1. repository state ----------------------------------------------------

Step "Checking the repository"

if (-not (Test-Path 'beeref\constants.py')) {
    Fail "run this from the repository root, not from inside tools\"
}

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'bvref') {
    Fail "on branch '$branch'; releases are cut from bvref"
}

$dirty = git status --porcelain
if ($dirty) {
    Write-Host $dirty
    Fail "there are uncommitted changes. Commit them first, so the version number identifies exactly this code."
}

$commit = (git rev-parse --short HEAD).Trim()
Write-Host "   branch bvref at $commit, working tree clean"

# --- 2. version -------------------------------------------------------------

$constants = Get-Content 'beeref\constants.py' -Raw
$match = [regex]::Match($constants, "(?m)^VERSION\s*=\s*'([^']+)'")
if (-not $match.Success) { Fail "could not find VERSION in beeref\constants.py" }
$version = $match.Groups[1].Value
Write-Host "   version $version"

$tag = "v$version"
if ((git tag --list $tag)) {
    Fail "tag $tag already exists. Bump VERSION in beeref\constants.py and commit before releasing again."
}

$python = '.\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { Fail "no virtualenv at .venv (see CLAUDE.md for how to build it)" }

# --- 3. checks --------------------------------------------------------------

Step "Checking style"
& $python -m flake8 beeref tests
if ($LASTEXITCODE -ne 0) { Fail "flake8 reported problems" }
Write-Host "   clean"

Step "Running tests (about 90 seconds)"
# Do not redirect stderr here. In Windows PowerShell 5.1, capturing a native
# command's stderr wraps every line in an error record, which $ErrorActionPreference
# = 'Stop' then treats as a fatal error -- and the Qt tests do write to stderr.
# pytest's summary line goes to stdout, which is all this needs.
$testOutput = & $python -m pytest tests -q
$summary = $testOutput | Select-String -Pattern '(\d+) failed, (\d+) passed' | Select-Object -Last 1
if ($summary) {
    $failed = [int]$summary.Matches[0].Groups[1].Value
    $passed = [int]$summary.Matches[0].Groups[2].Value
} else {
    $summary = $testOutput | Select-String -Pattern '(\d+) passed' | Select-Object -Last 1
    if (-not $summary) {
        $testOutput | Select-Object -Last 15 | ForEach-Object { Write-Host $_ }
        Fail "could not read the test results"
    }
    $failed = 0
    $passed = [int]$summary.Matches[0].Groups[1].Value
}

Write-Host "   $passed passed, $failed failed"
if ($failed -gt $MaxAllowedFailed) {
    $testOutput | Select-String -Pattern '^FAILED' | ForEach-Object { Write-Host $_ }
    Fail "$failed failing tests, more than the $MaxAllowedFailed known failures"
}
if ($passed -lt $ExpectedPassed) {
    Fail "only $passed tests passed, fewer than the expected $ExpectedPassed. Did some fail to run?"
}

# --- 4. build ---------------------------------------------------------------

Step "Building the executable"
& $python -m PyInstaller --noconfirm Blackboard.spec
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed" }

$builtExe = "dist\Blackboard-$version.exe"
if (-not (Test-Path $builtExe)) { Fail "expected $builtExe, but it is not there" }
$sizeMb = [math]::Round((Get-Item $builtExe).Length / 1MB, 1)
Write-Host "   $builtExe ($sizeMb MB)"

# --- 5. package -------------------------------------------------------------

Step "Packaging"

$staging = "dist\package-$version"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path "$staging\app" -Force | Out-Null

# Inside the package the executable has no version in its name: the installer
# copies it to a fixed path, and a fixed path cannot carry a version.
Copy-Item $builtExe "$staging\app\Blackboard.exe"
Copy-Item 'tools\Install.cmd' "$staging\Install.cmd"
# ASCII, not utf8: PowerShell 5.1 writes a byte-order mark with utf8, and
# cmd would read those bytes as part of the version string.
Set-Content -Path "$staging\app\version.txt" -Value $version -Encoding ascii -NoNewline

$zip = "dist\Blackboard-$version.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "$staging\*" -DestinationPath $zip
$zipMb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "   $zip ($zipMb MB)"

# --- 6. install here --------------------------------------------------------

Step "Installing this build on this PC"
Write-Host "   (running the same Install.cmd the other computer will run)"

$running = Get-Process -Name 'Blackboard' -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "   Blackboard is running, so the local install was skipped." -ForegroundColor Yellow
    Write-Host "   Close it and run $staging\Install.cmd yourself."
} else {
    # Call it by absolute path. Set-Location and Push-Location move
    # PowerShell's own location but not the working directory that a child
    # process inherits, so a bare 'Install.cmd' would not be found.
    # /nopause skips its "press any key" prompt.
    $installPath = (Resolve-Path "$staging\Install.cmd").Path
    $installOutput = & cmd.exe /c call "$installPath" /nopause
    $installExit = $LASTEXITCODE
    $installOutput | ForEach-Object { Write-Host "   $_" }
    if ($installExit -ne 0) { Fail "the local install failed" }
}

# --- 7. tag -----------------------------------------------------------------

Step "Tagging"
git tag -a $tag -m "Blackboard $version"
if ($LASTEXITCODE -ne 0) { Fail "could not create tag $tag" }
Write-Host "   created $tag"

# --- done -------------------------------------------------------------------

Write-Host ""
Write-Host "Release $version is ready." -ForegroundColor Green
Write-Host ""
Write-Host "Send to the other computer:"
Write-Host "  $zip"
Write-Host ""
Write-Host "To publish it (deliberately kept separate, so building never"
Write-Host "publishes by accident):"
Write-Host "  git push origin bvref --tags"
Write-Host "  gh release create $tag `"$zip`" --title `"Blackboard $version`" --notes `"...`""
Write-Host ""
Write-Host "On the other PC: unpack the zip and run Install.cmd."
Write-Host ""
