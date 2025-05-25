#!/bin/bash
set -e  # Exit immediately if any command fails

echo "Starting process to untrack large files and remove them from history..."

# --- Step 1: Untrack Files from Git and Git LFS ---

echo "Untracking all files in the repository (excluding .gitignore)..."
# Loop over all tracked files and remove them from the index unless they are .gitignore.
git ls-files | while IFS= read -r file; do
  if [ "$file" != ".gitignore" ]; then
    git rm -f --cached "$file" || true
  fi
done

# Remove .gitattributes to clear any previous Git LFS tracking rules (but keep .gitignore).
rm -f .gitattributes

# Commit the removal so that the repository history reflects that files are now untracked.
git commit -m "Untrack all files (excluding .gitignore) to reinitialize tracking" || echo "Nothing to commit"

# --- Step 2: Find and Process Large Files ---

# Define size threshold (50MB)
THRESHOLD="50M"

# Find large files in the specified directories.
# This example searches in YOUTUBE, TIKTOK, GEMINI_AI, FREDAPI, and AUTOMATIONS.
# It excludes unwanted directories and file types.
large_files=$(find ./YOUTUBE ./TIKTOK ./GEMINI_AI ./FREDAPI ./AUTOMATIONS -type f -size +50M \
  -not -path "*/.ipynb_checkpoints/*" \
  -not -path "*/Scripts/*" \
  -not -path "*/Lib/*" \
  -not -path "*/__pycache__/*" \
  -not -path "*/.venv/*" \
  -not -name "*.mp3" \
  -not -name "*.mp4" \
  -not -name "*.wav" \
  -not -name "*.ttf" \
  -not -name "*.otf" \
  -not -name "*.woff" \
  -not -name "*.woff2")
echo "Large files found: $large_files"  # Debug output

if [ -z "$large_files" ]; then
  echo "No files larger than $THRESHOLD found."
  exit 0
fi

for file in $large_files; do
  echo "Processing large file: $file"
  
  # Untrack the file from Git LFS (if it's being tracked by LFS)
  git lfs untrack "$file" || true

  # Remove the file from Git's index if it's tracked.
  if git ls-files --error-unmatch "$file" > /dev/null 2>&1; then
      git rm -f --cached "$file" || true
      git commit -m "Untrack large file $file" || echo "Nothing to commit for $file"
  else
      echo "File $file is not in the index; skipping removal."
  fi
  
  # Add the file to .gitignore if it's not already present.
  cleanfile=${file#./}
  if ! grep -Fxq "$cleanfile" .gitignore; then
      echo "$cleanfile" >> .gitignore
      git add .gitignore
      git commit -m "Add $cleanfile to .gitignore" || echo "Nothing to commit for .gitignore update"
  fi
done

# --- Step 3: Rewrite Repository History to Remove Large Blobs ---

# This command will remove all objects (blobs) larger than 50MB from your repository's history.
echo "Rewriting repository history to strip out blobs larger than 50MB..."
git filter-repo --strip-blobs-bigger-than 50M

# --- Step 4: Clean Up Local Repository ---
git reflog expire --expire=now --all && git gc --prune=now --aggressive

echo "Process complete. Large files have been untracked, added to .gitignore, and removed from repository history."
echo "Note: This operation rewrites history. Force push to update the remote repository if necessary."
