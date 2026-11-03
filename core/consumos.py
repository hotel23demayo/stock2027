"""
Módulo para gestionar operaciones de consumos individuales por habitación.
"""

import pandas as pd
import os
import uuid
from datetime import datetime
from pandas.errors import EmptyDataError
from pathlib import Path


CONSUMOS_COLUMNS = [
    'id_consumo',
    'id_estadia',
    'fecha',
    'habitacion',
    'pasajero',
    'categoria',
    'item',
    'cantidad',
    'precio_unitario',
    'monto',
    'estado',
    'fecha_anulacion',
    'motivo_anulacion',
]


CANTIDADES_RAPIDAS = [1, 2, 3, 4, 6]
RUTA_CATALOGO_PRODUCTOS = (
    Path(__file__).resolve().parent.parent
    / 'data'
    / 'catalogo_productos.csv'
)


ICONOS_CATEGORIA = {
    'gaseosas': '🥤',
    'aguas': '💧',
    'saborizadas': '🧃',
    'cervezas': '🍺',
    'vinos': '🍷',
    'cafetería': '☕',
}


def obtener_catalogo_bebidas():
    """Lee el catálogo independiente de productos para la interfaz."""
    try:
        df = pd.read_csv(RUTA_CATALOGO_PRODUCTOS)
    except (FileNotFoundError, EmptyDataError):
        print(f"No se pudo leer el catálogo: {RUTA_CATALOGO_PRODUCTOS}")
        return []

    columnas_requeridas = {
        'codigo', 'producto', 'categoria', 'sector', 'precio_actual'
    }
    if not columnas_requeridas.issubset(df.columns):
        raise ValueError(
            'El catálogo no contiene todas las columnas requeridas.'
        )

    catalogo = []

    for _, fila in df.iterrows():
        codigo = str(fila['codigo']).strip()
        nombre = str(fila['producto']).strip()
        categoria = str(fila['categoria']).strip()
        sector = str(fila['sector']).strip()

        precio = pd.to_numeric(fila['precio_actual'], errors='coerce')
        habilitado = pd.notna(precio) and float(precio) >= 0

        catalogo.append({
            'codigo': codigo,
            'nombre': nombre,
            'icono': ICONOS_CATEGORIA.get(
                categoria.lower(), '🛒'
            ),
            'precio': float(precio) if habilitado else None,
            'habilitado': habilitado,
            'categoria': categoria,
            'sector': sector,
        })

    return catalogo



def _leer_archivo_consumos(archivo_consumos):
    """Lee el CSV de consumos y garantiza las columnas esperadas."""
    if not os.path.exists(archivo_consumos):
        return pd.DataFrame(columns=CONSUMOS_COLUMNS)

    try:
        df = pd.read_csv(archivo_consumos)
    except EmptyDataError:
        return pd.DataFrame(columns=CONSUMOS_COLUMNS)

    for columna in CONSUMOS_COLUMNS:
        if columna in df.columns:
            continue

        if columna == 'item':
            df[columna] = ''
        elif columna == 'cantidad':
            df[columna] = 1
        elif columna == 'precio_unitario':
            df[columna] = pd.to_numeric(df['monto'], errors='coerce') if 'monto' in df.columns else 0

        elif columna == 'estado':
            df[columna] = 'vigente'
        elif columna in ('fecha_anulacion', 'motivo_anulacion'):
            df[columna] = ''

        elif columna == 'id_consumo':
            df[columna] = pd.NA

        else:
            df[columna] = pd.NA

    # Migración persistente: cada registro histórico recibe un ID una sola vez.
    ids = df['id_consumo'].fillna('').astype(str).str.strip()
    faltan_ids = ids.eq('')
    if faltan_ids.any():
        df.loc[faltan_ids, 'id_consumo'] = [uuid.uuid4().hex for _ in range(int(faltan_ids.sum()))]

    # Normalizar campos de estado sin cambiar consumos históricos.
    df['estado'] = df['estado'].fillna('vigente').replace('', 'vigente')
    df['fecha_anulacion'] = df['fecha_anulacion'].fillna('')
    df['motivo_anulacion'] = df['motivo_anulacion'].fillna('')

    columnas_ordenadas = CONSUMOS_COLUMNS + [c for c in df.columns if c not in CONSUMOS_COLUMNS]
    resultado = df[columnas_ordenadas]

    # Guardar la migración para que los IDs permanezcan estables entre lecturas.
    if faltan_ids.any():
        resultado.to_csv(archivo_consumos, index=False)

    return resultado


