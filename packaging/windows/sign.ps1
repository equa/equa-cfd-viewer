# Signing step of the Windows bundle, run on cfd-viewer.exe before the zip
# (openspec local-desktop-viewer, design D5). The method is chosen when EQUA's
# certificate is available; until CFD_VIEWER_SIGNING names one, this only says
# the zip is unsigned.
param([Parameter(Mandatory = $true)] [string] $Exe)

if (-not $env:CFD_VIEWER_SIGNING) {
    Write-Host "::notice::No signing configured: $Exe is unsigned, for internal testing only."
    if ($env:GITHUB_STEP_SUMMARY) {
        "**Unsigned** build: for internal testing only." | Add-Content $env:GITHUB_STEP_SUMMARY
    }
    exit 0
}
Write-Error "CFD_VIEWER_SIGNING is '$env:CFD_VIEWER_SIGNING', but no signing method is implemented yet (design D5)."
exit 1
