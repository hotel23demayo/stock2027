#!/bin/bash

# 🔄 Script de Cambio de Temporada
# Uso: ./cambiar_temporada.sh [activos|jubilados]

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Función de ayuda
mostrar_ayuda() {
    echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}    🏨 Sistema de Gestión Hotelera - Cambio de Temporada${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
    echo ""
    echo "Uso: $0 [activos|jubilados]"
    echo ""
    echo "Temporadas disponibles:"
    echo "  • activos    → Trabajadores activos (Ene-Feb, Jun-Sep)"
    echo "  • jubilados  → Trabajadores jubilados (Mar-May, Oct-Dic)"
    echo ""
    exit 1
}

adquirir_bloqueo_consumos() {
    RUTA_CONSUMOS=$(readlink -f -- data/consumos_diarios.csv) || {
        echo "No se pudo resolver la ruta de consumos." >&2
        return 1
    }
    exec {BLOQUEO_CONSUMOS}>>"${RUTA_CONSUMOS}.lock" || {
        echo "No se pudo abrir el archivo de bloqueo de consumos." >&2
        return 1
    }
    flock -x "$BLOQUEO_CONSUMOS" || {
        echo "No se pudo adquirir el bloqueo de consumos." >&2
        return 1
    }
}

# Verificar argumento
if [ $# -eq 0 ]; then
    mostrar_ayuda
fi

TEMPORADA=$1

# Validar temporada
if [ "$TEMPORADA" != "activos" ] && [ "$TEMPORADA" != "jubilados" ]; then
    echo -e "${RED}❌ Error: Temporada inválida '$TEMPORADA'${NC}"
    mostrar_ayuda
fi

# Verificar que estamos en un repositorio Git
if [ ! -d .git ]; then
    echo -e "${RED}❌ Error: No estás en un repositorio Git${NC}"
    exit 1
fi

# Mostrar branch actual
BRANCH_ACTUAL=$(git branch --show-current)
echo -e "${BLUE}📍 Branch actual: ${YELLOW}$BRANCH_ACTUAL${NC}"

# Confirmar cambio
echo ""
echo -e "${YELLOW}¿Deseas cambiar a temporada ${GREEN}$TEMPORADA${YELLOW}?${NC}"
echo -e "${YELLOW}Esto cambiará completamente el sistema de gestión.${NC}"
read -p "Presiona Enter para continuar o Ctrl+C para cancelar..."

# Guardar cambios pendientes
echo ""
echo -e "${BLUE}📦 Guardando cambios pendientes...${NC}"
git add .
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
git commit -m "💾 Guardado automático antes de cambiar a temporada $TEMPORADA - $TIMESTAMP" 2>/dev/null || echo "No hay cambios que guardar"

adquirir_bloqueo_consumos || exit 1

# Hacer backup de datos actuales
echo ""
echo -e "${BLUE}💾 Creando backup de datos...${NC}"
mkdir -p data/backups || exit 1
if [ -f data/pasajeros.csv ]; then
    cp data/pasajeros.csv "data/backups/pasajeros_backup_${TIMESTAMP}.csv"
    echo -e "${GREEN}✅ Backup creado: pasajeros_backup_${TIMESTAMP}.csv${NC}"
fi

if [ -f "$RUTA_CONSUMOS" ]; then
    if ! cp "$RUTA_CONSUMOS" "data/backups/consumos_backup_${TIMESTAMP}.csv"; then
        echo "No se pudo respaldar el archivo de consumos; se canceló el cambio." >&2
        exit 1
    fi
    echo -e "${GREEN}✅ Backup creado: consumos_backup_${TIMESTAMP}.csv${NC}"
fi

# Cambiar de branch
BRANCH_DESTINO="temporada-$TEMPORADA"
echo ""
echo -e "${BLUE}🔄 Cambiando a branch: ${GREEN}$BRANCH_DESTINO${NC}"

# Verificar si el branch existe
if git show-ref --verify --quiet "refs/heads/$BRANCH_DESTINO"; then
    # El branch existe, cambiamos a él
    git checkout "$BRANCH_DESTINO"
else
    echo -e "${YELLOW}⚠️  El branch $BRANCH_DESTINO no existe. ¿Deseas crearlo?${NC}"
    read -p "Presiona Enter para crear o Ctrl+C para cancelar..."
    git checkout -b "$BRANCH_DESTINO"
fi

# Limpiar datos para nueva temporada
echo ""
echo -e "${BLUE}🧹 Limpiando datos de temporada anterior...${NC}"

# Resetear consumos
if [ "$(readlink -f -- data/consumos_diarios.csv)" != "$RUTA_CONSUMOS" ]; then
    echo "La ruta de consumos cambió durante el cambio de temporada." >&2
    exit 1
fi
TEMPORAL_CONSUMOS=$(mktemp "${RUTA_CONSUMOS}.tmp.XXXXXX") || {
    echo "No se pudo crear el archivo temporal de consumos." >&2
    exit 1
}
trap 'rm -f -- "$TEMPORAL_CONSUMOS"' EXIT
if [ -e "$RUTA_CONSUMOS" ]; then
    chmod --reference="$RUTA_CONSUMOS" "$TEMPORAL_CONSUMOS" || exit 1
else
    chmod =rw "$TEMPORAL_CONSUMOS" || exit 1
fi
if ! printf '%s\n' "fecha,habitacion,pasajero,categoria,monto" > "$TEMPORAL_CONSUMOS" ||
   ! mv -fT -- "$TEMPORAL_CONSUMOS" "$RUTA_CONSUMOS"; then
    echo "No se pudo reiniciar el archivo de consumos." >&2
    exit 1
fi
trap - EXIT
exec {BLOQUEO_CONSUMOS}>&-
echo -e "${GREEN}✅ Consumos reseteados${NC}"

# Información sobre pasajeros.csv
echo ""
echo -e "${YELLOW}⚠️  IMPORTANTE: Debes cargar el CSV de pasajeros para esta temporada${NC}"
echo -e "${YELLOW}   Elimina o reemplaza: ${BLUE}data/pasajeros.csv${NC}"
echo -e "${YELLOW}   Carga el archivo correspondiente a temporada $TEMPORADA${NC}"

# Resumen
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✅ CAMBIO DE TEMPORADA COMPLETADO             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "📊 ${BLUE}Temporada activa:${NC} ${GREEN}$TEMPORADA${NC}"
echo -e "📁 ${BLUE}Branch actual:${NC} ${GREEN}$(git branch --show-current)${NC}"
echo -e "💾 ${BLUE}Backups guardados en:${NC} data/backups/"
echo ""

# Verificar características por temporada
if [ "$TEMPORADA" = "activos" ]; then
    echo -e "${BLUE}🔧 Sistema configurado para TRABAJADORES ACTIVOS:${NC}"
    echo "   ✅ Checkout anticipado disponible"
    echo "   ✅ Pasajeros vienen por sus medios"
    echo "   ✅ Voucher compartido por SEDE"
    echo "   ✅ Media pensión"
else
    echo -e "${BLUE}🔧 Sistema configurado para TRABAJADORES JUBILADOS:${NC}"
    echo "   ✅ Sin checkout anticipado"
    echo "   ✅ Traslado incluido (horarios fijos)"
    echo "   ✅ Voucher individual por persona/familia"
    echo "   ✅ Pensión completa"
    echo "   ✅ Consumos individuales por pasajero"
fi

echo ""
echo -e "${YELLOW}📝 Próximos pasos:${NC}"
echo "   1. Cargar archivo CSV de pasajeros en data/pasajeros.csv"
echo "   2. Verificar que los datos estén correctos"
echo "   3. Iniciar servidor: python app.py o flask run"
echo ""
