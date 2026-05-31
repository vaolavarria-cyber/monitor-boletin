# Monitor Boletín Oficial — updater gratis (sin créditos de Claude)

Actualiza solo cada mañana (lunes a viernes) usando **GitHub Actions** (cron gratis) +
**Groq** (IA gratis para los resúmenes) y deploya a tu sitio de **Netlify**.
Una vez configurado, **no consume créditos de Claude nunca más**.

## Qué hace cada archivo
- `update.py` — baja el Boletín, genera resúmenes con Groq y escribe `index.html`.
- `.github/workflows/update.yml` — corre `update.py` cada día hábil 8:01 (hora ARG) y deploya a Netlify.

## Configuración (una sola vez)

### 1. Subir esta carpeta a un repo de GitHub
Creá un repositorio nuevo (privado está bien) y subí estos archivos.

### 2. Sacar las 3 claves
- **GROQ_API_KEY**: entrá a https://console.groq.com/keys → "Create API Key" → copiala.
- **NETLIFY_AUTH_TOKEN**: en Netlify → User settings → Applications → "New access token".
- **NETLIFY_SITE_ID**: en tu sitio de Netlify → Site configuration → "Site ID" (o el nombre, ej. `strong-pasca-8d77e8`).

### 3. Cargar las claves como Secrets en GitHub
En el repo → **Settings → Secrets and variables → Actions → New repository secret**.
Creá los tres: `GROQ_API_KEY`, `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID`.

### 4. Probar
En el repo → pestaña **Actions → "Actualizar monitor" → Run workflow**.
Mirá los logs. Si todo va bien, tu sitio Netlify queda actualizado.

## Ajustes
- **Indicadores INDEC**: se editan a mano en `update.py` (lista `INDEC_INDICADORES`).
  No se scrapean porque el INDEC no tiene API estable; se actualizan cuando salen datos nuevos.
- **Endpoint del Boletín**: si los logs muestran que no trae decretos/resoluciones,
  ajustá la constante `BORA_SUMARIO` en `update.py`. Ese es el único punto frágil:
  el sitio del Boletín cambia su forma de servir datos cada tanto.
- **Horario**: cambiá el `cron` en `update.yml` (está en UTC; ARG = UTC-3).

## Importante
- El día a día corre 100% en GitHub + Groq + Netlify, todo en capas gratuitas.
- Tu antigua tarea programada de Claude quedó **desactivada** para que no te cobre créditos.
