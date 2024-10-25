#!/bin/bash

# Initialize an empty associative array to store placeholders and their respective replacement values
declare -A replacements

# Array to store files or patterns to exclude
excludes=()

# Function to print usage
usage() {
  echo "Usage: $0 [--set placeholder=value] [--dir directory] [--exclude file_or_pattern]"
  echo "Example: $0 --set setup.repo=https://github.com/TSD/lol.git --set another.placeholder=some_other_value --dir ./ --exclude Jenkinsfile --exclude *.md"
  exit 1
}

# Default directory is the current directory
ROOT_DIR="./"

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --set)
      # Extract placeholder and value from --set argument
      if [[ "$2" =~ ^([^=]+)=(.*)$ ]]; then
        placeholder="${BASH_REMATCH[1]}"
        value="${BASH_REMATCH[2]}"
        replacements["$placeholder"]="$value"
      else
        echo "Error: Invalid format for --set. Use --set placeholder=value."
        usage
      fi
      shift 2
      ;;
    --dir)
      # Set the root directory for the search
      ROOT_DIR="$2"
      shift 2
      ;;
    --exclude)
      # Add files or patterns to exclude
      excludes+=("$2")
      shift 2
      ;;
    *)
      echo "Error: Unknown option $1"
      usage
      ;;
  esac
done

# Check if at least one --set argument is provided
if [ ${#replacements[@]} -eq 0 ]; then
  echo "Error: No placeholders provided. Use --set placeholder=value."
  usage
fi

# Check if the directory exists
if [ ! -d "$ROOT_DIR" ]; then
  echo "Error: Directory $ROOT_DIR does not exist."
  exit 1
fi

# Prepare the find command with exclusion
exclude_cmd=""
for exclude in "${excludes[@]}"; do
  exclude_cmd+="! -name '$exclude' "
done

# Find all files recursively in the specified directory, excluding specified patterns
eval "find \"$ROOT_DIR\" -type f $exclude_cmd" | while read -r file; do
  echo "Processing file: $file"

  # Loop through each placeholder in the associative array
  for placeholder in "${!replacements[@]}"; do
      value="${replacements[$placeholder]}"

      # Use sed to replace the placeholder with the corresponding value
      sed -i "s|<<$placeholder>>|$value|g" "$file"

      # Confirm replacement (optional logging)
      if grep -q "$value" "$file"; then
        echo "  Successfully replaced $placeholder with $value in $file"
      else
        echo "  No occurrences of $placeholder found in $file"
      fi
  done
done

echo "All files processed."

