#!/usr/bin/env bash
#
# Helper multiplataforma para evitar suspension/hibernacion durante corridas largas.
#
# Uso (desde un runner):
#   source "$REPO_ROOT/shared/utils/keep_awake.sh"
#   keep_awake_start
#   trap keep_awake_stop EXIT INT TERM
#
# Desactivable con KEEP_AWAKE=0. No cambia la configuracion global de energia:
# usa inhibidores con ciclo de vida propio que se liberan al terminar el runner.

_KEEP_AWAKE_PID=""
_KEEP_AWAKE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

keep_awake_start() {
    if [ "${KEEP_AWAKE:-1}" != "1" ]; then
        echo "[KEEP-AWAKE] desactivado (KEEP_AWAKE=0)"
        return 0
    fi
    case "$(uname -s)" in
        Linux*)
            if command -v systemd-inhibit >/dev/null 2>&1; then
                systemd-inhibit --what=sleep:idle --who="reflexio" \
                    --why="batch de pruebas" --mode=block sleep infinity &
                _KEEP_AWAKE_PID=$!
                echo "[KEEP-AWAKE] systemd-inhibit activo (PID $_KEEP_AWAKE_PID)"
            else
                echo "[KEEP-AWAKE] systemd-inhibit no disponible; omitido"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*)
            local ps1="$_KEEP_AWAKE_DIR/keep_awake.ps1"
            if command -v cygpath >/dev/null 2>&1; then
                ps1="$(cygpath -w "$ps1")"
            fi
            powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ps1" &
            _KEEP_AWAKE_PID=$!
            echo "[KEEP-AWAKE] SetThreadExecutionState activo (PID $_KEEP_AWAKE_PID)"
            ;;
        Darwin*)
            caffeinate -dimsu &
            _KEEP_AWAKE_PID=$!
            echo "[KEEP-AWAKE] caffeinate activo (PID $_KEEP_AWAKE_PID)"
            ;;
        *)
            echo "[KEEP-AWAKE] SO no reconocido; omitido"
            ;;
    esac
}

keep_awake_stop() {
    if [ -n "$_KEEP_AWAKE_PID" ]; then
        kill "$_KEEP_AWAKE_PID" >/dev/null 2>&1 || true
        wait "$_KEEP_AWAKE_PID" 2>/dev/null || true
        echo "[KEEP-AWAKE] liberado"
        _KEEP_AWAKE_PID=""
    fi
}
