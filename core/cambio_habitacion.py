"""
Módulo para gestionar cambios de habitación por desperfectos o emergencias.
Permite mover un huésped de una habitación a otra manteniendo sus consumos.
"""

import pandas as pd
import os
from core.dashboard import extraer_num_hab

DB_PASAJEROS = 'data/pasajeros.csv'
DB_CONSUMOS = 'data/consumos_diarios.csv'


def _obtener_letra_cama(valor_habitacion):
    """Obtiene la letra de cama (A/B/C) desde valores como '343 A'."""
    partes = str(valor_habitacion).strip().split()
    if len(partes) >= 2:
        letra = partes[1].strip().upper()
        if letra.isalpha() and len(letra) == 1:
            return letra
    return ''


def _capacidad_maxima_habitacion(num_habitacion, df_pasajeros):
    """
    Reglas operativas de capacidad para cambio parcial:
    - Habitación 240: 4 plazas
    - TRIPLE A COMPARTIR: 3 plazas
    - Resto: 2 plazas (dobles)
    """
    if int(num_habitacion) == 240:
        return 4

    filas_hab = df_pasajeros[df_pasajeros['_num_hab'] == int(num_habitacion)]
    if not filas_hab.empty and 'Tipo habitación' in filas_hab.columns:
        tipos = filas_hab['Tipo habitación'].astype(str).str.upper().str.strip()
        if tipos.str.contains('TRIPLE').any():
            return 3

    return 2


def _asignar_habitacion_con_letra(habitacion_destino, letras_ocupadas, capacidad_maxima):
    """
    Asigna el próximo sufijo de cama disponible en la habitación destino.
    Asigna letra de cama según capacidad (A/B/C/D).
    """
    letras_posibles = ['A', 'B', 'C', 'D'][:max(1, int(capacidad_maxima))]
    for letra in letras_posibles:
        if letra not in letras_ocupadas:
            return f"{habitacion_destino} {letra}"
    return None


def obtener_habitaciones_destino_para_cambio_parcial(habitacion_origen):
    """
    Lista habitaciones destino para mover un solo pasajero.
    Incluye habitaciones vacías u ocupadas con cupo (hasta 3 plazas por habitación).
    """
    from core.dashboard import PISOS

    if not os.path.exists(DB_PASAJEROS):
        return []

    try:
        habitacion_origen = int(habitacion_origen)
    except:
        return []

    df_pasajeros = pd.read_csv(DB_PASAJEROS)
    df_pasajeros['_num_hab'] = df_pasajeros['Nro. habitación'].apply(extraer_num_hab)

    todas_habitaciones = []
    for piso_habs in PISOS.values():
        todas_habitaciones.extend(piso_habs)

    destinos = []
    for hab in sorted(todas_habitaciones):
        if hab == habitacion_origen:
            continue

        ocupantes = df_pasajeros[df_pasajeros['_num_hab'] == hab]
        cantidad_ocupantes = len(ocupantes)

        capacidad_maxima = _capacidad_maxima_habitacion(hab, df_pasajeros)
        if cantidad_ocupantes >= capacidad_maxima:
            continue

        destinos.append({
            'habitacion': hab,
            'ocupantes': cantidad_ocupantes,
            'capacidad_maxima': capacidad_maxima,
            'estado': 'Vacía' if cantidad_ocupantes == 0 else f'Ocupada ({cantidad_ocupantes}/{capacidad_maxima})',
            'tipo': 'vacia' if cantidad_ocupantes == 0 else 'ocupada'
        })

    return destinos


def obtener_habitaciones_disponibles_para_cambio(habitacion_origen):
    """
    Obtiene las habitaciones disponibles para hacer un cambio,
    excluyendo la habitación actual del huésped.
    
    Args:
        habitacion_origen (int): Habitación actual del huésped
        
    Returns:
        list: Lista de habitaciones disponibles
    """
    from core.dashboard import PISOS, obtener_habitaciones_ocupadas
    
    # Todas las habitaciones del hotel
    todas_habitaciones = []
    for piso_habs in PISOS.values():
        todas_habitaciones.extend(piso_habs)
    
    # Habitaciones ocupadas
    ocupadas = obtener_habitaciones_ocupadas()
    
    # Retornar disponibles, excluyendo la habitación origen
    disponibles = [h for h in todas_habitaciones 
                   if h not in ocupadas.keys() and h != habitacion_origen]
    return sorted(disponibles)


