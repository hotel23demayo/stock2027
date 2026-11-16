# PLAN_IMPLEMENTACION_v1

Estado: **borrador para revisión. No se escribe código hasta que este plan sea aprobado.**
Base aprobada: [MODELO_LOGICO_v1.1.md](./MODELO_LOGICO_v1.1.md) y [ARQUITECTURA_APP_v1.md](./ARQUITECTURA_APP_v1.md).
Sin código, SQL ni migraciones en este documento.

> **Vigencia:** este plan es una propuesta de implementación del modelo objetivo; no representa el avance real del sistema. Algunas funciones ya existen en la aplicación legacy y otras decisiones del plan no se han implementado. Para el estado vigente, consultar el [README del proyecto](../README.md).

## 1. Reglas que gobiernan todo el plan

1. **Una importación es una fuente de novedades y diferencias, nunca una orden de borrar historia.** Un pasajero ausente en una nueva importación se conserva y queda marcado para revisión, sin afectar sus estadías, cuentas ni consumos.
2. **Se distinguen dos hechos:** "el CSV no lo trae" (`presente_en_ultima_carga = falso`) y "el hotel determinó que ya no está" (decisión de recepción). Para no mezclarlos, el pasajero ausente tiene además un **estado de revisión de la diferencia** (pendiente de revisión / confirmado como egresado / confirmado como vigente). Ver §11, nota de diseño N1.
3. **El modelo v1.1 está aprobado y no se modifica por cuestiones menores.** Los ajustes pequeños que aparezcan se anotan en §11 y se resuelven al iniciar la etapa que los necesite, sin rediseñar.
4. **Cada etapa termina en algo usable y probado**, con criterios de aceptación explícitos; no se avanza con la etapa anterior sin cerrar.
5. **Los CSV reales son el material de prueba** (ver §3). Ninguna regla de importación, clasificación o cuentas se da por buena sin pasar sus casos.
6. **Se construye de adentro hacia afuera:** reglas y datos primero, pantallas después; pero cada etapa incluye las pantallas mínimas para poder usarla.
7. **Sin modo temporada** en ninguna etapa: si una prueba requiere "configurar temporada", la prueba falla.
8. **`legacy/` es solo referencia**; no se modifica ni se ejecuta en producción.

## 2. Visión general

```text
Etapa 0  Fundaciones          →  base, usuarios, permisos, auditoría, backup local
Etapa 1  Importación          →  CSV → validación → clasificación → vista previa → confirmar
Etapa 2  Alojamiento/cuentas  →  habitaciones, fichas, cambio de habitación, corregir cuenta
Etapa 3  Catálogo y consumos  →  productos, precios, registrar consumo, deshacer/anular, stock automático
Etapa 4  Stock                →  ingresos, roturas, vencimientos, conteo, ajustes
Etapa 5  Checkout             →  individual y de grupo
Etapa 6  Informes y control   →  informes, auditoría, usuarios, configuración
Etapa 7  Puesta en marcha     →  backup externo, red local, piloto, histórico
Etapa 8  Segunda fase         →  lotes/vencimientos operativos, comedor, etc.
```

Dependencias principales: 0 → 1 → 2 → 3 → (4, 5) → 6 → 7. Las etapas 4 y 5 pueden hacerse en cualquier orden entre sí. El reemplazo de cargas (Etapa 1B) requiere 1 y 2.

## 3. Material de prueba (se prepara antes de la Etapa 1)

| Material | Uso |
|---|---|
| `reservaIndividual.csv` (27 filas) | Caso individual: 12 vouchers → 12 cuentas; habitaciones 109 a 353; DOBLE INDIVIDUALES; voucher compartido entre habitaciones (186000164); filas con servicios vacíos; estados T/O (DNI 23265607 y 27707673, hab. 103 → 121) |
| `pruebaGroup.csv` (47 filas) | Caso contingente: 36 cuentas; sufijos de cama (`227 A`); 11 parejas con voucher común; habitación base común; DOBLE/TRIPLE A COMPARTIR |
| Variantes derivadas (se crean a mano) | CSV corregido con pasajero faltante, con pasajero nuevo, con cambio de habitación, con voucher cambiado; CSV con columnas faltantes; CSV vacío; CSV con fechas inválidas; mismo archivo dos veces; **CSV mixto** (individuales + contingente) |
| `consumos_diarios.csv` legacy | Referencia de nombres de ítem y comparación de totales |
| Comanda de la habitación 350 | Catálogo inicial de bebidas y fichas |

Los CSV con datos personales se guardan solo en el entorno de desarrollo y no se publican en el repositorio.

