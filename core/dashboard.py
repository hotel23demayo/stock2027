"""
Módulo para gestionar el dashboard de habitaciones del hotel.
Calcula estados y colores según ocupación y consumos.
"""

import pandas as pd
import os
from datetime import datetime
from pandas.errors import EmptyDataError

def extraer_num_hab(valor):
    """
    Extrae el número de habitación como int, ignorando sufijos de cama como 'A', 'B', 'C'.
    Ejemplos: '227 A' → 227, '238 C' → 238, 227 → 227
    Retorna None si el valor no es parseable.
    """
    try:
        return int(str(valor).strip().split()[0])
    except (ValueError, IndexError):
        return None


# Estructura del hotel
PISOS = {
    1: list(range(101, 122)),  # 101-121 (21 habitaciones)
    2: list(range(222, 243)),  # 222-242 (21 habitaciones)
    3: list(range(343, 354)),  # 343-353 (11 habitaciones)
}

def obtener_titular_por_edad(pasajeros_lista):
    """
    Selecciona el titular de un grupo de pasajeros según la edad.
    Retorna el pasajero de mayor edad.
    
    Args:
        pasajeros_lista: lista de diccionarios con datos de pasajeros
    
    Returns:
        Diccionario con datos del titular (mayor edad)
    """
    if not pasajeros_lista:
        return None
    
    # Ordenar por edad de forma descendente
    try:
        titular = max(pasajeros_lista, key=lambda p: int(p.get('Edad', 0)))
        return titular
    except:
        # Si falla, retornar el primero
        return pasajeros_lista[0]


def obtener_habitaciones_ocupadas(archivo_pasajeros='data/pasajeros.csv'):
    """
    Obtiene la lista de habitaciones ocupadas ACTUALMENTE desde el CSV de pasajeros.
    Solo retorna habitaciones donde la fecha de ingreso ya pasó o es hoy.
    
    Para cada habitación, selecciona como titular al pasajero de mayor edad.
    Si hay múltiples habitaciones con el mismo voucher (familia), selecciona
    como titular al adulto mayor del grupo familiar completo.
    
    Retorna un diccionario con número de habitación como key y datos del titular.
    """
    if not os.path.exists(archivo_pasajeros):
        return {}
    
    df = pd.read_csv(archivo_pasajeros)
    fecha_hoy = datetime.now().strftime('%d/%m/%Y')
    
    # Filtrar pasajeros realmente activos hoy: ingreso <= hoy <= egreso
    pasajeros_activos = []
    for _, row in df.iterrows():
        fecha_ingreso = row['Fecha de ingreso']
        fecha_egreso = row.get('Fecha de egreso', '')
        
        try:
            ingreso_dt = datetime.strptime(fecha_ingreso, '%d/%m/%Y')
            egreso_dt = datetime.strptime(fecha_egreso, '%d/%m/%Y')
            hoy_dt = datetime.strptime(fecha_hoy, '%d/%m/%Y')
            
            if ingreso_dt <= hoy_dt <= egreso_dt:
                pasajeros_activos.append(row.to_dict())
        except:
            # Si hay error en la fecha, incluir por defecto
            pasajeros_activos.append(row.to_dict())
    
    # Agrupar por voucher para identificar grupos familiares
    vouchers = {}
    for pasajero in pasajeros_activos:
        voucher = str(pasajero.get('Voucher', '')).strip()
        if voucher:
            if voucher not in vouchers:
                vouchers[voucher] = []
            vouchers[voucher].append(pasajero)
    
    # Para cada grupo de voucher, seleccionar el titular (mayor edad)
    titulares_por_voucher = {}
    for voucher, grupo in vouchers.items():
        titular = obtener_titular_por_edad(grupo)
        if titular:
            titulares_por_voucher[voucher] = titular
    
    # Ahora agrupar por habitación
    # Si hay varias personas en una habitación, usar el mayor de esa habitación
    # PERO si comparten voucher con otras habitaciones, usar el titular del voucher completo
    habitaciones_ocupadas = {}
    habitaciones_con_pasajeros = {}
    
    # Primero agrupar todos los pasajeros por habitación
    for pasajero in pasajeros_activos:
        num_hab = extraer_num_hab(pasajero['Nro. habitación'])
        if num_hab is None:
            continue
        if num_hab not in habitaciones_con_pasajeros:
            habitaciones_con_pasajeros[num_hab] = []
        habitaciones_con_pasajeros[num_hab].append(pasajero)
    
    # Para cada habitación, determinar quién es el titular
    for num_hab, pasajeros_hab in habitaciones_con_pasajeros.items():
        # Obtener voucher de esta habitación
        voucher = str(pasajeros_hab[0].get('Voucher', '')).strip()
        
        # Si el voucher tiene múltiples habitaciones, usar el titular del voucher
        habitaciones_del_voucher = [p['Nro. habitación'] for p in vouchers.get(voucher, [])]
        
        if voucher and len(set(habitaciones_del_voucher)) > 1:
            # Familia con múltiples habitaciones: usar titular del voucher completo
            titular = titulares_por_voucher.get(voucher)
        else:
            # Habitación individual o sin voucher: usar el mayor de esta habitación
            titular = obtener_titular_por_edad(pasajeros_hab)
        
        if titular:
            cantidad_pasajeros = len(pasajeros_hab)

            try:
                plazas_titular = int(titular.get('Plazas ocupadas', 0))
            except:
                plazas_titular = 0

            habitaciones_ocupadas[num_hab] = {
                'id_estadia': str(titular.get('id_estadia', '')).strip(),
                'pasajero': titular['Apellido y nombre'],
                'plazas': max(cantidad_pasajeros, plazas_titular),
                'ingreso': titular['Fecha de ingreso'],
                'egreso': titular['Fecha de egreso'],
                'servicios': titular['Servicios'],
                'edad': int(titular.get('Edad', 0)),
                'voucher': voucher
}
    
    return habitaciones_ocupadas


