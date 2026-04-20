# Sprints del proyecto

## Cómo usar este archivo

Este archivo actúa como tablero vivo del proyecto.

- `- [ ]` significa pendiente.
- `- [x]` significa completado.
- Una tarea solo debe marcarse como completada cuando exista código, prueba, benchmark o validación real que lo respalde.
- Si una tarea afecta a latencia, también debe quedar acompañada por una medición o una prueba reproducible.

## Objetivo global

Construir una aplicación de traducción de voz en tiempo real o casi real con este flujo:

1. Captura y segmentación con `sounddevice` + `Silero VAD`
2. Transcripción con `Whisper Large V3 Turbo`
3. Traducción semántica con `Qwen3-8B` o `Gemma 4 27B` en `Ollama`
4. Síntesis de voz con `Kokoro-82M TTS`

Objetivos de latencia:

- Operativo: extremo a extremo por debajo de `1 segundo`
- Ideal: acercarse a `500 ms` en fragmentos cortos y con modelos ya cargados

## Requisitos funcionales del MVP

- [ ] La aplicación pregunta al inicio el idioma destino.
- [ ] El idioma de entrada se detecta automáticamente.
- [ ] El MVP solo soporta estos idiomas de salida:
  - [ ] Español
  - [ ] Inglés
  - [ ] Francés
  - [ ] Alemán
  - [ ] Italiano
- [ ] La traducción usa siempre el idioma destino de la sesión.
- [ ] El TTS usa siempre el idioma destino de la sesión.

## Presupuesto objetivo de latencia

| Etapa | Objetivo p50 | Límite p95 |
| --- | ---: | ---: |
| Captura + cierre de segmento VAD | 80-150 ms | 250 ms |
| Transcripción ASR | 150-300 ms | 450 ms |
| Traducción LLM | 80-200 ms | 300 ms |
| Síntesis TTS hasta primer audio | 100-200 ms | 300 ms |
| Coordinación interna | < 50 ms | < 100 ms |

## Estado actual del repositorio

- [x] Proyecto Python mínimo creado con `pyproject.toml`
- [x] Punto de entrada mínimo presente en `main.py`
- [x] `AGENTS.MD` creado
- [x] Tablero de sprints documentado en `Fases.md`
- [x] Estructura objetivo del proyecto creada en `src/`
- [x] Suite de tests creada
- [x] Benchmarks creados

## Sprint 0. Base del proyecto y medición

### Objetivo

Disponer de una base mínima medible para construir el pipeline sin perder visibilidad de latencia.

### Entregables

- [x] Proyecto Python mínimo inicializado
- [x] Punto de entrada mínimo disponible
- [x] Estructura base creada:
  - [x] `src/traductor_tiempo_real/`
  - [x] `tests/`
  - [x] `benchmarks/`
  - [x] `samples/`
- [x] Configuración centralizada creada
- [x] Catálogo de idiomas destino definido internamente:
  - [x] `es`
  - [x] `en`
  - [x] `fr`
  - [x] `de`
  - [x] `it`
- [x] Utilidades de métricas creadas
- [x] Benchmark base sobre audios pregrabados preparado
- [x] Validación inicial de hardware, modelos y arranque completada

### Pruebas

- [x] Smoke test de arranque del proyecto
- [x] Prueba de carga de modelos
- [x] Benchmark offline inicial ejecutado

### Criterio de cierre

Sprint cerrado cuando exista una base ejecutable y medible para continuar con el resto del pipeline.

## Sprint 1. Captura y segmentación

### Objetivo

Capturar audio del micrófono sin bloquear y generar segmentos rápidos y estables.

### Entregables

- [ ] Captura con `sounddevice` implementada
- [ ] Callback no bloqueante implementado
- [ ] Búfer circular implementado
- [ ] Conversión a mono y sample rate objetivo implementada
- [ ] Integración con `Silero VAD`
- [ ] Ajustes básicos de VAD definidos:
  - [ ] tamaño de ventana
  - [ ] pre-roll
  - [ ] hangover
  - [ ] duración máxima de segmento