## 4. Etapas

Convención por etapa: **Objetivo · Se construye · Entidades · Pantallas · Pruebas · Criterios de aceptación · No incluye**.

### Etapa 0 — Fundaciones
- **Objetivo:** base técnica sobre la que se apoya todo; sin funciones de negocio visibles.
- **Se construye:**
  - Estructura del proyecto (capas web / servicios / datos) y configuración.
  - Esquema de la base según el modelo v1.1 y su mecanismo de versionado.
  - Capa de acceso a datos con transacciones, claves foráneas activas y escritura solo por servicios.
  - Usuarios individuales con ingreso, credencial protegida y bloqueo temporal; sesión en servidor.
  - Control de permisos por perfil en la capa de servicios.
  - Servicio de auditoría y catálogo de textos en lenguaje hotelero.
  - Backup local automático y su registro; verificación de integridad al iniciar.
  - Marco de pruebas automáticas.
- **Entidades:** usuario, auditoria, configuracion, backup_registro (y esquema completo vacío).
- **Pantallas:** ingreso; inicio mínimo con nombre y perfil.
- **Pruebas:** permisos por perfil, bloqueo por intentos, transaccionalidad (si algo falla, no se guarda nada), backup y restauración en base de prueba, claves foráneas.
- **Aceptación:** una persona puede ingresar con su usuario; cada perfil ve solo lo suyo; las operaciones de prueba quedan auditadas; se genera y verifica un backup local; un error en medio de una operación no deja datos a medias.
- **No incluye:** ninguna pantalla de negocio.

### Etapa 1 — Importación y clasificación
- **Objetivo:** convertir un CSV de rooming en reservas, pasajeros y estadías, pasando siempre por cargar → validar → resumen → confirmar.
- **Se construye:**
  - Lectura del CSV (pandas) y huella del archivo; detección de reimportación.
  - **Validación** (columnas, fechas, documentos, estado O/T, habitaciones desconocidas).
  - **Normalización** (texto, habitación base + cama, voucher por pasajero, servicios vacíos como dato faltante).
  - **Clasificador** Individual / Contingente / No determinado con confianza y motivo (paquete y transporte con peso muy alto).
  - **Vista previa** con semáforo y lista de observaciones en lenguaje claro; botón Confirmar.
  - **Creación** en una transacción: importación, reservas, pasajeros, habitaciones nuevas, estadías (T/O como cierre y apertura).
  - Backup previo automático a la confirmación.
  - Reglas de cuenta **como parte de la confirmación** (Etapa 2 las usa y las muestra).
- **Entidades:** importacion, reserva, pasajero, habitacion, estadia, cuenta, cuenta_pasajero.
- **Pantallas:** Cargar rooming, Revisión de la carga, Vista de reservas (lista y detalle).
- **Pruebas** (casos reales de §3):
  - `reservaIndividual.csv` → INDIVIDUAL, confianza alta, 27 pasajeros, 12 cuentas; voucher 186000164 = 1 cuenta, 3 pasajeros, 2 habitaciones; 231 (DOBLE INDIVIDUALES) = 1 cuenta; hab. 103 → 121 interpretado como cambio de habitación.
  - `pruebaGroup.csv` → CONTINGENTE, confianza alta, 47 pasajeros, 36 cuentas; 227 A/B = 2 cuentas; 231 A/B (voucher común) = 1 cuenta.
  - Archivo mixto → reservas separadas según su clasificación; archivo ambiguo → NO_DETERMINADO sin cuentas.
  - Archivo malformado o vacío → rechazo con mensaje claro y sin guardar nada.
  - Mismo archivo dos veces → aviso, sin duplicados.
  - Falla simulada a mitad de la carga → no queda nada guardado.
  - Ninguna prueba depende de la fecha ni de "temporada".
- **Aceptación:** los dos CSV reales producen exactamente los resultados esperados; nada se guarda sin confirmar; la clasificación se puede corregir manualmente (con auditoría); recepción no ve identificadores ni términos técnicos.
- **No incluye:** reemplazo de cargas (1B), pantallas de habitaciones y cuentas (Etapa 2).

