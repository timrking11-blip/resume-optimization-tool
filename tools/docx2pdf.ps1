# Convert a .docx to PDF with Microsoft Word (read-only open, no save back).
# usage: powershell -NoProfile -ExecutionPolicy Bypass -File tools\docx2pdf.ps1 <in.docx> <out.pdf>
# Exit 0 on success. Never closes documents Tim has open: Word is only quit when this
# script's instance has no other documents.
param([Parameter(Mandatory=$true)][string]$In, [Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference = 'Stop'
$in = (Resolve-Path -LiteralPath $In).Path
$out = [System.IO.Path]::GetFullPath($Out)
$word = $null; $doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    # Open(FileName, ConfirmConversions, ReadOnly, AddToRecentFiles)
    $doc = $word.Documents.Open($in, $false, $true, $false)
    # ExportAsFixedFormat(OutputFileName, ExportFormat=17 PDF, OpenAfterExport, OptimizeFor=0 print,
    #                     Range=0 all, From, To, Item=0 content, IncludeDocProps, KeepIRM, CreateBookmarks=0 none)
    $doc.ExportAsFixedFormat($out, 17, $false, 0, 0, 1, 1, 0, $true, $true, 0)
    Write-Output "ok $out"
    exit 0
} catch {
    Write-Output ("error " + $_.Exception.Message)
    exit 1
} finally {
    if ($doc -ne $null) { $doc.Saved = $true; $doc.Close() | Out-Null; [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) }
    if ($word -ne $null) {
        if ($word.Documents.Count -eq 0) { $word.Quit() }
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
    }
}
