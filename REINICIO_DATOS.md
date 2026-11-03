# 🧹 Reinicio de Datos Operativos

Script: [`reiniciar_datos.py`](reiniciar_datos.py)

Sirve para **comenzar el seguimiento real desde cero** después de una etapa de pruebas (consumos y pasajeros de prueba).

---

## Qué hace

| Archivo | Acción |
|---------|--------|
| `data/consumos_diarios.csv` | Se vacía. Queda solo el encabezado actual (`CONSUMOS_COLUMNS` de `core/consumos.py`) |
| `data/pasajeros.csv` | Se vacía y conserva su encabezado (omitir con `--mantener-pasajeros`) |
| `data/catalogo_productos.csv` | **No se toca** (productos y precios se mantienen) |
| `data/backups/` y `data/cierres/` | No se tocan |

Antes de vaciar, copia los archivos existentes a `data/backups/reinicio_AAAAMMDD_HHMMSS/`. Si algún backup queda incompleto, aborta sin modificar nada.

---

## Uso

Con la aplicación **cerrada** y después de un `git pull`:

```bash
python3 reiniciar_datos.py --simular             # muestra qué se haría, sin modificar nada
python3 reiniciar_datos.py                       # reinicio real (pide escribir REINICIAR)
python3 reiniciar_datos.py --mantener-pasajeros  # vacía solo los consumos
python3 reiniciar_datos.py --yes                 # omite la confirmación interactiva
python3 reiniciar_datos.py --datos /otra/carpeta # usa otra carpeta de datos
```

Cualquier respuesta distinta de `REINICIAR` cancela la operación.

---

## Recomendaciones

1. Ejecutar primero `--simular`.
2. Cerrar la aplicación (`Ctrl+C`) antes del reinicio real.
3. Después del reinicio, volver a cargar el CSV de pasajeros real desde **Gestionar pasajeros** (o crear reservas express).
4. Conservar la carpeta de backup hasta confirmar que el arranque fue correcto.
5. Para recuperar datos: copiar los archivos de la carpeta de backup de vuelta a `data/`.

> ⚠️ El historial de consumos es **permanente** durante la operación normal (anular = marcar `estado=anulado`; el checkout no borra consumos). Este script es la única vía prevista de vaciado, y siempre deja backup.

> ℹ️ La ruta web `/reiniciar-temporada` sigue deshabilitada a propósito; el reinicio se hace solo por CLI.

---

## Pruebas

```bash
python3 -m unittest tests.test_reiniciar_datos
```