def obtener_listado_pasajeros_alojados(
    archivo_pasajeros='data/pasajeros.csv',
    fecha_referencia=None
):
    """
    Obtiene todos los pasajeros alojados en una fecha determinada.
    Agrupa por habitación y excluye registros con fechas inválidas.
    No modifica el CSV original.
    """
    if fecha_referencia is None:
        fecha_referencia = datetime.today().date()

    resultado_vacio = {
        'habitaciones': [],
        'total_habitaciones': 0,
        'total_pasajeros': 0
    }

    if not os.path.exists(archivo_pasajeros):
        return resultado_vacio

    try:
        df = pd.read_csv(
            archivo_pasajeros,
            dtype=str,
            keep_default_na=False
        )
    except (EmptyDataError, pd.errors.ParserError, OSError):
        return resultado_vacio

    columnas = [
        'Nro. habitación',
        'Fecha de ingreso',
        'Fecha de egreso',
        'Apellido y nombre'
    ]

    if not all(col in df.columns for col in columnas):
        return resultado_vacio

    habitaciones = {}

    for _, fila in df.iterrows():
        try:
            ingreso = datetime.strptime(
                fila['Fecha de ingreso'].strip(),
                '%d/%m/%Y'
            ).date()

            egreso = datetime.strptime(
                fila['Fecha de egreso'].strip(),
                '%d/%m/%Y'
            ).date()
        except (ValueError, TypeError):
            continue

        if not ingreso <= fecha_referencia <= egreso:
            continue

        numero = extraer_num_hab(fila['Nro. habitación'])

        if numero is None:
            continue

        nombre = fila['Apellido y nombre'].strip()

        if not nombre:
            continue

        tipo_doc = fila.get('Tipo documento', '').strip()
        nro_doc = fila.get('Nro. doc.', '').strip()

        documento = ' '.join(
            parte for parte in (tipo_doc, nro_doc) if parte
        )

        pasajero = {
            'nombre': nombre,
            'documento': documento,
            'ingreso': ingreso.strftime('%d/%m/%Y'),
            'egreso': egreso.strftime('%d/%m/%Y')
        }

        habitaciones.setdefault(numero, []).append(pasajero)

    listado = []

    for numero in sorted(habitaciones):
        pasajeros = sorted(
            habitaciones[numero],
            key=lambda p: p['nombre'].casefold()
        )

        listado.append({
            'numero': numero,
            'cantidad': len(pasajeros),
            'pasajeros': pasajeros
        })

    return {
        'habitaciones': listado,
        'total_habitaciones': len(listado),
        'total_pasajeros': sum(
            h['cantidad'] for h in listado
        )
    }