def cambiar_habitacion(habitacion_origen, habitacion_destino, motivo=""):
    """
    Cambia un huésped de una habitación a otra.
    Actualiza el registro del pasajero y traslada todos sus consumos.
    
    Args:
        habitacion_origen (int): Habitación actual
        habitacion_destino (int): Nueva habitación
        motivo (str): Razón del cambio (opcional)
        
    Returns:
        tuple: (bool_exito, str_mensaje)
    """
    
    if not os.path.exists(DB_PASAJEROS):
        return False, "No existe el archivo de pasajeros"
    
    try:
        habitacion_origen = int(habitacion_origen)
        habitacion_destino = int(habitacion_destino)
    except:
        return False, "Números de habitación inválidos"
    
    if habitacion_origen == habitacion_destino:
        return False, "Las habitaciones origen y destino son iguales"
    
    try:
        # 1. Verificar que la habitación origen esté ocupada
        df_pasajeros = pd.read_csv(DB_PASAJEROS)
        df_pasajeros['_num_hab'] = df_pasajeros['Nro. habitación'].apply(extraer_num_hab)
        pasajero_origen = df_pasajeros[df_pasajeros['_num_hab'] == habitacion_origen]
        
        if pasajero_origen.empty:
            return False, f"La habitación {habitacion_origen} no está ocupada"
        
        # 2. Verificar que la habitación destino esté disponible
        pasajero_destino = df_pasajeros[df_pasajeros['_num_hab'] == habitacion_destino]
        if not pasajero_destino.empty:
            return False, f"La habitación {habitacion_destino} ya está ocupada"
        
        # 3. Obtener datos del pasajero
        nombre_pasajero = pasajero_origen.iloc[0]['Apellido y nombre']
        
        # 4. Actualizar habitación en pasajeros.csv
        # Para cada fila del origen, reemplazar el sufijo conservando el formato si aplica
        def reemplazar_num_hab(valor):
            s = str(valor).strip()
            partes = s.split()
            if len(partes) > 1:
                return f"{habitacion_destino} {partes[1]}"
            return str(habitacion_destino)
        
        df_pasajeros.loc[df_pasajeros['_num_hab'] == habitacion_origen, 'Nro. habitación'] = \
            df_pasajeros.loc[df_pasajeros['_num_hab'] == habitacion_origen, 'Nro. habitación'].apply(reemplazar_num_hab)
        
        df_pasajeros = df_pasajeros.drop(columns=['_num_hab'])
        
        # 5. Agregar observación si existe el campo
        if 'Observaciones' in df_pasajeros.columns:
            obs_actual = str(df_pasajeros.loc[df_pasajeros['Nro. habitación'].apply(extraer_num_hab) == habitacion_destino, 
                                              'Observaciones'].iloc[0])
            if pd.isna(obs_actual) or obs_actual == 'nan':
                obs_actual = ""
            
            nueva_obs = f"Cambio desde Hab {habitacion_origen}. Motivo: {motivo}" if motivo else f"Cambio desde Hab {habitacion_origen}"
            if obs_actual:
                nueva_obs = f"{obs_actual} | {nueva_obs}"
            
            df_pasajeros.loc[df_pasajeros['Nro. habitación'].apply(extraer_num_hab) == habitacion_destino, 
                            'Observaciones'] = nueva_obs
        
        df_pasajeros.to_csv(DB_PASAJEROS, index=False)
        
        # 6. Actualizar consumos si existen
        consumos_actualizados = 0
        if os.path.exists(DB_CONSUMOS):
            df_consumos = pd.read_csv(DB_CONSUMOS)
            ids_estadia = set()
            if 'id_estadia' in pasajero_origen.columns:
                ids_estadia = {
                    str(identificador).strip()
                    for identificador in pasajero_origen['id_estadia']
                    if pd.notna(identificador) and str(identificador).strip()
                }

            if ids_estadia and 'id_estadia' in df_consumos.columns:
                ids_consumos = (
                    df_consumos['id_estadia']
                    .fillna('')
                    .astype(str)
                    .str.strip()
                )
                mask_consumos = ids_consumos.isin(ids_estadia)
                consumos_actualizados = int(mask_consumos.sum())
            else:
                mask_consumos = pd.Series(False, index=df_consumos.index)

            if consumos_actualizados:
                df_consumos.loc[mask_consumos, 'habitacion'] = habitacion_destino
                df_consumos.to_csv(DB_CONSUMOS, index=False)
        
        mensaje = f"Cambio exitoso: {nombre_pasajero} movido de habitación {habitacion_origen} → {habitacion_destino}"
        if consumos_actualizados > 0:
            mensaje += f" ({consumos_actualizados} consumo(s) trasladado(s))"
        
        return True, mensaje
        
    except Exception as e:
        return False, f"Error al cambiar habitación: {str(e)}"


