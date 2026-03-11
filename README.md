# Delta Neutral Dashboard — HyENA × Hibachi

Dashboard en tiempo real para monitorizar spreads y oportunidades de funding rate entre HyENA (Hyperliquid HIP-3) y Hibachi (Base).

## Archivos

| Archivo | Función |
|---------|---------|
| `proxy.py` | Servidor Python: workers de datos + sirve el dashboard |
| `index.html` | Dashboard frontend (single-file HTML/JS/CSS) |
| `render.yaml` | Configuración de deploy para Render.com |

## Deploy en Render.com (Gratis)

### Opción A: Deploy automático desde GitHub

1. Sube esta carpeta a un repositorio en GitHub
2. Ve a [render.com](https://render.com) → New → Web Service
3. Conecta tu repo de GitHub
4. Render detectará el `render.yaml` automáticamente
5. Click en **Deploy** → listo

### Opción B: Deploy manual en Render

1. Ve a [render.com](https://render.com) → New → Web Service
2. Conecta tu repo
3. Configura:
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python proxy.py`
4. Deploy

### URL

Una vez desplegado, Render te dará una URL tipo:  
`https://delta-neutral-dashboard.onrender.com`

Ábrela en el móvil y listo.

## Ejecución local

```bash
python proxy.py
# Abre http://localhost:8765
```

## Notas

- El plan gratuito de Render **duerme** el servicio tras 15 min sin tráfico. La primera carga tras inactividad tarda ~30s.
- No se necesitan dependencias externas (usa stdlib de Python).
- Las APIs de HyENA y Hibachi se consultan en background (2s y 6s respectivamente).
