# AGENTS.MD

## Proposito

Este repositorio desarrolla un traductor de voz local en tiempo real o casi real. El flujo operativo actual es:

1. Captura de audio con `sounddevice`
2. Segmentacion con `Silero VAD`
3. Transcripcion con `mlx-whisper` y `Whisper Large V3 Turbo`
4. Traduccion semantica con `Ollama`
5. Sintesis y reproduccion con `Kokoro-82M TTS`

El comportamiento esperado del producto es escuchar audio desde el microfono, detectar voz, transcribirla, traducirla al idioma destino activo de la sesion y reproducir esa traduccion como audio sintetizado.

La prioridad principal es la latencia total de extremo a extremo.

## Estado Operativo Actual

El repositorio ya dispone de una ruta local completa:

```text
microfono -> VAD -> ASR -> traduccion -> TTS
```

Componentes implementados:

- captura de microfono y normalizacion de audio
- segmentacion con VAD y metadatos por segmento
- ASR real con deteccion automatica de idioma
- traduccion local por API HTTP de Ollama
- TTS local con Kokoro y reproduccion con `sounddevice`
- pipeline `asyncio` con colas acotadas entre etapas principales
- eventos por `utterance_id`
- metricas por etapa y end-to-end
- benchmarks por etapa y benchmark del pipeline completo

El siguiente frente natural es optimizacion de latencia, no integracion basica.

## Entorno y Comandos

Usar `uv` como gestor principal del proyecto.

Reglas:

1. Instalar dependencias con `uv sync`.
2. Ejecutar comandos con `uv run`.
3. Documentar la CLI instalada `traductor-ia` como ruta principal.
4. Evitar documentar `python main.py` como forma principal salvo que se necesite depurar el wrapper local.
5. Ejecutar tests con `uv run python -m unittest discover -s tests -v`.
6. No modificar `uv.lock` manualmente.

Comandos minimos utiles:

```bash
uv sync
uv run traductor-ia info
uv run traductor-ia captura-diagnostico --seconds 5
uv run traductor-ia transcribe-en-vivo --seconds 15
uv run traductor-ia --target-language en traducir-en-vivo --seconds 15
uv run traductor-ia --target-language en pipeline-diagnostico --seconds 15
uv run python -m unittest discover -s tests -v
```

## Modelos Configurados

### VAD

- Backend: `silero-vad`
- Sample rate esperado: `16000`

### ASR

- Backend: `mlx-whisper`
- Modelo: `mlx-community/whisper-large-v3-turbo`
- Deteccion de idioma: automatica
- Parciales: disponibles en diagnostico ASR
- Pipeline completo: traduce resultados finales

### Traduccion

- Backend: `Ollama` por API HTTP
- URL por defecto: `http://localhost:11434`
- Modelo preferido actual: `gemma4:26b`
- Modelo candidato pendiente de comparativa: `qwen3:8b`
- `think`: `false`
- `stream`: `false`
- `temperature`: `0.0`
- Salida esperada: JSON con clave `translation`

No hay fallback automatico real entre modelos. Si se cambia el modelo de traduccion, medir latencia y calidad antes de considerarlo valido para el MVP.

### TTS

- Backend: `kokoro`
- Modelo/repo: `hexgrad/Kokoro-82M`
- Sample rate: `24000`
- Reproduccion: `sounddevice`
- Politica actual: secuencial y conservadora para estabilidad

## Idiomas Del MVP

Idiomas destino del MVP documentado:

- `es`: Espanol
- `en`: Ingles
- `fr`: Frances
- `it`: Italiano

El idioma de entrada se detecta automaticamente. El idioma destino actual se pasa por CLI con `--target-language`; si no se indica, el valor por defecto es `en`.

Objetivo pendiente para MVP usable: seleccionar el idioma destino de forma explicita al inicio de la sesion.

## Objetivos Tecnicos