def validar_cambio_habitacion(habitacion_origen, habitacion_destino):
    """
    Valida que el cambio de habitación sea posible.
    
    Returns:
        tuple: (bool_valido, str_error)
    """
    
    try:
        habitacion_origen = int(habitacion_origen)
        habitacion_destino = int(habitacion_destino)
    except:
        return False, "Números de habitación inválidos"
    
    if habitacion_origen == habitacion_destino:
        return False, "Debe seleccionar una habitación diferente"
    
    if not os.path.exists(DB_PASAJEROS):
        return False, "No existe el archivo de pasajeros"
    
    df_pasajeros = pd.read_csv(DB_PASAJEROS)
    
    # Verificar origen ocupada
    if df_pasajeros[df_pasajeros['Nro. habitación'].apply(extraer_num_hab) == habitacion_origen].empty:
        return False, f"La habitación {habitacion_origen} no está ocupada"
    
    # Verificar destino disponible
    if not df_pasajeros[df_pasajeros['Nro. habitación'].apply(extraer_num_hab) == habitacion_destino].empty:
        return False, f"La habitación {habitacion_destino} ya está ocupada"
    
    return True, ""


def validar_cambio_parcial(habitacion_origen, habitacion_destino, nombre_pasajero):
    """Valida si es posible mover un solo pasajero desde origen hacia destino."""
    try:
        habitacion_origen = int(habitacion_origen)
        habitacion_destino = int(habitacion_destino)
    except:
        return False, "Números de habitación inválidos"

    if not nombre_pasajero:
        return False, "Debe seleccionar un pasajero"

    if habitacion_origen == habitacion_destino:
        return False, "Debe seleccionar una habitación diferente"

    if not os.path.exists(DB_PASAJEROS):
        return False, "No existe el archivo de pasajeros"

    df_pasajeros = pd.read_csv(DB_PASAJEROS)
    df_pasajeros['_num_hab'] = df_pasajeros['Nro. habitación'].apply(extraer_num_hab)

    origen = df_pasajeros[df_pasajeros['_num_hab'] == habitacion_origen]
    if origen.empty:
        return False, f"La habitación {habitacion_origen} no está ocupada"

    pasajero_origen = origen[origen['Apellido y nombre'].astype(str).str.strip() == str(nombre_pasajero).strip()]
    if pasajero_origen.empty:
        return False, "El pasajero seleccionado no pertenece a la habitación origen"

    ocupantes_destino = df_pasajeros[df_pasajeros['_num_hab'] == habitacion_destino]
    capacidad_maxima = _capacidad_maxima_habitacion(habitacion_destino, df_pasajeros)
    if len(ocupantes_destino) >= capacidad_maxima:
        return False, f"La habitación {habitacion_destino} no tiene cupo disponible"

    return True, ""


