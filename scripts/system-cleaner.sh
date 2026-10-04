#!/bin/bash
set -euo pipefail
scope=${1:-all}
case "$scope" in packages|journal|temporary|all) ;; *) printf 'Unknown cleanup scope.\n' >&2; exit 2;; esac
for tool in sudo; do command -v "$tool" >/dev/null || { printf 'Missing dependency: %s\n' "$tool" >&2; exit 1; }; done
if [[ $scope == packages || $scope == all ]]; then command -v paccache >/dev/null || { printf 'Install pacman-contrib for package cleanup.\n' >&2; exit 1; }; fi
printf 'System Cleanup — %s\n\n' "$scope"
if [[ $scope == packages || $scope == all ]]; then
 printf 'Package policy: retain 3 versions per package.\n'
 paccache -d -k 3
fi
if [[ $scope == journal || $scope == all ]]; then
 printf '\nJournal policy: keep up to 14 days / 200 MiB of archived logs.\n'
 journalctl --disk-usage --no-pager
fi
if [[ $scope == temporary || $scope == all ]]; then
 printf '\nTemporary files: use systemd age and exclusion rules.\n'
 sudo systemd-tmpfiles --clean --dry-run --prefix=/tmp --prefix=/var/tmp
fi
printf '\nApply this cleanup? [y/N] '
read -r answer
case "$answer" in y|Y|yes|YES) ;; *) printf 'Cancelled.\n'; exit 0;; esac
if [[ $scope == packages || $scope == all ]]; then sudo paccache -r -k 3; fi
if [[ $scope == journal || $scope == all ]]; then sudo journalctl --vacuum-time=14d --vacuum-size=200M; fi
if [[ $scope == temporary || $scope == all ]]; then sudo systemd-tmpfiles --clean --prefix=/tmp --prefix=/var/tmp; fi
printf '\nDone. Scan Again in CleanMacaci to refresh the report.\nPress Enter to close.\n'
read -r
