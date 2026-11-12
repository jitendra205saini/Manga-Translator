# Installer isse chalata hai: apna Python (embeddable), packages, models. Admin ki zarurat nahi.
param([string]$AppDir = (Split-Path -Parent $PSScriptRoot))

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Host.UI.RawUI.WindowTitle = "Manga Translator setup"

$PyVer = "3.13.9"
$PyDir = Join-Path $AppDir "python"
$Py = Join-Path $PyDir "python.exe"
$Server = Join-Path $AppDir "server"
$Log = Join-Path $AppDir "install.log"
Start-Transcript -Path $Log -Force | Out-Null
# laptop mein bahar kuch na bache: pip cache band, HuggingFace cache app folder ke andar
$env:PIP_NO_CACHE_DIR = "1"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:HF_HOME = Join-Path $AppDir ".hf"

function Step($n, $text) { Write-Host ""; Write-Host "[$n/4] $text" -ForegroundColor Cyan }

try {
    Step 1 "Python $PyVer download ho raha hai"
    if (-not (Test-Path $Py)) {
        $zip = Join-Path $env:TEMP "mt-python-embed.zip"
        Invoke-WebRequest "https://www.python.org/ftp/python/$PyVer/python-$PyVer-embed-amd64.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive $zip -DestinationPath $PyDir -Force
        Remove-Item $zip
        # embeddable Python mein site-packages chalu karo
        $pth = Get-ChildItem $PyDir -Filter "python*._pth" | Select-Object -First 1
        (Get-Content $pth.FullName) -replace "^#\s*import site", "import site" | Set-Content $pth.FullName -Encoding ascii
        $getpip = Join-Path $env:TEMP "mt-get-pip.py"
        Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile $getpip -UseBasicParsing
        & $Py $getpip --no-warn-script-location
        if ($LASTEXITCODE) { throw "pip install fail" }
        Remove-Item $getpip
    } else { Write-Host "  pehle se hai" }

    Step 2 "Packages install ho rahe hain (~200 MB)"
    & $Py -m pip install --no-warn-script-location -r (Join-Path $Server "requirements.txt")
    if ($LASTEXITCODE) { throw "packages install fail" }

    Step 3 "Fonts aur AI models download ho rahe hain (~400 MB)"
    Push-Location $Server
    & $Py download_assets.py --no-nllb
    $code = $LASTEXITCODE
    Pop-Location
    if ($code) { throw "models download fail" }

    Step 4 "Check"
    & $Py -c "import onnxruntime, cv2, PIL, fastapi, uvicorn; print('  sab theek')"
    if ($LASTEXITCODE) { throw "check fail" }
    Write-Host ""
    Write-Host "Setup complete." -ForegroundColor Green
    Stop-Transcript | Out-Null
    exit 0
}
catch {
    Write-Host ""
    Write-Host "[ERROR] $_" -ForegroundColor Red
    Write-Host "Internet check karke installer dobara chalao. Log: $Log"
    Stop-Transcript | Out-Null
    Read-Host "Enter dabao"
    exit 1
}
