
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd


COLUMNAS_PASAJEROS = [
    'id_estadia',
    'Nro. habitación',
    'Apellido y nombre',
    'Fecha de ingreso',
    'Fecha de egreso',
    'Voucher'
]

COLUMNAS_CONSUMOS = [
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
    'motivo_anulacion'
]


def leer_csv_seguro(archivo, columnas_esperadas):
    """
    Lee un CSV sin modificar el archivo original.
    Garantiza la presencia de las columnas esperadas.
    """

    try:
        df = pd.read_csv(
            archivo,
            dtype=str,
            keep_default_na=False,
            encoding='utf-8'
        )

    except FileNotFoundError:
        return pd.DataFrame(columns=columnas_esperadas)

    for columna in columnas_esperadas:
        if columna not in df.columns:
            df[columna] = ''

    return df


def leer_pasajeros(archivo_pasajeros):
    """Lee los pasajeros sin modificar el CSV original."""

    return leer_csv_seguro(
        archivo_pasajeros,
        COLUMNAS_PASAJEROS
    )


def leer_consumos(archivo_consumos):
    """Lee los consumos sin modificar el CSV original."""

    return leer_csv_seguro(
        archivo_consumos,
        COLUMNAS_CONSUMOS
    )


def obtener_pasajeros_con_salida(df_pasajeros, fecha_referencia=None):
    """
    Selecciona pasajeros cuya fecha de egreso coincide
    exactamente con la fecha de referencia.

    Las fechas inválidas o incompletas se excluyen.
    No modifica el DataFrame original.
    """

    if fecha_referencia is None:
        fecha_referencia = date.today()

    elif isinstance(fecha_referencia, str):
        fecha_referencia = datetime.strptime(
            fecha_referencia,
            '%d/%m/%Y'
        ).date()

    elif isinstance(fecha_referencia, datetime):
        fecha_referencia = fecha_referencia.date()

    df = df_pasajeros.copy()

    fechas_ingreso = pd.to_datetime(
        df['Fecha de ingreso'],
        format='%d/%m/%Y',
        errors='coerce'
    )

    fechas_egreso = pd.to_datetime(
        df['Fecha de egreso'],
        format='%d/%m/%Y',
        errors='coerce'
    )

    fecha_comparacion = pd.Timestamp(fecha_referencia)

    mascara = (
        fechas_ingreso.notna()
        & fechas_egreso.notna()
        & (fechas_ingreso <= fecha_comparacion)
        & (fechas_egreso == fecha_comparacion)
        & df['id_estadia'].str.strip().ne('')
    )

    return df.loc[mascara].copy()


