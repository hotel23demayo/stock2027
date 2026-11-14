# ARQUITECTURA_APP_v1

Estado: **borrador v1.1 — incorpora las decisiones de §17**. Etapa de diseño: no incluye código, SQL, migraciones ni cambios en Python/HTML.
Parte de [MODELO_LOGICO_v1.md](./MODELO_LOGICO_v1.md) (aprobado). Las entidades se nombran como en ese documento.

> **Vigencia:** este documento describe una arquitectura objetivo, no la aplicación actualmente implementada. Para el estado operativo y sus diferencias con esta propuesta, consultar el [README del proyecto](../README.md).

## 1. Principios

1. **La complejidad está en el sistema, no en el mostrador.** Recepción nunca ve tablas, IDs, movimientos, transacciones ni el origen AUTO/MANUAL.
2. **El comportamiento sale de los datos del rooming y de la clasificación de la reserva**, no de un "modo temporada". `temporada` es solo una etiqueta de reportes; ninguna pantalla ni regla la consulta.
3. **Selección antes que escritura.** Botones grandes, iconos, pocos pasos, lenguaje hotelero.
4. **Nada se borra ni se edita en silencio.** Se anula, se cierra o se ajusta, y queda registrado.
5. **Nunca bloquear una operación real** (p. ej. por stock insuficiente): se advierte y se audita.
6. **Una operación de negocio = una transacción**: o se guarda completa o no se guarda.

## 2. Arquitectura técnica

Stack del legacy, sin cambios de tecnología: Flask, Python, pandas (solo importación/procesamiento de CSV), HTML/CSS/JavaScript, Bootstrap como apoyo visual, SQLite como persistencia interna.

```text
Navegador (HTML/CSS/JS + Bootstrap)
        │  páginas y llamadas JSON simples
        ▼
CAPA WEB (Flask: rutas, sesión, perfil, mensajes en lenguaje hotelero)
        │  solo llama a servicios; no conoce tablas
        ▼
CAPA DE SERVICIOS (reglas de negocio, una operación = una transacción)
  ├─ Importación (pandas)   ├─ Clasificador de reserva   ├─ Reglas de cuenta
  ├─ Alojamiento (estadías) ├─ Consumos                  ├─ Stock (movimientos)
  ├─ Catálogo y precios     ├─ Conteo físico             ├─ Informes
  └─ Auditoría y permisos
        │
        ▼
CAPA DE ACCESO A DATOS (SQLite; único lugar que conoce el esquema)
        │
        ▼
Archivo de base de datos + carpeta de backups + CSV originales importados
```

Reglas de la arquitectura:
- **Las pantallas no hablan con la base:** solo con servicios. El esquema puede cambiar sin tocar la interfaz.
- **El stock solo lo escribe el servicio de Stock**; los consumos lo invocan, nunca insertan movimientos por su cuenta.
- **Un único punto de entrada para auditoría y permisos**: los servicios consultan el perfil y registran la auditoría; no depende de cada pantalla.
- **Vocabulario:** un único catálogo de textos de interfaz traduce estados y acciones internos a lenguaje hotelero.
- **Inicialmente una sola PC**, con un único proceso de la aplicación y un archivo de base; sin servidor de base de datos.
- **Preparada para varios puestos en red local:** la aplicación se publica en la red del hotel y cada puesto la usa desde el navegador (sin instalar nada). Para que eso sea posible desde el inicio: toda la escritura pasa por la capa de servicios (un único escritor de la base, con transacciones cortas), la sesión y los permisos viven en el servidor, y ninguna pantalla depende de archivos locales del puesto. No se expone a internet.
- **Usuario individual por persona**, con inicio de sesión propio; no hay usuarios compartidos por puesto. Toda auditoría identifica a una persona.
- **Lógica sin temporada:** ningún servicio tiene ramas por temporada; las diferencias (cuentas por voucher vs. por persona) las determina `reserva.tipo_reserva`.

## 3. Flujo completo del sistema

```text
CSV rooming
 → IMPORTACIÓN   (lectura, huella del archivo, registro en importacion)
 → VALIDACIÓN    (columnas, fechas, documentos, habitaciones, duplicados, estado O/T)
 → NORMALIZACIÓN (texto sin tildes/mayúsculas, habitación base + cama, voucher, servicios vacíos)
 → CLASIFICACIÓN (Individual / Contingente / No determinado, con confianza y motivo)
 → VISTA PREVIA  (recepción confirma, nada se guardó todavía)
 → CREACIÓN      reserva → pasajeros → estadías (habitación y cama)
 → CUENTAS       reglas de cuenta según tipo de reserva (origen AUTO)
 → OPERACIÓN DIARIA (consumos, cambios de habitación, correcciones de cuenta)
 → CHECKOUT      (cierre de estadías y cuentas)
 → INFORMES      (consumo y stock por período)
```

Puntos de control: no se guarda nada hasta que recepción confirma la vista previa; un archivo con errores graves no se importa; los problemas leves se importan con observaciones.

