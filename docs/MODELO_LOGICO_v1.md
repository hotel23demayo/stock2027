# Modelo lógico v1 — Control de stock y consumos

Estado: **APROBADO con ajustes (ver §11)**. Sin SQL, Python, HTML ni migraciones.
Base: [ANALISIS_MATRIZ_RESERVA_Y_CUENTAS.md](./ANALISIS_MATRIZ_RESERVA_Y_CUENTAS.md) y [MODELO_DATOS_CONCEPTUAL_v1.md](./MODELO_DATOS_CONCEPTUAL_v1.md).

> **Vigencia:** “aprobado” se refiere al diseño lógico propuesto; no significa que ese esquema SQLite esté implementado. Para el comportamiento del sistema actual, consultar el [README del proyecto](../README.md).

## 0. Decisiones de partida

1. Persistencia interna en **SQLite**, invisible para el usuario. El CSV de rooming es solo entrada de importación.
2. Web App guiada para recepción; todo el modelo es interno.
3. Stock v1: **bebidas y fichas de café**. El modelo admite comedor más adelante (ver `producto.controla_stock`).
4. El stock **nunca** es un saldo editable: es la suma de `movimiento_stock`.
5. Precios modificables sin alterar el historial.
6. La temporada no gobierna la lógica; es solo un dato de contexto.

## 1. Flujo y origen de los datos

```text
CSV rooming → importación → normalización → clasificador → reserva / pasajero / estadía
   → reglas de cuenta → cuenta / cuenta_pasajero → consumo → movimiento_stock → informes
```

## 2. Diagrama de relaciones

```text
importacion 1──* reserva 1──* pasajero 1──* estadia *──1 habitacion
                                │
                                *
cuenta 1──* cuenta_pasajero *───┘
  │
  1
  *
consumo *──1 pasajero          consumo *──1 estadia
  │  *──1 producto 1──* precio_producto
  │
  1
  1..*
movimiento_stock *──1 producto
        *──0..1 lote *──1 producto
        *──0..1 conteo_fisico_detalle *──1 conteo_fisico
```

## 3. Tablas

Convenciones: PK = clave primaria; FK = clave foránea; **CSV** = dato que viene del rooming; **APP** = lo genera la aplicación. Todas las tablas llevan `creado_en` (APP); las editables, también `modificado_en` y `modificado_por`. Las claves son identificadores internos, nunca visibles.

### 3.1 `importacion` — cada carga de un CSV de rooming
| Campo | Origen | Notas |
|---|---|---|
| importacion_id (PK) | APP | |
| nombre_archivo | APP | |
| huella_archivo | APP | Hash para detectar recarga del mismo archivo |
| fecha_carga, usuario | APP | |
| filas_leidas, filas_aceptadas, filas_observadas | APP | Resumen para mostrar a recepción |
| estado | APP | `PROCESADA`, `CON_OBSERVACIONES`, `ANULADA` |

### 3.2 `reserva` — grupo de reserva del rooming
| Campo | Origen | Notas |
|---|---|---|
| reserva_id (PK) | APP | |
| importacion_id (FK → importacion) | APP | |
| referencia | APP | Identificador legible de la operación/grupo importado |
| sede, entidad | CSV | Informativos |
| codigo_alojamiento | CSV | `900`, `900 B` |
| servicios, paquete, transporte | CSV | Texto normalizado (mayúsculas, sin tildes); servicios puede venir vacío |
| fecha_ingreso, fecha_egreso | CSV | |
| tipo_reserva | APP | `INDIVIDUAL`, `CONTINGENTE`, `NO_DETERMINADO` |
| confianza_clasificacion | APP | `ALTA`, `MEDIA`, `BAJA` |
| motivo_clasificacion | APP | Texto: señales que decidieron |
| tipo_reserva_origen | APP | `AUTO` / `MANUAL` |
| estado | APP | ver §6 |
| temporada | APP | Etiqueta opcional para reportes; **no participa de ninguna regla** |

