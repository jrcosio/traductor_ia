# AGENTS.MD

## Propósito

Este repositorio desarrolla un traductor de voz local en tiempo real o casi real con este flujo:

1. `sounddevice` + `Silero VAD`
2. `Whisper Large V3 Turbo`
3. `Qwen3-8B` o `Gemma 4 27B` sobre `Ollama`
4. `Kokoro-82M TTS`

El comportamiento esperado del producto es escuchar audio desde el micrófono, detectar la voz, transcribirla, traducirla al idioma destino activo de la sesión y reproducir esa traducción como audio sintetizado.

La prioridad principal es la latencia total de extremo a extremo.

## Objetivos técnicos

1. Objetivo operativo: latencia global inferior a `1 segundo`.
2. Objetivo ideal: aproximarse a `500 ms` en fragmentos cortos.
3. Mantener calidad suficiente sin sacrificar la respuesta en tiempo real.
4. Medir siempre antes de optimizar.

## Requisitos funcionales del MVP

1. El idioma de entrada es automático.
2. Al iniciar la aplicación se debe seleccionar el idioma destino.
3. El MVP solo soporta estos idiomas de salida:
   - Español
   - Inglés
   - Francés
   - Alemán
   - Italiano
4. No se debe aceptar texto libre para el idioma destino en la primera versión.
5. Todas las etapas posteriores deben usar el idioma destino de la sesión.
6. El flujo principal del MVP empieza en el micrófono y termina en reproducción de audio traducido por TTS.

## Reglas principales

1. La latencia manda.
2. Cada etapa debe exponer métricas.
3. No bloquear nunca la captura de audio.
4. No introducir colas sin límite.
5. No añadir complejidad innecesaria.
6. No cambiar de modelo o backend sin comparar rendimiento y calidad.
7. No asumir mejoras sin medirlas.
8. Preferir procesamiento incremental frente a esperar frases completas.
9. Mantener prompts mínimos, estables y sin texto decorativo.
10. Mantener el contexto del LLM corto para reducir latencia y errores.

## Criterios de desarrollo

1. Hacer cambios pequeños y verificables.
2. Leer el código existente antes de modificar arquitectura.
3. Priorizar claridad y observabilidad.
4. Añadir comentarios solo cuando aclaren una parte realmente no obvia.
5. No crear abstracciones nuevas si no aportan valor directo.

## Estructura objetivo del proyecto

La estructura esperada puede evolucionar hacia algo parecido a esto:

```text
src/
  traductor_tiempo_real/
    audio/
    vad/
    asr/
    traduccion/
    tts/
    pipeline/
    metricas/
    configuracion/
tests/
benchmarks/
samples/
```

## Contratos entre etapas

Cada etapa debe tener entradas y salidas claras:

1. Audio crudo
2. Segmento detectado por VAD
3. Transcripción parcial
4. Transcripción final
5. Traducción
6. Audio sintetizado

Cada unidad procesada debe incluir:

- identificador
- marca de tiempo de creación
- marca de tiempo de inicio de proceso
- marca de tiempo de fin de proceso
- duración total de etapa

## Reglas de implementación

1. Usar `asyncio` o un diseño equivalente no bloqueante.
2. Usar colas acotadas.
3. Aplicar backpressure cuando sea necesario.
4. Reutilizar modelos y sesiones en memoria.
5. Evitar conversiones de audio redundantes.
6. Reducir copias de memoria innecesarias.
7. Diferenciar claramente resultados parciales de resultados finales.
8. Centralizar la configuración crítica del sistema.

## Presupuesto orientativo de latencia por etapa

Tomar esta referencia al desarrollar:

1. Captura + cierre de segmento: `80-150 ms` p50
2. ASR: `150-300 ms` p50
3. Traducción: `80-200 ms` p50
4. TTS hasta primer audio: `100-200 ms` p50
5. Coordinación interna: `< 50 ms` p50

Si una etapa supera claramente su presupuesto, hay que:

1. documentarlo
2. identificar la causa
3. proponer alternativas

## Reglas de pruebas

Antes de considerar una tarea como terminada:

1. Ejecutar o dejar listas pruebas unitarias del módulo afectado.
2. Ejecutar o dejar listas pruebas de integración de la ruta afectada.
3. Ejecutar benchmark corto si se toca VAD, ASR, LLM, TTS o el pipeline.
4. Validar manualmente al menos un caso real si afecta al comportamiento final.

## Seguimiento del trabajo

1. El archivo `Fases.md` actúa como tablero vivo del proyecto.
2. Las fases del proyecto se gestionan como sprints.
3. Cada sprint debe mantener tareas con checkboxes Markdown.
4. Una tarea solo puede marcarse con `- [x]` cuando exista código, prueba, benchmark o validación real que la respalde.
5. Si un cambio completa una tarea de un sprint, debe actualizarse `Fases.md` en la misma entrega.
6. No marcar tareas como completadas por intención, diseño o documentación si aún no existe implementación real.

## Pruebas mínimas esperadas

### Unitarias

- procesamiento de audio
- segmentación
- validación de eventos
- adaptación de respuestas de modelos
- construcción de prompts

### Integración

- audio a ASR
- ASR a traducción
- traducción a TTS
- flujo completo

### Rendimiento

- latencia p50/p95/p99
- uso de CPU
- uso de memoria
- arranque en frío
- rendimiento con modelos ya cargados

## Criterios de aceptación

Un cambio se considera aceptable si:

1. no rompe el flujo completo
2. no empeora la latencia sin justificación clara
3. mantiene o mejora la observabilidad
4. incluye pruebas adecuadas o benchmark
5. evita complejidad gratuita

## Riesgos conocidos

1. Modelos demasiado grandes en `Ollama` pueden impedir el tiempo real.
2. La suma de pequeñas latencias entre etapas puede hacer fallar el objetivo global.
3. Un VAD demasiado conservador empeora mucho la experiencia.
4. Esperar siempre a frase completa puede ser demasiado lento.
5. El coste de arranque de algunos modelos puede ser alto si no se mantienen precalentados.
6. `Gemma 4 27B` debe validarse con benchmark real antes de considerarse apto para el MVP.

## Recomendaciones para el MVP

1. Empezar con una sola dirección de traducción por sesión.
2. Empezar con una interfaz de línea de comandos.
3. Priorizar respuesta rápida frente a cobertura de casos raros.
4. Seleccionar primero la combinación de modelos más rápida y estable.
5. Mantener el sistema sencillo y medible.

## Qué documentar siempre

1. Hardware usado en las pruebas.
2. Modelo exacto de ASR.
3. Modelo exacto de traducción.
4. Modelo exacto de TTS.
5. Idiomas de origen y destino.
6. Latencias p50 y p95.
7. Problemas observados de calidad o estabilidad.

## Prioridad de toma de decisiones

Ante una duda técnica, decidir en este orden:

1. opción que cumpla mejor el objetivo de latencia
2. opción más simple de operar y medir
3. opción con menos complejidad accidental
4. opción con mejor calidad, si no rompe las anteriores