def cambiar_pasajero_individual(habitacion_origen, habitacion_destino, nombre_pasajero, motivo=""):
    """
    Mueve un único pasajero de una habitación a otra.
    Soporta destino vacío u ocupado con cupo, y traslada consumos del pasajero.
    """
    valido, error = validar_cambio_parcial(habitacion_origen, habitacion_destino, nombre_pasajero)
    if not valido:
        return False, error

    habitacion_origen = int(habitacion_origen)
    habitacion_destino = int(habitacion_destino)
    nombre_pasajero = str(nombre_pasajero).strip()

    try:
        df_pasajeros = pd.read_csv(DB_PASAJEROS)
        df_pasajeros['_num_hab'] = df_pasajeros['Nro. habitación'].apply(extraer_num_hab)

        mask_pasajero_origen = (
            (df_pasajeros['_num_hab'] == habitacion_origen) &
            (df_pasajeros['Apellido y nombre'].astype(str).str.strip() == nombre_pasajero)
        )

        fila_pasajero = df_pasajeros[mask_pasajero_origen]
        if fila_pasajero.empty:
            return False, "No se encontró el pasajero en la habitación origen"

        # Determinar próximo sufijo de cama disponible en destino.
        ocupantes_destino = df_pasajeros[df_pasajeros['_num_hab'] == habitacion_destino]
        letras_ocupadas = set(
            _obtener_letra_cama(v)
            for v in ocupantes_destino['Nro. habitación'].tolist()
        )
        letras_ocupadas.discard('')

        capacidad_maxima = _capacidad_maxima_habitacion(habitacion_destino, df_pasajeros)
        nuevo_valor_habitacion = _asignar_habitacion_con_letra(
            habitacion_destino,
            letras_ocupadas,
            capacidad_maxima
        )
        if not nuevo_valor_habitacion:
            return False, f"No hay letra de cama disponible en la habitación {habitacion_destino}"

        # Mover solo la fila del pasajero seleccionado.
        idx_pasajero = fila_pasajero.index[0]
        df_pasajeros.at[idx_pasajero, 'Nro. habitación'] = nuevo_valor_habitacion

        if 'Observaciones' in df_pasajeros.columns:
            obs_actual = str(df_pasajeros.at[idx_pasajero, 'Observaciones'])
            if pd.isna(obs_actual) or obs_actual == 'nan':
                obs_actual = ''

            nueva_obs = f"Cambio parcial {habitacion_origen} -> {habitacion_destino}. Motivo: {motivo}" if motivo else f"Cambio parcial {habitacion_origen} -> {habitacion_destino}"
            if obs_actual:
                nueva_obs = f"{obs_actual} | {nueva_obs}"

            df_pasajeros.at[idx_pasajero, 'Observaciones'] = nueva_obs

        df_pasajeros = df_pasajeros.drop(columns=['_num_hab'])
        df_pasajeros.to_csv(DB_PASAJEROS, index=False)

        consumos_actualizados = 0
        if os.path.exists(DB_CONSUMOS):
            df_consumos = pd.read_csv(DB_CONSUMOS)
            identificador = fila_pasajero.iloc[0].get('id_estadia', '')
            identificador = (
                ''
                if pd.isna(identificador)
                else str(identificador).strip()
            )
            if identificador and 'id_estadia' in df_consumos.columns:
                mask_consumos = (
                    df_consumos['id_estadia']
                    .fillna('')
                    .astype(str)
                    .str.strip()
                    .eq(identificador)
                )
                consumos_actualizados = int(mask_consumos.sum())
            else:
                mask_consumos = pd.Series(False, index=df_consumos.index)

            if consumos_actualizados > 0:
                df_consumos.loc[mask_consumos, 'habitacion'] = habitacion_destino
                df_consumos.to_csv(DB_CONSUMOS, index=False)

        mensaje = (
            f"Cambio parcial exitoso: {nombre_pasajero} movido de habitación "
            f"{habitacion_origen} a {habitacion_destino}"
        )
        if consumos_actualizados > 0:
            mensaje += f" ({consumos_actualizados} consumo(s) trasladado(s))"

        return True, mensaje

    except Exception as e:
        return False, f"Error al procesar cambio parcial: {str(e)}"
