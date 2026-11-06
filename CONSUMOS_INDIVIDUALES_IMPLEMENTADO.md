# Sistema de Consumos Individuales por Pasajero

## 📋 Resumen de Funcionalidad

Se ha implementado un sistema completo de **consumos individuales por pasajero** que permite manejar correctamente las situaciones donde:

- **Habitación con mismo voucher** (matrimonios/familias): Los consumos se cargan a cualquier miembro del grupo y se facturan de forma compartida.
- **Habitación con vouchers diferentes** (personas que no se conocen): Cada pasajero tiene su propia cuenta de consumos que se factura por separado.

---

## 🎯 Casos de Uso

### Caso 1: Habitación con Matrimonio/Familia (Mismo Voucher)
**Ejemplo:** Habitación 102 - 2 personas con voucher 30238977

- Los consumos se pueden cargar a cualquiera de los dos
- El sistema muestra una cuenta unificada
- Al hacer checkout, se cobra un total general para toda la familia

### Caso 2: Habitación con Personas Desconocidas (Vouchers Diferentes)
**Ejemplo:** Habitación 103 (testJubis.csv) - 2 personas con vouchers 30188715 y 30188714

- **IMPORTANTE:** Al agregar un consumo, el sistema OBLIGA a seleccionar a qué pasajero cargarlo
- Cada pasajero tiene su cuenta separada
- Los consumos se muestran agrupados por pasajero
- Al hacer checkout, se muestran totales separados por persona

---

## 🔧 Modificaciones Realizadas

### 1. **core/dashboard.py**
#### Nueva función: `obtener_todos_pasajeros_habitacion()`
```python
def obtener_todos_pasajeros_habitacion(num_habitacion, archivo_pasajeros='data/pasajeros.csv')
```
- Retorna **TODOS** los pasajeros de una habitación (no solo el titular)
- Incluye: nombre, voucher, edad, documento, servicios
- Ordenados por edad (mayor primero)

### 2. **core/consumos.py**
#### Nuevas funciones:

**`obtener_consumos_por_pasajero()`**
- Agrupa consumos de una habitación por pasajero individual
- Retorna diccionario con consumos y totales de cada pasajero

**`obtener_total_consumos_pasajero()`**
- Calcula totales de un pasajero específico
- Permite facturación separada

**`obtener_resumen_habitacion()` - MODIFICADA**
- Ahora incluye lista completa de pasajeros
- Detecta si hay vouchers separados
- Incluye consumos agrupados por pasajero
- Retorna flag `tiene_vouchers_separados`

### 3. **app.py**
#### Ruta modificada: `/habitacion/<num>/agregar`
```python
def agregar_consumo_habitacion(num_habitacion)
```
- Ahora recibe parámetro `pasajero` del formulario
- Si hay múltiples pasajeros, usa el pasajero seleccionado
- Si es habitación individual o mismo voucher, usa el titular

### 4. **templates/ficha_habitacion.html**
#### Nuevas secciones:

**📋 Lista de Pasajeros** (si hay más de uno)
- Muestra todos los pasajeros de la habitación
- Indica si comparten voucher o no
- Alerta visual cuando hay vouchers separados

**Formulario de Consumos**
- **Nuevo campo:** Selector de pasajero (aparece solo si hay múltiples pasajeros)
- Obligatorio cuando hay vouchers diferentes

**Vista de Consumos**
- **Modo separado:** Muestra consumos agrupados por pasajero con subtotales
- **Modo unificado:** Muestra consumos con columna de pasajero
- Totales por pasajero cuando hay vouchers separados
- Total general de la habitación

### 5. **templates/checkout.html**
#### Modificaciones:

**Información del Pasajero**
- Muestra titular y cantidad de pasajeros
- Lista completa de pasajeros si hay más de uno

**Resumen de Consumos**
- Vista separada por pasajero cuando hay vouchers diferentes
- Subtotales individuales
- Total general de la habitación

**Totales Finales**
- Desglose por pasajero cuando hay cuentas separadas
- Total unificado cuando comparten voucher

---

## 📊 Flujo de Trabajo

### Para Habitaciones con Vouchers Diferentes:

1. **Al abrir la ficha de habitación:**
   - Se muestra alerta: "Los pasajeros tienen vouchers diferentes y NO se conocen"
   - Aparece lista de todos los pasajeros