1. Objetivo operativo: latencia global inferior a `1 segundo`.
2. Objetivo ideal: aproximarse a `500 ms` en fragmentos cortos con modelos ya cargados.
3. Mantener calidad suficiente sin sacrificar respuesta en tiempo real.
4. Medir siempre antes de optimizar.
5. Distinguir claramente latencia de arranque, latencia con modelos calientes y latencia end-to-end real.

## Presupuesto Orientativo de Latencia

| Etapa | Objetivo p50 | Limite p95 |
| --- | ---: | ---: |
| Captura + cierre de segmento VAD | 80-150 ms | 250 ms |
| Transcripcion ASR | 150-300 ms | 450 ms |
| Traduccion LLM | 80-200 ms | 300 ms |
| Sintesis TTS hasta primer audio | 100-200 ms | 300 ms |
| Coordinacion interna | < 50 ms | < 100 ms |

Si una etapa supera claramente su presupuesto, hay que documentarlo, identificar causa y proponer alternativas medibles.

## Reglas Principales

1. La latencia manda.
2. Cada etapa debe exponer metricas.
3. No bloquear nunca la captura de audio.
4. No introducir colas sin limite en codigo nuevo.
5. No anadir complejidad innecesaria.
6. No cambiar de modelo o backend sin comparar rendimiento y calidad.
7. No asumir mejoras sin medirlas.
8. Preferir procesamiento incremental frente a esperar frases completas cuando sea fiable.
9. Mantener prompts minimos, estables y sin texto decorativo.
10. Mantener el contexto del LLM corto para reducir latencia y errores.
11. Reutilizar modelos y sesiones en memoria.
12. Evitar conversiones de audio y copias de memoria innecesarias.

## Estructura Del Proyecto

```text
src/traductor_tiempo_real/
  audio/          captura, normalizacion y modelos de audio
  vad/            Silero VAD y segmentador
  asr/            servicio ASR y backend mlx-whisper
  traduccion/     servicio de traduccion y cliente Ollama
  tts/            Kokoro, servicio TTS y reproductor
  pipeline/       bootstrap, orquestador asyncio y reportes
  metricas/       eventos, checks y medicion de tiempos
  configuracion/  dataclasses e idiomas soportados
tests/
benchmarks/
samples/
Informe/
```

## Contratos Entre Etapas

Cada etapa debe tener entradas y salidas claras:

1. Audio crudo o normalizado
2. Segmento detectado por VAD
3. Transcripcion parcial, cuando aplique
4. Transcripcion final
5. Traduccion
6. Audio sintetizado o resultado TTS

Cada unidad procesada debe incluir, cuando aplique:

- identificador estable
- `utterance_id` en el pipeline
- marca de tiempo de creacion
- marca de tiempo de inicio de proceso
- marca de tiempo de fin de proceso
- duracion total de etapa
- estado final o error trazable

## Reglas de Implementacion

1. Leer el codigo existente antes de modificar arquitectura.
2. Hacer cambios pequenos y verificables.
3. Priorizar claridad y observabilidad.
4. Usar `asyncio` en la orquestacion del pipeline cuando sea natural.
5. Usar colas acotadas en codigo nuevo.
6. Aplicar backpressure cuando sea necesario.
7. Diferenciar claramente resultados parciales de resultados finales.
8. Centralizar la configuracion critica en `configuracion/`.
9. No crear abstracciones nuevas si no aportan valor directo.
10. Anadir comentarios solo cuando aclaren una parte realmente no obvia.

## CLI Actual

Entry point principal:

```bash
uv run traductor-ia <comando>
```

Opciones globales relevantes:

- `--target-language`: idioma destino, actualmente con valor por defecto `en`
- `--debug`: salida adicional

Comandos existentes:

- `info`
- `benchmark-base`
- `captura-diagnostico`
- `transcribe-en-vivo`
- `validar-asr-real`
- `benchmark-asr`
- `traducir-en-vivo`
- `validar-traduccion-real`
- `benchmark-traduccion`
- `tts-diagnostico`
- `benchmark-tts`
- `pipeline-diagnostico`
- `benchmark-pipeline`