### Etapa 1B — Reemplazo y corrección de cargas (Administración)
- **Objetivo:** corregir un rooming ya cargado sin perder historia.
- **Se construye:** comparación contra la carga anterior por documento + reserva; resumen de diferencias; confirmación; estado `REEMPLAZADA`; marcación de ausentes con revisión; cierre y apertura de estadías ante cambio de habitación; propuestas de corrección de cuenta sin reescribir cuentas con consumos.
- **Pruebas:** pasajero nuevo; pasajero ausente **sin** consumos y **con** consumos (se conserva siempre, queda en revisión y no se tocan estadías, cuentas ni consumos); cambio de habitación; cambio de voucher sobre cuenta con consumos; decisiones manuales previas no revertidas sin confirmación; backup previo; falla simulada sin pérdida.
- **Aceptación:** tras cualquier reemplazo, un recuento de pasajeros, estadías, cuentas y consumos nunca disminuye; las diferencias aparecen para revisión en el Inicio.
- **No incluye:** eliminación física de cualquier dato (no existe en el sistema).
- **Nota:** se construye cuando existan los consumos (Etapa 3) para poder probar el caso "ausente con consumos"; la lógica de comparación se puede preparar antes.

### Etapa 2 — Alojamiento y cuentas
- **Objetivo:** que recepción vea el hotel y administre ubicaciones y cuentas.
- **Se construye:** mapa de habitaciones, ficha de habitación y de pasajero, búsqueda global; **Pasar huésped de habitación** (total y parcial); **Corregir cuenta** (mover, unir, separar con vista Antes/Después); gestión de cuentas.
- **Entidades:** habitacion, estadia, pasajero, cuenta, cuenta_pasajero, auditoria.
- **Pantallas:** Inicio (versión de recepción), Habitaciones, Ficha de habitación, Ficha de huésped, Cuenta, Cambio de habitación, Corregir cuenta.
- **Pruebas:** cambio total y parcial; el pasajero conserva su cuenta; una sola estadía abierta por pasajero; un pasajero en una sola cuenta vigente; corrección manual auditada y que prevalece ante una reimportación; permisos por perfil.
- **Aceptación:** con las cargas de la Etapa 1, recepción puede ubicar a cualquier persona, cambiarla de habitación y corregir una cuenta sin ver un solo identificador interno; el historial de habitaciones se reconstruye.
- **No incluye:** consumos, checkout.

### Etapa 3 — Catálogo y consumos (con stock automático)
- **Objetivo:** registrar consumos asociados a cuenta y pasajero, y que cada consumo de bebida o ficha genere su salida de stock.
- **Se construye:**
  - Categorías, productos y precios históricos (carga inicial desde la comanda 350: productos individuales por sabor/marca).
  - **Registrar consumo** en 4 toques (habitación → huésped → producto → cantidad → registrar).
  - Transacción única: consumo + movimiento de stock; advertencia por stock negativo sin bloquear.
  - **Deshacer** propio en 5 minutos; **anulación posterior** (Administración); registro y revisión de anulaciones con umbral configurable.
  - Servicio de stock con los movimientos `CONSUMO` y `ANULACION` (los demás tipos se agregan en la Etapa 4).
- **Entidades:** categoria_producto, producto, precio_producto, consumo, movimiento_stock, anulacion, configuracion.
- **Pantallas:** Registrar consumo, Ficha de habitación y huésped con consumos, Catálogo de productos (Administración), Anular consumo, Avisos de revisión para Gerencia.
- **Pruebas:** el consumo queda con cuenta, pasajero y estadía; el precio histórico no cambia al modificar el precio; consumo y movimiento son atómicos; stock negativo se permite y se audita; deshacer solo por quien registró y dentro de 5 minutos; anulación posterior exige motivo; el umbral decide si queda pendiente de revisión; el stock calculado = suma de movimientos; un consumo en una cuenta cerrada se rechaza; doble toque no duplica.
- **Aceptación:** registrar 2 cervezas a un huésped deja un consumo correcto y su salida de stock, visible solo como "Listo: 2 × Cerveza a la cuenta de …"; el consumo sobrevive intacto a un cambio de habitación.
- **No incluye:** ingresos, roturas, conteos (Etapa 4); lotes.

### Etapa 4 — Stock
- **Objetivo:** control operativo del inventario.
- **Se construye:** **Recibí mercadería**, **Se rompió**, **Se venció** (sin lote obligatorio); pantalla de Stock con semáforo y movimientos en lenguaje claro; **conteo físico** semanal y extraordinario (conteo ciego, diferencias, confirmación → ajustes); alertas de stock bajo y de negativos a revisar; stock inicial por conteo.
- **Entidades:** movimiento_stock (INGRESO, ROTURA, VENCIMIENTO, AJUSTE), conteo_fisico, conteo_fisico_detalle, producto.
- **Pruebas:** ningún saldo editable; fórmula stock = suma de movimientos; ajustes solo al confirmar el conteo; motivos obligatorios; permisos (conteo solo Gerencia); movimientos de solo agregado.
- **Aceptación:** tras un conteo con diferencias, el stock coincide con lo contado y cada diferencia aparece como ajuste auditado.
- **No incluye:** lotes operativos, proveedores.