La reserva representa la **operación/grupo que ingresa al hotel**. En contingente **no se agrupa por voucher**: el voucher pertenece al pasajero y participa en la determinación de la cuenta.

### 3.3 `pasajero`
| Campo | Origen | Notas |
|---|---|---|
| pasajero_id (PK) | APP | |
| reserva_id (FK → reserva) | APP | |
| voucher | CSV | Voucher propio del pasajero (base de la regla de cuenta) |
| tipo_documento, nro_documento | CSV | |
| apellido_nombre | CSV | Se normaliza para búsqueda; se conserva el original |
| edad, fecha_nacimiento | CSV | Menores permitidos |
| estado_rooming | CSV | `O` vigente, `T` trasladado (ver §9) |
| es_titular | APP | Marcado por reglas/recepción para pantalla |
| estado | APP | ver §6 |

Unicidad: (nro_documento, reserva_id).

### 3.4 `habitacion` — catálogo físico del hotel
| Campo | Origen | Notas |
|---|---|---|
| habitacion_id (PK) | APP | |
| numero | CSV/APP | Número base (`227`), único |
| piso, tipo_habitacion, capacidad | APP | Capacidad del catálogo; **no** se confía en `Cantidad plazas` del CSV |
| activa | APP | |

La cama (`A`/`B`) no es una habitación; se guarda en `estadia.cama`. Las habitaciones desconocidas se dan de alta al importar, con observación.

### 3.5 `estadia` — dónde duerme un pasajero y desde/hasta cuándo
| Campo | Origen | Notas |
|---|---|---|
| estadia_id (PK) | APP | |
| pasajero_id (FK → pasajero) | APP | |
| habitacion_id (FK → habitacion) | APP | |
| cama | CSV | `A`, `B` o vacío |
| tipo_habitacion_reserva | CSV | Tipo reservado (`DOBLE A COMPARTIR`…) |
| desde, hasta | CSV/APP | `hasta` vacío = abierta |
| motivo_inicio | APP | `INGRESO`, `CAMBIO_HABITACION`, `IMPORTACION` |
| motivo_cierre | APP | `CAMBIO_HABITACION`, `CHECKOUT`, `CANCELACION` |
| estadia_anterior_id (FK → estadia, opcional) | APP | Encadena los cambios |

### 3.6 `cuenta`
| Campo | Origen | Notas |
|---|---|---|
| cuenta_id (PK) | APP | |
| codigo_visible | APP | Referencia legible tipo `C-30243135`; uso interno/impresión |
| reserva_id (FK → reserva) | APP | Reserva que originó la cuenta |
| criterio | APP | `VOUCHER`, `VOUCHER_Y_HABITACION` (pareja en contingente), `PASAJERO` |
| origen | APP | `AUTO` / `MANUAL` |
| estado | APP | `ABIERTA`, `CERRADA` |
| cerrada_en | APP | |

### 3.7 `cuenta_pasajero` — pertenencia de pasajeros a cuentas
| Campo | Origen | Notas |
|---|---|---|
| cuenta_id (FK → cuenta) | APP | PK compuesta |
| pasajero_id (FK → pasajero) | APP | PK compuesta |
| vigente_desde | APP | PK compuesta |
| vigente_hasta | APP | Vacío = vigente |
| origen | APP | `AUTO` / `MANUAL` |

Permite que recepción corrija una cuenta sin perder qué se propuso antes.

### 3.8 `categoria_producto`
`categoria_id` (PK), `nombre` (Gaseosa, Agua, Saborizada, Cerveza, Vino, Ficha de café y, a futuro, Comedor), `ambito` (`BEBIDAS`, `FICHAS`, `COMEDOR`), `orden`, `activa`.

