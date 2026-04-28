# Traductor IA

Traductor de voz local en tiempo real o casi real. El flujo actual es:

1. Captura de audio con `sounddevice`
2. Segmentacion de voz con `Silero VAD`
3. Transcripcion con `mlx-whisper` y `Whisper Large V3 Turbo`
4. Traduccion semantica con `Ollama`
5. Sintesis y reproduccion con `Kokoro-82M TTS`

El proyecto ya tiene un pipeline funcional `microfono -> VAD -> ASR -> traduccion -> TTS`, con metricas por etapa, colas acotadas en la orquestacion y benchmarks por modulo.

## Estado Actual

Implementado:

- paquete Python en `src/traductor_tiempo_real/`
- CLI instalable `traductor-ia`
- configuracion centralizada por dataclasses
- catalogo cerrado de idiomas destino del MVP
- captura de microfono y segmentacion VAD
- ASR real con deteccion automatica de idioma
- traduccion local por API HTTP de Ollama
- TTS local con Kokoro y reproduccion con `sounddevice`
- pipeline completo con `asyncio`, eventos y metricas end-to-end
- tests unitarios e integracion mockeada
- benchmarks reales por etapa y benchmark del pipeline con WAVs locales

Pendiente principal:

- optimizacion de latencia para acercar el flujo completo al objetivo de menos de `1 segundo`
- comparativa real entre `gemma4:26b` y `qwen3:8b`
- validacion prolongada de estabilidad
- selector obligatorio de idioma destino al inicio de la sesion

## Requisitos

- Python `3.12`
- `uv`
- macOS con Apple Silicon recomendado para `mlx-whisper`
- permisos de microfono y salida de audio
- Ollama levantado en `http://localhost:11434`
- modelo de traduccion disponible en Ollama, por defecto `gemma4:26b`

Instalar `uv` si no esta disponible:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Preparar el entorno:

```bash
uv sync
```

Preparar Ollama:

```bash
ollama serve
ollama pull gemma4:26b
```

Opcional para comparar latencia/calidad:

```bash
ollama pull qwen3:8b
```

## Modelos Configurados

| Etapa | Backend | Modelo actual |
| --- | --- | --- |
| VAD | `silero-vad` | Silero VAD |
| ASR | `mlx-whisper` | `mlx-community/whisper-large-v3-turbo` |
| Traduccion | `Ollama` HTTP API | `gemma4:26b` |
| TTS | `kokoro` | `hexgrad/Kokoro-82M` |

`qwen3:8b` esta registrado como candidato para comparativa, pero no es fallback automatico. La configuracion actual usa `gemma4:26b` como modelo preferido.

## Idiomas Del MVP

Idiomas destino documentados para el MVP:

- `es`: Espanol
- `en`: Ingles
- `fr`: Frances
- `it`: Italiano

El idioma de entrada se detecta automaticamente desde el ASR. Actualmente el idioma destino se pasa con `--target-language`; si no se indica, el CLI usa `en`.

## Uso Rapido

Mostrar la configuracion efectiva:

```bash
uv run traductor-ia info
```

Ejecutar diagnostico de captura y segmentacion:

```bash
uv run traductor-ia captura-diagnostico --seconds 5
```

Transcribir en vivo desde el microfono:

```bash
uv run traductor-ia transcribe-en-vivo --seconds 15
```

Traducir en vivo con TTS activo:

```bash
uv run traductor-ia --target-language en traducir-en-vivo --seconds 15
```

Traducir en vivo sin reproduccion de audio:

```bash
uv run traductor-ia --target-language en traducir-en-vivo --seconds 15 --mute
```

Ejecutar el pipeline completo con metricas end-to-end:

```bash
uv run traductor-ia --target-language en pipeline-diagnostico --seconds 15
```

Nota: para usar traduccion en vivo con TTS activo conviene usar auriculares para evitar realimentacion del audio de salida al microfono.

## Comandos Disponibles

### Configuracion

```bash
uv run traductor-ia info
```

### Captura y VAD

```bash
uv run traductor-ia captura-diagnostico --seconds 5
uv run traductor-ia captura-diagnostico --seconds 15 --max-segments 3
```

### ASR

```bash
uv run traductor-ia transcribe-en-vivo --seconds 15
uv run traductor-ia transcribe-en-vivo --seconds 15 --no-partials
uv run traductor-ia validar-asr-real --script es-basico
uv run traductor-ia benchmark-asr
```

### Traduccion y TTS

