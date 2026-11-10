# 🏨 Sistema de Gestión Hotelera - Recepción 2026 (Consumos)

Sistema web modular para la gestión integral de consumos del hotel con **Dashboard interactivo de 53 habitaciones**, control individual por habitación, detección automática de checkouts, **Reserva Express (Walk-ins)** y generación de reportes consolidados.

---

## 📋 Características Principales

✅ **Dashboard visual de 53 habitaciones** con estados en tiempo real  
✅ **Detección automática de checkouts** del día actual con indicadores visuales  
✅ **Checkout masivo de contingentes** con preview y confirmación  
✅ **Checkout inteligente** (texto adaptado según cantidad: 1 hab vs múltiples)  
✅ **Checkout anticipado** para retiros antes de la fecha programada  
✅ **Reservas futuras visibles** para evitar overbooking  
✅ **Gestión de reservas futuras** con herramienta de carga/eliminación por fecha  
✅ **Reserva Express (Walk-ins)** con **múltiples noches** y validación inteligente  
✅ **Cambio de habitación** por desperfectos con traspaso automático de consumos  
✅ **Consumos de último momento** antes del checkout  
✅ **Selección inteligente de titulares** (mayor de edad del grupo familiar)  
✅ **Fichas individuales por habitación** con CRUD completo de consumos  
✅ **Sistema flexible de consumos** (todos los pasajeros pueden comprar cualquier producto)  
✅ **Generación de Excel consolidado** con formato salidas.xlsx  
✅ **Carga de archivos CSV** con modo dual (agregar/reemplazar)  
✅ **Backups automáticos** al subir nuevos archivos de pasajeros  
✅ **Descargas temporales** sin almacenamiento persistente de exportaciones  
✅ **Consulta de consumos centralizada** en el header del dashboard  
✅ **Identidad de estadías** (`id_estadia`): cada cuenta de consumos pertenece a una estadía, no a un número de habitación  
✅ **Bebidas rápidas** con catálogo de productos (`data/catalogo_productos.csv`)  
✅ **Anulación de consumos** conservando el registro (nunca se borran)  
✅ **Informe de consumos** consolidado por producto (pantalla y XLSX)  
✅ **Pase de turno** de recepción con planilla imprimible de pase de caja  
✅ **Listado diario de pasajeros alojados**  
✅ **Reinicio de datos por CLI** con backup y confirmación (`reiniciar_datos.py`)  

---

## 🏢 Estructura del Hotel

El sistema trabaja sobre la estructura real del establecimiento:

| Piso | Habitaciones | Cantidad |
|------|--------------|----------|
| **Piso 1** | 101–121 | 21 |
| **Piso 2** | 222–242 | 21 |
| **Piso 3** | 343–353 | 11 |
| **Total** | — | **53 habitaciones** |

Esta distribución define la grilla del dashboard y las rutas de acceso a cada ficha.

---

## 🚀 Inicio Rápido

### Instalación

**Opción 1: Script Automatizado (Recomendado)**
```bash
./run_hotel.sh  # Crea venv, instala dependencias y abre navegador automáticamente
```

**Opción 2: Manual (WSL/Linux)**
```bash
# 1. Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Iniciar servidor
./iniciar_recepcion.sh
```

**Opción 3: Acceso Directo desde Escritorio (Ubuntu)**
```bash
# Doble clic en el icono "Sistema Recepción 2026" del escritorio
```

Luego accede desde tu navegador a: **http://localhost:5000/dashboard**

Para detener el servidor: `Ctrl+C` en la terminal.

---

## 🎨 Dashboard de Habitaciones

### Código de Colores

El dashboard utiliza colores intuitivos para identificar el estado de cada habitación:

| Color | Estado | Descripción |
|-------|--------|-------------|
| 🔴 **Rojo pulsante** | Checkout hoy | Fecha de egreso coincide con hoy (prioridad máxima) |
| 🟠 **Naranja** | Con consumos | Habitación ocupada con consumos registrados |
| 🟢 **Verde** | Ocupada | Habitación ocupada sin consumos |
| 🔵 **Azul** | Reserva futura | Ingreso programado para fecha futura |
| ⚪ **Gris** | Vacía | Disponible para Reserva Express |

### Indicadores Visuales