def _filtrar_consumos_por_estadia(consumos, id_estadia):
    """Filtra por uno o varios IDs; una lista vacía no devuelve consumos."""
    if id_estadia is None:
        return consumos

    if isinstance(id_estadia, (list, tuple, set)):
        ids_estadia = {
            str(identificador).strip()
            for identificador in id_estadia
            if (
                identificador is not None
                and pd.notna(identificador)
                and str(identificador).strip()
            )
        }
    else:
        identificador = str(id_estadia).strip()
        ids_estadia = {identificador} if identificador else set()

    if not ids_estadia or 'id_estadia' not in consumos.columns:
        return consumos.iloc[0:0].copy()

    ids_registros = (
        consumos['id_estadia']
        .fillna('')
        .astype(str)
        .str.strip()
    )
    return consumos[ids_registros.isin(ids_estadia)].copy()


def obtener_cantidad_consumos_sin_estadia(
    num_habitacion,
    archivo_consumos='data/consumos_diarios.csv'
):
    """Cuenta consumos de la habitación sin identidad, sin escribir el CSV."""
    if not os.path.exists(archivo_consumos):
        return 0

    try:
        df = pd.read_csv(archivo_consumos, dtype={'id_estadia': str})
    except EmptyDataError:
        return 0

    if df.empty or 'habitacion' not in df.columns:
        return 0

    habitaciones = pd.to_numeric(df['habitacion'], errors='coerce')
    if 'id_estadia' in df.columns:
        ids_estadia = df['id_estadia'].fillna('').astype(str).str.strip()
    else:
        ids_estadia = pd.Series('', index=df.index)

    return int(
        (
            (habitaciones == int(num_habitacion))
            & ids_estadia.eq('')
        ).sum()
    )


def obtener_consumos_habitacion(
    num_habitacion,
    archivo_consumos='data/consumos_diarios.csv',
    id_estadia=None
):
    """
    Obtiene consumos por habitación y, opcionalmente, por estadía.
    Si no se entrega ``id_estadia``, conserva el alcance histórico por habitación.

    Returns:
        DataFrame con los consumos ordenados por fecha
    """
    df = _leer_archivo_consumos(archivo_consumos)

    if df.empty or 'habitacion' not in df.columns:
        return pd.DataFrame(columns=CONSUMOS_COLUMNS)

    habitaciones = pd.to_numeric(df['habitacion'], errors='coerce').fillna(-1).astype(int)
    consumos_hab = df[habitaciones == int(num_habitacion)].copy()
    consumos_hab = _filtrar_consumos_por_estadia(
        consumos_hab,
        id_estadia
    )

    # Agregar índice para identificar cada consumo
    if not consumos_hab.empty:
        consumos_hab['indice'] = range(len(consumos_hab))

    return consumos_hab


def obtener_total_consumos(
    num_habitacion,
    archivo_consumos='data/consumos_diarios.csv',
    id_estadia=None
):
    """
    Calcula el total de consumos de una habitación y, opcionalmente, una estadía.

    Returns:
        Diccionario con totales por categoría y total general
    """
    consumos = obtener_consumos_habitacion(
        num_habitacion,
        archivo_consumos,
        id_estadia
    )

    if 'estado' in consumos.columns:
        consumos = consumos[
            consumos['estado'].fillna('vigente').astype(str).str.lower()
            != 'anulado'
        ]


    if consumos.empty:
        return {
            'Bebidas': 0,
            'Estadía': 0,
            'Map': 0,
            'total': 0
        }

    totales = {
        'Bebidas': consumos[consumos['categoria'] == 'Bebidas']['monto'].sum() if 'Bebidas' in consumos['categoria'].values else 0,
        'Estadía': consumos[consumos['categoria'] == 'Estadía']['monto'].sum() if 'Estadía' in consumos['categoria'].values else 0,
        'Map': consumos[consumos['categoria'] == 'Map']['monto'].sum() if 'Map' in consumos['categoria'].values else 0,
    }
    totales['total'] = sum(totales.values())

    return totales


