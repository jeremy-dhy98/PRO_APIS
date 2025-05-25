#!/bin/bash
set -e

# Usage: clone_and_assemble.sh <repo-url> [assemble]
#   repo-url : URL of the Git repository to clone.
#   assemble : Optional flag (e.g., "assemble") that triggers the extraction and reassembly of split files.
if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <repo-url> [assemble]"
  exit 1
fi

REPO_URL="$1"
DO_ASSEMBLE="${2:-no}"

echo "Cloning repository from $REPO_URL..."
git clone "$REPO_URL"

# Extract repository name from the URL (assumes URL ends with .git)
REPO_NAME=$(basename "$REPO_URL" .git)
cd "$REPO_NAME"

echo "Initializing Git LFS..."
git lfs install

if [ "$DO_ASSEMBLE" = "assemble" ]; then
  echo "Checking for split and zipped large files..."

  # Find all files that match the split archive naming convention.
  SPLIT_ZIPPED_FILES=$(find . -type f -name "*_part_*.csv.zip")
  
  if [ -n "$SPLIT_ZIPPED_FILES" ]; then
    echo "Found split zipped files. Starting extraction..."
    
    # Extract each archive in place
    while IFS= read -r archive; do
      echo "Extracting $archive..."
      unzip -o "$archive" -d "$(dirname "$archive")"
    done <<< "$SPLIT_ZIPPED_FILES"
    
    echo "Reassembling extracted parts..."
    # Find unique base filenames from the extracted parts.
    # Assumes parts are named: <filename>_part_<number>.csv
    BASE_FILES=$(find . -type f -name "*_part_*.csv" | sed -E 's/(.*)_part_[0-9]+\.csv/\1/' | sort | uniq)
    
    for base in $BASE_FILES; do
      output="${base}.assembled.csv"
      echo "Assembling parts for $base into $output..."
      
      # Find all parts for the base file and sort them by their part number.
      # This assumes part filenames do not contain spaces.
      parts=$(find . -type f -name "$(basename "$base")_part_*.csv" | sort -t '_' -k3,3n)
      cat $parts > "$output"
      echo "Created assembled file: $output"
    done
  else
    echo "No split zipped large files found."
  fi
else
  echo "Assembly not requested. Cloning complete."
fi

echo "Process complete."