### 3.9 `producto` — un artículo comercial concreto
| Campo | Notas |
|---|---|
| producto_id (PK) | |
| categoria_id (FK → categoria_producto) | |
| codigo | Código interno estable (equivale al código de `BEBIDAS_CATALOGO`) |
| nombre | `Gaseosa Cola`, `Gaseosa Lima-Limón`, `Cerveza`, `Vino Nampe Malbec`, `Ficha de café` |
| presentacion | Texto: botella individual, lata… (a definir con compras) |
| unidad_stock | `UNIDAD` (v1) |
| icono, orden | Para la pantalla de botones |
| controla_stock | Verdadero para bebidas y fichas; falso para comedor (futuro) |
| controla_vencimiento | Verdadero para productos con fecha |
| stock_minimo | Umbral de alerta |
| activo | No se borran productos; se desactivan |

Nunca una categoría genérica como producto ("Bebidas").

### 3.10 `precio_producto` — historial de precios
`precio_id` (PK), `producto_id` (FK), `precio`, `vigente_desde`, `vigente_hasta` (vacío = vigente), `usuario`. Un producto tiene como máximo un precio vigente. Cambiar un precio cierra el anterior y abre uno nuevo.

### 3.11 `consumo`
| Campo | Notas |
|---|---|
| consumo_id (PK) | |
| cuenta_id (FK → cuenta) | A quién se cobra |
| pasajero_id (FK → pasajero) | Quién consumió (trazabilidad) |
| estadia_id (FK → estadia) | Dónde estaba alojado en ese momento (la habitación se deduce de aquí) |
| producto_id (FK → producto) | |
| cantidad | Entero > 0 |
| precio_unitario | **Copia** del precio vigente al registrar; no se recalcula |
| precio_id (FK → precio_producto) | Referencia de auditoría |
| monto | cantidad × precio_unitario, guardado |
| fecha_hora | |
| usuario | |
| estado | `ACTIVO`, `ANULADO` |
| anulado_en, anulado_por, motivo_anulacion | Solo si `ANULADO` |

Los consumos no se borran ni se editan; se anulan.

### 3.12 `lote` (tabla prevista; uso opcional en v1)
`lote_id` (PK), `producto_id` (FK), `proveedor`, `remito`, `fecha_ingreso`, `fecha_vencimiento`, `cantidad_inicial`, `estado` (`DISPONIBLE`, `AGOTADO`, `VENCIDO`). Solo aplica a productos con `controla_vencimiento`. Si no se informa lote, el movimiento queda sin lote.

### 3.13 `movimiento_stock`
| Campo | Notas |
|---|---|
| movimiento_id (PK) | |
| producto_id (FK → producto) | |
| lote_id (FK → lote, opcional) | |
| tipo | `INGRESO`, `CONSUMO`, `ROTURA`, `VENCIMIENTO`, `AJUSTE`, `ANULACION` |
| cantidad | Con signo: INGRESO > 0; CONSUMO, ROTURA, VENCIMIENTO < 0; AJUSTE ±; ANULACION > 0 |
| fecha_hora, usuario | |
| consumo_id (FK → consumo, opcional) | Obligatorio para `CONSUMO` y `ANULACION` |
| conteo_detalle_id (FK → conteo_fisico_detalle, opcional) | Obligatorio para `AJUSTE` por conteo |
| movimiento_anulado_id (FK → movimiento_stock, opcional) | Solo en `ANULACION` |
| motivo, remito | Motivo obligatorio en ROTURA, VENCIMIENTO, AJUSTE |

Tabla de solo agregado (*append-only*): no se modifica ni se borra.

### 3.14 `conteo_fisico` y `conteo_fisico_detalle`
- `conteo_fisico`: `conteo_id` (PK), `tipo` (`SEMANAL`, `EXTRAORDINARIO`), `motivo` (si es extraordinario), `fecha_hora`, `usuario`, `estado` (`EN_CURSO`, `CONFIRMADO`, `CANCELADO`).
- `conteo_fisico_detalle`: `conteo_detalle_id` (PK), `conteo_id` (FK), `producto_id` (FK), `cantidad_teorica` (calculada al iniciar), `cantidad_contada`, `diferencia`.