- **Badge rojo "CHECKOUT HOY"**: Aparece sobre las habitaciones con egreso programado para hoy
- **Animación pulsante**: Las habitaciones de checkout tienen efecto visual llamativo
- **Click para Express**: Habitaciones vacías y reservadas muestran acceso rápido a Reserva Express
- **Botón consolidado**: "Descargar Salidas Hoy" (solo visible si hay checkouts)

### Acciones por Estado

- **Habitación Vacía (gris)** → Click directo a Reserva Express con habitación pre-seleccionada
- **Habitación Reservada (azul)** → Permite venta Express con advertencia de ingreso futuro
- **Habitación Ocupada** → Abre ficha detallada con consumos
- **Habitación Checkout (roja)** → Permite consumos de último momento antes del checkout

---

## 🛎️ Reserva Express (Walk-ins)

Sistema integrado para registrar huéspedes sin reserva previa con **estadías flexibles** (1 o más noches).

### Características

- ✅ **Check-in instantáneo**: Desde hoy hasta N noches
- ✅ **Noches flexibles**: Seleccionar 1 a 30 noches según disponibilidad
- ✅ **Validación inteligente**: Detecta conflictos con reservas futuras automáticamente
- ✅ **Límite dinámico**: Muestra máximo de noches disponibles antes de próxima reserva
- ✅ **Cálculo automático**: Fecha de salida calculada en tiempo real
- ✅ **Acceso directo**: Click en habitaciones disponibles desde el dashboard
- ✅ **Advertencia de reservas**: Permite vender habitaciones con ingreso futuro
- ✅ **Registro automático**: Genera voucher único y actualiza disponibilidad
- ✅ **Consumos inmediatos**: Se pueden cargar consumos apenas se registra

### Flujo de Uso

1. **Habitación Vacía (gris)**: Click → Reserva Express con habitación pre-seleccionada
2. **Habitación con Reserva Futura (azul)**: Click → Advertencia de ingreso programado + límite de noches
3. **Seleccionar datos**:
   - Habitación (pre-seleccionada o elegir otra)
   - Cantidad de personas (1-4)
   - **Cantidad de noches** (sistema muestra límite si hay reservas futuras)
   - Fecha de salida (calculada automáticamente)
   - Nombre del huésped
   - Régimen alimenticio
4. **Confirmación**: Habitación queda ocupada con las fechas establecidas

### Inteligencia de Disponibilidad

- Muestra solo habitaciones disponibles AHORA (sin ocupación actual)
- **Detecta reservas futuras** y calcula máximo de noches disponibles
- **Alerta visual**: Muestra "⚠️ Máximo X noche(s) por reserva futura"
- Valida conflictos antes de confirmar
- Ejemplo: Si hay reserva el 20/01, y hoy es 17/01, permite máximo 3 noches

---

## 🔄 Cambio de Habitación

Sistema para trasladar huéspedes entre habitaciones por desperfectos o emergencias.

### Casos de Uso

- ❄️ Aire acondicionado roto/defectuoso
- 🚿 Problemas de plomería (duchas, inodoros, canillas)
- ⚡ Problemas eléctricos
- 🔊 Ruidos o molestias
- 🧹 Problemas de limpieza
- 👤 Solicitud del huésped
- 🔧 Otros desperfectos

### Características

- ✅ **Traspaso completo**: Mueve pasajero + todos sus consumos
- ✅ **Mantiene datos**: Fechas de ingreso/egreso sin cambios
- ✅ **Habitación liberada**: La habitación original queda disponible inmediatamente
- ✅ **Selección visual**: Grid interactivo de habitaciones disponibles
- ✅ **Registro de motivo**: Documentación del cambio con observaciones
- ✅ **Seguridad**: Confirmación antes de procesar

### Flujo de Cambio

1. **Desde ficha de habitación**: Click en "🔄 Cambiar Habitación"
2. **Información actual**: Ver datos del huésped y cantidad de consumos
3. **Seleccionar nueva habitación**: Grid visual con habitaciones disponibles
4. **Motivo del cambio**: Seleccionar razón del traslado
5. **Observaciones**: Agregar detalles adicionales (opcional)
6. **Confirmar**: El sistema traslada todo automáticamente
7. **Redirección**: Se abre la ficha de la nueva habitación

---

## 🛎️ Ficha de Habitación

Cada habitación tiene una vista detallada que muestra:

### Banner de Checkout (si aplica)
- **Alerta roja**: Cuando la fecha de egreso es HOY (checkout programado)
- **Alerta amarilla**: Opción de check-out anticipado para retiros antes de la fecha programada
- Permite agregar consumos de último momento antes del checkout
- Botón "Procesar Check-out" visible cuando el huésped está listo

### Información del Pasajero
- Número de habitación
- Apellido y nombre completo (titular por edad)
- Fechas de ingreso y egreso
- Régimen alimenticio (Desayuno, Media Pensión, All Inclusive)

**Sistema de Titulares Inteligente:**
- El sistema selecciona automáticamente al pasajero de **mayor edad** como titular
- Para familias con múltiples habitaciones (mismo voucher), el titular es el mismo en todas las habitaciones
- Los menores de edad nunca aparecen como titulares
- Los consumos y checkouts se asocian al adulto responsable del grupo

### Gestión de Consumos
- **Ver consumos**: Lista completa con fecha, categoría, detalle y monto
- **Agregar consumo**: Formulario con categoría, detalle y monto
- **Eliminar consumo**: Botón individual por cada registro
- **Totales**: Resumen por categoría y total general

### Categorías de Consumos
- 🍷 Vinos
- 🥤 Gaseosas
- 🍫 Snacks
- 🧺 Lavandería
- 🍽️ Restaurant
- 🛎️ Otros

**Importante**: El sistema es flexible - todos los pasajeros pueden comprar cualquier producto, independientemente de su régimen alimenticio.

---

## 🚪 Sistema de Checkout

### Detección Automática

El sistema detecta automáticamente los checkouts del día comparando la fecha de egreso de cada pasajero con la fecha actual.

### Tipos de Checkout

**1. Checkout Programado (del día)**
- La fecha de egreso coincide con el día actual
- Aparece en el dashboard con color rojo pulsante
- Banner rojo en la ficha de habitación
- Es el proceso estándar según la reserva

**2. Checkout Masivo (Contingentes)**
- Para grupos grandes con misma fecha de salida (40-45 habitaciones)
- Acceso desde el dashboard con botón "Checkout Masivo"
- Preview con lista completa de habitaciones y consumos
- Confirmación única para procesar todos los checkouts simultáneamente
- Elimina todos los registros y consumos del día en una operación
- Ideal para temporada alta con contingentes

**3. Checkout Anticipado**
- Para huéspedes que se retiran antes de la fecha programada
- Casos comunes: emergencias personales, cambios de plan, problemas urgentes
- Banner amarillo en la ficha de habitación con confirmación adicional
- Mismo proceso de checkout pero con advertencia clara

### Proceso de Checkout

1. **Dashboard**: Las habitaciones de checkout aparecen en rojo pulsante
2. **Click en habitación**: Se abre la ficha con botón "Procesar Checkout"
3. **Resumen**: Vista previa con:
   - Información del pasajero
   - Indicador de checkout normal o anticipado
   - Desglose de consumos por categoría
   - Totales individuales
4. **Confirmación**: Advertencia de que el proceso eliminará el registro
5. **Generación Excel**: Se crea archivo temporal con el formato salidas.xlsx
6. **Limpieza**: Se elimina el pasajero de pasajeros.csv y sus consumos

### Checkout Consolidado

**Botón "Descargar Salidas Hoy"** en el dashboard genera un único archivo Excel con:
- Todos los checkouts del día actual
- Formato idéntico a salidas.xlsx (columnas: HAB, Estadía, Map, Bebidas, Forma de pago, Total)
- Descarga directa sin almacenamiento persistente

---

## 📊 Gestión de Pasajeros

### Ver Archivo Actual

La página **"Gestionar Pasajeros"** muestra estadísticas en tiempo real:
- Total de pasajeros registrados
- Habitaciones ocupadas
- Checkouts programados para hoy
- Rango de fechas (ingreso más antiguo → egreso más lejano)

### Cargar Nuevo Archivo

**Modo Dual de Carga:**

**Opción A: Agregar/Actualizar** (Recomendado para walk-ins)
- Mantiene las reservas existentes en pisos 2 y 3
- Agrega nuevas reservas del CSV (típicamente piso 1)
- Actualiza habitaciones que coinciden en número
- Ideal para cargar pasajeros individuales sin borrar contingentes

**Opción B: Reemplazar Todo** (Para contingentes completos)
- Borra todos los datos actuales
- Carga solo lo que viene en el CSV
- Crear backup automático antes de reemplazar
- Ideal para inicio de temporada o cambio completo de grupo

