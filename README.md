# Traductor IA

Base del proyecto para un traductor de voz local en tiempo real o casi real.

## Sprint 0

Este sprint deja preparada la base del repositorio:

- paquete Python en `src/`
- configuración centralizada
- catálogo cerrado de idiomas del MVP
- utilidades de métricas
- benchmark offline base
- tests mínimos de humo y configuración

## Sprint 1

Este sprint añade la primera etapa real del flujo:

- captura desde el micrófono por defecto del sistema
- buffer circular no bloqueante
- integración con `Silero VAD`
- segmentación con `pre-roll`, `hangover` y duración máxima
- diagnóstico manual de captura y segmentación

## Sprint 2

Este sprint añade ASR real sobre los segmentos detectados:

- integración con `mlx-whisper`
- `Whisper Large V3 Turbo` sobre MLX
- resultados parciales y finales en terminal
- detección automática de idioma
- validación real hablando al micrófono
- benchmark ASR sobre muestras locales de voz

## Sprint 3

Este sprint añade traducción semántica sobre los resultados finales del ASR:

- integración con `Ollama`
- uso de `gemma4:26b` por API local
- salida limpia en JSON para extraer solo la traducción
- salto automático de traducción si idioma origen y destino coinciden
- traducción en vivo en terminal mostrando `ASR-FINAL` y `TRAD-FINAL` o `TRAD-SKIP`
- benchmark de traducción con frases de 3, 8 y 15 palabras

## Sprint 4

Este sprint añade TTS local con `Kokoro-82M`:

- integración con `kokoro`
- reproducción secuencial no bloqueante usando `sounddevice`
- voces base para `en`, `es`, `fr` e `it`
- alemán pospuesto explícitamente
- diagnóstico TTS y benchmark de voz
- reproducción integrada en `traducir-en-vivo`

## Sprint 5

Este sprint añade un pipeline explícito y medible de extremo a extremo:

- orquestación con `asyncio`
- colas acotadas entre etapas
- backpressure con descarte controlado y métricas
- eventos de pipeline por `utterance_id`
- métricas end-to-end hasta traducción y primer audio
- benchmark del flujo completo sobre audio pregrabado
- diagnóstico del pipeline completo con micrófono real

## Uso rápido

Mostrar la configuración base:

```bash
python main.py info
```

Ejecutar benchmark base:

```bash
python benchmarks/benchmark_base.py --sample samples/base_silence.wav
```

Ejecutar diagnóstico de captura y segmentación:

```bash
python main.py captura-diagnostico --seconds 5
```

Ejecutar transcripción en vivo en terminal:

```bash
python main.py transcribe-en-vivo --seconds 15
```

Ejecutar validación guiada en terminal:

```bash
python main.py validar-asr-real --script es-basico
```

Ejecutar benchmark ASR sobre muestras locales:

```bash
python main.py benchmark-asr
```

Ejecutar traducción en vivo en terminal:

```bash
python main.py --target-language en traducir-en-vivo --seconds 15
```

Ejecutar validación guiada de traducción:

```bash
python main.py --target-language en validar-traduccion-real --script es-basico
```

Ejecutar benchmark de traducción:

```bash
python main.py --target-language en benchmark-traduccion
```

Ejecutar diagnóstico TTS:

```bash
python main.py --target-language es tts-diagnostico --text "Hola, esta es una prueba de voz."
```

Ejecutar benchmark TTS:

```bash
python main.py --target-language es benchmark-tts
```

Ejecutar traducción en vivo con voz:

```bash
python main.py --target-language en traducir-en-vivo --seconds 15
```

Ejecutar diagnóstico del pipeline completo:

```bash
python main.py --target-language en pipeline-diagnostico --seconds 15
```

Ejecutar benchmark del pipeline completo con muestras pregrabadas:

```bash
python main.py --target-language en benchmark-pipeline
```

Nota: para usar `traducir-en-vivo` con reproducción activa es mejor usar auriculares para evitar realimentación del audio de salida al micrófono.

Ejecutar tests:

```bash
python -m unittest discover -s tests -v
```
