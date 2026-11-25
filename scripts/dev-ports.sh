#!/usr/bin/env bash

check_dev_port() {
    local component=$1 port=$2 variable=$3 status=0
    if [[ ! $port =~ ^[1-9][0-9]{0,4}$ ]] || (( port > 65535 )); then
        printf '%s must be a decimal port from 1 to 65535. Received %q.\n' "$variable" "$port" >&2
        return 1
    fi
    python3 - "$port" <<'PY' || status=$?
import errno
import socket
import sys

port = int(sys.argv[1])
for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
    try:
        with socket.socket(family) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((address, port))
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            sys.exit(10)
        if error.errno not in (errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT, errno.EADDRNOTAVAIL):
            print(error, file=sys.stderr)
            sys.exit(11)
PY
    if (( status == 0 )); then return 0; fi
    if (( status != 10 )); then
        printf 'Could not check %s port %s.\n' "$component" "$port" >&2
        return 1
    fi

    printf '%s port %s is already in use.\n' "$component" "$port" >&2
    if command -v ss >/dev/null; then
        ss -H -ltnp "sport = :$port" >&2 || true
    fi
    if command -v curl >/dev/null; then
        local host ready landing health
        for host in 127.0.0.1 '[::1]'; do
            ready=$(curl -gfsS --noproxy '*' --max-time 2 "http://$host:$port/api/v1/ready/" 2>/dev/null) || ready=
            landing=
            health=
            if [[ $component == Angular ]]; then
                landing=$(curl -gfsS --noproxy '*' --max-time 2 "http://$host:$port/" 2>/dev/null) || landing=
            else
                health=$(curl -gfsS --noproxy '*' --max-time 2 "http://$host:$port/api/v1/health/" 2>/dev/null) || health=
            fi
            if [[ $ready == *'"status":"ready"'* && $ready == *'"database":"connected"'* ]]; then
                if [[ $health == *'"service":"school-management-backend"'* || $landing == *'School &amp; College Management System'* ]]; then
                    printf 'Existing school service at http://%s:%s is ready and reports PostgreSQL connected.\n' "$host" "$port" >&2
                    break
                fi
            elif [[ $landing == *'School &amp; College Management System'* ]]; then
                printf 'Existing school frontend at http://%s:%s responded. API readiness could not be confirmed.\n' "$host" "$port" >&2
                break
            fi
        done
    fi
    printf 'Reuse a verified instance, or set %s to an available port before starting.\n' "$variable" >&2
    return 1
}
