#!/usr/bin/env bash
# Shared helpers for Spec Kit bash scripts.

get_repo_root() {
    git rev-parse --show-toplevel 2>/dev/null || pwd
}

get_current_branch() {
    git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"
}
