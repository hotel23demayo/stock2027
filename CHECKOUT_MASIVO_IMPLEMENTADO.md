# Implementación: Checkout Masivo para Contingentes

> **Estado vigente (noviembre de 2026):** el checkout elimina del padrón activo las filas de pasajeros que egresan, pero **no borra ni marca como pagados los consumos**. Los consumos quedan en `consumos_diarios.csv` como historial. Esta nota reemplaza las descripciones anteriores de eliminación de consumos.

## ✅ Implementado con Éxito

### Características Implementadas:

#### 1. **Checkout Masivo del Contingente** 🚪
- Acceso desde el dashboard cuando hay checkouts pendientes
- Vista previa con resumen detallado antes de confirmar
- Procesa las estadías cuyo ingreso y egreso son hoy o fechas anteriores

#### 2. **Checkout Individual** (Sin cambios) 👤
- Mantiene el proceso manual para reservas express
- Click en habitación → Ver resumen → Confirmar checkout

#### 3. **Gestión de Consumos** 💰
- El resumen presenta los consumos de la estadía antes de confirmar.
- El checkout no cambia su estado ni los elimina; el archivo conserva el historial.
- Una nueva estadía en esa habitación no hereda esos consumos porque se identifica por `id_estadia`.

---

## Flujo de Trabajo

### Para Contingentes (Ingresos Masivos)

```
Día 1: Carga masiva de rooming desde CSV
       ↓
Días 2-5: Registro de consumos individuales por habitación
          ↓
Día 5: Sistema detecta checkout pendiente (egreso hoy o vencido)
                 Habitaciones se marcan en ROJO
                 ↓
Recepcionista: Click en "Checkout Masivo Contingente"
               ↓
Sistema muestra: - 40+ habitaciones
                 - Total registrado de consumos
                 - Confirmación de acción
                 ↓
Recepcionista: Confirma con 1 click
               ↓
Sistema: • Retira del padrón los pasajeros con checkout pendiente
         • Conserva todos los consumos históricos
         • Habitaciones quedan disponibles para nuevas estadías
         ↓
Listo para nuevo rooming ✅
```

### Para Reservas Express (Individuales)

```
Cliente de mostrador: Check-in express
                      ↓
Estadía: 2-3 días (fecha flexible)
         ↓
Checkout: Manual e individual desde la habitación
          ↓
Sistema: Retira del padrón activo al pasajero; conserva sus consumos históricos
```

---

## Archivos Modificados

### 1. `app.py`
- ✅ Ruta `/checkout-masivo` - Vista previa del checkout
- ✅ Ruta `/checkout-masivo/confirmar` - Procesa el checkout masivo
- ✅ `confirmar_checkout()` conserva los consumos históricos

### 2. `templates/checkout_masivo.html` (NUEVO)
- ✅ Pantalla de confirmación con tabla detallada
- ✅ Muestra: habitaciones, pasajeros, vouchers, consumos
- ✅ Totales generales
- ✅ Alerta de acción irreversible

### 3. `templates/dashboard.html`
- ✅ Botón "Checkout Masivo Contingente" con animación pulsante
- ✅ Aparece cuando hay checkouts pendientes

---

## Seguridad y Validaciones

✅ **Confirmación doble:**
   - Vista previa con resumen completo
   - Confirmación JavaScript antes de ejecutar

✅ **Validaciones:**
   - Verifica que existan habitaciones con checkout pendiente
   - Maneja errores de lectura/escritura de archivos
   - Mensajes claros de éxito/error

✅ **Confirmación y seguridad:**
   - La acción NO se puede deshacer desde la aplicación
   - Alerta clara en pantalla
   - Se recomienda realizar backups periódicos de los datos
   - El checkout no genera un backup propio

---

## Respuestas a tus Preguntas

### ¿Qué pasa con los consumos?
✅ Se conservan en `consumos_diarios.csv`; el checkout no registra un estado de pago.

### ¿La habitación queda en cero?
✅ La nueva estadía comienza sin consumos anteriores, ya que el sistema los filtra por `id_estadia`.

### ¿Lista para nuevo rooming?
✅ **SÍ**, puedes cargar inmediatamente el nuevo CSV con el siguiente contingente

### ¿Los checkouts individuales también conservan consumos?
✅ **SÍ**, se conserva el historial y se retira al pasajero del padrón activo.

---

## Ventajas de esta Implementación

1. ⚡ **Velocidad**: 40+ checkouts en 2 clicks vs 80+ clicks individuales
2. 📊 **Transparencia**: Resumen completo antes de ejecutar
3. 🔄 **Flexibilidad**: Contingentes (masivo) + Express (individual)
4. 💾 **Historial**: Los consumos permanecen disponibles después del checkout
5. 🎯 **Operativa real**: Diseñado para tu flujo de trabajo con contingentes

---

El checkout no archiva automáticamente las filas de pasajeros retiradas ni crea un backup. Los detalles de persistencia y reinicio se documentan en [data/README.md](data/README.md) y [REINICIO_DATOS.md](REINICIO_DATOS.md).