Opciones frecuentes por comando:

- `--seconds`
- `--max-segments`
- `--mute`
- `--json`
- `--sample`
- `--no-partials`
- `--play`

## Pruebas Minimas Esperadas

Antes de considerar una tarea como terminada:

1. Ejecutar pruebas unitarias o de integracion del modulo afectado.
2. Ejecutar `uv run python -m unittest discover -s tests -v` si el cambio toca contratos compartidos.
3. Ejecutar benchmark corto si se toca VAD, ASR, traduccion, TTS o pipeline.
4. Validar manualmente al menos un caso real si afecta al comportamiento final.
5. Documentar cualquier prueba que no se haya podido ejecutar y por que.

Comando de tests:

```bash
uv run python -m unittest discover -s tests -v
```

Benchmarks principales:

```bash
uv run traductor-ia benchmark-base --sample samples/base_silence.wav
uv run traductor-ia benchmark-asr
uv run traductor-ia --target-language en benchmark-traduccion
uv run traductor-ia --target-language en benchmark-traduccion --compare-models
uv run traductor-ia --target-language es benchmark-tts
uv run traductor-ia --target-language en benchmark-pipeline
```

## Seguimiento Del Trabajo

1. `Fases.md` actua como tablero vivo del proyecto.
2. Las fases se gestionan como sprints.
3. Cada sprint debe mantener tareas con checkboxes Markdown.
4. Una tarea solo puede marcarse con `- [x]` cuando exista codigo, prueba, benchmark o validacion real que la respalde.
5. Si un cambio completa una tarea de un sprint, actualizar `Fases.md` en la misma entrega.
6. No marcar tareas como completadas por intencion, diseno o documentacion si aun no existe implementacion real.

## Criterios de Aceptacion

Un cambio se considera aceptable si:

1. no rompe el flujo completo
2. no empeora la latencia sin justificacion clara
3. mantiene o mejora la observabilidad
4. incluye pruebas adecuadas o benchmark cuando corresponde
5. evita complejidad gratuita
6. mantiene comandos y documentacion alineados con `uv`

## Riesgos Conocidos

1. `gemma4:26b` funciona, pero puede ser demasiado costoso para tiempo real estricto.
2. La comparativa con `qwen3:8b` sigue pendiente.
3. La suma de pequenas latencias entre etapas puede romper el objetivo global.
4. Un VAD demasiado conservador empeora mucho la experiencia.
5. Esperar siempre a resultado final puede ser demasiado lento para algunos casos.
6. La deteccion automatica de idioma puede fallar en segmentos muy cortos.
7. El coste de arranque de algunos modelos es alto si no se mantienen precalentados.
8. Falta validacion prolongada de estabilidad en sesiones largas.
9. El TTS secuencial actual prioriza estabilidad por encima de minima latencia percibida.

## Deuda Tecnica Actual

- Optimizar latencia del modelo de traduccion.
- Validar `qwen3:8b` contra `gemma4:26b` con benchmark reproducible.
- Afinar umbrales VAD y tamanos de chunk.
- Revisar backpressure y limites de colas internas de servicios.
- Definir estrategia de interrupcion, sustitucion o compactacion para TTS.
- Ejecutar stress test prolongado de pipeline.
- Convertir la seleccion de idioma destino en decision explicita de inicio.

## Que Documentar Siempre

1. Hardware usado en las pruebas.
2. Modelo exacto de ASR.
3. Modelo exacto de traduccion.
4. Modelo exacto de TTS.
5. Idiomas de origen y destino.
6. Latencias p50 y p95 cuando existan datos suficientes.
7. Problemas observados de calidad o estabilidad.
8. Si los modelos estaban frios o ya cargados.

## Prioridad de Toma de Decisiones

Ante una duda tecnica, decidir en este orden:

1. opcion que cumpla mejor el objetivo de latencia
2. opcion mas simple de operar y medir
3. opcion con menos complejidad accidental
4. opcion con mejor calidad, si no rompe las anteriores