## 4. Módulos

Convenciones: **R** = Recepción, **A** = Administración, **G** = Gerencia (cada perfil incluye el anterior en lo operativo; ver §7). "Aud." = se audita.

### A. Pantalla principal / Dashboard
- **Objetivo:** responder "¿qué tengo que hacer ahora?" con un vistazo y accesos grandes.
- **Usuario:** R, A, G (contenido según perfil).
- **Muestra:** botones grandes (Registrar consumo, Pasar huésped de habitación, Salida de huéspedes, Cargar rooming); resumen de habitaciones (ocupadas/libres); avisos: "reservas por confirmar", "stock bajo" (A/G), "conteo semanal pendiente" (G).
- **Acciones:** ir a cada operación; buscar huésped o habitación por nombre o número.
- **Sensibles:** ninguna. **Confirmaciones:** ninguna. **Entidades:** habitacion, estadia, pasajero, reserva (lectura); producto y movimiento_stock (avisos). **Aud.:** nada.

### B. Importación de rooming
- **Objetivo:** cargar el archivo recibido del sistema externo.
- **Usuario:** R y A (carga). **Solo A** puede hacer reemplazos/correcciones de una carga existente.
- **Muestra:** zona "Arrastrar archivo aquí", últimas cargas ("Rooming del 11/03 – 47 huéspedes").
- **Acciones:** elegir archivo, "Revisar", ver cargas anteriores; (A) "Corregir o reemplazar esta carga".
- **Sensibles:** reimportar un archivo ya cargado; reemplazar/corregir una carga. **Confirmaciones:** aviso "Este archivo ya fue cargado el…"; los reemplazos siempre pasan por la revisión del módulo C con un resumen de **qué cambia respecto de lo ya cargado**. Nunca se reemplaza nada automáticamente.
- **Entidades:** importacion (escribe el registro de la carga; el contenido pasa por la vista previa del módulo C). **Aud.:** carga de archivo, reimportación, reemplazo/corrección de carga, anulación de carga.

### C. Resultado de validación de importación
- **Objetivo:** mostrar qué se entendió del archivo **antes** de guardar.
- **Usuario:** R.
- **Muestra:** tarjeta resumen ("47 huéspedes, 24 habitaciones, Grupo – confianza alta"); semáforo ✔ correcto / ⚠ observación / ✖ error; lista de observaciones en lenguaje claro ("Habitación 103 → 121: se interpretó como cambio de habitación", "Servicios sin informar en 3 filas"); cuentas que se crearán ("36 cuentas").
- **Acciones:** "Confirmar y cargar", "Cancelar", "Cambiar tipo de reserva" (si es No determinado o recepción discrepa). En un reemplazo (A) muestra además "Qué cambia": huéspedes nuevos, que desaparecen, que cambian de habitación, y cuentas/consumos afectados.
- **Sensibles:** confirmar la carga; cambiar el tipo de reserva sugerido. **Confirmaciones:** resumen final antes de guardar.
- **Entidades:** importacion, reserva, pasajero, estadia, habitacion, cuenta, cuenta_pasajero (se crean al confirmar, en una transacción). **Aud.:** confirmación de carga, cambio manual de tipo de reserva (valor anterior, nuevo y usuario).

### D. Vista de reservas
- **Objetivo:** ver los grupos/operaciones que ingresan.
- **Usuario:** R, A, G.
- **Muestra:** lista con fechas de ingreso/egreso, cantidad de huéspedes, etiqueta "Grupo" o "Individual", aviso "Confirmar tipo de reserva" si es No determinado, estado (por llegar, alojados, finalizada).
- **Acciones:** abrir reserva (ver huéspedes), confirmar tipo de reserva, marcar cancelada.
- **Sensibles:** cambiar tipo de reserva, cancelar reserva. **Confirmaciones:** ambas.
- **Entidades:** reserva, pasajero, importacion. **Aud.:** cambio de tipo, cancelación.

### E. Vista de habitaciones
- **Objetivo:** mapa visual del hotel.
- **Usuario:** R, A, G.
- **Muestra:** grilla por piso con colores (libre, ocupada, ocupada por grupo), nombres abreviados, indicador de cuenta con consumo pendiente.
- **Acciones:** tocar una habitación → ficha; filtrar (ocupadas, libres, por piso).
- **Sensibles / confirmaciones:** ninguna. **Entidades:** habitacion, estadia, pasajero. **Aud.:** nada.

### F. Ficha de habitación
- **Objetivo:** centro operativo de una habitación.
- **Usuario:** R, A, G.
- **Muestra:** quiénes están alojados (cada uno con su cuenta, p. ej. "Cuenta de Silvia Zustovich"), consumos recientes por cuenta, historial de ocupantes de la habitación.
- **Acciones:** Registrar consumo (preselecciona habitación), Pasar huésped de habitación, Ver ficha del huésped.
- **Sensibles:** las de sus subflujos. **Entidades:** habitacion, estadia, pasajero, cuenta, consumo. **Aud.:** nada propio.

