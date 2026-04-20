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

Ejecutar tests:

```bash
python -m unittest discover -s tests -v
```
