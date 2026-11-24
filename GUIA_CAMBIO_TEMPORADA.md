# 📆 Guía de Cambio entre Temporadas

## 🎯 Sistema de Branches Git

Este proyecto maneja **DOS SISTEMAS** diferentes según la temporada del año:

### 📅 Calendario de Temporadas

| Temporada | Meses | Branch a usar |
|-----------|-------|---------------|
| **Activos** | Enero-Febrero, Junio-Septiembre | `temporada-activos` |
| **Jubilados** | Marzo-Mayo, Octubre-Diciembre | `temporada-jubilados` |

---

## 🔧 Configuración Inicial (SOLO UNA VEZ)

### Paso 1: Crear Branch de Jubilados (YA HECHO)

```bash
# Guardar cambios actuales en temporada-jubilados
git checkout -b temporada-jubilados
git add .
git commit -m "✅ Sistema configurado para temporada jubilados - Consumos individuales implementados"
git push -u origin temporada-jubilados
```

### Paso 2: Crear/Recuperar Branch de Activos

Si ya existe una versión anterior del sistema de activos:
```bash
# Opción A: Si tienes commits anteriores con checkout anticipado
git checkout main
git checkout -b temporada-activos
# Buscar el commit ANTES de eliminar checkout anticipado
git log --oneline --all | grep -i "checkout\|anticipado"
# Restaurar ese commit si existe
```

Si NO existe, lo crearás cuando terminen los jubilados:
```bash
# Cuando termine temporada jubilados y necesites activos
git checkout main
git revert <commits-de-jubilados>  # Restaurar funcionalidades de activos
git checkout -b temporada-activos
```

---

## 🔄 Cambiar de Temporada

Conserva el historial de consumos: no lo vacíes manualmente. El script
automatizado indicado al final cambia de rama, intenta crear un commit y vacía
los consumos después de respaldarlos; ejecútalo únicamente si se autoriza ese
reinicio destructivo. Cierra la aplicación antes de cambiar de temporada.

### 📋 De JUBILADOS → ACTIVOS (Junio)

```bash
# 1. Guardar cualquier cambio pendiente en jubilados
git add .
git commit -m "💾 Fin temporada jubilados Mayo 2026"

# 2. Cambiar a temporada activos
git checkout temporada-activos

# 3. Preparar pasajeros conservando el historial de consumos
rm data/pasajeros.csv  # O hacer backup
# Cargar nuevo CSV de activos

# 4. Iniciar servidor
flask run
```

### 📋 De ACTIVOS → JUBILADOS (Octubre o Marzo)

```bash
# 1. Guardar cualquier cambio pendiente en activos
git add .
git commit -m "💾 Fin temporada activos $(date +%B\ %Y)"

# 2. Cambiar a temporada jubilados
git checkout temporada-jubilados

# 3. Preparar pasajeros conservando el historial de consumos
rm data/pasajeros.csv  # O hacer backup
# Cargar nuevo CSV de jubilados

# 4. Iniciar servidor
flask run
```

---

## 🆘 Comandos Útiles

### Ver en qué branch estás
```bash
git branch
# El que tiene * es el actual
```

### Ver diferencias entre branches
```bash
git diff temporada-activos temporada-jubilados
```

### Listar todos los branches
```bash
git branch -a
```

### Ver archivos modificados en cada branch
```bash
git log --oneline --decorate --graph --all
```

---

## ⚠️ Reglas Importantes

1. **NUNCA hagas merge** entre `temporada-activos` y `temporada-jubilados`
   - Son sistemas independientes
   - Solo comparten la estructura base

2. **Siempre confirma el branch** antes de hacer cambios
   ```bash
   git branch  # Verificar
   ```

3. **Haz commit frecuentemente** en cada branch
   - Así tienes historial de cada temporada

4. **Backups de datos** antes de cambiar
   ```bash
   cp data/pasajeros.csv data/backups/pasajeros_$(date +%Y%m%d).csv
   ```

---

## 📊 Diferencias entre Temporadas

### Temporada ACTIVOS
- ✅ Checkout anticipado disponible
- ✅ Pasajeros vienen por sus medios
- ✅ Voucher compartido por SEDE
- ✅ Media pensión (desayuno + cena)
- ❌ Sin consumos individuales obligatorios

### Temporada JUBILADOS
- ❌ SIN checkout anticipado
- ✅ Traslado incluido (horarios fijos)
- ✅ Voucher individual por persona/familia
- ✅ Pensión completa (desayuno + almuerzo + cena)
- ✅ Consumos individuales por pasajero

---

## 🔍 Verificar qué Sistema estás Usando

Abre `templates/ficha_habitacion.html` y busca:

**Sistema JUBILADOS:**
```html
<!-- Solo aparece si es checkout hoy -->
{% if habitacion.es_checkout_hoy %}
  <div class="alert alert-danger">
    🚪 CHECK-OUT PROGRAMADO PARA HOY
    El huésped tiene traslado incluido...
  </div>
{% endif %}
```

**Sistema ACTIVOS:**
```html
<!-- Aparece siempre el botón de checkout anticipado -->
{% if habitacion.es_checkout_hoy %}
  ...
{% else %}
  <div class="alert alert-warning">
    ⚠️ Check-out Anticipado
    Si el huésped se retira antes...
  </div>
{% endif %}
```

---

## 📝 Notas de Mantenimiento

- **Fecha de creación:** 1 de Marzo 2026
- **Última actualización:** 1 de Marzo 2026
- **Branch actual:** temporada-jubilados
- **Próximo cambio:** Junio 2026 → temporada-activos

---

## 🚀 Script de Cambio Automatizado

Puedes usar el script `cambiar_temporada.sh`:

```bash
./cambiar_temporada.sh activos    # Cambiar a trabajadores activos
./cambiar_temporada.sh jubilados  # Cambiar a trabajadores jubilados
```