- [ ] Metadatos por segmento añadidos:
  - [ ] identificador
  - [ ] timestamps
  - [ ] duración
  - [ ] energía

### Pruebas

- [ ] Test con silencio
- [ ] Test con voz continua
- [ ] Test con pausas cortas
- [ ] Test con ruido de fondo
- [ ] Test de estabilidad de captura prolongada
- [ ] Medición de latencia de cierre de segmento

### Criterio de cierre

Sprint cerrado cuando la captura sea estable, no bloquee y entregue segmentos útiles dentro del presupuesto esperado.

## Sprint 2. ASR con detección automática de idioma

### Objetivo

Obtener transcripción parcial y final con baja latencia y con detección automática del idioma de entrada.

### Entregables

- [ ] `Whisper Large V3 Turbo` integrado
- [ ] Estrategia incremental por fragmentos implementada
- [ ] Soporte de resultados parciales implementado
- [ ] Soporte de resultados finales implementado
- [ ] Detección automática del idioma habilitada
- [ ] Registro del idioma detectado por segmento implementado
- [ ] Registro de estabilidad del idioma detectado implementado

### Pruebas

- [ ] Test de transcripción con audios cortos
- [ ] Test de transcripción con audios medios
- [ ] Medición de tiempo a primer parcial
- [ ] Medición de tiempo a texto final
- [ ] Validación de estabilidad de detección de idioma en segmentos de 1 a 3 segundos

### Criterio de cierre

Sprint cerrado cuando ASR produzca texto usable, con parciales y finales, dentro del presupuesto de latencia.

## Sprint 3. Traducción semántica

### Objetivo

Traducir al idioma destino elegido al inicio con salida limpia, fiel y rápida.

### Entregables

- [ ] Integración con `Ollama`
- [ ] Prompt mínimo y estable definido
- [ ] Soporte para idioma destino de sesión implementado
- [ ] Comparativa `Qwen3-8B` vs `Gemma 4 27B` realizada
- [ ] Métricas de latencia de traducción registradas
- [ ] Modelo candidato del MVP seleccionado

### Pruebas

- [ ] Benchmark con frases de 3 palabras
- [ ] Benchmark con frases de 8 palabras
- [ ] Benchmark con frases de 15 palabras
- [ ] Validación de fidelidad semántica
- [ ] Validación de salida sin texto extra

### Criterio de cierre

Sprint cerrado cuando la traducción sea estable, limpia y suficientemente rápida para el objetivo del MVP.

## Sprint 4. TTS

### Objetivo

Generar voz entendible con inicio de audio rápido y sin bloquear el resto del pipeline.

### Entregables

- [ ] Integración con `Kokoro-82M TTS`
- [ ] Voz base por idioma definida:
  - [ ] Español
  - [ ] Inglés
  - [ ] Francés
  - [ ] Alemán
  - [ ] Italiano
- [ ] Reproducción no bloqueante implementada
- [ ] Fallback de voz por idioma definido
- [ ] Métricas de time-to-first-audio registradas

### Pruebas

- [ ] Medición de time-to-first-audio
- [ ] Medición de tiempo total de síntesis
- [ ] Validación manual de inteligibilidad
- [ ] Prueba de frases consecutivas

### Criterio de cierre

Sprint cerrado cuando el audio se reproduzca de forma estable, entendible y rápida.

## Sprint 5. Pipeline completo

### Objetivo

Unir captura, ASR, traducción y TTS en un flujo no bloqueante y medible.

### Entregables

- [ ] Pipeline con `asyncio` implementado
- [ ] Colas acotadas implementadas
- [ ] Backpressure implementado
- [ ] Eventos del pipeline definidos
- [ ] Métricas end-to-end añadidas
- [ ] Configuración de idioma destino de sesión aplicada en todo el flujo

