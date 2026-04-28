# Informe Técnico del Proyecto de Traductor de Voz en Tiempo Real

## Alcance del informe

Este documento resume el trabajo técnico realizado en el proyecto hasta el cierre del Sprint 5. No es un manual de uso ni una guía operativa. El objetivo es dejar constancia de qué se ha construido, cómo se ha resuelto cada bloque y por qué se han tomado determinadas decisiones de arquitectura.

## Resumen ejecutivo

El proyecto ha evolucionado desde una base mínima en Python hasta un sistema funcional capaz de:

- capturar audio desde el micrófono
- detectar voz en tiempo casi real
- transcribir con Whisper sobre Apple Silicon
- traducir semánticamente mediante un LLM local en Ollama
- sintetizar y reproducir audio con Kokoro
- medir el flujo completo con eventos, colas y métricas end-to-end

En la situación actual ya existe un pipeline local completo `micrófono -> VAD -> ASR -> traducción -> TTS`, precargado antes de entrar en escucha y con modos de validación en terminal. La arquitectura ya está suficientemente instrumentada como para pasar a una fase de optimización de latencia y endurecimiento.

## Objetivo técnico del sistema

El producto busca traducción de voz local en tiempo real o casi real. El pipeline objetivo es:

1. Captura y segmentación con `sounddevice` + `Silero VAD`
2. Transcripción con `Whisper Large V3 Turbo`
3. Traducción semántica con LLM local en `Ollama`
4. Síntesis con `Kokoro-82M TTS`

Los objetivos de latencia definidos desde el inicio son:

- objetivo operativo: extremo a extremo por debajo de `1 segundo`
- objetivo ideal: aproximarse a `500 ms` en fragmentos cortos con modelos ya cargados

## Arquitectura construida hasta ahora

La estructura principal del proyecto se ha organizado en módulos especializados:

- `configuracion/`: configuración centralizada del sistema y de sesión
- `metricas/`: eventos, tiempos y reportes estructurados
- `audio/`: captura, normalización y modelos de audio
- `vad/`: integración con Silero y segmentación
- `asr/`: transcripción con MLX Whisper
- `traduccion/`: integración con Ollama y servicio de traducción
- `tts/`: integración con Kokoro, reproducción y servicio TTS
- `pipeline/`: bootstrap, eventos de pipeline, trazas y orquestación end-to-end

La arquitectura final construida hasta Sprint 5 es híbrida:

- cada etapa pesada opera como servicio desacoplado
- los servicios siguen un modelo de trabajo con colas internas y workers propios
- el flujo completo se coordina desde un orquestador `asyncio`

Esta solución se eligió para no reescribir de cero cada backend una vez validados individualmente en sprints anteriores. Primero se estabilizó cada etapa por separado y después se añadió una capa de orquestación común.

## Evolución por sprints

## Sprint 0. Base, configuración y medición

### Qué se hizo

Se preparó la base estructural del proyecto:

- paquete Python en `src/`
- configuración centralizada mediante dataclasses
- catálogo cerrado de idiomas destino del MVP
- utilidades de métricas y benchmark base
- tests mínimos de humo y configuración

### Cómo se resolvió

Se creó una configuración centralizada en `configuracion/modelos.py` y `configuracion/carga.py`, que fija desde el principio los parámetros de audio, ASR, traducción, TTS y sesión. También se añadió un benchmark base de entorno para validar que el repositorio arrancaba y que el hardware/modelos respondían correctamente.

### Por qué se hizo así

Se priorizó una base medible antes de integrar audio o modelos pesados. El objetivo era evitar decisiones posteriores sin observabilidad y sin una línea base reproducible.

## Sprint 1. Captura y segmentación

### Qué se hizo

- captura desde el micrófono por defecto con `sounddevice`
- callback no bloqueante
- buffer circular acotado
- normalización a mono `float32`
- integración con `Silero VAD`
- segmentador con `pre-roll`, `hangover` y duración máxima
- metadatos por segmento

### Cómo se resolvió

La captura se implementó con `InputStream` y un callback reducido a la mínima responsabilidad posible: convertir el chunk, encapsularlo como `AudioFrame` y dejarlo en un buffer circular. La lógica de segmentación y VAD quedó fuera del callback para no bloquear la captura.

El segmentador mantiene estado entre frames y construye `SpeechSegment` cuando se cumplen criterios de cierre por silencio o longitud máxima.

### Por qué se hizo así

El callback de audio es el punto más sensible del sistema. Si se bloquea ahí, se rompe todo el objetivo de tiempo real. La decisión fue separar captura y decisión VAD para garantizar estabilidad y backpressure controlado.