**Proceso:**
1. Seleccionar modo de carga (Agregar/Reemplazar)
2. Elegir archivo CSV desde sistema externo de reservas
3. El sistema crea backup automático del archivo anterior (con timestamp)
4. Se procesa según el modo seleccionado
5. Se actualiza el dashboard automáticamente

**Requisitos del CSV:**
- Formato: Separado por comas (`;` o `,`)
- Columnas necesarias: `Nro. habitación`, `Fecha de ingreso`, `Fecha de egreso`, `Apellido y nombre`, `Servicios`
- Fechas en formato `DD/MM/YYYY`
- Sin necesidad de nombre específico (acepta cualquier .csv)

**Formatos de Servicios Soportados:**
- `DESAYUNO`
- `MEDIA PENSION` / `MEDIA PENSIÓN`
- `ALL INCLUSIVE`

---

## 📥 Exportaciones y Descargas

### Sistema de Archivos Temporales

Todas las exportaciones utilizan archivos temporales que:
- ✅ Se descargan directamente al navegador (carpeta Descargas/Downloads)
- ✅ No ocupan espacio en el servidor
- ✅ Son limpiados automáticamente por el sistema operativo
- ✅ Reducen el mantenimiento y gestión de archivos

### Tipos de Exportación

**1. Consulta de Consumos (CSV)**
- Ruta: `/cierre-dia`
- Formato: Tabla pivote con totales por habitación y categoría
- Archivo: `consulta_consumos_DD-MM-YYYY.csv`

**2. Salidas Excel (XLSX)**
- Ruta: `/cierre-xlsx`
- Formato: Columnas separadas (HAB, Estadía, Map, Bebidas, Forma de pago, Total)
- Archivo: `salidas_DD-MM-YYYY.xlsx`

**3. Checkouts del Día (XLSX)**
- Ruta: `/generar-salidas-checkouts`
- Formato: Consolidado con todos los checkouts de hoy
- Archivo: `checkouts_DD-MM-YYYY.xlsx`

**4. Informe de Consumos (XLSX)**
- Ruta: `/informe-consumos` (pantalla) y `/informe-consumos-xlsx` (descarga)
- Formato: Período seleccionado, unidades consumidas por producto y total general de unidades, sin importes (pantalla, impresión y Excel)

**5. Pase de Turno**
- Ruta: `/pase-turno`
- Formato: Informe de recepción con planilla imprimible de pase de caja

**6. Listado de Pasajeros Alojados**
- Ruta: `/listado-pasajeros-alojados`
- Formato: Listado diario actualizado, imprimible

---

## 🗂️ Arquitectura del Proyecto

```
recepcion2026-consumos/
│
├── app.py                     # Punto de entrada Flask (rutas y lógica)
├── requirements.txt           # Dependencias del proyecto
├── run_hotel.sh              # Script automatizado de instalación
├── iniciar_recepcion.sh      # Script de inicio rápido
├── generar_consumos_prueba.py # Generador de datos de prueba
├── reiniciar_datos.py        # Reinicio de consumos/pasajeros con backup (CLI)
│
├── data/                      # Datos persistentes
│   ├── pasajeros.csv         # Registro actual de huéspedes
│   ├── consumos_diarios.csv  # Base de datos de consumos
│   ├── catalogo_productos.csv # Catálogo y precios (versionado)
│   └── backups/              # Backups automáticos y de reinicio
│
├── core/                      # Módulos principales
│   ├── dashboard.py          # Lógica de estados y checkout
│   ├── consumos.py           # CRUD de consumos (filtrado por id_estadia)
│   ├── identidad_estadias.py # Asigna/conserva id_estadia por pasajero
│   ├── reserva_express.py    # Reservas walk-in
│   ├── cambio_habitacion.py  # Cambio total/parcial con traspaso de consumos
│   ├── informe_consumos.py   # Informe consolidado de productos
│   └── pase_caja.py          # Pase de turno / pase de caja
│
├── templates/                 # Vistas HTML
│   ├── dashboard.html        # Grilla de 53 habitaciones
│   ├── ficha_habitacion.html # Vista individual de habitación
│   ├── checkout.html         # Resumen de checkout
│   ├── bebidas_rapidas.html  # Carga rápida de bebidas
│   ├── informe_consumos.html # Informe de consumos
│   ├── pase_turno.html       # Pase de turno / caja imprimible
│   ├── listado_pasajeros_alojados.html # Listado diario de alojados
│   └── gestionar_pasajeros.html # Carga de archivos CSV
│
├── tests/                     # Suite unittest (python3 -m unittest discover -s tests)
│
├── docs/                      # Diseño y arquitectura
│
└── static/                    # Recursos estáticos
    └── (CSS, JS, imágenes)
```

