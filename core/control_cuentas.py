"""Consulta preventiva de cuentas, sin modificar los archivos operativos."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

from core.pase_caja import (
    clave_cuenta,
    consolidar_salidas_por_habitacion,
    vincular_consumos_bebidas,
)


def generar_control_cuentas(pasajeros, consumos, fecha_referencia=None):
    """Consolida estadías activas y señala consumos que requieren revisión."""
    fecha = pd.Timestamp(fecha_referencia or date.today())
    ingresos = pd.to_datetime(
        pasajeros['Fecha de ingreso'], format='%d/%m/%Y', errors='coerce'
    )
    egresos = pd.to_datetime(
        pasajeros['Fecha de egreso'], format='%d/%m/%Y', errors='coerce'
    )
    activos = pasajeros.loc[(ingresos <= fecha) & (egresos >= fecha)].copy()
    observaciones = []

    def observar(motivo, registro):
        observaciones.append({'motivo': motivo, 'registro': registro})

    for _, fila in pasajeros.loc[ingresos.isna() | egresos.isna()].iterrows():
        observar('Fechas de estadía inválidas; pasajero excluido', fila.to_dict())

    ids_padron = pasajeros['id_estadia'].str.strip()
    repetidos = set(ids_padron[ids_padron.ne('') & ids_padron.duplicated(keep=False)])
    grupos = {}
    for _, fila in activos.iterrows():
        habitacion, voucher = clave_cuenta(fila)
        identificador = fila['id_estadia'].strip()
        if not habitacion or not voucher:
            observar('Habitación o voucher faltante; pasajero excluido de las cuentas', fila.to_dict())
            continue
        if not identificador:
            observar('Pasajero sin id_estadia; no se pueden atribuir consumos', fila.to_dict())
        elif identificador in repetidos:
            observar('id_estadia duplicado en el padrón; consumos excluidos', fila.to_dict())
        grupos.setdefault((habitacion, voucher), []).append(fila)

    # La vinculación y el cálculo de importes siguen la validación del pase.
    vinculacion = vincular_consumos_bebidas(activos, consumos)
    confirmados = vinculacion['detalle_confirmado'].to_dict('records')
    confirmados = [c for c in confirmados if c['id_estadia'].strip() not in repetidos]
    totales = dict(vinculacion['totales_por_estadia'])
    for identificador in repetidos:
        if identificador in totales:
            totales[identificador] = 0.0
    for registro in vinculacion['pendientes'].to_dict('records'):
        observar('Consumo sin id_estadia', registro)
    for registro in vinculacion['inconsistencias'].to_dict('records'):
        identificador = registro['id_estadia'].strip()
        coincidencias = activos.loc[activos['id_estadia'].str.strip() == identificador]
        if identificador in repetidos:
            motivo = 'Consumo con id_estadia duplicado'
        elif registro['estado'].strip().lower() != 'vigente':
            motivo = 'Estado de consumo desconocido'
        elif not identificador:
            motivo = 'Consumo sin id_estadia'
        elif not coincidencias.empty and registro['habitacion'].strip() != clave_cuenta(coincidencias.iloc[0])[0]:
            motivo = 'Habitación del consumo inconsistente'
        else:
            motivo = 'Importe de consumo inválido'
        observar(motivo, registro)

    por_id = {}
    for _, fila in activos.iterrows():
        identificador = fila['id_estadia'].strip()
        if identificador and identificador not in repetidos:
            por_id[identificador] = fila

    habitaciones_activas = {clave_cuenta(fila)[0] for _, fila in activos.iterrows()}
    periodos_por_habitacion = {}
    for indice, fila in activos.iterrows():
        habitacion = clave_cuenta(fila)[0]
        periodos_por_habitacion.setdefault(habitacion, []).append(
            (ingresos.loc[indice].date(), egresos.loc[indice].date())
        )
    habitaciones_fechas_invalidas = {
        clave_cuenta(fila)[0]
        for _, fila in pasajeros.loc[
            ingresos.isna() | egresos.isna() | (ingresos > egresos)
        ].iterrows()
    }
    ids_activos = set(activos['id_estadia'].str.strip())
    ids_duplicados_activos = set(vinculacion['estadias_duplicadas']['id_estadia'].str.strip())
    anulados = []
    for _, fila in consumos.iterrows():
        consumo = fila.to_dict()
        if consumo['categoria'].strip().lower() != 'bebidas':
            continue
        identificador = consumo['id_estadia'].strip()
        habitacion = consumo['habitacion'].strip()
        estado = consumo['estado'].strip().lower()
        if identificador in repetidos:
            if identificador in ids_activos and identificador not in ids_duplicados_activos:
                observar('Consumo con id_estadia duplicado', consumo)
            continue
        if identificador not in por_id:
            if habitacion in habitaciones_activas and identificador:
                fecha_consumo = None
                for formato in ('%d/%m/%Y %H:%M', '%d/%m/%Y',
                                '%Y-%m-%d', '%Y-%m-%d %H:%M:%S'):
                    try:
                        fecha_consumo = datetime.strptime(consumo['fecha'].strip(), formato).date()
                        break
                    except ValueError:
                        continue
                periodos = periodos_por_habitacion[habitacion]
                if fecha_consumo is not None and any(
                    ingreso < fecha_consumo <= egreso for ingreso, egreso in periodos
                ):
                    observar('Consumo de otra estadía durante el alojamiento actual', consumo)
                elif not (fecha_consumo is not None
                          and habitacion not in habitaciones_fechas_invalidas
                          and all(fecha_consumo < ingreso for ingreso, _ in periodos)):
                    observar('Consumo de origen no verificable', consumo)
            elif habitacion in habitaciones_activas and estado == 'anulado':
                observar('Consumo anulado sin id_estadia', consumo)
            continue
        if estado == 'anulado':
            if habitacion != clave_cuenta(por_id[identificador])[0]:
                observar('Consumo anulado con habitación inconsistente', consumo)
            else:
                anulados.append(consumo)

    detalles = {}
    for consumo in confirmados + anulados:
        identificador = consumo['id_estadia'].strip()
        if identificador in por_id:
            clave = clave_cuenta(por_id[identificador])
            detalles.setdefault(clave, []).append(consumo)

    cuentas = []
    for clave, filas in grupos.items():
        consolidado = consolidar_salidas_por_habitacion(pd.DataFrame(filas), totales).iloc[0]
        detalle = detalles.get(clave, [])
        unidades = Decimal(0)
        unidades_incompletas = False
        for consumo in detalle:
            if consumo['estado'].strip().lower() != 'vigente':
                continue
            try:
                cantidad = Decimal(consumo['cantidad'])
                if not cantidad.is_finite() or cantidad <= 0:
                    raise InvalidOperation
                unidades += cantidad
            except (InvalidOperation, ValueError):
                unidades_incompletas = True
                observar('Cantidad inválida o faltante en consumo confirmado', consumo)
        cuentas.append({
            'habitacion': clave[0],
            'voucher': clave[1],
            'titular': consolidado['titular'],
            'pasajeros': [fila['Apellido y nombre'].strip() for fila in filas],
            'bebidas': consolidado['bebidas'],
            'detalle': detalle,
            'unidades': unidades,
            'unidades_incompletas': unidades_incompletas,
            'tiene_consumos': any(c['estado'].strip().lower() == 'vigente' for c in detalle),
        })

    def orden(cuenta):
        try:
            return (0, int(cuenta['habitacion']))
        except ValueError:
            return (1, cuenta['habitacion'])

    cuentas.sort(key=orden)
    return {
        'cuentas': cuentas,
        'total_habitaciones': len({clave_cuenta(fila)[0] for _, fila in activos.iterrows() if clave_cuenta(fila)[0]}),
        'total_pasajeros': len(activos),
        'total_bebidas': sum(cuenta['bebidas'] for cuenta in cuentas),
        'cuentas_con_consumos': sum(cuenta['tiene_consumos'] for cuenta in cuentas),
        'observaciones': observaciones,
    }