def obtener_todos_pasajeros_habitacion(num_habitacion, archivo_pasajeros='data/pasajeros.csv'):
    """
    Obtiene TODOS los pasajeros de una habitación específica con sus datos individuales.
    Esto permite manejar consumos separados cuando hay personas con distintos vouchers.
    
    Args:
        num_habitacion (int): Número de habitación
        archivo_pasajeros (str): Ruta al archivo CSV de pasajeros
    
    Returns:
        Lista de diccionarios con datos de cada pasajero de la habitación.
        Cada pasajero incluye: nombre, voucher, edad, documento, servicios
        Retorna lista vacía si la habitación no está ocupada.
    """
    if not os.path.exists(archivo_pasajeros):
        return []
    
    df = pd.read_csv(archivo_pasajeros)
    fecha_hoy = datetime.now().strftime('%d/%m/%Y')
    
    # Filtrar pasajeros de esta habitación que ya ingresaron
    pasajeros = []
    for _, row in df.iterrows():
        # Verificar que sea la habitación correcta
        if extraer_num_hab(row['Nro. habitación']) != num_habitacion:
            continue
        
        # Verificar que ya ingresó
        fecha_ingreso = row['Fecha de ingreso']
        try:
            ingreso_dt = datetime.strptime(fecha_ingreso, '%d/%m/%Y')
            hoy_dt = datetime.strptime(fecha_hoy, '%d/%m/%Y')
            
            if ingreso_dt > hoy_dt:
                continue  # No ha ingresado aún
        except:
            pass  # Si hay error en fecha, incluir
        
        # Agregar pasajero a la lista
        pasajeros.append({
            'id_estadia': str(row.get('id_estadia', '')).strip(),
            'nombre': row['Apellido y nombre'],
            'voucher': str(row.get('Voucher', '')).strip(),
            'edad': int(row.get('Edad', 0)),
            'documento': f"{row.get('Tipo documento', 'DNI')} {row.get('Nro. doc.', '')}",
            'servicios': row.get('Servicios', ''),
            'ingreso': row['Fecha de ingreso'],
            'egreso': row['Fecha de egreso']
        })
    
    # Ordenar por edad (mayor edad primero) para que el titular aparezca primero
    pasajeros.sort(key=lambda p: p['edad'], reverse=True)
    
    return pasajeros


def obtener_habitaciones_reservadas_futuras(archivo_pasajeros='data/pasajeros.csv'):
    """
    Obtiene la lista de habitaciones con reservas para ingresos futuros.
    Retorna un diccionario con número de habitación como key y datos de la reserva.
    """
    if not os.path.exists(archivo_pasajeros):
        return {}
    
    df = pd.read_csv(archivo_pasajeros)
    habitaciones_futuras = {}
    fecha_hoy = datetime.now().strftime('%d/%m/%Y')
    hoy_dt = datetime.strptime(fecha_hoy, '%d/%m/%Y')
    pasajeros_futuros_por_habitacion = {}

    for _, row in df.iterrows():
        fecha_ingreso = row['Fecha de ingreso']

        try:
            ingreso_dt = datetime.strptime(fecha_ingreso, '%d/%m/%Y')
            if ingreso_dt > hoy_dt:
                num_hab = extraer_num_hab(row['Nro. habitación'])
                if num_hab is None:
                    continue
                if num_hab not in pasajeros_futuros_por_habitacion:
                    pasajeros_futuros_por_habitacion[num_hab] = []
                pasajeros_futuros_por_habitacion[num_hab].append(row.to_dict())
        except:
            pass

    for num_hab, pasajeros_hab in pasajeros_futuros_por_habitacion.items():
        titular = obtener_titular_por_edad(pasajeros_hab)
        if not titular:
            continue

        cantidad_pasajeros = len(pasajeros_hab)

        try:
            plazas_titular = int(titular.get('Plazas ocupadas', 0))
        except:
            plazas_titular = 0

        habitaciones_futuras[num_hab] = {
            'pasajero': titular['Apellido y nombre'],
            'plazas': max(cantidad_pasajeros, plazas_titular),
            'ingreso': titular['Fecha de ingreso'],
            'egreso': titular['Fecha de egreso'],
            'servicios': titular['Servicios']
        }
    
    return habitaciones_futuras