---

## 🧾 Cuentas de Consumos por Estadía

- Cada pasajero tiene un `id_estadia` (se genera en reservas express y en importaciones de CSV).
- La ficha, los totales, el checkout y el dashboard filtran los consumos por los `id_estadia` de los ocupantes **actuales**; una reserva nueva en la misma habitación empieza en cero.
- Los consumos históricos sin `id_estadia` se conservan en el CSV, no se suman a estadías nuevas y se advierten en la ficha.
- El cambio de habitación (total o parcial) traslada solo los consumos de la misma estadía.
- Los pasajeros con estadía finalizada no se listan como ocupantes.
- Detalle: [CONSUMOS_INDIVIDUALES_IMPLEMENTADO.md](CONSUMOS_INDIVIDUALES_IMPLEMENTADO.md).

---

## 🧹 Reinicio de Datos (empezar de cero)

Para iniciar el seguimiento real tras las pruebas:

```bash
python3 reiniciar_datos.py --simular   # vista previa sin cambios
python3 reiniciar_datos.py             # backup + vaciado (pide escribir REINICIAR)
```

Vacía `consumos_diarios.csv` y `pasajeros.csv` (conserva encabezados), guarda backup en `data/backups/reinicio_*` y **no toca el catálogo**. Opciones y recomendaciones: [REINICIO_DATOS.md](REINICIO_DATOS.md).

---

## 🧱 Tecnologías Utilizadas

- **Backend**: Flask 3.x (Python 3.10+)
- **Data Processing**: Pandas 2.x
- **Excel Generation**: OpenPyXL 3.1.5+
- **Frontend**: Bootstrap 5 + HTML5 + CSS3
- **Temporal Files**: Python tempfile module
- **Data Storage**: CSV (pasajeros.csv, consumos_diarios.csv)

---

## 📝 Requisitos del Sistema

```bash
Python 3.10+
Flask 3.x
pandas 2.x
openpyxl 3.1.5+
```

**Instalación automática de dependencias:**
```bash
pip install -r requirements.txt
```

---

## 🔄 Flujo de Trabajo Típico

### Temporada Alta (Grupos/Contingentes)

1. **Cargar archivo de reservas** desde sistema externo
2. **Registrar consumos** diariamente por habitación
3. **Verificar dashboard** para monitorear estados
4. **Día de checkout masivo:**
   - Dashboard muestra todas las habitaciones en rojo
   - Click en "Descargar Salidas Hoy"
   - Se genera Excel consolidado con todos los checkouts
   - Procesar checkouts individuales según necesidad

### Temporada Baja (Pasajeros Individuales)

1. **Cargar archivo de reservas** con fechas dispersas
2. **Dashboard** muestra checkouts individuales en rojo
3. **Click en habitación de checkout:**
   - Ver resumen de consumos
   - Confirmar checkout
   - Descargar Excel individual
4. **Auditoría diaria:** Revisar consumos por habitación según necesidad

---

## 🔒 Seguridad y Backups

- ✅ **Backups automáticos**: Al cargar nuevo archivo de pasajeros, se crea backup del anterior
- ✅ **Formato**: `pasajeros_backup_YYYYMMDD_HHMMSS.csv` en `data/backups/`
- ✅ **Reinicio por CLI**: `reiniciar_datos.py` respalda en `data/backups/reinicio_*` antes de vaciar (ver [REINICIO_DATOS.md](REINICIO_DATOS.md))
- ✅ **Historial permanente**: los consumos se anulan (`estado=anulado`), no se borran
- ✅ **Validaciones**: Verificación de formato CSV, fechas y habitaciones
- ✅ **Archivos temporales**: Exportaciones no persisten en el servidor
- ⚠️ **Importante**: Los checkouts eliminan registros de forma permanente (backup recomendado)

---

## 🆕 Changelog

