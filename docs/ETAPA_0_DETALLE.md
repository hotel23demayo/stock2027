# ETAPA_0_DETALLE

Estado: **propuesta para aprobación. No se escribe código hasta que sea aprobada.**
Parte de [PLAN_IMPLEMENTACION_v1.md](./PLAN_IMPLEMENTACION_v1.md) (Etapa 0) y [MODELO_LOGICO_v1.1.md](./MODELO_LOGICO_v1.1.md).
Esta etapa construye **el cerebro interno**, sin interfaz de negocio. `legacy/` no se modifica.

> **Vigencia:** esta etapa sigue siendo una propuesta; no describe la arquitectura implementada en la aplicación actual. Consultar el [README del proyecto](../README.md) para conocer el sistema operativo.

## 1. Alcance

**Entra:** estructura del proyecto; base SQLite con el esquema del modelo v1.1; acceso a datos con transacciones; autenticación y sesiones; permisos por perfil; auditoría; backup local con verificación; configuración; marco de pruebas; ingreso y un inicio mínimo.

**No entra:** importación, clasificación, cuentas, consumos, stock, informes, pantallas de negocio, red local, backup externo, catálogo cargado.

## 2. Estructura inicial

```text
stock2027/
├── legacy/                  referencia, solo lectura
├── docs/
├── app/
│   ├── web/                 rutas, sesión, plantillas mínimas (ingreso e inicio)
│   ├── servicios/           reglas de negocio (en Etapa 0: autenticación, permisos, auditoría, backup, configuración)
│   ├── datos/               acceso a SQLite y esquema (único lugar que conoce las tablas)
│   ├── textos/              catálogo de mensajes en lenguaje hotelero
│   └── configuracion/       valores por defecto y lectura de entorno
├── pruebas/
│   ├── unitarias/
│   ├── integracion/
│   └── fixtures/            CSV reales (individual, contingente) y casos sintéticos rotulados
├── datos_locales/           base y backups (fuera del repositorio)
└── importaciones/           CSV originales (fuera del repositorio)
```

Los nombres definitivos de carpetas se ajustan a la convención del proyecto al comenzar.

## 3. Responsabilidades de cada módulo

| Módulo | Responsabilidad | No debe hacer |
|---|---|---|
| **datos** | Crear/abrir la base, aplicar el esquema versionado, ofrecer transacciones, activar claves foráneas, verificar integridad al iniciar | Reglas de negocio |
| **servicios/autenticación** | Alta de usuarios, verificación de credenciales, bloqueo por intentos, cambio de clave, desactivación | Dibujar pantallas |
| **servicios/permisos** | Decidir si un perfil puede ejecutar una operación; se invoca **desde los servicios**, no solo desde la web | Depender de qué botones se ven |
| **servicios/auditoría** | Registrar quién, cuándo, qué, sobre qué, valor anterior/nuevo, motivo; solo agregado | Editar o borrar registros |
| **servicios/backup** | Crear copia consistente, verificarla, registrarla, aplicar retención, restaurar (solo Gerencia) | Decidir el destino externo (queda para Etapa 7) |
| **servicios/configuración** | Leer/escribir parámetros (solo Gerencia, auditado) | Mezclar parámetros con datos de negocio |
| **textos** | Traducir estados y errores internos a lenguaje hotelero | Contener lógica |
| **web** | Recibir pedidos, llamar a servicios, mostrar mensajes | Acceder a la base directamente |

Regla de dependencia: `web → servicios → datos`. Nunca al revés ni saltando capas.

## 4. Esquema de datos de la Etapa 0

Se crea **el esquema completo del modelo v1.1** (vacío) para validar claves y relaciones desde el comienzo, pero solo se usan en esta etapa: `usuario`, `auditoria`, `configuracion` y `backup_registro`. El esquema queda versionado: cada cambio posterior es un paso numerado y registrado; se **aplica automáticamente al iniciar** solo si hay copia previa.

Reglas verificadas por prueba: claves foráneas activas; sin borrado físico de entidades con historia; `auditoria` y `backup_registro` de solo agregado.

## 5. Autenticación

- **Un usuario por persona.** No hay usuarios compartidos.
- **Credencial protegida:** solo se guarda un resultado de derivación con sal individual (función de derivación de claves estándar y lenta); nunca la clave legible. Comparación en tiempo constante.
- **Bloqueo temporal** tras intentos fallidos repetidos; los intentos y bloqueos se auditan.
- **Cambio de clave obligatorio** tras alta o restablecimiento (`debe_cambiar_clave`).
- **Sesión en el servidor:** identificador aleatorio no adivinable, cookie con atributos de seguridad, vencimiento por inactividad y cierre explícito. No se guarda el perfil en el navegador; se consulta en cada operación.
- **Protección de formularios** contra pedidos falsificados desde otros sitios.
- **Primer usuario:** al instalar, se crea un único usuario de Gerencia mediante un procedimiento de instalación local (no desde la web), que fuerza el cambio de clave. Los demás usuarios los crea Gerencia desde la aplicación (Etapa 6). Los nombres reales se definen durante la implementación.
- **Perfiles:** Recepción, Administración, Gerencia, con la tabla de permisos ya aprobada.
- **Sin recuperación por correo** en v1: el restablecimiento lo hace Gerencia.

## 6. Permisos