### G. Ficha de pasajero
- **Objetivo:** ver todo de una persona.
- **Usuario:** R, A, G.
- **Muestra:** datos básicos (nombre, edad, documento), habitación actual y anteriores ("Estuvo en 350 hasta el 29/09"), a qué cuenta pertenece y con quién la comparte, consumos.
- **Acciones:** Registrar consumo, Pasar de habitación, Corregir cuenta, Ver cuenta.
- **Sensibles:** Corregir cuenta. **Entidades:** pasajero, reserva, estadia, cuenta_pasajero, cuenta, consumo. **Aud.:** las de sus subflujos.

### H. Gestión de cuentas
- **Objetivo:** ver y corregir quién comparte cuenta, y el detalle de lo consumido.
- **Usuario:** R (ver y corregir), A/G (idem).
- **Muestra:** cuenta con sus personas y consumos por día y total; avisos de cuentas con situación a revisar.
- **Acciones:** ver detalle e imprimir; **"Corregir cuenta"**: "Mover a otra cuenta", "Unir con…", "Separar de…" mediante selección de personas (sin teclear códigos).
- **Sensibles:** mover/unir/separar (afecta cómo se cobra). **Confirmaciones:** vista previa "Antes / Después" y botón "Confirmar corrección". Los consumos ya cargados **no cambian de dueño** salvo decisión explícita para consumos futuros.
- **Entidades:** cuenta, cuenta_pasajero, pasajero, consumo (lectura). **Aud.:** toda corrección (quién, antes, después, motivo); origen pasa a MANUAL.

### I. Registro de consumos
- **Objetivo:** cargar lo que consumió un huésped, rápido y sin errores.
- **Usuario:** R, A, G.
- **Muestra:** flujo en 4 toques: 🛏️ Habitación → 👤 Huésped → producto (botones grandes con icono, agrupados por categoría) → cantidad (botones − / + , valor 1 por defecto) → ✅ Registrar consumo. Resumen "2 × Cerveza = $11.000 a la cuenta de Leonardo Brondino".
- **Acciones:** registrar consumo; **"Deshacer"** el propio consumo durante 5 minutos (R, A, G); "Anular consumo" posterior (A/G) con motivo.
- **Sensibles:** deshacer/anular consumo; cantidades altas (umbral configurable). **Confirmaciones:** deshacer y anular con confirmación (la anulación posterior, con motivo); aviso suave ante cantidad inusual.
- **Entidades:** consumo, cuenta, pasajero, estadia (abierta del pasajero), producto, precio_producto, movimiento_stock (lo genera el servicio, invisible). **Aud.:** deshacer (indicando que fue dentro de la ventana de 5 minutos), anulación posterior, consumo con stock negativo (advertencia registrada). Nada se elimina físicamente.
- **Comportamientos:** el huésped aparece con su cuenta ya resuelta; si la habitación tiene varias cuentas, se elige a quién cargar; si hay stock insuficiente se muestra "⚠ Stock bajo, se registró igual" y se continúa.

### J. Cambio de habitación
- **Objetivo:** pasar a un huésped (o a varios) a otra habitación.
- **Usuario:** R, A, G.
- **Muestra:** 1) elegir huésped(es) (por defecto, todos los de la habitación), 2) elegir habitación destino en el mapa (libres resaltadas, ocupadas con aviso), 3) resumen "Juan pasa de 350 a 420. Su cuenta y consumos se mantienen".
- **Acciones:** Pasar huésped de habitación; elegir parcial (solo algunos).
- **Sensibles:** el cambio en sí. **Confirmaciones:** pantalla de resumen con "Confirmar cambio".
- **Entidades:** estadia (cierra y abre), pasajero, habitacion; **no toca** cuenta, cuenta_pasajero ni consumo. **Aud.:** cada cambio (huésped, origen, destino, fecha/hora).

### K. Checkout
- **Objetivo:** cerrar estadía y cuenta, entregar el detalle.
- **Usuario:** R, A, G.
- **Muestra:** por habitación o por cuenta: cuentas a cerrar con total y detalle; huéspedes incluidos; aviso si una cuenta compartida tiene personas que siguen alojadas. Modo **"Salida del grupo"** para cerrar muchas cuentas a la vez.
- **Acciones:** cerrar cuenta (imprimir/exportar detalle), cerrar habitación completa, salida masiva de un grupo.
- **Sensibles:** cierre de cuentas (no se reabren sin acción registrada), salida masiva. **Confirmaciones:** resumen con totales y "Confirmar salida"; la salida masiva lista todas las cuentas antes de ejecutar.
- **Entidades:** cuenta, estadia, pasajero, reserva (pasa a finalizada al salir el último), consumo (lectura). **Aud.:** cierre de cuenta, salida masiva, reapertura (solo G).

