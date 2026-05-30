# Mantiene Windows despierto mientras este proceso viva.
# Lo lanzan en background los runners del repo (keep_awake.sh); al matarlo,
# el estado de ejecucion se libera automaticamente. No cambia el plan de energia.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class KeepAwake {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
'@
# ES_CONTINUOUS (0x80000000) | ES_SYSTEM_REQUIRED (0x00000001) = 2147483649.
# Se pasa como decimal con cast a uint32: el literal hex 0x80000001 lo interpreta
# PowerShell como Int32 negativo y falla la conversion a UInt32.
[KeepAwake]::SetThreadExecutionState([uint32]2147483649) | Out-Null
while ($true) { Start-Sleep -Seconds 60 }
