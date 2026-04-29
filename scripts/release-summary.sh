#!/usr/bin/env bash
set -euo pipefail

repo="${1:-ghcr.io/owner/repo}"
version="${2:-dev}"
sha="${3:-unknown}"

cat <<EOF
Release summary
  image: ${repo}
  version: ${version}
  sha: ${sha}

Suggested pull examples
  docker pull ${repo}:${version}
  docker pull ${repo}:sha-${sha}
EOF
