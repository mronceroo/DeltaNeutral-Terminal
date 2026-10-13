# Delta Neutral Dashboard — HyENA × Hibachi

Dashboard en tiempo real para monitorizar spreads y oportunidades de funding rate entre HyENA (Hyperliquid HIP-3) y Hibachi (Base).

## Archivos

| Archivo | Función |
|---------|---------|
| `proxy.py` | Servidor Python: workers de datos + sirve el dashboard |
| `index.html` | Dashboard frontend (single-file HTML/JS/CSS) |
| `render.yaml` | Configuración de deploy para Render.com |

## Visitar

https://deltaneutral-terminal.onrender.com/

## Ejecución local

```bash
python proxy.py
# Abre http://localhost:8765
```

## Notas

- El plan gratuito de Render **duerme** el servicio tras 15 min sin tráfico. La primera carga tras inactividad tarda ~30s.
- No se necesitan dependencias externas (usa stdlib de Python).
- Las APIs de HyENA y Hibachi se consultan en background (2s y 6s respectivamente).