### L. Catálogo de productos
- **Objetivo:** mantener qué se vende y a qué precio.
- **Usuario:** A, G.
- **Muestra:** lista visual por categoría (icono, nombre, precio vigente, activo), solo bebidas y fichas en v1.
- **Acciones:** **Agregar producto**, **Cambiar precio** (el historial no se modifica), **Desactivar/Activar**, ordenar botones.
- **Sensibles:** cambiar precio, desactivar producto. **Confirmaciones:** "Cambiar precio de Cerveza: $5.500 → $6.000, vale desde ahora" con confirmación.
- **Entidades:** producto, categoria_producto, precio_producto. **Aud.:** alta de producto, cambio de precio (antes/después), desactivación.

### M. Stock
- **Objetivo:** saber cuánto hay y registrar lo que entra o se pierde.
- **Usuario:** A, G.
- **Muestra:** semáforo por producto (suficiente / bajo / sin stock / negativo a revisar), "unidades disponibles", últimos movimientos en lenguaje claro ("Recibí 24 – 02/10", "Consumo habitación 350 – 2").
- **Acciones:** **"Recibí mercadería"** (ingreso), **"Se rompió"** (rotura), **"Se venció"** (vencimiento, activo operativamente en segunda etapa si se usan lotes); ver historial.
- **Sensibles:** rotura, vencimiento, ingreso con cantidades grandes. **Confirmaciones:** resumen y motivo obligatorio para rotura/vencimiento.
- **Entidades:** producto, movimiento_stock, lote (preparado, no obligatorio). **Aud.:** ingresos, roturas, vencimientos, advertencias por stock negativo.

### N. Conteo físico
- **Objetivo:** comparar lo contado con lo teórico y ajustar con trazabilidad.
- **Usuario:** G.
- **Muestra:** lista de productos con campo "¿Cuántas unidades contaste?"; la cantidad esperada **no** se muestra hasta cargar el conteo (conteo ciego); luego una pantalla de diferencias.
- **Acciones:** iniciar conteo semanal o extraordinario (motivo), guardar borrador, **"Confirmar conteo"** (genera los ajustes), cancelar.
- **Sensibles:** confirmar conteo. **Confirmaciones:** "Se detectaron diferencias en 3 productos. ¿Confirmar ajustes?" con detalle.
- **Entidades:** conteo_fisico, conteo_fisico_detalle, movimiento_stock (AJUSTE), producto. **Aud.:** inicio, confirmación, cancelación y cada ajuste generado.

### O. Informes
- **Objetivo:** consumo y stock por período para gerencia.
- **Usuario:** A, G.
- **Muestra:** selector de período (hoy, semana, mes, rango); informes: consumo por producto y categoría (más vendidos), consumo por tipo de reserva, por habitación, por cuenta o pasajero, roturas, vencimientos, diferencias de inventario, stock actual vs. mínimo.
- **Acciones:** filtrar por **tipo de reserva, producto, categoría, pasajero, habitación, cuenta**; exportar (planilla/PDF).
- **Sensibles:** exportar datos de pasajeros. **Confirmaciones:** ninguna. **Entidades:** consumo, movimiento_stock, producto, categoria_producto, cuenta, pasajero, estadia, habitacion, reserva (lectura). **Aud.:** exportación de informes.

### P. Auditoría
- **Objetivo:** reconstruir quién hizo qué y cuándo.
- **Usuario:** G.
- **Muestra:** lista cronológica en lenguaje claro ("María anuló 1 Cerveza de la cuenta Brondino – motivo: error de carga"), filtros por fecha, usuario y tipo de operación.
- **Acciones:** buscar, filtrar, exportar. Solo lectura.
- **Entidades:** auditoria (lectura). **Aud.:** exportación de auditoría.

### Q. Administración de usuarios
- **Objetivo:** gestionar quién accede y con qué perfil.
- **Usuario:** G.
- **Muestra:** lista de personas con perfil y estado (activo/inactivo).
- **Acciones:** crear usuario, asignar perfil, restablecer clave, desactivar.
- **Sensibles:** cambiar perfil, desactivar, restablecer clave. **Confirmaciones:** todas.
- **Entidades:** usuario. **Aud.:** alta, cambio de perfil, desactivación, restablecimiento.

## 5. Navegación para recepción

Pensada para quien está detrás del mostrador: **cuatro botones grandes, tres toques para la operación más frecuente**.

```text
┌─────────────────────────────────────────────┐
│  🏨 Hotel 23 de Mayo        👤 María (Recepción) │
├─────────────────────────────────────────────┤
│  [ 🍺 Registrar consumo ]  [ 🛏️ Pasar huésped │
│                               de habitación ] │
│  [ 🚪 Salida de huéspedes ] [ 📥 Cargar rooming]│
│                                              │
│  🔍 Buscar huésped o habitación...            │
│                                              │
│  Habitaciones (mapa por piso)                │
└─────────────────────────────────────────────┘
```

