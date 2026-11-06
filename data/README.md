# 📂 Carpeta de Datos - Hotel Recepción

## ⚠️ IMPORTANTE: Datos Sensibles

Esta carpeta contiene información sensible de pasajeros y **NO se sube al repositorio Git**.

---

## 📋 Archivos Requeridos

### 1️⃣ `pasajeros.csv`

Archivo principal con datos de pasajeros.

**Estructura según temporada:**

**TEMPORADA ACTIVOS:**
```csv
Apellido y nombre,Nro. doc.,Edad,Nro. habitación,Tipo habitación,Voucher,Sede,Fecha de ingreso,Fecha de egreso,Servicios,Plazas ocupadas
```

**TEMPORADA JUBILADOS:**
```csv
Cód. Alojamiento,Descripción,Nro. habitación,Tipo habitación,Observación habitación,Cantidad plazas,Voucher,Sede,Fecha de ingreso,Fecha de egreso,Plazas ocupadas,Tipo documento,Nro. doc.,Apellido y nombre,Edad,Entidad,Servicios,Paquete,Transporte,Fecha viaje,Hora viaje,Parada,Email,Estado,Fecha de nacimiento,Teléfono,Celular,Usuario
```

---

### 2️⃣ `consumos_diarios.csv`

Archivo para registrar consumos de los pasajeros.

**Estructura:**
```csv
id_consumo,id_estadia,fecha,habitacion,pasajero,categoria,item,cantidad,precio_unitario,monto,estado,fecha_anulacion,motivo_anulacion
```

- `id_estadia` identifica la **cuenta de consumos**; el número de habitación es solo la ubicación física.
- Un consumo sin `id_estadia` (histórico) **no se suma** a la cuenta de una estadía nueva; se conserva en el CSV y la ficha muestra una advertencia.
- Anular un consumo no lo borra: se marca `estado=anulado` con fecha y motivo.
- El checkout no elimina consumos: el historial es permanente.
- Las columnas faltantes en archivos viejos se migran automáticamente al leer.

**Para empezar de cero** (p. ej. tras las pruebas) usar el script de reinicio, que hace backup antes de vaciar: ver [REINICIO_DATOS.md](../REINICIO_DATOS.md).

---

### 2️⃣ bis `catalogo_productos.csv`

Catálogo de productos y precios. **Sí está versionado en Git** y no es dato operativo: el reinicio no lo modifica.

```csv
codigo,producto,categoria,sector,precio_actual
nampe_malbec,Nampe Malbec,vinos,Bar,6500
```

---

### 3️⃣ `consultaRegimenReport.csv` (Opcional - Solo Activos)

CSV exportado del sistema de gestión con datos de trabajadores activos.

---

### 4️⃣ `testJubis.csv` (Opcional - Solo Jubilados)

CSV con datos de trabajadores jubilados.

---

## 📁 Estructura de Carpetas

```
data/
├── README.md                    # Este archivo
├── pasajeros.csv               # ⚠️ NO SUBIR AL REPO
├── consumos_diarios.csv        # ⚠️ NO SUBIR AL REPO
├── consultaRegimenReport.csv   # ⚠️ NO SUBIR AL REPO (opcional)
├── testJubis.csv               # ⚠️ NO SUBIR AL REPO (opcional)
└── backups/                    # ⚠️ NO SUBIR AL REPO
    └── pasajeros_backup_YYYYMMDD_HHMMSS.csv
```

---

## 🔒 Seguridad

- ✅ Todos los archivos `.csv` están ignorados por Git (ver `.gitignore`)
- ✅ La carpeta `backups/` está ignorada por Git
- ✅ Solo archivos `*_ejemplo.csv` se pueden subir al repositorio
- ⚠️ **NUNCA** hacer commit de datos reales de pasajeros

---

## 🚀 Cómo Empezar

### En tu PC de Trabajo:

1. **Clonar el repositorio:**
   ```bash
   git clone <url-del-repositorio>
   cd recepcion2026-consumos
   ```

2. **Crear archivos iniciales:**
   ```bash
   # Crear consumos vacío (se genera con el encabezado correcto)
   python3 reiniciar_datos.py --simular   # ver qué haría
   python3 reiniciar_datos.py             # reiniciar con backup

   # Copiar tu CSV de pasajeros
   cp /ruta/a/tu/archivo.csv data/pasajeros.csv
   ```

3. **Seleccionar temporada:**
   ```bash
   # Para trabajadores activos
   git checkout temporada-activos
   
   # Para jubilados
   git checkout temporada-jubilados
   ```

4. **Si usas trabajadores activos:**
   ```bash
   # Copiar CSV exportado del sistema
   cp /ruta/consultaRegimenReport.csv data/
   
   # Procesar y cargar
   python3 cargar_trabajadores_activos.py
   ```

5. **Iniciar servidor:**
   ```bash
   python3 app.py
   ```

---

## 🔄 Cambio de Temporada

```bash
# Ver temporada actual
git branch

# Cambiar temporada (automático)
./cambiar_temporada.sh [activos|jubilados]

# Cambiar temporada (manual)
git checkout temporada-activos    # O temporada-jubilados

# Reemplazar pasajeros.csv con datos de la nueva temporada
```

---

## 📊 Backups

Los backups se crean automáticamente en `data/backups/` cuando:
- Usas el script `cambiar_temporada.sh`
- Procesas un check-out (se archiva el pasajero)

**Formato:**
```
pasajeros_backup_20260301_183045.csv
consumos_backup_20260301_183045.csv
reinicio_20261107_093000/        # generado por reiniciar_datos.py
├── pasajeros.csv
└── consumos_diarios.csv
```

---

## ⚠️ RECORDATORIOS

1. **NUNCA** hacer `git add data/pasajeros.csv`
2. **NUNCA** hacer `git add data/*.csv` (excepto `*_ejemplo.csv`)
3. Siempre verificar con `git status` antes de hacer commit
4. Los datos reales solo existen en tu PC de trabajo
5. El repositorio remoto solo tiene código y documentación

---

**Última actualización:** 3 de Noviembre 2026