def obtener_consumos_por_pasajero(
    num_habitacion,
    archivo_consumos='data/consumos_diarios.csv',
    id_estadia=None
):
    """
    Agrupa los consumos de una habitación por pasajero individual.
    Útil cuando hay múltiples personas con distintos vouchers en una habitación.

    Args:
        num_habitacion (int): Número de habitación
        archivo_consumos (str): Ruta al archivo CSV de consumos

    Returns:
        Diccionario donde la key es el nombre del pasajero y el valor es:
        {
            'consumos': lista de consumos,
            'totales': diccionario con totales por categoría,
            'total_general': suma total
        }
    """
    consumos = obtener_consumos_habitacion(
        num_habitacion,
        archivo_consumos,
        id_estadia
    )

    if consumos.empty:
        return {}

    consumos_por_identidad = {}

    for _, row in consumos.iterrows():
        pasajero = str(row['pasajero'])
        identificador = (
            ''
            if pd.isna(row.get('id_estadia', ''))
            else str(row.get('id_estadia', '')).strip()
        )
        clave = (identificador, pasajero)

        if clave not in consumos_por_identidad:
            consumos_por_identidad[clave] = {
                'consumos': [],
                'totales': {'Bebidas': 0, 'Estadía': 0, 'Map': 0},
                'total_general': 0,
                'id_estadia': identificador,
            }

        # Agregar consumo a la lista
        consumos_por_identidad[clave]['consumos'].append({
            'indice': row.get('indice', 0),
            'id_consumo': str(row.get('id_consumo', '')),
            'id_estadia': '' if pd.isna(row.get('id_estadia', '')) else str(row.get('id_estadia', '')).strip(),
            'fecha': row['fecha'],
            'categoria': row['categoria'],
            'item': '' if pd.isna(row.get('item', '')) else row.get('item', ''),
            'cantidad': '' if pd.isna(row.get('cantidad', '')) else row.get('cantidad', ''),
            'precio_unitario': '' if pd.isna(row.get('precio_unitario', '')) else row.get('precio_unitario', ''),
            'monto': float(row['monto']),
            'estado': 'vigente' if pd.isna(row.get('estado', 'vigente')) else str(row.get('estado', 'vigente')).strip().lower(),
            'fecha_anulacion': '' if pd.isna(row.get('fecha_anulacion', '')) else row.get('fecha_anulacion', ''),
            'motivo_anulacion': '' if pd.isna(row.get('motivo_anulacion', '')) else row.get('motivo_anulacion', '')
        })


        # Los anulados se conservan en el historial, pero no suman.
        estado = str(row.get('estado', 'vigente')).strip().lower()

        if estado != 'anulado':
            categoria = row['categoria']

            if categoria in consumos_por_identidad[clave]['totales']:
                consumos_por_identidad[clave]['totales'][categoria] += float(row['monto'])

            consumos_por_identidad[clave]['total_general'] += float(row['monto'])


    consumos_por_pasajero = {}
    for (identificador, pasajero), datos in consumos_por_identidad.items():
        nombre = pasajero
        if nombre in consumos_por_pasajero:
            sufijo = identificador[:8] if identificador else 'sin ID'
            nombre = f'{pasajero} ({sufijo})'
            while nombre in consumos_por_pasajero:
                nombre += '*'
        consumos_por_pasajero[nombre] = datos

    return consumos_por_pasajero