### Etapa 5 — Checkout
- **Objetivo:** cerrar estadías y cuentas con detalle imprimible.
- **Se construye:** salida por habitación, por cuenta y **salida de grupo**; aviso si alguien de una cuenta compartida sigue alojado; cierre en una transacción con backup previo para salidas masivas; finalización de la reserva al salir el último; reapertura (Gerencia).
- **Pruebas:** cuenta compartida con una persona que se queda; salida de grupo de 47 pasajeros del CSV de contingente; consumos bloqueados tras el cierre; reapertura auditada.
- **Aceptación:** el detalle de cada cuenta coincide con la suma de sus consumos activos; ningún dato se pierde al cerrar.

### Etapa 6 — Informes y control
- **Objetivo:** valor para Gerencia.
- **Se construye:** informes por período con filtros (tipo de reserva, producto, categoría, pasajero, habitación, cuenta); más vendidos, roturas, vencimientos, diferencias de inventario, stock vs. mínimo; exportación; **Auditoría** navegable; **Administración de usuarios**; pantalla de configuración (umbral de anulaciones, destino de backup, etc.).
- **Pruebas:** totales de informes = totales de consumos y movimientos; filtros combinados; un cambio de precio no altera períodos pasados; exportaciones auditadas; permisos.
- **Aceptación:** Gerencia obtiene "cuánto se consumió de cada producto en un período" y puede filtrar por tipo de reserva.

### Etapa 7 — Puesta en marcha
- **Objetivo:** pasar a uso real con seguridad.
- **Se construye:**
  - **Destino externo de backup configurable** con reintentos y avisos; prueba de restauración.
  - **Publicación en red local desde la PC servidor** para varios puestos; pruebas con dos puestos simultáneos; procedimiento de contingencia ante caída del servidor.
  - Importación del histórico del legacy solo si Gerencia lo solicita.
  - Carga inicial de productos y primer conteo.
  - **Piloto** con usuarios reales de recepción y ajuste de textos y pantallas.
  - Manual breve para recepción y guía para Gerencia.
- **Pruebas:** dos puestos operando a la vez; apagado del servidor durante una operación (no deja datos a medias); restauración en otra PC; usabilidad con recepción (¿completan un consumo y un cambio de habitación sin ayuda?).
- **Aceptación:** una jornada completa de piloto sin pérdida de datos, con backup local y externo verificados.

### Etapa 8 — Fase posterior (fuera de v1)
Uso operativo de lotes y vencimientos; stock del comedor; proveedores y reposición; integración directa con el sistema de reservas; facturación y cobranza; migración automática del histórico (si no se hizo en la Etapa 7).

## 5. Qué se prueba y cómo

| Nivel | Qué cubre | Cuándo |
|---|---|---|
| Reglas de negocio (automáticas) | Clasificador, reglas de cuenta, cambio de habitación, stock = suma de movimientos, anulaciones, permisos | En cada etapa; deben pasar todas antes de cerrarla |
| Datos reales | Dos CSV reales y variantes (§3), con resultados esperados fijos | Desde la Etapa 1 y se mantienen como pruebas de regresión |
| Integridad | Transacciones, claves foráneas, ausencia de borrado físico, recuento de historia tras reemplazos | Desde la Etapa 0 |
| Flujos de punta a punta | CSV → reserva → cuenta → consumo → stock → checkout → informe | Al cerrar la Etapa 5 y en la Etapa 7 |
| Usabilidad | Personal de recepción hace consumo, cambio de habitación y corrección de cuenta sin explicación técnica | Pantallas de la Etapa 2 en adelante y piloto |
| Recuperación | Falla a mitad de operación, base dañada, restauración | Etapas 0, 5 y 7 |

Pruebas de regresión permanentes: **ningún recuento histórico disminuye**, **ninguna regla consulta temporada**, **recepción nunca ve identificadores**.

## 6. Criterio de "terminada" para cada etapa

1. Criterios de aceptación cumplidos y pruebas pasando.
2. Auditoría y permisos verificados para lo nuevo.
3. Textos de la interfaz en lenguaje hotelero, revisados.
4. Documentación de diseño actualizada si algo cambió (`docs/`).
5. Demostración a vos con datos reales; aprobación explícita para pasar a la siguiente.

## 7. Qué se reutiliza del legacy y qué no

