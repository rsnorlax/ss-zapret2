#!/usr/bin/env sh

set -eu

for process in sslocal ssserver nfqws2; do
  if ! pidof "$process" >/dev/null 2>&1; then
    echo "[healthcheck] ERROR: $process is not running" >&2
    exit 1
  fi
done

ZAPRET_CONFIG=${ZAPRET_CONFIG:-/opt/zapret2/config}
if [ ! -r "$ZAPRET_CONFIG" ]; then
  echo "[healthcheck] ERROR: cannot read $ZAPRET_CONFIG" >&2
  exit 1
fi

# shellcheck disable=SC1090
. "$ZAPRET_CONFIG"

if [ "${INIT_APPLY_FW:-0}" = "1" ]; then
  if [ "${FWTYPE:-}" != "nftables" ]; then
    echo "[healthcheck] ERROR: INIT_APPLY_FW=1 requires FWTYPE=nftables" >&2
    exit 1
  fi

  nft_table=${ZAPRET_NFT_TABLE:-zapret2}
  queue_num=${QNUM:-300}
  rules=$(nft list table inet "$nft_table" 2>/dev/null) || {
    echo "[healthcheck] ERROR: nft table inet $nft_table is missing" >&2
    exit 1
  }

  if ! printf '%s\n' "$rules" | awk -v queue_num="$queue_num" '
    /queue/ && $0 ~ ("(^|[^0-9])" queue_num "([^0-9]|$)") { found = 1 }
    END { exit found ? 0 : 1 }
  '; then
    echo "[healthcheck] ERROR: nft queue $queue_num rule is missing from inet $nft_table" >&2
    exit 1
  fi
fi