def obtener_total_consumos_pasajero(
    num_habitacion,
    nombre_pasajero,
    archivo_consumos='data/consumos_diarios.csv',
    id_estadia=None
):
    """
    Calcula el total de consumos de un pasajero específico en una habitación.

    Args:
        num_habitacion (int): Número de habitación
        nombre_pasajero (str): Nombre completo del pasajero
        archivo_consumos (str): Ruta al archivo CSV de consumos

    Returns:
        Diccionario con totales por categoría y total general del pasajero
    """
    consumos = obtener_consumos_habitacion(
        num_habitacion,
        archivo_consumos,
        id_estadia
    )

    if consumos.empty:
        return {
            'Bebidas': 0,
            'Estadía': 0,
            'Map': 0,
            'total': 0
        }

    # Filtrar solo consumos de este pasajero
    consumos_pasajero = consumos[consumos['pasajero'] == nombre_pasajero]

    if 'estado' in consumos_pasajero.columns:
        consumos_pasajero = consumos_pasajero[
            consumos_pasajero['estado'].fillna('vigente').astype(str).str.lower()
            != 'anulado'
        ]


    if consumos_pasajero.empty:
        return {
            'Bebidas': 0,
            'Estadía': 0,
            'Map': 0,
            'total': 0
        }

    totales = {
        'Bebidas': consumos_pasajero[consumos_pasajero['categoria'] == 'Bebidas']['monto'].sum() if 'Bebidas' in consumos_pasajero['categoria'].values else 0,
        'Estadía': consumos_pasajero[consumos_pasajero['categoria'] == 'Estadía']['monto'].sum() if 'Estadía' in consumos_pasajero['categoria'].values else 0,
        'Map': consumos_pasajero[consumos_pasajero['categoria'] == 'Map']['monto'].sum() if 'Map' in consumos_pasajero['categoria'].values else 0,
    }
    totales['total'] = sum(totales.values())

    return totales


def agregar_consumo(num_habitacion, categoria, monto, pasajero, archivo_consumos='data/consumos_diarios.csv', id_estadia=None):
    """
    Agrega un nuevo consumo a una habitación.

    Returns:
        True si se agregó correctamente, False en caso contrario
    """
    return agregar_consumo_detallado(
        num_habitacion=num_habitacion,
        categoria=categoria,
        monto=monto,
        pasajero=pasajero,
        archivo_consumos=archivo_consumos,
        id_estadia=id_estadia
    )


def agregar_consumo_detallado(
    num_habitacion,
    categoria,
    monto,
    pasajero,
    item='',
    cantidad=1,
    precio_unitario=None,
    archivo_consumos='data/consumos_diarios.csv',
    id_estadia=None
):
    """Agrega un consumo permitiendo almacenar item, cantidad y precio unitario."""
    try:
        cantidad = int(cantidad) if cantidad else 1
        monto = float(monto)
        if precio_unitario is None:
            precio_unitario = monto / cantidad if cantidad else monto

        nuevo_registro = {
            'id_consumo': uuid.uuid4().hex,
            'id_estadia': str(id_estadia).strip() if id_estadia else '',
            'fecha': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'habitacion': int(num_habitacion),
            'pasajero': pasajero,
            'categoria': categoria,
            'item': item,
            'cantidad': cantidad,
            'precio_unitario': float(precio_unitario),
            'monto': monto,
            'estado': 'vigente',
            'fecha_anulacion': '',
            'motivo_anulacion': '',


        }

        df = _leer_archivo_consumos(archivo_consumos)
        if df.empty:
            df = pd.DataFrame([nuevo_registro], columns=CONSUMOS_COLUMNS)
        else:
            registro_completo = {columna: pd.NA for columna in df.columns}
            registro_completo.update(nuevo_registro)
            df.loc[len(df)] = registro_completo
        df.to_csv(archivo_consumos, index=False)
        return True
    except Exception as e:
        print(f"Error al agregar consumo: {e}")
        return False