Al **confirmar** el conteo, cada diferencia distinta de cero genera un `AJUSTE`. Nunca se corrige el saldo en silencio.

### 3.15 `auditoria` (transversal)
`auditoria_id` (PK), `fecha_hora`, `usuario`, `entidad`, `entidad_id`, `accion`, `detalle`. Registra correcciones manuales (cuenta, tipo de reserva, anulaciones, cambios de precio).

### 3.16 `usuario` y perfil
`usuario_id` (PK), `nombre`, `perfil` (`RECEPCION`, `ADMINISTRACION`, `GERENCIA`), `activo`. Todo `usuario` de las demás tablas referencia esta entidad (FK). Permisos en §11.

## 4. Cardinalidades

| Relación | Cardinalidad |
|---|---|
| importacion → reserva | 1 a N |
| reserva → pasajero | 1 a N (≥ 1) |
| pasajero → estadia | 1 a N (≥ 1); a lo sumo **1 abierta** |
| habitacion → estadia | 1 a N |
| estadia → estadia_anterior | 0..1 a 0..1 (cadena) |
| cuenta ↔ pasajero (por cuenta_pasajero) | N a M con vigencia; un pasajero tiene **1 cuenta vigente** |
| cuenta → consumo | 1 a N |
| pasajero → consumo | 1 a N |
| estadia → consumo | 1 a N |
| producto → precio_producto | 1 a N; 1 vigente |
| producto → consumo | 1 a N |
| consumo → movimiento_stock | 1 a 1 (`CONSUMO`) + 0..1 (`ANULACION`) si el producto controla stock; 0 si no |
| producto → lote | 1 a N |
| producto → movimiento_stock | 1 a N |
| conteo_fisico → detalle → movimiento (AJUSTE) | 1 a N → 0..1 |

## 5. Cómo se representan los conceptos pedidos

### 5.1 Cuenta
Una `cuenta` es la unidad económica. Se vincula con personas mediante `cuenta_pasajero`. Reglas (propuestas por el sistema, `origen = AUTO`):

| Tipo de reserva | Regla | `criterio` |
|---|---|---|
| INDIVIDUAL | Pasajeros con el mismo voucher comparten cuenta (también en `DOBLE INDIVIDUALES` y en varias habitaciones) | `VOUCHER` |
| CONTINGENTE | Pareja con voucher común **y** habitación base común comparte cuenta | `VOUCHER_Y_HABITACION` |
| CONTINGENTE | Resto: una cuenta por pasajero, aunque compartan habitación | `PASAJERO` |
| NO_DETERMINADO | No se crean cuentas hasta que recepción defina el tipo | — |

Recepción puede mover un pasajero de cuenta, unir o separar cuentas (`origen = MANUAL`).

### 5.2 Cambio de habitación
1. Se cierra la `estadia` actual (`hasta`, `motivo_cierre = CAMBIO_HABITACION`).
2. Se abre una nueva `estadia` con la nueva habitación (`motivo_inicio = CAMBIO_HABITACION`, `estadia_anterior_id` apuntando a la anterior).
3. **No** se toca `cuenta`, `cuenta_pasajero` ni los `consumo` existentes.
4. Los consumos anteriores conservan su `estadia_id` (habitación vieja); los nuevos usan la nueva. En un cambio parcial (solo una persona de la habitación) solo se cierra la estadía de ese pasajero.

### 5.3 Vínculo cuentas ↔ pasajeros ↔ estadías ↔ consumos
```text
cuenta ─(cuenta_pasajero)─ pasajero ─ estadia ─ habitacion
  └──────────────── consumo ───────────┘
```
Un consumo siempre lleva: cuenta (a quién se cobra), pasajero (quién lo pidió) y estadía (dónde estaba). Coherencia obligatoria: el pasajero debe pertenecer a la cuenta, y la estadía debe ser del pasajero y estar abierta al momento del consumo.