2. **Al agregar un consumo:**
   - **OBLIGATORIO:** Seleccionar a qué pasajero cargar el consumo
   - Ejemplo: "Guion Cecilia (64 años - Voucher: 30188715)"

3. **Visualización de consumos:**
   - Consumos agrupados por pasajero
   - Subtotal por cada persona
   - Total general de la habitación

4. **Al hacer checkout:**
   - Resumen separado por pasajero
   - Permite cobrar a cada uno su parte
   - Total unificado para control

### Para Habitaciones con Mismo Voucher:

1. **Al abrir la ficha de habitación:**
   - Se muestra info: "Los pasajeros comparten voucher (familia/grupo)"
   - No es obligatorio seleccionar pasajero

2. **Al agregar un consumo:**
   - Se puede seleccionar a quién cargarlo (opcional)
   - Si no se selecciona, se carga al titular

3. **Visualización de consumos:**
   - Lista unificada con columna de pasajero
   - Total general del grupo

4. **Al hacer checkout:**
   - Un solo total para toda la familia/grupo

---

## 🔍 Detección Automática de Vouchers Separados

El sistema detecta automáticamente si hay vouchers diferentes mediante:

```python
vouchers_unicos = set(p['voucher'] for p in todos_pasajeros)
tiene_vouchers_separados = len(vouchers_unicos) > 1 and len(todos_pasajeros) > 1
```

Esta lógica se aplica en:
- Ficha de habitación
- Checkout
- Generación de reportes

---

## ✅ Ventajas del Sistema

1. **Flexibilidad:** Maneja tanto familias como personas desconocidas
2. **Claridad:** Interfaz visual diferente según el caso
3. **Precisión:** Cada persona paga exactamente lo que consumió
4. **Control:** Los totales siempre cuadran
5. **Trazabilidad:** Registro detallado de quién consumió qué

---

## 📝 Compatibilidad con Ambos CSV

### pasajeros.csv (Trabajadores Activos)
- Mismo voucher por SEDE
- Múltiples habitaciones no relacionadas
- Consumos por habitación (pueden no conocerse pero comparten sede)

### testJubis.csv (Trabajadores Pasivos/Jubilados)
- Voucher único por persona/familia
- Solo comparten voucher matrimonios/familiares

---

## Aislamiento de consumos por estadía

- La ficha, los totales de cuenta y el check-out filtran por los `id_estadia` de los pasajeros activos, no solo por el número físico de habitación.
- Como cada pasajero puede tener su propio `id_estadia`, una cuenta de habitación puede filtrar por el conjunto de IDs de sus ocupantes actuales.
- Los consumos históricos sin `id_estadia` no se asignan automáticamente: permanecen en el CSV y en los informes históricos, se excluyen de la cuenta actual y se indican en la ficha.
- Los cambios de habitación actualizan únicamente consumos vinculados por `id_estadia`; los registros sin identidad permanecen intactos.
- **Sistema detecta automáticamente vouchers diferentes**
- Consumos separados por default

---

## 🚀 Próximos Pasos Sugeridos

1. **Agregar campo de "Almuerzo"** para PENSIÓN COMPLETA (testJubis.csv)
2. **Exportar resumen de checkout** con consumos separados por pasajero
3. **Reportes de consumos** agrupados por voucher o por pasajero
4. **Estadísticas** de consumo promedio por tipo de pasajero

---

## 📌 Notas Importantes

- El sistema **NO modifica** la lógica de titular por edad
- El titular sigue siendo el de mayor edad para efectos administrativos
- Los consumos se pueden cargar a cualquier pasajero independientemente de quién sea el titular
- Al hacer checkout, se eliminan TODOS los pasajeros de la habitación y TODOS sus consumos
- El archivo consumos_diarios.csv ya tenía el campo "pasajero" - ahora se usa completamente

### ✈️ Checkout para Jubilados (Traslado Incluido)

- Los jubilados tienen **traslado incluido** (el hotel los trae y lleva)
- **NO hay checkouts anticipados** - todos los retiros son en la fecha programada
- El botón de "Checkout Anticipado" ha sido **eliminado** de la interfaz
- Solo aparece el botón de checkout cuando es la fecha programada de salida
- Esto difiere de los trabajadores activos que vienen por sus propios medios

---

**Fecha de Implementación:** 1 de Marzo de 2026  
**Estado:** ✅ Funcionalidad Completa