Reglas de navegación:
- **Menú inferior fijo de 4 ítems:** Inicio · Habitaciones · Huéspedes · Más. Administración y Gerencia ven ítems adicionales ("Productos", "Stock", "Informes", "Auditoría", "Usuarios") que **no existen** para Recepción (no se muestran deshabilitados).
- **Siempre un botón "Volver" y "Inicio"**; nunca más de 3 niveles de profundidad.
- **Búsqueda global** arriba: escribir "350" o "Bron…" lleva a la ficha.
- **Camino más corto al consumo:** Inicio → Registrar consumo → toca la habitación (o busca al huésped) → producto → cantidad → ✅. Desde la ficha de habitación se salta el primer paso.
- **Mensajes:** "✅ Listo: 2 × Cerveza a la cuenta de Leonardo Brondino", con botón "Deshacer" visible durante 5 minutos, solo para quien registró el consumo. Pasado ese tiempo, se pide a Administración.
- **Tamaños:** botones táctiles grandes, texto legible, colores consistentes (verde = confirmar, rojo = anular/peligro, amarillo = aviso).

## 6. Mapa de pantallas

```text
Inicio (A)
├── Cargar rooming (B) → Revisión de la carga (C) → Reservas (D)
├── Reservas (D) → Detalle de reserva
├── Habitaciones (E) → Ficha de habitación (F)
│                         ├── Registrar consumo (I)
│                         ├── Pasar huésped de habitación (J)
│                         └── Ficha de huésped (G) → Cuenta (H) → Corregir cuenta
├── Huéspedes (búsqueda) → Ficha de huésped (G)
├── Registrar consumo (I)
├── Salida de huéspedes (K)
└── Más
    ├── Productos (L)          [A/G]
    ├── Stock (M)              [A/G]
    ├── Conteo físico (N)      [G]
    ├── Informes (O)           [A/G]
    ├── Auditoría (P)          [G]
    └── Usuarios (Q)           [G]
```

## 7. Mapa de navegación (flujos entre pantallas)

```text
Inicio ──► Registrar consumo ──► Habitación/Huésped ──► Producto ──► Cantidad ──► Confirmación
Inicio ──► Habitaciones ──► Ficha habitación ──► (Consumo | Cambio | Huésped)
Inicio ──► Cargar rooming ──► Revisión ──► Confirmar ──► Reservas
Inicio ──► Salida ──► Elegir habitación/cuenta/grupo ──► Resumen ──► Confirmar ──► Detalle imprimible
Más ──► Stock ──► (Recibí | Se rompió | Se venció) ──► Resumen ──► Confirmar
Más ──► Conteo ──► Contar ──► Diferencias ──► Confirmar ajustes
```

## 8. Flujos detallados

### 8.1 Importación
1. Recepción elige o arrastra el archivo.
2. El sistema calcula la huella; si ya existe, avisa y ofrece cancelar.
3. **Validación:** columnas esperadas, fechas, documentos, habitaciones inexistentes, estado O/T, servicios vacíos, plazas inconsistentes (se ignoran).
4. **Normalización:** texto sin tildes y en mayúsculas, habitación base + cama (`227 A`), un pasajero por documento + reserva, T/O interpretado como cambio de habitación.
5. **Clasificación** por paquete y transporte (peso muy alto), confirmada por servicios, tipo de habitación, estructura de vouchers; resultado Individual / Contingente / No determinado, con confianza y motivo.
6. **Vista previa** (módulo C): resumen y observaciones; nada se guardó.
7. **Confirmar:** en una transacción se crean reserva(s), pasajeros, estadías, habitaciones nuevas si faltan, y cuentas por regla.
8. Si falla algo: se revierte todo y se muestra "No se pudo cargar el archivo, no se guardó nada".
9. **Regla general:** toda importación sigue **cargar → validar → mostrar resumen → confirmar**. Ningún dato existente se reemplaza o modifica sin ese resumen y una confirmación explícita.
10. **Reemplazo/corrección (solo Administración):** se carga el archivo corregido, se valida, y el resumen muestra la diferencia contra lo ya cargado. Al confirmar, se aplica en una transacción con backup previo. Los consumos existentes no se pierden: los huéspedes con consumos nunca se eliminan, y las diferencias que los afecten se informan para decisión manual.
11. Si es No determinado: la reserva queda "Por confirmar" y **no crea cuentas** hasta que recepción defina el tipo; se avisa en el Inicio.

### 8.2 Cuentas
1. **Individual:** mismo voucher ⇒ misma cuenta (incluye DOBLE INDIVIDUALES y varias habitaciones).
2. **Contingente:** pareja con voucher común **y** habitación base común ⇒ cuenta compartida; resto ⇒ una cuenta por pasajero, aunque compartan habitación.
3. Las cuentas se crean al importar (origen AUTO); la persona nunca ve la regla, solo "Cuenta de X" o "Cuenta familiar".
4. **Corregir cuenta:** elegir personas → elegir acción (mover, unir, separar) → ver Antes/Después → confirmar → queda auditado y el origen pasa a MANUAL (interno).
5. Un cambio de habitación no cambia cuentas. Un pasajero solo tiene una cuenta vigente.
6. Una corrección manual de tipo de reserva prevalece ante reimportaciones.