### 5.4 Consumo ↔ movimiento de stock
En una **única transacción**: crear `consumo` + crear `movimiento_stock(CONSUMO, −cantidad, consumo_id)` si `producto.controla_stock`. Si falla una operación, no se guarda ninguna. Anular un consumo crea `movimiento_stock(ANULACION, +cantidad, consumo_id, movimiento_anulado_id)` y marca el consumo `ANULADO`.

Stock teórico de un producto = suma de `cantidad` de todos sus movimientos. Los informes por período suman movimientos o consumos activos dentro del rango.

### 5.5 Productos y precios históricos
El `consumo` guarda `precio_unitario` y `monto` propios; cambiar el precio solo agrega una fila en `precio_producto`. Un producto dado de baja se desactiva, no se elimina, para conservar nombres en informes pasados. El precio se resuelve al registrar, nunca se reconstruye.

## 6. Estados

| Entidad | Estados y transiciones |
|---|---|
| importacion | `PROCESADA`, `CON_OBSERVACIONES`, `ANULADA` |
| reserva | `PENDIENTE_CLASIFICACION` → `ACTIVA` → `FINALIZADA` / `CANCELADA` (`NO_DETERMINADO` queda pendiente hasta confirmar) |
| pasajero | `ESPERADO` → `ALOJADO` → `EGRESADO` (o `NO_SE_PRESENTO`) |
| estadia | abierta / cerrada (según `hasta`) |
| cuenta | `ABIERTA` → `CERRADA` (checkout); no se reabre salvo acción registrada |
| consumo | `ACTIVO` → `ANULADO` |
| conteo_fisico | `EN_CURSO` → `CONFIRMADO` / `CANCELADO` |
| lote | `DISPONIBLE` → `AGOTADO` / `VENCIDO` |

## 7. Reglas de integridad

1. Claves foráneas siempre activas; no se borran filas con historial (se cambian de estado).
2. Un pasajero: a lo sumo 1 `estadia` abierta y 1 `cuenta_pasajero` vigente.
3. No se permite consumo sobre cuenta `CERRADA` ni sobre pasajero no `ALOJADO`.
4. `consumo.cantidad` entero > 0; `monto = cantidad × precio_unitario`.
5. Un producto tiene como máximo un `precio_producto` vigente, sin solapamientos de fechas.
6. `movimiento_stock` es *append-only*; los errores se corrigen con `ANULACION` o `AJUSTE`.
7. Signo de `cantidad` según `tipo` (§3.13).
8. Todo `CONSUMO` y `ANULACION` referencia un `consumo`; todo consumo de producto con `controla_stock` tiene su movimiento (transaccional).
9. Un consumo `ANULADO` tiene exactamente una `ANULACION`; no se anula dos veces.
10. Stock negativo: **permitido con advertencia**. Nunca se bloquea una operación real por stock insuficiente; el hecho se registra y queda disponible para auditoría.
11. Un `AJUSTE` por conteo solo se genera al confirmar el conteo.
12. Un `tipo_reserva` manual prevalece sobre el automático ante una reimportación.
13. Reimportar el mismo archivo (misma huella) avisa y no duplica.
14. Las correcciones manuales de cuenta o clasificación quedan en `auditoria`.

## 8. Qué viene del CSV y qué genera la app

| Dato | CSV | App |
|---|---|---|
| Voucher, sede, entidad, servicios, paquete, transporte, fechas | ✔ | normaliza |
| Nombre, documento, edad, nacimiento, estado O/T | ✔ | normaliza |
| Habitación y cama (`227 A`) | ✔ | separa base/cama y vincula a `habitacion` |
| Plazas, email, teléfonos, usuario | se ignoran en v1 (no confiables o innecesarios) | — |
| tipo_reserva, confianza, motivo | | ✔ clasificador |
| cuentas y pertenencias | | ✔ reglas de cuenta |
| estadías | inicial desde CSV | ✔ cambios y cierres |
| consumos, movimientos, precios, lotes, conteos | | ✔ |

