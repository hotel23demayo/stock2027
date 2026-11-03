#!/usr/bin/env python3
"""
Reinicia los datos operativos para comenzar el seguimiento real desde cero.

Vacía (conservando solo la fila de encabezados):
  - data/consumos_diarios.csv  (historial de consumos y bebidas)
  - data/pasajeros.csv         (pasajeros y reservas, incluidas las express)

Nunca modifica data/catalogo_productos.csv (catálogo y precios).
Antes de vaciar, copia los archivos a data/backups/reinicio_AAAAMMDD_HHMMSS/.

Uso:
    python3 reiniciar_datos.py --simular
    python3 reiniciar_datos.py
    python3 reiniciar_datos.py --mantener-pasajeros
    python3 reiniciar_datos.py --yes
"""

import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DIRECTORIO_DATOS = RAIZ / 'data'
PALABRA_CONFIRMACION = 'REINICIAR'

ARCHIVO_CONSUMOS = 'consumos_diarios.csv'
ARCHIVO_PASAJEROS = 'pasajeros.csv'


def _encabezado_consumos():
    from core.consumos import CONSUMOS_COLUMNS
    return list(CONSUMOS_COLUMNS)


def _leer_encabezado(ruta):
    """Devuelve el encabezado existente o None si el archivo no se puede leer."""
    try:
        with open(ruta, newline='', encoding='utf-8-sig') as archivo:
            return next(csv.reader(archivo), None)
    except OSError:
        return None


def _contar_filas(ruta):
    try:
        with open(ruta, newline='', encoding='utf-8-sig') as archivo:
            return max(sum(1 for _ in csv.reader(archivo)) - 1, 0)
    except OSError:
        return 0


def _escribir_encabezado(ruta, encabezado):
    with open(ruta, 'w', newline='', encoding='utf-8') as archivo:
        csv.writer(archivo).writerow(encabezado)


def planificar(directorio_datos, mantener_pasajeros=False):
    """Lista los archivos a reiniciar con su encabezado de destino."""
    plan = []

    ruta = directorio_datos / ARCHIVO_CONSUMOS
    plan.append({
        'ruta': ruta,
        'encabezado': _encabezado_consumos(),
        'filas': _contar_filas(ruta) if ruta.exists() else 0,
        'existe': ruta.exists(),
    })

    if not mantener_pasajeros:
        ruta = directorio_datos / ARCHIVO_PASAJEROS
        encabezado = _leer_encabezado(ruta) if ruta.exists() else None
        plan.append({
            'ruta': ruta,
            # Sin pasajeros.csv previo no hay estructura que conservar.
            'encabezado': encabezado,
            'filas': _contar_filas(ruta) if ruta.exists() else 0,
            'existe': ruta.exists(),
        })

    return plan


def reiniciar(directorio_datos, mantener_pasajeros=False, simular=False, ahora=None):
    """
    Respalda y vacía los archivos operativos.

    Returns:
        (plan, carpeta_backup). carpeta_backup es None en simulación o si no
        había archivos existentes que respaldar.
    """
    directorio_datos = Path(directorio_datos)
    plan = planificar(directorio_datos, mantener_pasajeros)

    if simular:
        return plan, None

    existentes = [item for item in plan if item['existe']]
    carpeta_backup = None

    if existentes:
        marca = (ahora or datetime.now()).strftime('%Y%m%d_%H%M%S')
        carpeta_backup = directorio_datos / 'backups' / f'reinicio_{marca}'
        carpeta_backup.mkdir(parents=True, exist_ok=False)
        for item in existentes:
            shutil.copy2(item['ruta'], carpeta_backup / item['ruta'].name)
        # El reinicio solo continúa si cada copia quedó completa.
        for item in existentes:
            copia = carpeta_backup / item['ruta'].name
            if copia.stat().st_size != item['ruta'].stat().st_size:
                raise RuntimeError(f'Backup incompleto de {item["ruta"].name}; no se modificó nada.')

    for item in plan:
        if item['encabezado']:
            _escribir_encabezado(item['ruta'], item['encabezado'])

    return plan, carpeta_backup


def _imprimir_plan(plan):
    for item in plan:
        nombre = item['ruta'].name
        if not item['existe']:
            estado = 'no existe' + (' (se creará vacío)' if item['encabezado'] else ' (se omite)')
        else:
            estado = f'{item["filas"]} fila(s) a eliminar'
        print(f'  - data/{nombre}: {estado}')
    print('  - data/catalogo_productos.csv: NO se modifica')


def main(argumentos=None):
    parser = argparse.ArgumentParser(
        description='Reinicia consumos y pasajeros para comenzar el seguimiento real desde cero.'
    )
    parser.add_argument('--simular', action='store_true',
                        help='Muestra qué se haría sin modificar nada.')
    parser.add_argument('--mantener-pasajeros', action='store_true',
                        help='Vacía solo los consumos y conserva pasajeros.csv.')
    parser.add_argument('--yes', '-y', action='store_true',
                        help='Omite la confirmación interactiva.')
    parser.add_argument('--datos', default=str(DIRECTORIO_DATOS),
                        help='Carpeta de datos (por defecto ./data).')
    args = parser.parse_args(argumentos)

    directorio = Path(args.datos)
    if not directorio.is_dir():
        print(f'No existe la carpeta de datos: {directorio}', file=sys.stderr)
        return 1

    plan = planificar(directorio, args.mantener_pasajeros)
    print('Se reiniciarán los siguientes datos:' if not args.simular else 'SIMULACIÓN (no se modifica nada):')
    _imprimir_plan(plan)

    if args.simular:
        return 0

    print('\nIMPORTANTE: cierre la aplicación (python3 app.py) antes de continuar.')
    print('Se creará un backup en data/backups/ antes de vaciar los archivos.')

    if not args.yes:
        respuesta = input(f'Escriba {PALABRA_CONFIRMACION} para confirmar: ').strip()
        if respuesta != PALABRA_CONFIRMACION:
            print('Cancelado. No se modificó nada.')
            return 1

    _, carpeta_backup = reiniciar(directorio, args.mantener_pasajeros)

    if carpeta_backup:
        print(f'\nBackup guardado en: {carpeta_backup}')
    print('Reinicio completo. El sistema comienza desde cero.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