| Legacy | Tratamiento |
|---|---|
| Catálogo de `BEBIDAS_CATALOGO` | Fuente para la carga inicial de productos (ampliada por sabor/marca) |
| Detalle de consumo (fecha, ítem, cantidad, precio, monto) | Referencia de campos; el nuevo `consumo` suma cuenta, pasajero y estadía |
| Lógica de cambio de habitación, reserva express, checkout masivo | Referencia funcional, reescrita sobre estadías y cuentas |
| Vouchers separados en dashboard | Reemplazado por clasificación + reglas de cuenta |
| Temporadas (scripts, cambio de temporada, guías) | No se reutilizan |
| Parches ACTIVOS/JUBILADOS | No se reutilizan |
| Plantillas de pantallas | Inspiración visual; las nuevas se diseñan para la navegación de recepción |

## 8. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Archivos CSV con variantes no vistas | Validación tolerante con observaciones, vista previa obligatoria, pruebas con variantes |
| Clasificación incorrecta | Confianza y motivo visibles; NO_DETERMINADO no crea cuentas; corrección manual auditada |
| Un reemplazo daña la historia | Backup previo, resumen de diferencias, recuentos de regresión, sin borrado físico |
| Registro de consumos lento o confuso en el mostrador | Prueba de usabilidad temprana (Etapa 2/3) con recepción real; máximo 4 toques |
| Caída de la PC servidor | Backups frecuentes, contingencia documentada, aviso de dependencia |
| Dos puestos escriben a la vez | Un único escritor en el servidor, transacciones cortas, pruebas de concurrencia |
| Stock inicial incorrecto | Primer conteo guiado; ajustes auditados |
| Alcance que crece | Fuera de v1 explícito (§10 de la arquitectura); todo pedido nuevo se evalúa contra el plan |
| Datos personales de pasajeros | CSV fuera del repositorio, credenciales protegidas, red local sin exposición a internet |

## 9. Orden recomendado y puntos de decisión

| Hito | Contenido | Decisión tuya |
|---|---|---|
| H0 | Etapa 0 | Aprobar estructura y pruebas de base |
| H1 | Etapa 1 (+1B parcial) | **Aprobar los resultados de importación con los dos CSV reales** |
| H2 | Etapa 2 | Aprobar navegación y pantallas de recepción |
| H3 | Etapa 3 (+1B completa) | Aprobar catálogo inicial y flujo de consumo; fijar monto del umbral de anulaciones |
| H4 | Etapas 4 y 5 | Aprobar stock, conteo y checkout |
| H5 | Etapa 6 | Aprobar informes |
| H6 | Etapa 7 | Autorizar el piloto |

## 10. Qué se necesita antes de empezar

1. Aprobación de este plan.
2. Catálogo real de productos (marca/sabor, presentación, precio vigente) y stock inicial aproximado.
3. Al menos otro rooming real (si existe) para ampliar las pruebas, o la autorización para derivar variantes de los dos actuales.
4. Lista inicial de usuarios y perfiles.
5. Confirmar que la PC servidor estará definida antes de la Etapa 7 (no hace falta antes).

## 11. Notas de diseño registradas (no modifican el modelo aprobado)

| # | Nota | Se resuelve en |
|---|---|---|
| N1 | Distinguir "el CSV no lo trae" de "el hotel determinó que ya no está": además de `presente_en_ultima_carga`, el pasajero ausente lleva un estado de revisión de la diferencia (pendiente / egresado confirmado / vigente confirmado). El modelo v1.1 ya conserva al pasajero y lo deja "no confirmado"; falta nombrar este estado como campo propio. | Inicio de la Etapa 1B; se anota como addendum de v1.1 sin rehacer el modelo |
| N2 | Umbral de anulaciones sin valor inicial: mientras Gerencia no lo fije, toda anulación posterior queda visible en Auditoría | Etapa 3 |
| N3 | Procedimiento de contingencia ante caída del servidor | Etapa 7 |
| N4 | Política de pasajero ausente sin consumos: queda "pendiente de revisión" hasta que recepción decida | Etapa 1B |

## 12. Lo que queda fuera de la v1 (recordatorio)

Lotes y vencimientos operativos, stock del comedor, facturación y cobranza, integración directa con reservas, app móvil o sin conexión, reservas futuras con disponibilidad, proveedores y reposición, paneles analíticos avanzados, multi-hotel y acceso desde internet, migración automática del histórico, temporada como regla de negocio.

## 13. Próximo paso

Revisar este plan. Con tu aprobación, la **Etapa 0** es la primera en construirse, y antes de comenzar te presento su lista de tareas concreta para una última confirmación.
