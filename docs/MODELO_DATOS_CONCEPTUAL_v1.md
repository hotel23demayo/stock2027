# Modelo de datos conceptual v1

Solo diseño, sin código. Complementa [ANALISIS_MATRIZ_RESERVA_Y_CUENTAS.md](./ANALISIS_MATRIZ_RESERVA_Y_CUENTAS.md).

> **Vigencia:** representa el modelo conceptual propuesto y no el esquema persistente de la aplicación actual. El estado implementado se describe en el [README del proyecto](../README.md).

## Flujo en capas

```text
ROOMING (CSV) → NORMALIZACIÓN → CLASIFICACIÓN (individual/contingente/no determinado)
  → REGLAS DE CUENTA → CUENTAS → CONSUMOS → CHECKOUT → REPORTES / STOCK
```

La temporada deja de gobernar el comportamiento; sale del rooming.

## Diagrama de entidades

```text
RESERVA 1──* PASAJERO 1──* ESTADIA (ubicación)
                │
                *
          CUENTA_PASAJERO *──1 CUENTA 1──* CONSUMO *──1 PRODUCTO 1──* MOVIMIENTO_STOCK
                                              (cuenta+pasajero+habitación)     │
                                                              LOTE ────────────┘
```

## Dominio huéspedes

| Entidad | Campos | Notas |
|---|---|---|
| **reserva** | reserva_id, tipo_reserva (INDIVIDUAL/CONTINGENTE/NO_DETERMINADO), confianza, voucher, servicios, paquete, transporte, fecha_ingreso, fecha_egreso, origen_archivo | Clasificada al importar |
| **pasajero** | pasajero_id, reserva_id, nombre, documento, edad, estado_rooming | Clave natural: documento + reserva. Filtrar por Estado (O vigente, T traslado) |
| **estadia** | pasajero_id, habitacion_base, cama, fecha_desde, fecha_hasta | Un cambio de habitación cierra una estadía y abre otra |
| **cuenta** | cuenta_id (p. ej. `C-30243135`), tipo, referencia, estado (abierta/cerrada), origen (AUTO/MANUAL) | Unidad económica |
| **cuenta_pasajero** | cuenta_id, pasajero_id | N pasajeros por cuenta; un pasajero en una sola cuenta vigente |

`cuenta_id` lo propone el sistema (reglas de la Matriz B) y recepción puede corregirlo (`origen = MANUAL`).

## Dominio consumos y stock

| Entidad | Campos | Notas |
|---|---|---|
| **producto** | producto_id, categoria (gaseosa, agua, saborizada, cerveza, vino, ficha café, comedor), nombre (Coca-Cola, Sprite…), presentacion, unidad_stock, precio, activo, stock_minimo | Una unidad física concreta; reemplaza `BEBIDAS_CATALOGO` |
| **consumo** | consumo_id, cuenta_id, pasajero_id, habitacion, producto_id, cantidad, precio_unitario, monto, fecha_hora, usuario, anulado | Mantiene cuenta + pasajero + habitación por trazabilidad; el precio queda congelado |
| **lote** (fase 2) | lote_id, producto_id, proveedor, fecha_ingreso, vencimiento, cantidad | Habilita vencimientos |
| **movimiento_stock** | movimiento_id, producto_id, lote_id?, tipo, cantidad (con signo), fecha_hora, referencia (consumo_id / remito), motivo, usuario | Fuente de verdad del stock |

Tipos de movimiento: `INGRESO`, `CONSUMO` (generado por cada consumo de bebida), `ROTURA`, `VENCIMIENTO`, `AJUSTE` (diferencia contra conteo físico), `ANULACION` (reversa de un consumo).

```text
stock teórico = stock inicial + Σ INGRESO − Σ CONSUMO − Σ ROTURA − Σ VENCIMIENTO ± AJUSTE
```

Reglas:
- Stock = suma de movimientos; nunca se edita un saldo directamente.
- Registrar un consumo de bebida crea su movimiento `CONSUMO` en la misma operación; anular el consumo crea `ANULACION`.
- Los consumos de comedor no descuentan stock en v1 (solo bebidas y fichas de café).
- Un consumo no cambia de propietario si el pasajero cambia de habitación.

## Informes previstos

- Consumo por período, producto y categoría (más vendidos).
- Consumo por tipo de reserva / contingente / cuenta.
- Stock actual vs. mínimo; roturas y vencimientos; diferencia teórico vs. físico.

## Verificación manual con los CSV

**Individual — voucher 186000164 (familia en dos habitaciones)**

| Pasajero | Hab. | Cuenta |
|---|---|---|
| Gomez Lucia Pilar (20) | 119 | C-186000164 |
| Gomez Marcos Javier (53) | 222 | C-186000164 |
| Nuñez Rosana Cecilia (48) | 222 | C-186000164 |

Clasificación INDIVIDUAL (MDP + sin transporte) → 1 cuenta, 3 pasajeros, 2 habitaciones. ✔
Caso `DOBLE INDIVIDUALES` hab. 231 (voucher 30237751, Hillaert / Gatti): 1 cuenta; si recepción detecta que no corresponde, la divide manualmente.

**Contingente — hab. 227 y 231**

| Pasajero | Hab. | Voucher | Cuenta |
|---|---|---|---|
| Panatti Liliana | 227 A | 30243127 | C-30243127 |
| Ugarriz Irma Susana | 227 B | 31243127 | C-31243127 |
| Gabborin Susana Ester | 231 A | 30243133 | C-30243133 (compartida) |
| Santoro Ernesto Angel | 231 B | 30243133 | C-30243133 (compartida) |

Clasificación CONTINGENTE (PPJ + bus) → 227 genera 2 cuentas separadas; 231 es pareja con voucher común y habitación base común: 1 cuenta. ✔

Cambio de habitación: si Ugarriz pasa de 227 B a otra habitación, solo se cierra su estadía y se abre otra; `C-31243127` y sus consumos no cambian. ✔

## Mapa del legacy (a decidir en el paso siguiente)

| Legacy | Destino |
|---|---|
| `BEBIDAS_CATALOGO` (core/consumos.py) | `producto` |
| `consumos_diarios.csv` | `consumo` (+ cuenta_id, producto_id) |
| detección de vouchers separados (dashboard.py) | resultado de la clasificación, no regla central |
| cambio_habitacion.py, reserva_express.py | operan sobre `estadia` |
| temporadas (`cambiar_temporada.sh`, etc.) | información de la reserva, no comportamiento |

## Preguntas abiertas

1. ¿Persistencia: seguir con CSV o pasar a SQLite? (stock con movimientos y lotes se beneficia mucho de SQLite).
2. ¿El comedor entra al control de stock o solo bebidas y fichas?
3. ¿Hay conteo físico periódico (diario/semanal) para generar ajustes?