### 8.3 Consumos
1. Elegir habitación o huésped → el sistema resuelve la cuenta del pasajero y su estadía abierta.
2. Elegir producto → cantidad (≥ 1) → confirmar.
3. **En una transacción:** se crea el consumo con el precio vigente copiado; si el producto controla stock, se crea el movimiento de consumo; se valida que la cuenta esté abierta y el pasajero alojado.
4. Stock insuficiente: se registra igual y se muestra una advertencia; queda auditado.
5. **Deshacer** (quien lo registró, dentro de 5 minutos): confirmación simple; se marca anulado y se revierte el stock con un movimiento de anulación. Auditado, sin borrado físico.
5b. **Anulación posterior** (A/G): motivo + confirmación. Gerencia puede revisar y, según corresponda, autorizar las anulaciones (p. ej. importes altos o reiteradas); la anulación queda marcada "pendiente de revisión" hasta que Gerencia la revisa.
6. Los consumos no se editan ni se borran.

### 8.4 Cambio de habitación
1. Elegir huésped(es) → elegir destino → resumen → confirmar.
2. El servicio cierra la estadía abierta y abre una nueva, encadenada a la anterior.
3. **No** se modifican cuentas, pertenencias ni consumos previos.
4. Cambio parcial: solo se mueve a quienes se eligen.
5. Aviso (no bloqueo) si la habitación destino está ocupada o es inconsistente con el tipo reservado.
6. Se audita huésped, origen, destino y momento.

### 8.5 Checkout
1. Elegir habitación, cuenta o "Salida de grupo".
2. El sistema lista las cuentas afectadas con totales; avisa si alguien de una cuenta compartida sigue alojado.
3. Confirmar → en una transacción: se cierran las estadías abiertas, las cuentas pasan a cerradas, y la reserva finaliza cuando sale el último pasajero.
4. Se entrega el detalle imprimible por cuenta.
5. Después del cierre no se permiten consumos; reabrir una cuenta requiere perfil Gerencia y queda auditado.

### 8.6 Stock
1. **Ingreso:** "Recibí mercadería" → producto → cantidad → (remito opcional) → confirmar.
2. **Consumo:** automático desde el registro de consumos; el usuario no interviene.
3. **Rotura / vencimiento:** producto → cantidad → motivo → confirmar.
4. **Conteo semanal:** el conteo ciego produce diferencias; al confirmar se generan ajustes con referencia al conteo. Los conteos extraordinarios requieren motivo.
5. **Stock negativo:** permitido; se muestra "A revisar" en Stock y se incluye en el aviso del Inicio.
6. El stock mostrado siempre es el resultado de sumar movimientos; ninguna pantalla permite escribir un saldo.
7. **Lotes y vencimientos:** la estructura existe pero no se pide a recepción; en la segunda etapa se activa con un ajuste de configuración (Gerencia) y se exige lote solo en ingresos.

## 9. Permisos por perfil

| Capacidad | Recepción | Administración | Gerencia |
|---|:-:|:-:|:-:|
| Dashboard, habitaciones, fichas | ✔ | ✔ | ✔ |
| Cargar rooming | ✔ | ✔ | ✔ |
| Reemplazar / corregir una carga de rooming | | ✔ | ✔ |
| Reservas (ver); confirmar tipo de reserva | ✔ | ✔ | ✔ |
| Cambio de habitación | ✔ | ✔ | ✔ |
| Registrar consumo | ✔ | ✔ | ✔ |
| Corregir cuenta | ✔ | ✔ | ✔ |
| Checkout | ✔ | ✔ | ✔ |
| Deshacer el propio consumo (5 min) | ✔ | ✔ | ✔ |
| Anular consumo posterior | | ✔ | ✔ |
| Revisar/autorizar anulaciones | | | ✔ |
| Catálogo y cambio de precio | | ✔ | ✔ |
| Stock (ingreso, rotura, vencimiento) | | ✔ | ✔ |
| Informes | | ✔ | ✔ |
| Conteo físico | | | ✔ |
| Reabrir cuenta cerrada | | | ✔ |
| Auditoría | | | ✔ |
| Usuarios y configuración sensible | | | ✔ |

Los permisos se aplican en la capa de servicios (no solo ocultando botones). Cada perfil ve únicamente su menú.

## 10. Puntos donde el sistema pide confirmación