### v7.0 (11/2026) - Identidad de Estadías, Pase de Turno y Reinicio de Datos
- ➕ **`id_estadia`**: identidad de estadía para pasajeros y consumos (`core/identidad_estadias.py`)
- ➕ **Bebidas rápidas** con catálogo de productos y **anulación** de consumos conservando el registro
- ➕ **Informe de consumos** (pantalla y XLSX) y **listado de pasajeros alojados**
- ➕ **Pase de turno** y planilla imprimible de pase de caja (`/pase-turno`)
- ➕ **`reiniciar_datos.py`**: reinicio de consumos/pasajeros con simulación, backup y confirmación
- 🐛 **Corregido**: una reserva express mostraba consumos de un huésped anterior de la misma habitación
- 🔧 **Cambio**: totales, checkout, dashboard y cambio de habitación filtran por `id_estadia`; consumos sin ID quedan excluidos con advertencia
- 📝 **Documentado**: [REINICIO_DATOS.md](REINICIO_DATOS.md), [CONSUMOS_INDIVIDUALES_IMPLEMENTADO.md](CONSUMOS_INDIVIDUALES_IMPLEMENTADO.md)

### v6.1 (25/01/2026) - Gestión de Reservas Futuras y UX Mejorado
- ➕ **Herramienta de gestión de reservas futuras** (`gestionar_reservas_futuras.py`)
- ➕ **Textos adaptables en checkout** (singular para 1 hab, masivo para múltiples)
- ➕ **Flujo documentado de reservas** con mejores prácticas hoteleras
- 🔧 **Optimizado**: Eliminación/carga de reservas por fecha con backups automáticos
- 📝 **Documentado**: Ver [FLUJO_RESERVAS_FUTURAS.md](FLUJO_RESERVAS_FUTURAS.md)
- 🎨 **Mejorado**: UX del botón de checkout según cantidad de habitaciones

### v6.0 (23/01/2026) - Checkout Masivo y Selección Inteligente
- ➕ **Checkout masivo de contingentes** con preview y confirmación única
- ➕ **Sistema de titular por edad** (voucher-wide, menores nunca titulares)
- ➕ **Carga dual de CSV** (agregar/reemplazar) para mix walk-ins + contingentes
- ➕ **Fix estadísticas dashboard** (evita conteo doble de habitaciones con doble reserva)
- 🔧 **Optimizado**: Gestión de familias multi-habitación con titular único
- 📝 **Documentado**: Ver [CAMBIOS_TITULAR_POR_EDAD.md](CAMBIOS_TITULAR_POR_EDAD.md)

### v5.0 (10/01/2026) - Sistema Modular Completo
- ➕ **Dashboard de 53 habitaciones** con estados visuales en tiempo real
- ➕ **Detección automática de checkouts** con indicadores rojos pulsantes
- ➕ **Fichas individuales** con información completa del pasajero
- ➕ **CRUD completo de consumos** (agregar, ver, eliminar)
- ➕ **Sistema de checkout** con generación de Excel individual
- ➕ **Checkout consolidado** para múltiples salidas del mismo día
- ➕ **Gestión de archivos CSV** con carga flexible (cualquier nombre)
- ➕ **Backups automáticos** al subir nuevos archivos
- ➕ **Archivos temporales** para todas las exportaciones (sin persistencia)
- 🗑️ **Eliminado**: data/cierres/, templates/formulario.html, carpeta examples/
- 🔧 **Optimizado**: Migracion completa a tempfile para descargas
- 🎨 **Mejorado**: Interfaz Bootstrap 5 con animaciones CSS

### v4.0 (06/01/2026) - Sistema de Consumos Web
- ➕ Aplicación web Flask para registro de consumos
- ➕ Formulario intuitivo con validación de habitaciones
- ➕ 3 categorías: Bebidas, Estadía, Map
- ➕ Generación de reportes Excel (salidas.xlsx)
- ➕ Consulta diaria en CSV con tabla pivote

---

## 📞 Soporte

Para consultas o reportar problemas:
- Crear un issue en el repositorio
- Consultar [INSTALACION_UBUNTU.md](INSTALACION_UBUNTU.md) para troubleshooting
- Revisar [INSTRUCCIONES_TRABAJO.md](INSTRUCCIONES_TRABAJO.md) para deployment

---

## 📄 Licencia

Proyecto privado de uso interno hotelero.

---

**Desarrollado para Hotel 23 de Mayo - 2025/2026**