def vincular_consumos_bebidas(df_salidas, df_consumos):
    """
    Vincula consumos de bebidas con las estadías que tienen salida.

    Devuelve:
    - totales_por_estadia: importes confirmados por estadía.
    - detalle_confirmado: consumos que integran esos importes, con monto_confirmado validado.
    - pendientes: consumos sin id_estadia de habitaciones con salida.
    - inconsistencias: consumos con datos que requieren revisión.
    - estadias_duplicadas: registros del padrón con id_estadia repetido.

    Los consumos anulados nunca se contabilizan.
    Solo se contabilizan consumos con estado vigente.
    """

    # Normalizar identificadores del padrón.
    ids = df_salidas['id_estadia'].astype(str).str.strip()

    # Detectar identificadores duplicados.
    mascara_duplicados = (
        ids.ne('')
        & ids.duplicated(keep=False)
    )

    estadias_duplicadas = df_salidas.loc[
        mascara_duplicados
    ].copy()

    ids_duplicados = set(ids[mascara_duplicados])

    # Inicializar los totales.
    # Los identificadores duplicados conservan total cero,
    # pero quedan identificados separadamente para revisión.
    totales = {
        id_estadia: Decimal('0')
        for id_estadia in ids
        if id_estadia
    }

    ids_salidas = set(totales.keys())

    habitaciones_salida = set(
        df_salidas['Nro. habitación']
        .astype(str)
        .str.strip()
    )

    confirmados = []
    pendientes = []
    inconsistencias = []

    for _, consumo in df_consumos.iterrows():

        categoria = str(
            consumo.get('categoria', '')
        ).strip().lower()

        # El informe solamente contempla bebidas.
        if categoria != 'bebidas':
            continue

        id_estadia = str(
            consumo.get('id_estadia', '')
        ).strip()

        habitacion_consumo = str(
            consumo.get('habitacion', '')
        ).strip()

        # Determinar si el consumo pertenece al alcance del informe.
        if id_estadia:

            # Consumos de estadías que no salen hoy.
            if id_estadia not in ids_salidas:
                continue

            # Identificador duplicado: no se puede atribuir con certeza.
            if id_estadia in ids_duplicados:
                inconsistencias.append(consumo.to_dict())
                continue

        else:

            # Sin identificador, solo interesa si la habitación
            # tiene una salida en la fecha del informe.
            if habitacion_consumo not in habitaciones_salida:
                continue

        estado = str(
            consumo.get('estado', '')
        ).strip().lower()

        # Los consumos anulados nunca se contabilizan.
        if estado == 'anulado':
            continue

        # Solo se contabilizan consumos vigentes.
        if estado != 'vigente':
            inconsistencias.append(consumo.to_dict())
            continue

        # Sin identificador: queda pendiente de revisión.
        if not id_estadia:
            pendientes.append(consumo.to_dict())
            continue

        # Verificar que la habitación coincida con el padrón.
        estadia = df_salidas.loc[
            ids == id_estadia
        ].iloc[0]

        habitacion_padron = str(
            estadia['Nro. habitación']
        ).strip()

        if habitacion_padron != habitacion_consumo:
            inconsistencias.append(consumo.to_dict())
            continue

        # Validar el importe.
        try:
            monto_confirmado = Decimal(str(consumo.get('monto', '')))

            if not monto_confirmado.is_finite() or monto_confirmado < 0:
                raise ValueError('Importe inválido')

        except (InvalidOperation, ValueError):
            inconsistencias.append(consumo.to_dict())
            continue

        # Incorporar el consumo confirmado.
        totales[id_estadia] += monto_confirmado
        registro = consumo.to_dict()
        registro['monto_confirmado'] = monto_confirmado
        confirmados.append(registro)

    return {
        'totales_por_estadia': totales,
        'detalle_confirmado': pd.DataFrame(confirmados),
        'pendientes': pd.DataFrame(pendientes),
        'inconsistencias': pd.DataFrame(inconsistencias),
        'estadias_duplicadas': estadias_duplicadas
    }


def clave_cuenta(estadia):
    """Identifica una cuenta con el mismo criterio usado en el pase."""
    return (
        str(estadia.get('Nro. habitación', '')).strip(),
        str(estadia.get('Voucher', '')).strip()
    )


def consolidar_salidas_por_habitacion(df_salidas, totales_por_estadia):
    """
    Consolida las salidas por habitación y voucher.

    El primer pasajero encontrado en cada grupo se utiliza
    como titular, respetando el orden original del CSV.

    Los consumos se suman por id_estadia.
    """

    filas = {}

    for _, estadia in df_salidas.iterrows():

        habitacion, voucher = clave_cuenta(estadia)

        titular = str(
            estadia.get('Apellido y nombre', '')
        ).strip()

        clave = (habitacion, voucher)

        fila = filas.setdefault(
            clave,
            {
                'habitacion': habitacion,
                'titular': titular,
                'bebidas': Decimal('0')
            }
        )

        id_estadia = str(
            estadia.get('id_estadia', '')
        ).strip()

        fila['bebidas'] += Decimal(str(totales_por_estadia.get(
            id_estadia,
            0
        )))

    return (
     pd.DataFrame(
         filas.values(),
         columns=['habitacion', 'titular', 'bebidas']
    )
     .sort_values(
         by='habitacion',
         key=lambda columna:
     pd.to_numeric(columna, errors='coerce'),
       kind='stable',
       na_position='last'
    )
    .reset_index(drop=True)
)