## 9. Interpretación de duplicados del rooming
Un mismo pasajero con estado `T` (traslado) en una habitación y `O` en otra no es un duplicado: se interpreta como cambio de habitación y genera una estadía cerrada (T) y una abierta (O). Caso real: DNI 23265607 y 27707673, habitaciones 103 → 121.

## 10. Experiencia de usuario / separación entre modelo y UI

**Premisa:** la complejidad está en el sistema, no en el usuario.

**Conceptos solo internos (nunca se muestran a recepción):** SQLite y tablas, claves e identificadores (`cuenta_id`, `estadia_id`, `consumo_id`…), `codigo_visible`, `movimiento_stock` y sus tipos, `precio_id`, `huella_archivo`, `criterio` de cuenta, `origen AUTO/MANUAL`, `estadia_anterior_id`, `auditoria`, signos de cantidades y vigencias.

**Cómo lo ve el usuario:**

| Interno | Lenguaje hotelero |
|---|---|
| reserva / tipo_reserva | "Grupo" / "Pasajeros individuales"; si es NO_DETERMINADO, aviso "Confirmar tipo de reserva" |
| cuenta | "Cuenta de Leonardo Brondino" o "Cuenta familiar" |
| estadia | "Habitación 350 (desde 28/09)" |
| cambio de habitación | Botón "🛏️ Cambiar de habitación" (el pasajero conserva su cuenta) |
| consumo + movimiento | "✅ Registrar consumo" |
| anulación | "Anular consumo" con confirmación y motivo |
| ajuste por conteo | Pantalla "Contar mercadería" → "Se detectó una diferencia de 3 unidades. ¿Confirmar?" |
| rotura / vencimiento | Botones "Se rompió" / "Se venció" |
| ingreso | "Recibí mercadería" |
| precio nuevo | "Cambiar precio" (el historial no se modifica) |

**Flujo típico:** 🛏️ Habitación 350 → 👤 Pasajero → 🍺 Producto → [ 2 ] → ✅ Registrar.

**Principios:** botones grandes e iconos; selección antes que escritura; solo la información necesaria; confirmación en operaciones sensibles (anular, cerrar cuenta, confirmar conteo, cambiar precio); mensajes sin términos técnicos; alertas en lugar de bloqueos (stock bajo, producto por vencer, tipo de reserva no determinado).

## 11. Decisiones aprobadas

1. **Reserva:** aprobada con ajuste. Es la operación/grupo que ingresa; en contingente no se agrupa por voucher. El voucher es del pasajero y participa en la cuenta.
2. **Stock negativo:** permitido con advertencia; nunca bloquea; se registra para auditoría.
3. **Lotes/vencimientos:** el modelo (`lote`, `controla_vencimiento`) queda preparado desde v1; su uso operativo se activa en una segunda etapa y no se obliga a recepción a usarlos.
4. **Perfiles y permisos:**

| Capacidad | Recepción | Administración | Gerencia |
|---|:-:|:-:|:-:|
| Pasajeros, habitaciones, cambios de habitación, consumos | ✔ | ✔ | ✔ |
| Precios | | ✔ | ✔ |
| Anulaciones | | ✔ | ✔ |
| Stock (ingresos, roturas, vencimientos) | | ✔ | ✔ |
| Informes | | ✔ | ✔ |
| Conteos físicos | | | ✔ |
| Auditoría | | | ✔ |
| Configuración sensible | | | ✔ |

   Anulaciones y cambios de precio requieren confirmación y quedan registrados en `auditoria`.
5. **Informes por período:** filtrables por tipo de reserva, producto, categoría, pasajero, habitación y cuenta. Todos los filtros salen de campos existentes (`reserva.tipo_reserva`, `consumo.producto_id`, `producto.categoria_id`, `consumo.pasajero_id`, `estadia → habitacion`, `consumo.cuenta_id`); no requieren cambios al modelo.

## 12. Próximo entregable propuesto

Diseño de la arquitectura de la aplicación y plan de implementación por etapas (importación y clasificador → cuentas y consumos → stock → informes), todavía sin código.