## Sprint 2. ASR con detección automática de idioma

### Qué se hizo

- integración de `Whisper Large V3 Turbo`
- backend `mlx-whisper` para Apple Silicon
- resultados parciales y finales
- detección automática de idioma
- validación real con micrófono y terminal

### Cómo se resolvió

Se implementó un servicio ASR desacoplado que recibe snapshots o segmentos finales y devuelve `AsrResult`. El backend escogido fue `mlx-whisper` porque encaja mejor con el hardware objetivo del proyecto. Los parciales se construyen por snapshot de audio acumulado, no por streaming token a token.

### Por qué se hizo así

Se descartó una implementación más compleja de streaming puro para priorizar robustez y latencia razonable. En Apple Silicon, MLX era la opción más alineada con el objetivo del sistema.

## Sprint 3. Traducción semántica

### Qué se hizo

- integración con `Ollama` por API HTTP
- uso de `gemma4:26b` como modelo disponible real
- prompts mínimos y salida estructurada JSON
- desactivación explícita de `thinking`
- salto de traducción cuando origen y destino coinciden
- validación real en terminal

### Cómo se resolvió

La traducción se implementó como servicio separado, consumiendo solo resultados finales del ASR. Se pidió salida JSON con una única clave `translation` para evitar texto adicional, razonamiento visible o respuestas decorativas. El servicio devuelve `TranslationResult` con estados `translated`, `skipped` o `error`.

### Por qué se hizo así

El modelo `Gemma 4` mostró explícitamente contenido de razonamiento cuando se usó por CLI. Por eso se eligió la API HTTP de Ollama con `think: false`, `stream: false` y salida estructurada. Se añadió además la regla de salto cuando idioma origen y destino coinciden para ahorrar latencia y coste de inferencia.

## Sprint 4. TTS y reproducción

### Qué se hizo

- integración con `Kokoro-82M`
- reproducción mediante `sounddevice`
- worker TTS desacoplado
- métricas de `time-to-first-audio`
- voces base para inglés, español, francés e italiano

### Cómo se resolvió

Se creó un backend TTS con `KPipeline` y un reproductor secuencial no bloqueante. El TTS sintetiza y va entregando chunks, que se pueden reproducir sin esperar a tener todo el audio completo. Esto permite medir `TTFA` y deja la etapa preparada para optimización posterior.

### Por qué se hizo así

Se priorizó una solución simple y estable. La salida se hace a `24 kHz`, frecuencia nativa de Kokoro, evitando remuestreo innecesario.

## Mejora transversal previa al Sprint 5

Antes de consolidar el pipeline se realizó una mejora importante de arranque y sincronización:

- precarga explícita de VAD, ASR, traducción y TTS
- validación previa de entrada y salida de audio
- warmup real de los backends antes de escuchar
- feedback de arranque en terminal
- corrección de condiciones de carrera entre ASR, traducción y TTS

### Motivo

Sin esta mejora, el sistema daba una falsa sensación de disponibilidad porque mostraba `Escuchando...` antes de tener todos los backends preparados. Además, el modo guiado podía cerrar etapas demasiado pronto o mezclar resultados tardíos entre frases. Esta corrección dejó el sistema listo para ser orquestado como pipeline completo.

## Sprint 5. Pipeline completo

### Qué se hizo

- orquestador `asyncio` para el flujo completo
- colas acotadas entre etapas
- backpressure con descarte controlado y trazable
- eventos de pipeline por `utterance_id`
- métricas end-to-end hasta traducción y primer audio
- benchmark del flujo completo sobre audio pregrabado

### Cómo se resolvió

Se añadió una capa `pipeline/` con modelos y orquestador propios:

- `PipelineEvent`
- `UtteranceTrace`
- `QueueStats`
- `PipelineReport`

El orquestador coordina varias tareas:

- producción de segmentos desde micrófono o WAV
- despacho de segmentos a ASR
- recogida de resultados ASR
- despacho a traducción
- recogida de traducciones
- despacho a TTS
- recogida de resultados TTS
- sumidero de eventos

El pipeline sigue reutilizando los servicios ya construidos en sprints anteriores, pero ahora bajo una política explícita de colas acotadas y eventos estructurados.

### Por qué se hizo así

No se optó por reescribir el sistema entero en `asyncio` puro porque ya existía una base funcional por servicios desacoplados. El objetivo del Sprint 5 no era cambiar los backends, sino dar una orquestación formal, trazable y medible al conjunto.

## Decisiones técnicas relevantes

### Uso de MLX Whisper

Se eligió `mlx-whisper` para la transcripción porque el hardware objetivo es Apple Silicon y era la opción más razonable para latencia y despliegue local.

