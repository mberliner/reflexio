#!/bin/bash
# Demo GEPA Standalone — ejecutar desde gepa_standalone/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GEPA_DIR="$(dirname "$SCRIPT_DIR")"
ROOT_DIR="$(dirname "$GEPA_DIR")"

BOLD="\033[1m"
CYAN="\033[1;36m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RESET="\033[0m"

seccion() {
    echo ""
    echo -e "${CYAN}================================================================${RESET}"
    echo -e "${BOLD}  $1${RESET}"
    echo -e "${CYAN}================================================================${RESET}"
    echo ""
}

pausa() {
    echo ""
    echo -e "${YELLOW}--- Presiona cualquier tecla para continuar ---${RESET}"
    read -n 1 -s -r
    clear
}

cd "$GEPA_DIR"

clear
echo -e "${BOLD}"
echo "  ================================================================"
echo "  DEMO: GEPA Standalone — Optimizacion Reflexiva de Prompts"
echo "              o      TDD para prompts!"
echo "              con Refactor Automático"
echo "  ================================================================"
echo -e "${RESET}"
echo ""  
echo "  Flujo de la demo:"
echo "    Inputs (CSV + prompt + config + .env)"
echo "      -> optimizer (~1 min, ~\$0.09)"
echo "    Outputs (best_prompt + scores + run metadata)"
echo "    Outputs (Estadistica gral)"
echo ""
pausa

# ------------------------------------------------------------------
# SECCION 0 — Arquitectura en capas (vision general)
# ------------------------------------------------------------------
seccion "0/8 | Arquitectura en capas — entradas, optimizer, salidas"

echo ""
echo -e "${BOLD}Arquitectura en capas:${RESET}"
echo ""
echo "  +--------------------------------------------------------------+"
echo "  |  CAPA 1 - ENTRADAS (versionadas en git)                      |"
echo "  +--------------------------------------------------------------+"
echo "  |   experiments/datasets/email_urgency.csv   (train/val/test)  |"
echo "  |   experiments/prompts/email_urgency_v1.json (prompt inicial) |"
echo "  |   experiments/configs/email_urgency.yaml   (hiperparametros) |"
echo "  |   .env                                     (LLM_API_KEY +    |"
echo "  |                                             modelos T/R)     |"
echo "  +--------------------------------------------------------------+"
echo "                              |"
echo "                              v"
echo "  +--------------------------------------------------------------+"
echo "  |  CAPA 2 - OPTIMIZER (universal_optimizer.py)                 |"
echo "  +--------------------------------------------------------------+"
echo "  |   Adapter (classifier) -> evalua prompt sobre train/val      |"
echo "  |   Estudiante (TASK)    -> ejecuta cada candidato (barato)    |"
echo "  |   Profesor  (REFLECTION) -> propone mutaciones (caro)        |"
echo "  |   Loop reflexivo: mutar -> evaluar val -> aceptar/descartar  |"
echo "  +--------------------------------------------------------------+"
echo "                              |"
echo "                              v"
echo "  +--------------------------------------------------------------+"
echo "  |  CAPA 3 - SALIDAS (results/, gitignoreado, regenerable)      |"
echo "  +--------------------------------------------------------------+"
echo "   results/runs/email_urgency/<timestamp>/"
echo "      final_prompt.txt      -> prompt optimizado (artefacto clave)"
echo "      results.json          -> baseline, optimized, test scores"
echo "      run.json              -> seed, modelos, version frameworks"
echo "      experiment.meta.json  -> hash dataset, contador de runs"
echo "      metrics.csv           -> traza por iteracion"
echo "                              |"
pausa

# ------------------------------------------------------------------
# SECCION 1 — INPUT: Dataset CSV
# ------------------------------------------------------------------
seccion "1/8 | INPUT: Dataset — experiments/datasets/email_urgency.csv"

echo -e "${BOLD}30 filas | 3 columnas | Distribucion: 15 train / 10 val / 5 test${RESET}"
echo ""
cat  experiments/datasets/email_urgency.csv
#head -1 experiments/datasets/email_urgency.csv
#grep -m 3 "^train," experiments/datasets/email_urgency.csv
#echo "  ... 12 filas train mas ..."
#grep -m 3 "^val," experiments/datasets/email_urgency.csv
#echo "  ... 7 filas val mas ..."
#grep -m 3 "^test," experiments/datasets/email_urgency.csv
#echo "  ... 2 filas test mas ..."
echo ""
echo -e "${BOLD}Contrato:${RESET} columna de entrada + columna de salida esperada + columna split"
echo ""
echo -e "${BOLD}Rol de cada split durante la optimizacion:${RESET}"
echo ""
echo "  train (15) -> REFLEXION. GEPA evalua el prompt aqui y los errores"
echo "                se pasan al LLM Profesor para proponer mutaciones."
echo "                Es el material del que el optimizador 'aprende'."
echo ""
echo "  val   (10) -> SELECCION. Cada prompt mutado se prueba contra val."
echo "                El score en val decide si la mutacion entra al pool."
echo "                Es el 'juez' de la optimizacion."
echo ""
echo "  test  (5)  -> VERIFICACION. GEPA NUNCA lo ve durante la optimizacion."
echo "                Solo al final, para medir si generaliza o hay overfitting."
pausa

# ------------------------------------------------------------------
# SECCION 2 — INPUT: Prompt inicial JSON
# ------------------------------------------------------------------
seccion "2/8 | INPUT: Prompt inicial — experiments/prompts/email_urgency_v1.json"

cat experiments/prompts/email_urgency_v1.json
echo ""
echo ""
echo -e "${BOLD}Una sola instruccion de partida.${RESET} No tiene que ser buena."
echo "  GEPA la evoluciona usando los errores del modelo como feedback."
pausa

# ------------------------------------------------------------------
# SECCION 3 — INPUT: Configuracion YAML
# ------------------------------------------------------------------
seccion "3/8 | INPUT: Configuracion — experiments/configs/email_urgency.yaml"

cat experiments/configs/email_urgency.yaml
echo ""
echo -e "${BOLD}Campos clave:${RESET}"
echo "  adapter.type        -> tipo de tarea (classifier / extractor / sql / rag)"
echo "  prompt.filename     -> apunta al JSON versionado en git"
echo "  max_metric_calls    -> presupuesto maximo de evaluaciones"
echo "  skip_perfect_score  -> se detiene si alcanza 100%"
pausa

# ------------------------------------------------------------------
# SECCION 4 — INPUT: Modelos (.env, estrategia Profesor-Estudiante)
# ------------------------------------------------------------------
seccion "4/8 | INPUT: Modelos — .env (estrategia Profesor-Estudiante)"

echo -e "${BOLD}Configuracion en .env:${RESET}"
echo ""
grep -E "^LLM_MODEL_(TASK|REFLECTION)" .env 2>/dev/null || \
    grep -E "^LLM_MODEL_(TASK|REFLECTION)" .env.example
echo ""
echo -e "${BOLD}Esto es la clave del ROI:${RESET}"
echo ""
echo "  Profesor (REFLECTION) -> caro y potente. Solo durante optimizacion."
echo "    Lee errores del Estudiante y propone mejoras al prompt."
echo ""
echo "  Estudiante (TASK)     -> barato y rapido. Corre cada evaluacion"
echo "    durante optimizacion Y todas las llamadas en produccion."
echo ""
echo "  Resultado: pagas inteligencia de gpt-4o UNA vez para destilar"
echo "  instrucciones que un modelo ~10x mas barato sabe seguir."
pausa

# ------------------------------------------------------------------
# SECCION 5 — OPERACION: Optimizer (corre por separado)
# ------------------------------------------------------------------
seccion "5/8 | OPERACION: Optimizer — corre por separado"

echo "  Comando:"
echo ""
echo -e "${BOLD}    python universal_optimizer.py --config experiments/configs/email_urgency.yaml${RESET}"
echo ""
echo "  Salida esperada:"
echo ""
echo "    Baseline: 60.0%"
echo ""
echo "    GEPA Optimization:  20%|## | 10/50"
echo "    Iteration 1: Found a better program with score 0.9."
echo "    Iteration 3: Found a better program with score 1.0."
echo "    Iteration 5: All subsample scores perfect. Skipping."
echo ""
echo "    Baseline:   60.0%"
echo "    Optimizado: 100.0%"
echo "    Mejora:     +40.0%"
echo "    Presupuesto usado: 51 llamadas"
echo ""
echo "    DETALLE TEST SET (5/5 correctos):"
echo "      Alerta roja: BD corrupta...        | urgent | urgent | SI"
echo "      Compartiendo ideas estrategia Q3.. | low    | low    | SI"
echo "      Por favor completa capacitacion..  | normal | normal | SI"
echo "      Bug critico produccion login...    | urgent | urgent | SI"
echo "      Recordatorio evento integracion..  | low    | low    | SI"
echo ""
echo -e "${BOLD}  Tiempo aprox: ~1 minuto. Costo aprox: \$0.09 USD.${RESET}"
echo ""
echo -e "${YELLOW}  Ejecuta el optimizer ahora en otra terminal, luego continua.${RESET}"
pausa

# ------------------------------------------------------------------
# SECCION 6 — OUTPUT: Archivos del run + prompts
# ------------------------------------------------------------------
seccion "6/8 | OUTPUT: Archivos del run y prompts"

LATEST_RUN=$(ls -td results/runs/email_urgency/2026-*/ 2>/dev/null | head -1)

if [ -z "$LATEST_RUN" ]; then
    echo "  No hay runs previos en results/runs/email_urgency/. Ejecuta el optimizer primero."
    pausa
else
    echo -e "${BOLD}Directorio del run:${RESET} $LATEST_RUN"
    echo ""
    ls "$LATEST_RUN"
    echo ""

    RESULTS_FILE="${LATEST_RUN}results.json"
    if [ -f "$RESULTS_FILE" ]; then
        BASELINE=$(python -c "import json; d=json.load(open('$RESULTS_FILE')); print(f\"{d['baseline_score']*100:.0f}%\")" 2>/dev/null)
        OPTIMIZED=$(python -c "import json; d=json.load(open('$RESULTS_FILE')); print(f\"{d['optimized_score']*100:.0f}%\")" 2>/dev/null)
        TEST=$(python -c "import json; d=json.load(open('$RESULTS_FILE')); print(f\"{d['test_score']*100:.0f}%\")" 2>/dev/null)
        echo -e "${BOLD}Scores:${RESET}  Baseline $BASELINE  ->  Optimizado $OPTIMIZED  |  Test $TEST"
        echo ""
    fi

    INITIAL_FILE="${LATEST_RUN}initial_prompt.txt"
    FINAL_FILE="${LATEST_RUN}final_prompt.txt"

    if [ -f "$INITIAL_FILE" ]; then
        echo -e "${BOLD}Prompt inicial:${RESET}"
        cat "$INITIAL_FILE"
        echo ""
    fi

    if [ -f "$FINAL_FILE" ]; then
        echo -e "${BOLD}Prompt optimizado:${RESET}"
        cat  "$FINAL_FILE"
        echo
        echo "  ........................................................"
    fi
fi
pausa

# ------------------------------------------------------------------
# SECCION 5 — OUTPUT: Leaderboard
# ------------------------------------------------------------------
seccion "7/8 | OUTPUT: Leaderboard — casos de gepa_standalone"

echo -e "${BOLD}  \$ python analyze leaderboard --project gepa_standalone${RESET}"
echo ""
cd "$ROOT_DIR"
python analyze leaderboard --project gepa_standalone 2>&1 \
    | grep -v "^\[INFO\]" \
    | grep -v "^CSVs" \
    | grep -v "^\s*-" \
    | sed '/ANOMALIAS DETECTADAS/,$d'
pausa

# ------------------------------------------------------------------
# SECCION 8 — OUTPUT: Evolucion temporal
# ------------------------------------------------------------------
seccion "8/8 | OUTPUT: Evolucion temporal del caso"

echo -e "${BOLD}  \$ python analyze stats --case \"Email Urgency\"${RESET}"
echo ""
python analyze stats --case "Email Urgency" 2>&1 | grep -v "^\[INFO\]" | grep -v "^CSVs" | grep -v "^\s*-"

echo ""
echo -e "${GREEN}================================================================${RESET}"
echo -e "${GREEN}  Demo completada.${RESET}"
echo -e "${GREEN}================================================================${RESET}"
echo ""
echo "  Documentacion:"
echo "    guion_demo.md          -> guion completo de la demo"
echo "    ROI_ANALYSIS.md        -> analisis de costos y ROI (245 experimentos)"
echo "    UNIVERSAL_OPTIMIZER.md -> anatomia del YAML y jerarquia de config"
echo "    docs/GEPA_DOCUMENTACION.md   -> arquitectura y filosofia de GEPA"
echo "    docs/LECCIONES_APRENDIDAS.md -> errores reales y como resolverlos"
echo ""