def obtener_habitaciones_con_consumos(archivo_consumos='data/consumos_diarios.csv'):
    """
    Obtiene la lista de habitaciones que tienen consumos registrados.
    Retorna un set con los números de habitación.
    """
    if not os.path.exists(archivo_consumos):
        return set()
    
    try:
        df = pd.read_csv(archivo_consumos)
    except EmptyDataError:
        return set()

    if df.empty or 'habitacion' not in df.columns:
        return set()

    return set(df['habitacion'].astype(int).unique())


def es_checkout_hoy(fecha_egreso):
    """
    Verifica si la fecha de egreso es hoy.
    Formato esperado: DD/MM/YYYY
    """
    try:
        fecha_hoy = datetime.now().strftime('%d/%m/%Y')
        return fecha_egreso == fecha_hoy
    except:
        return False


def obtener_habitaciones_checkout():
    """
    Obtiene las habitaciones con checkout programado para hoy.
    Retorna un set con los números de habitación.
    """
    habitaciones_ocupadas = obtener_habitaciones_ocupadas()
    checkouts_hoy = set()
    
    for num_hab, datos in habitaciones_ocupadas.items():
        if es_checkout_hoy(datos['egreso']):
            checkouts_hoy.add(num_hab)
    
    return checkouts_hoy


def obtener_habitaciones_checkout_pendientes(archivo_pasajeros='data/pasajeros.csv'):
    """
    Obtiene habitaciones con checkout pendiente: ingreso <= hoy y egreso <= hoy.
    Incluye checkouts de hoy y vencidos por cambio de fecha del sistema.

    Retorna un diccionario con número de habitación como key y datos del titular.
    """
    if not os.path.exists(archivo_pasajeros):
        return {}

    df = pd.read_csv(archivo_pasajeros)
    hoy_dt = datetime.now().date()
    ingreso_dt = pd.to_datetime(df['Fecha de ingreso'], format='%d/%m/%Y', errors='coerce')
    egreso_dt = pd.to_datetime(df['Fecha de egreso'], format='%d/%m/%Y', errors='coerce')

    mask_pendientes = (
        ingreso_dt.dt.date <= hoy_dt
    ) & (
        egreso_dt.dt.date <= hoy_dt
    )

    df_pendientes = df[mask_pendientes].copy()
    if df_pendientes.empty:
        return {}

    habitaciones_pendientes = {}
    habitaciones_con_pasajeros = {}

    for _, row in df_pendientes.iterrows():
        num_hab = extraer_num_hab(row['Nro. habitación'])
        if num_hab is None:
            continue
        if num_hab not in habitaciones_con_pasajeros:
            habitaciones_con_pasajeros[num_hab] = []
        habitaciones_con_pasajeros[num_hab].append(row.to_dict())

    for num_hab, pasajeros_hab in habitaciones_con_pasajeros.items():
        titular = obtener_titular_por_edad(pasajeros_hab)
        if not titular:
            continue

        cantidad_pasajeros = len(pasajeros_hab)

        try:
            plazas_titular = int(titular.get('Plazas ocupadas', 0))
        except:
            plazas_titular = 0

        habitaciones_pendientes[num_hab] = {
            'pasajero': titular['Apellido y nombre'],
            'plazas': max(cantidad_pasajeros, plazas_titular),
            'ingreso': titular['Fecha de ingreso'],
            'egreso': titular['Fecha de egreso'],
            'servicios': titular.get('Servicios', ''),
            'edad': int(titular.get('Edad', 0)),
            'voucher': str(titular.get('Voucher', '')).strip()
        }

    return habitaciones_pendientes


