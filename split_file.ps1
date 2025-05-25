param(
    [string]$FilePath,
    [int64]$ChunkSize = 50MB
)

if (-not (Test-Path $FilePath)) {
    Write-Host "File not found: $FilePath"
    exit 1
}

# Create a buffer with the defined chunk size
$buffer = New-Object Byte[] $ChunkSize
$reader = [System.IO.File]::OpenRead($FilePath)
$index = 0

while ($true) {
    $bytesRead = $reader.Read($buffer, 0, $ChunkSize)
    if ($bytesRead -eq 0) { break }
    # Name each chunk by appending _part_<index> before the extension
    $chunkPath = "$FilePath`_part_$index.csv"
    $writer = [System.IO.File]::OpenWrite($chunkPath)
    $writer.Write($buffer, 0, $bytesRead)
    $writer.Close()
    $index++
}

$reader.Close()
Write-Host "Finished splitting $FilePath into $index parts."