```bash
uv run traductor-ia --target-language en traducir-en-vivo --seconds 15
uv run traductor-ia --target-language en traducir-en-vivo --seconds 15 --mute
uv run traductor-ia --target-language en validar-traduccion-real --script es-basico
uv run traductor-ia --target-language en benchmark-traduccion
uv run traductor-ia --target-language en benchmark-traduccion --model qwen3:8b
uv run traductor-ia --target-language en benchmark-traduccion --compare-models
uv run traductor-ia --target-language es tts-diagnostico --text "Hola, esta es una prueba de voz."
uv run traductor-ia --target-language es tts-diagnostico --text "Hola, esta es una prueba de voz." --mute
uv run traductor-ia --target-language es benchmark-tts
uv run traductor-ia --target-language es benchmark-tts --play
```

### Pipeline Completo

```bash
uv run traductor-ia --target-language en pipeline-diagnostico --seconds 15
uv run traductor-ia --target-language en pipeline-diagnostico --seconds 15 --mute
uv run traductor-ia --target-language en benchmark-pipeline
```

### Benchmark Base

```bash
uv run traductor-ia benchmark-base --sample samples/base_silence.wav
```

Tambien existe este script instalable:

```bash
uv run traductor-benchmark-base --sample samples/base_silence.wav
```

### Salida JSON

La mayoria de comandos de diagnostico y benchmark aceptan `--json`:

```bash
uv run traductor-ia --target-language en benchmark-pipeline --json
```

## Tests

Ejecutar la suite completa:

```bash
uv run python -m unittest discover -s tests -v
```

La suite cubre configuracion, idiomas, metricas, audio, segmentacion VAD, ASR con backend falso, traduccion, TTS y pipeline pregrabado con servicios mockeados. Los benchmarks son los que ejercitan backends reales.

## Benchmarks

Benchmarks principales:

```bash
uv run traductor-ia benchmark-base --sample samples/base_silence.wav
uv run traductor-ia benchmark-asr
uv run traductor-ia --target-language en benchmark-traduccion
uv run traductor-ia --target-language en benchmark-traduccion --compare-models
uv run traductor-ia --target-language es benchmark-tts
uv run traductor-ia --target-language en benchmark-pipeline
```

Wrappers equivalentes en `benchmarks/`:

```bash
uv run python benchmarks/benchmark_base.py --sample samples/base_silence.wav
uv run python benchmarks/benchmark_asr.py
uv run python benchmarks/benchmark_translation.py
uv run python benchmarks/benchmark_tts.py
uv run python benchmarks/benchmark_pipeline.py
```

Muestras incluidas:

- `samples/base_silence.wav`: silencio mono `16 kHz`
- `samples/asr/en_corto.wav`: voz corta en ingles
- `samples/asr/es_corto.wav`: voz corta en espanol
- `samples/asr/es_medio.wav`: voz media en espanol

El benchmark del pipeline pregrabado espera WAVs PCM mono `16 kHz`.

## Arquitectura

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
```

El pipeline en vivo inicializa y calienta backends antes de escuchar. Despues produce segmentos desde microfono, despacha ASR, traduce resultados finales y envia traducciones a TTS. El reporte final incluye resultados, eventos, estadisticas de colas, CPU/RSS y metricas end-to-end.

Los reportes JSON del pipeline incluyen `latency_summary` con `p50_ms`, `p95_ms` y `p99_ms` para latencia hasta traduccion y hasta primer audio.

## Limitaciones Conocidas

- La latencia completa puede superar `1 segundo`, especialmente por traduccion con `gemma4:26b`.
- `qwen3:8b` esta pendiente de comparativa real contra `gemma4:26b`.
- Los resultados parciales de ASR existen en diagnostico, pero el pipeline completo traduce solo finales.
- El TTS actual prioriza estabilidad con reproduccion secuencial; aun no hay estrategia agresiva de interrupcion o sustitucion de audio.
- Falta una prueba prolongada de estres para sesiones largas.
- Algunos servicios internos usan workers propios; la orquestacion del pipeline usa colas acotadas, pero la optimizacion fina de backpressure sigue pendiente.

## Sprints Implementados

- Sprint 0: base del repositorio, configuracion, metricas y benchmark base.
- Sprint 1: captura con microfono, buffer circular, Silero VAD y segmentacion.
- Sprint 2: ASR real con `mlx-whisper`, parciales/finales y deteccion automatica de idioma.
- Sprint 3: traduccion con Ollama, prompt minimo, JSON limpio y benchmark de frases.
- Sprint 4: TTS con Kokoro, reproduccion no bloqueante y benchmark de voz.
- Sprint 5: pipeline completo con `asyncio`, colas acotadas, eventos y metricas end-to-end.

El tablero vivo del proyecto esta en `Fases.md` y el informe tecnico hasta Sprint 5 esta en `Informe/InformeTecnico.md`.