def calcular_estado_habitacion(num_habitacion, habitaciones_ocupadas, habitaciones_con_consumos, checkouts_hoy=None, habitaciones_reservadas=None):
    """
    Calcula el estado de una habitación según su ocupación y consumos.
    
    Retorna:
        - 'vacia': habitación no ocupada y sin reserva futura (gris)
        - 'reservada': reserva futura, aún no ingresó (gris con info de reserva)
        - 'ocupada': ocupada sin consumos (verde)
        - 'con_consumos': ocupada con consumos (naranja)
        - 'checkout': checkout programado para hoy (rojo)
    """
    # Prioridad 1: Check-out hoy (de habitaciones ocupadas)
    if checkouts_hoy and num_habitacion in checkouts_hoy:
        return 'checkout'
    
    # Prioridad 2: Habitación ocupada actualmente
    if num_habitacion in habitaciones_ocupadas:
        # Con consumos
        if num_habitacion in habitaciones_con_consumos:
            return 'con_consumos'
        # Sin consumos
        return 'ocupada'
    
    # Prioridad 3: Habitación con reserva futura
    if habitaciones_reservadas and num_habitacion in habitaciones_reservadas:
        return 'reservada'
    
    # Por defecto: vacía
    return 'vacia'


def obtener_datos_dashboard():
    """
    Obtiene todos los datos necesarios para renderizar el dashboard.
    
    Retorna un diccionario con:
        - pisos: estructura de habitaciones por piso
        - estados: estado de cada habitación
        - ocupadas: datos de habitaciones ocupadas
        - reservadas: datos de habitaciones con reserva futura
        - estadisticas: resumen general
        - checkouts_hoy: habitaciones con checkout hoy
    """
    habitaciones_ocupadas = obtener_habitaciones_ocupadas()
    habitaciones_reservadas = obtener_habitaciones_reservadas_futuras()
    habitaciones_con_consumos = obtener_habitaciones_con_consumos()
    checkouts_hoy = obtener_habitaciones_checkout()
    
    # Calcular estados de todas las habitaciones
    estados = {}
    for piso, habitaciones in PISOS.items():
        for num_hab in habitaciones:
            estados[num_hab] = calcular_estado_habitacion(
                num_hab, 
                habitaciones_ocupadas, 
                habitaciones_con_consumos,
                checkouts_hoy,
                habitaciones_reservadas
            )
    
    # Calcular estadísticas correctamente
    # IMPORTANTE: Una habitación puede tener reserva futura Y estar ocupada hoy
    total_habitaciones = sum(len(habs) for habs in PISOS.values())
    total_ocupadas = len(habitaciones_ocupadas)
    total_con_consumos = len([h for h, e in estados.items() if e == 'con_consumos'])
    total_checkouts = len(checkouts_hoy)
    total_checkouts_pendientes = len(obtener_habitaciones_checkout_pendientes())
    
    # Contar reservadas que NO están ocupadas actualmente
    reservadas_no_ocupadas = len([h for h in habitaciones_reservadas if h not in habitaciones_ocupadas])
    
    # Habitaciones realmente disponibles = total - ocupadas - reservadas_futuras_sin_ocupacion
    habitaciones_usadas = len(set(list(habitaciones_ocupadas.keys()) + list(habitaciones_reservadas.keys())))
    total_disponibles = total_habitaciones - habitaciones_usadas
    
    estadisticas = {
        'total': total_habitaciones,
        'ocupadas': total_ocupadas,
        'vacias': total_disponibles,
        'reservadas': reservadas_no_ocupadas,  # Solo las que no están ocupadas ahora
        'con_consumos': total_con_consumos,
        'sin_consumos': total_ocupadas - total_con_consumos,
        'checkouts_hoy': total_checkouts,
        'checkouts_pendientes': total_checkouts_pendientes
    }
    
    return {
        'pisos': PISOS,
        'estados': estados,
        'ocupadas': habitaciones_ocupadas,
        'reservadas': habitaciones_reservadas,
        'estadisticas': estadisticas,
        'checkouts_hoy': checkouts_hoy
    }


def obtener_total_consumos_habitacion(num_habitacion, archivo_consumos='data/consumos_diarios.csv'):
    """
    Calcula el total de consumos de una habitación específica.
    """
    if not os.path.exists(archivo_consumos):
        return 0
    
    df = pd.read_csv(archivo_consumos)
    consumos_hab = df[df['habitacion'] == num_habitacion]
    
    if consumos_hab.empty:
        return 0
    
    return consumos_hab['monto'].sum()