### Uso de Ollama por API y no por CLI

La traducción se resolvió sobre HTTP porque permitía:

- desactivar `thinking`
- pedir JSON estructurado
- controlar mejor los parámetros de generación
- obtener métricas de inferencia de forma limpia

### Traducción solo sobre finales

Se decidió no traducir parciales para no aumentar ruido ni latencia con el modelo `gemma4:26b`, que ya consume una fracción importante del presupuesto de tiempo.

### TTS secuencial con cola acotada

Para Sprint 5 se decidió encolar secuencialmente la síntesis y reproducción. No se implementó interrupción agresiva de audio, porque la prioridad era estabilidad del flujo y medición fiable. La política más agresiva queda pospuesta para optimización posterior.

### Precarga previa completa

Antes de escuchar, el sistema ahora valida y precarga:

- micrófono
- salida de audio
- VAD
- Whisper
- traducción con Ollama
- Kokoro

La decisión se tomó para evitar latencias de primera llamada mezcladas con latencias reales del flujo, y para mejorar la percepción de estabilidad del sistema.

## Estado técnico actual

En este momento el repositorio dispone de:

- captura de micrófono funcional
- segmentación VAD estable
- ASR con detección automática de idioma
- traducción local con LLM
- TTS con Kokoro y reproducción
- pipeline completo con colas y eventos
- tests y benchmarks por etapa y de extremo a extremo

En términos funcionales, ya existe una ruta completa local:

`micrófono -> VAD -> ASR -> traducción -> TTS`

## Resultados técnicos observados

Los datos observados hasta ahora muestran que el sistema es funcional, pero aún lejos del objetivo ideal de latencia bajo carga completa.

### Traducción con `gemma4:26b`

En frases breves y con modelo ya cargado se midieron latencias del orden de:

- alrededor de `579-599 ms` en frases cortas
- alrededor de `714 ms` en frases más largas del benchmark de Sprint 3

### TTS con Kokoro

Se observaron valores de `time-to-first-audio` en el rango de:

- `~200-350 ms` en frases cortas
- `~400-600 ms` en frases medias

### Pipeline completo

En benchmark completo con audio pregrabado se observaron métricas end-to-end de primer audio claramente superiores a `1 segundo` en varios casos. Esto es coherente con el peso del modelo de traducción actual y confirma que el siguiente problema ya no es funcional sino de optimización.

## Limitaciones y deuda técnica abierta

### 1. Modelo de traducción actual demasiado costoso

`gemma4:26b` funciona correctamente, pero es el principal cuello de botella de latencia. La comparativa con `qwen3:8b` sigue pendiente y es una tarea crítica para valorar el encaje del MVP en tiempo real.

### 2. Falta validación prolongada de estrés

Aunque el pipeline completo ya está instrumentado, sigue pendiente una prueba prolongada de estabilidad real para confirmar comportamiento de colas, memoria y degradación bajo sesiones largas.

### 3. TTS secuencial conservador

La política actual de TTS favorece estabilidad. Aún no se ha trabajado una estrategia de interrupción, sustitución o compactación de cola orientada a mínima latencia percibida.

## Por qué la implementación actual es válida como base de optimización

La situación técnica actual es buena para avanzar porque ya existe:

- separación clara entre etapas
- contratos de datos relativamente estables
- bootstrap centralizado
- métricas por etapa y por utterance
- benchmark del flujo completo

Esto significa que el siguiente trabajo importante ya no es de integración básica, sino de optimización, tuning de colas, mejora de modelo de traducción y ajuste fino de estrategia operacional.

## Próximo frente técnico natural

El siguiente bloque lógico de trabajo es Sprint 6, orientado a optimización de latencia. La base necesaria para ese sprint ya está construida:

- sistema funcional
- orquestación explícita
- medición end-to-end
- identificación preliminar de cuellos de botella

En términos prácticos, la prioridad técnica pasa a ser:

1. reducir latencia de traducción
2. decidir estrategia definitiva de cola de TTS
3. validar comportamiento prolongado del pipeline
4. cerrar huecos funcionales pendientes, especialmente la comparativa de modelos de traducción

## Conclusión

Hasta Sprint 5 se ha construido una base funcional completa de traductor de voz local en tiempo casi real, con arquitectura modular, bootstrap explícito, servicios desacoplados, métricas y pipeline end-to-end. El trabajo realizado ya resuelve el problema principal de integración. El reto pendiente no es ya conectar piezas, sino optimizar el comportamiento global del sistema para acercarlo al objetivo de latencia definido al inicio del proyecto.
