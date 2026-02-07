"""
Display Utilities

Funciones para formatear la salida en la terminal de manera consistente.
"""

def print_header(title: str):
    """Imprime un encabezado principal."""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def print_section(title: str):
    """Imprime un separador de sección."""
    print("\n" + "-" * 60)
    print(title)
    print("-" * 60)


def print_summary(
    baseline_avg: float,
    optimized_avg: float,
    test_avg: float,
    task_model: str,
    reflection_model: str,
    budget_used: int = None
):
    """Imprime un resumen estandarizado de resultados."""
    print_header("DEMO COMPLETADA")
    
    improvement = (optimized_avg - baseline_avg) * 100
    
    print("\nResumen de Rendimiento:")
    print(f"  Baseline:   {baseline_avg*100:.1f}%")
    print(f"  Optimizado: {optimized_avg*100:.1f}%")
    print(f"  Mejora:     {improvement:+.1f}%")
    print(f"  Set Prueba: {test_avg*100:.1f}%")

    print("\nConfiguración de Modelos:")
    print(f"   - Tarea (Task):       {task_model}")
    print(f"   - Profesor (Reflect): {reflection_model}")
    
    if budget_used:
        print(f"   - Presupuesto usado:  {budget_used} llamadas")
        
    print("\n>> El prompt fue optimizado automaticamente por GEPA")
    print("   usando reflexion sobre errores y mutacion iterativa.")
    
    print("\n" + "=" * 60)


def print_detailed_results(eval_batch):
    """
    Imprime una tabla detallada con los resultados de cada caso de prueba.
    Detecta automáticamente el tipo de tarea basado en las claves de salida.
    """
    if not eval_batch.outputs:
        print(">> No hay resultados para mostrar.")
        return

    print_section("DETALLE DE RESULTADOS (TEST SET)")
    
    # Detectar tipo de tarea
    first_out = eval_batch.outputs[0]
    
    if "field_comparisons" in first_out:
        # Extractor
        print(f"{'TEXTO (Inicio)':<30} | {'SCORE':<6} | {'ERRORES (Campo: Esp -> Obt)'}")
        print("-" * 100)
        for out, score in zip(eval_batch.outputs, eval_batch.scores):
            text_preview = out.get('text', '')[:27] + "..." if len(out.get('text', '')) > 27 else out.get('text', '')
            score_str = f"{score*100:.0f}%"
            
            errors = []
            for fname, comp in out.get('field_comparisons', {}).items():
                if not comp.get('correct'):
                    exp = str(comp.get('expected'))[:10]
                    got = str(comp.get('extracted'))[:10]
                    errors.append(f"{fname}: {exp}->{got}")
            
            error_str = ", ".join(errors) if errors else "CORRECTO"
            print(f"{text_preview:<30} | {score_str:<6} | {error_str}")

    elif "question" in first_out:
        # SQL
        print(f"{'PREGUNTA':<40} | {'CORRECTO':<8} | {'SQL GENERADO (Inicio)'}")
        print("-" * 100)
        for out, score in zip(eval_batch.outputs, eval_batch.scores):
            q_preview = out.get('question', '')[:37] + "..." if len(out.get('question', '')) > 37 else out.get('question', '')
            is_correct = "SI" if score == 1.0 else "NO"
            sql_preview = out.get('predicted', '')[:50]
            print(f"{q_preview:<40} | {is_correct:<8} | {sql_preview}")
            
    else:
        # Classifier (default)
        print(f"{'TEXTO (Inicio)':<40} | {'PREDICCION':<15} | {'ESPERADO':<15} | {'CORRECTO'}")
        print("-" * 100)
        for out, score in zip(eval_batch.outputs, eval_batch.scores):
            text_preview = out.get('text', '')[:37] + "..." if len(out.get('text', '')) > 37 else out.get('text', '')
            pred = str(out.get('predicted', ''))
            exp = str(out.get('expected', ''))
            is_correct = "SI" if score == 1.0 else "NO"
            print(f"{text_preview:<40} | {pred:<15} | {exp:<15} | {is_correct}")
    
    print("-" * 100)