| Operación | Tipo de confirmación |
|---|---|
| Confirmar carga de rooming | Resumen de la vista previa |
| Reimportar un archivo ya cargado | Aviso explícito |
| Cambiar tipo de reserva | Antes/Después |
| Cancelar reserva | Diálogo |
| Corregir cuenta (mover/unir/separar) | Antes/Después |
| Cambio de habitación | Resumen |
| Deshacer consumo (5 min) | Diálogo simple |
| Anular consumo posterior | Motivo + diálogo |
| Reemplazar/corregir carga de rooming | Resumen de diferencias |
| Cierre de cuenta / checkout / salida de grupo | Resumen con totales |
| Cambio de precio | Antes/Después |
| Desactivar producto | Diálogo |
| Rotura, vencimiento | Motivo + resumen |
| Confirmar conteo físico | Lista de diferencias |
| Reabrir cuenta | Diálogo + motivo |
| Cambios en usuarios | Diálogo |

Operaciones frecuentes y reversibles (registrar consumo) **no** piden diálogo previo: ofrecen "Deshacer" posterior.

## 11. Puntos donde se genera auditoría

Cada registro guarda quién, cuándo, qué operación, sobre qué elemento, valor anterior y nuevo, y motivo si corresponde.

- Carga de rooming, reimportación, reemplazo/corrección de carga, anulación de carga.
- Cambio de tipo de reserva, cancelación de reserva.
- Corrección de cuenta (mover, unir, separar), reapertura de cuenta.
- Cambio de habitación.
- Deshacer y anulación de consumo (con revisión de Gerencia cuando corresponda); consumos que dejan stock negativo.
- Alta de producto, cambio de precio, desactivación.
- Ingreso, rotura, vencimiento de stock; conteo (inicio, confirmación, cancelación) y ajustes.
- Cierre de cuenta, salida masiva.
- Altas, cambios de perfil y desactivación de usuarios; restablecimiento de clave.
- Exportación de informes y de auditoría; inicio de sesión fallido repetido.

El consumo común se guarda con usuario y fecha en su propia tabla; no requiere duplicarse en auditoría.

## 12. Recuperación ante errores

- **Transacciones:** toda operación compuesta (importar, registrar consumo, cambio de habitación, checkout, confirmar conteo) se guarda entera o no se guarda. El usuario ve "No se pudo guardar, intentá nuevamente. No se cambió nada".
- **Doble clic / reenvío:** cada operación lleva una marca de intención única para evitar duplicar un consumo por doble toque o por recargar la página.
- **Deshacer:** consumo propio dentro de 5 minutos → anulación guiada; luego, vía Administración; cambio de habitación → "Volver a pasar" (nuevo cambio, que queda también en el historial); corrección de cuenta → corregir de nuevo (historial íntegro).
- **Importación errónea:** una carga puede **anularse completa** mientras no tenga consumos; si ya hay consumos, se anula solo lo que no los tiene y se avisa a Gerencia.
- **Fallo del programa:** al reiniciar, la base queda consistente (SQLite con registro de transacciones activado); se muestra "Se recuperó el sistema" y se verifica la integridad.
- **Base dañada:** el sistema detecta el problema al iniciar, avisa a Gerencia y ofrece restaurar el último backup válido, informando qué período de operaciones se perdería.
- **Errores de datos externos:** el CSV malformado se rechaza con mensaje claro y el archivo original queda guardado para análisis.
- **Mensajes:** siempre en lenguaje hotelero, con una sola acción sugerida; el detalle técnico va a un registro interno que solo ve soporte.

## 13. Backup

- **Dos niveles:** copia **local automática** y **destino externo configurable**. El destino externo (USB, carpeta de red, nube u otra PC) **no se fija en este diseño**: Gerencia lo define en "Configuración", y el sistema solo conoce "una carpeta de destino" más su estado.
- **Local automático:** al cerrar la jornada, y antes y después de operaciones masivas (importación o reemplazo de rooming, salida de grupo, confirmación de conteo). Además, copia diaria programada. Se conservan las últimas 30 diarias y las de cierre semanal.
- **Externo configurable:** cada copia local se replica al destino configurado. Si el destino no está disponible, la copia local igualmente se hace, se reintenta y se avisa a Gerencia ("La copia externa está pendiente desde…"). Sin destino configurado, el sistema lo señala como advertencia permanente.
- **CSV originales** de cada importación se guardan con su huella y se incluyen en el respaldo.
- **Verificación:** cada copia se comprueba al crearse; el Inicio de Gerencia muestra "Última copia local correcta" y "Última copia externa correcta", con aviso si pasan más de 24 h.
- **Restauración:** solo Gerencia, con confirmación; antes de restaurar se hace una copia del estado actual. Se recomienda una prueba periódica de restauración.
- **Exportación legible:** Gerencia puede exportar consumos y movimientos a planilla como respaldo adicional.
- **Varios puestos:** el backup lo ejecuta el servidor de la aplicación, no cada puesto.

## 14. Datos y migración desde el legacy

- El legacy (`consumos_diarios.csv`, `pasajeros.csv`) **no se migra automáticamente** a v1; se conserva como histórico consultable en la carpeta [legacy/](../legacy).
- Si Gerencia lo pide, el histórico de consumos puede importarse más adelante como consumos de una reserva "histórica", sin afectar el stock (sin movimientos).
- Productos iniciales: se cargan desde el catálogo real del hotel (comanda 350: bebidas y fichas); presentación y stock inicial se completan con el primer conteo.