def agregar_consumo_bebida_rapida(
    num_habitacion,
    producto_codigo,
    cantidad,
    pasajero,
    archivo_consumos='data/consumos_diarios.csv',
    id_estadia=None
):
    """Registra un producto usando el catálogo independiente y su precio vigente."""

    codigo_buscado = str(producto_codigo).strip().lower()

    catalogo = obtener_catalogo_bebidas()
    producto = next(
        (
            item for item in catalogo
            if item['codigo'].strip().lower() == codigo_buscado
        ),
        None
    )

    if not producto:
        return False, 'Producto de bebida no válido'

    if not producto['habilitado'] or producto['precio'] is None:
        return False, (
            f"El precio de {producto['nombre']} "
            "todavía no está configurado"
        )

    try:
        cantidad = int(cantidad)
    except (TypeError, ValueError):
        return False, 'Cantidad inválida'

    if cantidad <= 0:
        return False, 'La cantidad debe ser mayor a cero'

    precio_unitario = float(producto['precio'])
    total = precio_unitario * cantidad

    exito = agregar_consumo_detallado(
        num_habitacion=num_habitacion,
        categoria='Bebidas',
        monto=total,
        pasajero=pasajero,
        item=producto['nombre'],
        cantidad=cantidad,
        precio_unitario=precio_unitario,
        archivo_consumos=archivo_consumos,
        id_estadia=id_estadia
    )

    if not exito:
        return False, 'No se pudo registrar la bebida'

    return (
        True,
        f"{cantidad} x {producto['nombre']} agregado(s) "
        f"a {pasajero} por ${total:,.0f}"
    )



def eliminar_consumo_por_indice(num_habitacion, indice, archivo_consumos='data/consumos_diarios.csv'):
    """Compatibilidad temporal: la eliminación física de consumos está deshabilitada."""
    return False


def anular_consumo_por_indice(
    num_habitacion,
    indice,
    motivo,
    archivo_consumos='data/consumos_diarios.csv'
):
    """Anula un consumo sin borrar su registro histórico."""
    try:
        motivo = str(motivo).strip()
        if not motivo:
            return False

        df = _leer_archivo_consumos(archivo_consumos)
        if df.empty:
            return False

        habitaciones = (
            pd.to_numeric(df['habitacion'], errors='coerce')
            .fillna(-1)
            .astype(int)
        )
        indices_habitacion = df.index[
            habitaciones == int(num_habitacion)
        ].tolist()

        if indice < 0 or indice >= len(indices_habitacion):
            return False

        indice_global = indices_habitacion[indice]

        estado = str(df.at[indice_global, 'estado']).strip().lower()
        if estado == 'anulado':
            return False

        df.at[indice_global, 'estado'] = 'anulado'
        df.at[indice_global, 'fecha_anulacion'] = (
            datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        )
        df.at[indice_global, 'motivo_anulacion'] = motivo

        df.to_csv(archivo_consumos, index=False)
        return True

    except Exception as e:
        print(f"Error al anular consumo: {e}")
        return False



def obtener_historial_consumos(archivo_consumos='data/consumos_diarios.csv'):
    """Devuelve todos los consumos con IDs y campos de auditoría normalizados."""
    return _leer_archivo_consumos(archivo_consumos).copy()