- Tabla única *operación → perfiles autorizados*, consultada por los servicios antes de ejecutar.
- Una operación denegada **no modifica nada** y se audita si es sensible.
- Los perfiles ven solo su menú, pero la seguridad real está en los servicios.
- Prueba obligatoria: cada operación contra cada perfil.

## 7. Auditoría

- Un único servicio que todos los demás invocan; guarda usuario, fecha y hora, operación, entidad, valor anterior y nuevo, motivo.
- Se escribe **dentro de la misma transacción** que la operación auditada: si la operación falla, no queda un registro falso; si la operación se confirma, siempre queda su registro.
- Solo agregado: no hay operación de edición ni de borrado.
- En Etapa 0 se auditan: ingresos fallidos repetidos y bloqueos, altas y cambios de usuarios, cambios de configuración, creación y verificación de backups, restauraciones, y permisos denegados en operaciones sensibles.

## 8. Backup local

- **Método:** copia consistente de SQLite mediante su mecanismo de respaldo en caliente (no copiando el archivo mientras se usa), seguida de **verificación de integridad** de la copia.
- **Cuándo:** al cerrar la jornada, copia diaria programada, y antes/después de operaciones masivas (se activarán en etapas posteriores; en la Etapa 0 queda el servicio listo y probado).
- **Registro:** cada copia en `backup_registro` (tipo, resultado local, verificada). El resultado externo queda en `SIN_DESTINO` hasta la Etapa 7.
- **Retención:** 30 diarias más las de cierre semanal (parámetro de configuración).
- **Ubicación:** carpeta local fuera del repositorio; no visible para recepción.
- **Restauración:** solo Gerencia, con confirmación; antes de restaurar se hace una copia del estado actual; el procedimiento se prueba sobre una base de prueba.
- **Al iniciar:** verificación de integridad de la base; si falla, el sistema no opera y ofrece restaurar el último backup válido, informando qué período se perdería.
- **Aviso permanente** mientras no haya destino externo configurado.

## 9. Configuración

Parámetros del modelo v1.1 (umbral de anulaciones, ventana de deshacer, backup, lotes activos, umbral de cantidad inusual) se crean con sus valores iniciales; solo Gerencia los modifica, con auditoría de valor anterior y nuevo. El monto del umbral queda **sin valor** hasta que Gerencia lo fije.

## 10. Pantallas mínimas

Solo dos: **Ingreso** (usuario y clave, mensajes claros) e **Inicio mínimo** (nombre, perfil, "Cerrar sesión"). Sin menús de negocio. La interfaz completa comienza en la Etapa 2.

## 11. Estrategia de pruebas

| Tipo | Qué cubre |
|---|---|
| Unitarias | Derivación y verificación de credenciales, bloqueo, tabla de permisos, retención de backups |
| Integración | Esquema completo se crea y valida; claves foráneas rechazan datos inválidos; transacción que falla a mitad no deja datos; la auditoría se escribe y revierte con la operación; permisos por perfil en servicios |
| Integridad | Imposibilidad de editar/borrar auditoría y registros de backup; ningún borrado físico de entidades con historia |
| Backup/recuperación | Crear, verificar, restaurar sobre base de prueba; detectar una copia corrupta; arranque con base dañada |
| Seguridad básica | Sesión vence; acceso sin sesión rechazado; formularios sin protección rechazados; clave nunca aparece en registros ni auditoría |
| Reglas generales | Ninguna prueba ni servicio consulta "temporada" |

Las pruebas usan bases temporales; nunca la base real ni datos personales de `legacy/`.

## 12. Criterios de aceptación de la Etapa 0

1. El esquema v1.1 se crea completo y las pruebas de integridad pasan.
2. Se crea el primer usuario de Gerencia por el procedimiento local y se fuerza el cambio de clave.
3. Cada perfil ve y puede ejecutar solo lo autorizado; los denegados no cambian nada.
4. Un ingreso fallido repetido bloquea temporalmente y queda auditado.
5. Una operación de prueba que falla a mitad de camino no deja datos ni auditoría a medias.
6. Se genera, verifica y restaura un backup sobre una base de prueba; una copia corrupta se detecta.
7. Ninguna clave aparece en texto legible en la base ni en registros.
8. La aplicación arranca, permite ingresar y mostrar el inicio mínimo.
9. Todas las pruebas automáticas pasan, sin tocar `legacy/`.

## 13. Decisiones técnicas a confirmar antes de empezar

1. **Versión de Python y Flask:** ¿la del legacy (`requirements.txt`: dependencias actuales) o una versión actual compatible? Propuesta: Python estable reciente y Flask actual, con dependencias fijadas.
2. **Pruebas automáticas:** propuesta de usar el marco estándar `pytest`.
3. **Derivación de claves:** propuesta de usar la función estándar de la biblioteca de Python (sin dependencias nuevas) o una biblioteca específica de hash de contraseñas.
4. **Ubicación de la base y backups durante el desarrollo:** propuesta de `datos_locales/` fuera del control de versiones; en producción, una ruta configurable de la PC servidor.
5. **Control de versiones:** `stock2027` no es hoy un repositorio git. ¿Se inicializa uno al comenzar (propuesta: sí, con `.gitignore` que excluya datos, backups, importaciones y CSV con datos personales) y a qué repositorio remoto?
6. **Idioma del código:** propuesta de nombres de dominio en español (como el legacy y el modelo) y mensajes de usuario en español.

## 14. Qué espero de vos

Aprobación de este detalle (o ajustes) y respuesta a las seis decisiones del §13. Hasta entonces, no se escribe código.