## 15. Estructura propuesta del proyecto (a nivel de carpetas)

```text
stock2027/
├── legacy/        referencia histórica, solo lectura
├── docs/          documentación de diseño
├── app/           capa web (rutas y pantallas)
├── servicios/     reglas de negocio (importación, clasificador, cuentas, consumos, stock, informes...)
├── datos/         acceso a datos y esquema
├── plantillas/    pantallas HTML
├── estaticos/     CSS, JS, imágenes
├── backups/       copias de la base (fuera del control de versiones)
└── importaciones/ CSV originales (fuera del control de versiones)
```

## 16. Alcance

### Dentro de v1
- Todos los módulos A–Q con las capacidades descritas.
- Importación con validación, vista previa, clasificación y reglas de cuenta.
- Consumos con movimiento de stock automático; stock negativo con advertencia.
- Cambio de habitación (total y parcial); checkout individual y masivo.
- Catálogo de bebidas y fichas, precios históricos.
- Stock por movimientos: ingreso, rotura, vencimiento (sin lote obligatorio), ajuste por conteo, anulación.
- Conteo semanal y extraordinario.
- Informes por período con filtros por tipo de reserva, producto, categoría, pasajero, habitación y cuenta.
- Tres perfiles con permisos, confirmaciones y auditoría; usuario individual por persona.
- Reemplazo/corrección de cargas de rooming por Administración, siempre con resumen y confirmación.
- Funcionamiento en una PC, preparado para varios puestos por red local.
- Backups automáticos y recuperación.
- Funcionamiento idéntico en cualquier época del año, sin "modo temporada".

### Fuera de v1 (explícito)
- Uso operativo de lotes y vencimientos (modelo preparado; activación en segunda etapa).
- Control de stock del comedor (el modelo lo admite).
- Facturación fiscal y medios de pago/cobranza.
- Integración directa con el sistema externo de reservas (solo CSV).
- App móvil nativa y modo sin conexión.
- Reservas futuras con calendario de disponibilidad y asignación automática de habitaciones.
- Gestión de proveedores, órdenes de compra y reposición automática.
- Pronósticos y paneles analíticos avanzados.
- Migración automática del histórico del legacy.
- Multi-hotel, multi-sede o acceso desde internet (el uso en red local queda preparado, pero su puesta en marcha multipuesto se confirma aparte).
- Elección concreta del destino externo de backup (solo queda configurable).
- Temporada como regla de negocio (solo etiqueta opcional de informes).

## 17. Decisiones aprobadas

1. **Carga de rooming:** Recepción y Administración. Administración además realiza reemplazos/correcciones.
2. **Deshacer consumos:** Recepción puede deshacer sus propios consumos durante 5 minutos; queda auditado y no se elimina físicamente. Administración realiza anulaciones posteriores; Gerencia puede revisar/autorizarlas según corresponda.
3. **Backups:** automático local + destino externo configurable, sin fijar USB, nube ni PC.
4. **Infraestructura:** inicialmente una PC, preparada para varios puestos por red local.
5. **Usuarios:** individual por persona; perfiles Recepción, Administración y Gerencia.
6. **Importación:** siempre cargar → validar → mostrar resumen → confirmar; nunca se reemplazan datos sin confirmación.

## 18. Impacto en el modelo lógico (a aplicar si se aprueba)

Cambios menores, sin alterar el diseño aprobado:

| Tabla | Ajuste |
|---|---|
| `importacion` | Estado adicional `REEMPLAZADA` y referencia opcional a la carga que reemplaza (`importacion_reemplazada_id`) |
| `consumo` | Marca de `anulacion_en_ventana` (deshacer dentro de 5 minutos) y estado de revisión de la anulación (`SIN_REVISION`, `PENDIENTE`, `REVISADA`) con quién revisó y cuándo |
| `usuario` | Credencial propia (almacenada de forma segura), último acceso; un usuario por persona |
| `configuracion` (nueva) | Destino externo de backup, ventana de deshacer (5 min), umbrales de aviso; modificable solo por Gerencia |
| `backup_registro` (nueva) | Fecha, tipo (diaria/previa a operación), resultado local y externo |

## 19. Preguntas abiertas

1. **Autorización de Gerencia:** ¿qué anulaciones requieren su revisión: todas, las de importe alto (¿desde qué monto?) o las reiteradas? Propuesta: todas quedan visibles en Auditoría y Gerencia autoriza solo las que superen un umbral que ella misma configure.
2. **Reemplazo de carga con consumos:** ¿cuando el archivo corregido elimina a un huésped que ya tiene consumos, se conserva siempre al huésped y se avisa (propuesto), o se necesita otro tratamiento?
3. **Varios puestos:** ¿la PC principal quedará encendida durante toda la operación del hotel (actuando como servidor de la red local)?