def anular_consumo_por_id(
    num_habitacion,
    id_consumo,
    motivo,
    archivo_consumos='data/consumos_diarios.csv'
):
    """Anula por identificador estable, conservando el registro original."""
    try:
        motivo = str(motivo or '').strip()
        id_consumo = str(id_consumo or '').strip()
        if not motivo or not id_consumo:
            return False
        df = _leer_archivo_consumos(archivo_consumos)
        if df.empty or 'id_consumo' not in df.columns:
            return False
        coincidencias = df.index[df['id_consumo'].astype(str).str.strip().eq(id_consumo)].tolist()
        if len(coincidencias) != 1:
            return False
        indice = coincidencias[0]
        try:
            habitacion_registro = int(float(df.at[indice, 'habitacion']))
        except (TypeError, ValueError):
            return False
        if habitacion_registro != int(num_habitacion):
            return False
        estado = str(df.at[indice, 'estado'] or 'vigente').strip().lower()
        if estado == 'anulado':
            return False
        df.at[indice, 'estado'] = 'anulado'
        df.at[indice, 'fecha_anulacion'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        df.at[indice, 'motivo_anulacion'] = motivo
        df.to_csv(archivo_consumos, index=False)
        return True
    except Exception as e:
        print(f"Error al anular consumo por ID: {e}")
        return False


def obtener_resumen_habitacion(num_habitacion, datos_pasajero, archivo_consumos='data/consumos_diarios.csv'):
    """
    Obtiene un resumen completo de la habitación incluyendo pasajero y consumos.
    Incluye consumos separados por pasajero cuando hay múltiples personas.

    Args:
        num_habitacion (int): Número de habitación
        datos_pasajero (dict): Datos del titular de la habitación
        archivo_consumos (str): Ruta al archivo CSV de consumos

    Returns:
        Diccionario con toda la información de la habitación
    """
    from core.dashboard import obtener_todos_pasajeros_habitacion

    # Obtener TODOS los pasajeros de la habitación
    todos_pasajeros = obtener_todos_pasajeros_habitacion(num_habitacion)
    if 'ids_estadia' in datos_pasajero:
        ids_fuente = datos_pasajero.get('ids_estadia') or []
    else:
        ids_fuente = [
            pasajero.get('id_estadia', '')
            for pasajero in todos_pasajeros
        ]
        if not any(
            pd.notna(identificador) and str(identificador).strip()
            for identificador in ids_fuente
        ):
            ids_fuente = [datos_pasajero.get('id_estadia', '')]

    ids_estadia = {
        str(identificador).strip()
        for identificador in ids_fuente
        if pd.notna(identificador) and str(identificador).strip()
    }

    ids_estadia_actuales = sorted(ids_estadia)
    consumos = obtener_consumos_habitacion(
        num_habitacion,
        archivo_consumos,
        ids_estadia_actuales
    )
    totales = obtener_total_consumos(
        num_habitacion,
        archivo_consumos,
        ids_estadia_actuales
    )

    # Obtener consumos agrupados por pasajero
    consumos_por_pasajero = obtener_consumos_por_pasajero(
        num_habitacion,
        archivo_consumos,
        ids_estadia_actuales
    )

    # Convertir consumos a lista de diccionarios para el template
    lista_consumos = []

    if not consumos.empty:
        for idx, row in consumos.iterrows():
            item = row.get('item', '')
            cantidad = row.get('cantidad', '')
            precio_unitario = row.get('precio_unitario', '')
            id_consumo = row.get('id_consumo', '')
            estado = row.get('estado', 'vigente')
            fecha_anulacion = row.get('fecha_anulacion', '')
            motivo_anulacion = row.get('motivo_anulacion', '')

            # Normalizar valores vacíos o nulos
            if pd.isna(item):
                item = ''
            if pd.isna(cantidad):
                cantidad = ''
            if pd.isna(precio_unitario):
                precio_unitario = ''
            if pd.isna(id_consumo):
                id_consumo = ''
            if pd.isna(estado) or str(estado).strip() == '':
                estado = 'vigente'
            if pd.isna(fecha_anulacion):
                fecha_anulacion = ''
            if pd.isna(motivo_anulacion):
                motivo_anulacion = ''

            lista_consumos.append({
                'indice': row.get('indice', idx),
                'id_consumo': str(id_consumo),
                'id_estadia': '' if pd.isna(row.get('id_estadia', '')) else str(row.get('id_estadia', '')).strip(),
                'fecha': row['fecha'],
                'pasajero': row['pasajero'],
                'categoria': row['categoria'],
                'item': item,
                'cantidad': cantidad,
                'precio_unitario': precio_unitario,
                'monto': row['monto'],
                'estado': str(estado).strip().lower(),
                'fecha_anulacion': fecha_anulacion,
                'motivo_anulacion': motivo_anulacion
            })


    # Detectar si hay múltiples vouchers (personas que no se conocen)
    vouchers_unicos = set(p['voucher'] for p in todos_pasajeros)
    tiene_vouchers_separados = len(vouchers_unicos) > 1 and len(todos_pasajeros) > 1

    return {
        'numero': num_habitacion,
        'pasajero': datos_pasajero,
        'todos_pasajeros': todos_pasajeros,
        'consumos': lista_consumos,
        'consumos_por_pasajero': consumos_por_pasajero,
        'totales': totales,
        'cantidad_consumos': len(lista_consumos),
        'cantidad_consumos_sin_estadia': obtener_cantidad_consumos_sin_estadia(
            num_habitacion,
            archivo_consumos
        ),
        'tiene_vouchers_separados': tiene_vouchers_separados,
        'cantidad_pasajeros': len(todos_pasajeros)
    }