### Pruebas

- [ ] Test de integración con audio pregrabado
- [ ] Test con micrófono real
- [ ] Test de estrés prolongado
- [ ] Medición de RAM, CPU y tamaño de colas

### Criterio de cierre

Sprint cerrado cuando el flujo completo funcione de extremo a extremo sin bloqueos y con métricas trazables.

## Sprint 6. Optimización de latencia

### Objetivo

Bajar de `1 segundo` y acercarse a `500 ms` cuando sea viable.

### Entregables

- [ ] Ajuste fino de umbrales VAD
- [ ] Ajuste fino de tamaños de chunk
- [ ] Ajuste del prompt y parámetros del LLM
- [ ] Modelos precalentados y persistentes
- [ ] Copias y conversiones innecesarias reducidas
- [ ] Estrategia de disparo de traducción validada
- [ ] Estrategia de disparo de TTS validada

### Pruebas

- [ ] Benchmark antes y después de cada ajuste
- [ ] Medición p50
- [ ] Medición p95
- [ ] Medición p99
- [ ] Validación en sesiones largas

### Criterio de cierre

Sprint cerrado cuando el sistema cumpla el objetivo operativo y tenga casos cortos cercanos al ideal.

## Sprint 7. MVP usable

### Objetivo

Tener una versión utilizable, repetible y fácil de depurar.

### Entregables

- [ ] CLI inicial implementada
- [ ] Selector obligatorio de idioma destino implementado
- [ ] Soporte para estos idiomas en el selector:
  - [ ] Español
  - [ ] Inglés
  - [ ] Francés
  - [ ] Alemán
  - [ ] Italiano
- [ ] Idioma de entrada automático mantenido
- [ ] Logging claro implementado
- [ ] Modo benchmark implementado
- [ ] Documentación de instalación y uso escrita

### Pruebas

- [ ] Smoke test desde entorno limpio
- [ ] Prueba de error de dispositivo de audio
- [ ] Prueba de error de modelo
- [ ] Validación manual del flujo completo
- [ ] Validación del selector inicial de idioma destino

### Criterio de cierre

Sprint cerrado cuando el MVP pueda usarse localmente de forma repetible.

## Estrategia de pruebas global

### Unitarias

- [ ] Normalización de audio
- [ ] Segmentación VAD
- [ ] Encolado y desencolado
- [ ] Formateo de prompts
- [ ] Adaptadores de respuesta de ASR, LLM y TTS

### Integración

- [ ] Audio -> VAD -> ASR
- [ ] ASR -> LLM
- [ ] LLM -> TTS
- [ ] Flujo completo con audios de ejemplo

### Benchmarks

- [ ] Latencia por etapa
- [ ] Latencia total
- [ ] Uso de CPU
- [ ] Uso de memoria
- [ ] Tiempo de arranque en frío y en caliente

### Manuales

- [ ] Voz lenta
- [ ] Voz rápida
- [ ] Pausas cortas
- [ ] Ruido ambiente
- [ ] Nombres propios
- [ ] Frases ambiguas
- [ ] Alternancia entre idiomas

## Riesgos principales

1. `Gemma 4 27B` puede ser demasiado pesado para cumplir el objetivo de latencia del MVP.
2. `Whisper Large V3 Turbo` puede exigir un backend muy optimizado para cumplir tiempos.
3. La suma de pequeñas demoras entre etapas puede romper el objetivo global.
4. Un VAD demasiado conservador puede hacer que el sistema se sienta lento.
5. Esperar siempre al final de frase perjudica el tiempo real.
6. La detección automática del idioma puede fallar en segmentos muy cortos.

## Decisiones pendientes

- [ ] Definir el comportamiento cuando el idioma detectado ya coincide con el idioma destino.
- [ ] Seleccionar el modelo final de traducción del MVP tras benchmark real.
- [ ] Seleccionar la voz definitiva por idioma para el TTS.
