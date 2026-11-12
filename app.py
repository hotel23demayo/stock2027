from flask import Flask, abort, render_template, request, redirect, flash, send_file
import pandas as pd
import os
from datetime import datetime
from decimal import Decimal
import sys
import tempfile
from core.informe_consumos import generar_consolidado_productos
from core.control_cuentas import generar_control_cuentas


# Importar módulos del core
from core.dashboard import (
    obtener_datos_dashboard,
    obtener_habitaciones_ocupadas,
    extraer_num_hab,
    obtener_listado_pasajeros_alojados
)
from core.consumos import (
    obtener_resumen_habitacion,
    agregar_consumo,
    anular_consumo_por_id,
    obtener_historial_consumos,
    agregar_consumo_bebida_rapida,
    obtener_catalogo_bebidas,
    CANTIDADES_RAPIDAS
)
from core.reserva_express import crear_reserva_express, obtener_habitaciones_disponibles, validar_datos_reserva
from core.identidad_estadias import procesar_identidades
from core.pase_caja import (
    COLUMNAS_PASAJEROS,
    COLUMNAS_CONSUMOS,
    leer_pasajeros,
    leer_consumos,
    obtener_pasajeros_con_salida,
    vincular_consumos_bebidas,
    consolidar_salidas_por_habitacion,
    clave_cuenta
)

app = Flask(__name__)
app.secret_key = 'temporada_2026_recepcion_key_secreta'

# Archivos de datos
DB_PASAJEROS = 'data/pasajeros.csv'
DB_CONSUMOS = 'data/consumos_diarios.csv'


@app.template_filter('importe_pase')
def formatear_importe_pase(importe):
    """Conserva los decimales del importe confirmado al mostrarlo."""
    texto = format(Decimal(str(importe)), ',f')
    if '.' in texto:
        texto = texto.rstrip('0').rstrip('.')
    return texto.replace(',', 'X').replace('.', ',').replace('X', '.')


def validar_pasajero(habitacion):
    """
    Verifica que la habitación exista en el CSV de pasajeros activos.
    Retorna el nombre del pasajero si existe, None si no.
    """
    if not os.path.exists(DB_PASAJEROS):
        return None

    df_pasajeros = pd.read_csv(DB_PASAJEROS)
    pasajero = df_pasajeros[
        df_pasajeros['Nro. habitación'].apply(extraer_num_hab) == int(habitacion)
    ]

    if pasajero.empty:
        return None

    return pasajero.iloc[0]['Apellido y nombre']

def validar_estadia_para_consumo(id_estadia, habitacion, archivo_pasajeros=DB_PASAJEROS):
    """
    Valida que una estadía exista, corresponda a la habitación indicada
    y se encuentre vigente en la fecha actual.

    Retorna los datos del pasajero si la validación es correcta.
    Retorna None si no existe o no corresponde.
    """
    id_estadia = str(id_estadia or '').strip()

    if not id_estadia or not os.path.exists(archivo_pasajeros):
        return None

    try:
        df = pd.read_csv(archivo_pasajeros, dtype={'id_estadia': str})

        columnas_requeridas = {
            'id_estadia',
            'Nro. habitación',
            'Apellido y nombre',
            'Fecha de ingreso',
            'Fecha de egreso'
        }

        if not columnas_requeridas.issubset(df.columns):
            return None

        coincidencias = df[
            df['id_estadia'].fillna('').astype(str).str.strip() == id_estadia
        ]

        # El identificador debe corresponder a un único registro.
        if len(coincidencias) != 1:
            return None

        pasajero = coincidencias.iloc[0]

        habitacion_registro = extraer_num_hab(
            pasajero['Nro. habitación']
        )

        if habitacion_registro != int(habitacion):
            return None

        # Validar que la fecha actual esté dentro de la estadía.
        fecha_ingreso = datetime.strptime(
            str(pasajero['Fecha de ingreso']).strip(),
            '%d/%m/%Y'
        ).date()

        fecha_egreso = datetime.strptime(
            str(pasajero['Fecha de egreso']).strip(),
            '%d/%m/%Y'
        ).date()

        fecha_actual = datetime.now().date()

        if not (fecha_ingreso <= fecha_actual <= fecha_egreso):
            return None

        return {
            'id_estadia': id_estadia,
            'habitacion': habitacion_registro,
            'pasajero': str(pasajero['Apellido y nombre']).strip(),
            'ingreso': pasajero['Fecha de ingreso'],
            'egreso': pasajero['Fecha de egreso']
        }

    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"Error al validar estadía para consumo: {e}")
        return None

@app.route('/')
def index():
    """Redirige al dashboard principal"""
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    """Dashboard principal con las 53 habitaciones"""
    datos = obtener_datos_dashboard()
    return render_template('dashboard.html',
                         pisos=datos['pisos'],
                         estados=datos['estados'],
                         ocupadas=datos['ocupadas'],
                         reservadas=datos['reservadas'],
                         estadisticas=datos['estadisticas'],
                         checkouts_hoy=datos['checkouts_hoy'])

def obtener_datos_pase(ahora):
    """Construye el pase y sus cuentas a partir de los datos operativos."""
    df_pasajeros = leer_pasajeros(DB_PASAJEROS)
    df_consumos = leer_consumos(DB_CONSUMOS)
    salidas = obtener_pasajeros_con_salida(
        df_pasajeros,
        ahora.date()
    )
    resultado = vincular_consumos_bebidas(
        salidas,
        df_consumos
    )
    filas_pase = consolidar_salidas_por_habitacion(
        salidas,
        resultado['totales_por_estadia']
    )
    grupos = {}
    for _, estadia in salidas.iterrows():
        grupos.setdefault(clave_cuenta(estadia), []).append(estadia['id_estadia'].strip())
    claves = pd.DataFrame(
        [{'habitacion': habitacion, 'voucher': voucher}
         for habitacion, voucher in grupos],
        columns=['habitacion', 'voucher']
    ).sort_values(
        by='habitacion',
        key=lambda columna: pd.to_numeric(columna, errors='coerce'),
        kind='stable',
        na_position='last'
    ).reset_index(drop=True)
    cuentas = []
    for fila, clave in zip(filas_pase.to_dict('records'), claves.to_dict('records')):
        cuenta = {**fila, 'voucher': clave['voucher']}
        cuenta['ids_estadia'] = grupos[(clave['habitacion'], clave['voucher'])]
        cuentas.append(cuenta)
    return filas_pase, resultado, cuentas


def archivos_pase_disponibles():
    if not os.path.exists(DB_PASAJEROS):
        flash('No se encuentra el archivo de pasajeros.', 'warning')
        return False
    if not os.path.exists(DB_CONSUMOS):
        flash('No se encuentra el archivo de consumos.', 'warning')
        return False
    return True


@app.route('/pase-turno')
def pase_turno():
    """Informe de pase de turno de recepción."""
    if not archivos_pase_disponibles():
        return redirect('/dashboard')

    ahora = datetime.now()
    filas_pase, resultado, cuentas = obtener_datos_pase(ahora)
    filas_por_pagina = 28
    filas = filas_pase.to_dict('records')
    paginas_pase = [
        filas[inicio:inicio + filas_por_pagina]
        for inicio in range(0, len(filas), filas_por_pagina)
    ] or [[]]

    for pagina in paginas_pase:
        pagina.extend(
        {
            'habitacion': '',
            'titular': '',
            'bebidas': None
        }
        for _ in range(filas_por_pagina - len(pagina))
    )

    return render_template(
        'pase_turno.html',
        filas_pase=filas_pase,
        cuentas=cuentas,
        paginas_pase=paginas_pase,
        total_bebidas=filas_pase['bebidas'].sum(),
        detalle=resultado['detalle_confirmado'],
        pendientes=resultado['pendientes'],
        inconsistencias=resultado['inconsistencias'],
        estadias_duplicadas=resultado['estadias_duplicadas'],
        fecha_emision=ahora.strftime('%d/%m/%Y'),
    )


def fecha_consumo_para_orden(consumo):
    fecha = consumo.get('fecha', '').strip()
    for formato in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            return (0, datetime.strptime(fecha, formato))
        except ValueError:
            continue
    return (1, datetime.max)


@app.route('/pase-turno/detalle')
def detalle_cuenta_pase():
    """Detalle informativo de una cuenta incluida en el pase vigente."""
    if not archivos_pase_disponibles():
        return redirect('/dashboard')
    if 'habitacion' not in request.args or 'voucher' not in request.args:
        abort(404)

    ahora = datetime.now()
    _, resultado, cuentas = obtener_datos_pase(ahora)
    cuenta = next(
        (fila for fila in cuentas
         if fila['habitacion'] == request.args['habitacion']
         and fila['voucher'] == request.args['voucher']),
        None
    )
    if cuenta is None:
        abort(404)

    detalle = resultado['detalle_confirmado']
    if detalle.empty:
        consumos = []
    else:
        ids = set(cuenta['ids_estadia'])
        consumos = detalle.loc[
            detalle['id_estadia'].astype(str).str.strip().isin(ids)
        ].to_dict('records')
    consumos.sort(key=fecha_consumo_para_orden)
    return render_template(
        'detalle_cuenta_pase.html', cuenta=cuenta, consumos=consumos,
        fecha_emision=ahora.strftime('%d/%m/%Y')
    )

@app.route('/listado-pasajeros-alojados')
def listado_pasajeros_alojados():
    """Muestra el listado actualizado de pasajeros alojados."""

    datos = obtener_listado_pasajeros_alojados(DB_PASAJEROS)

    ahora = datetime.now()

    return render_template(
        'listado_pasajeros_alojados.html',
        habitaciones=datos['habitaciones'],
        total_habitaciones=datos['total_habitaciones'],
        total_pasajeros=datos['total_pasajeros'],
        fecha_emision=ahora.strftime('%d/%m/%Y'),
        hora_emision=ahora.strftime('%H:%M')
    )


@app.route('/control-cuentas')
def control_cuentas():
    """Consulta de solo lectura de cuentas de estadías activas."""
    try:
        pasajeros = pd.read_csv(DB_PASAJEROS, dtype=str, keep_default_na=False)
        consumos = pd.read_csv(DB_CONSUMOS, dtype=str, keep_default_na=False)
        requeridas = (
            (pasajeros, {'id_estadia', 'Nro. habitación', 'Apellido y nombre',
                         'Fecha de ingreso', 'Fecha de egreso', 'Voucher'}, 'pasajeros'),
            (consumos, {'id_estadia', 'habitacion', 'categoria', 'monto', 'estado'}, 'consumos'),
        )
        for tabla, columnas, nombre in requeridas:
            faltantes = columnas - set(tabla.columns)
            if faltantes:
                raise ValueError(f"Faltan columnas de {nombre}: {', '.join(sorted(faltantes))}")
        for tabla, columnas in ((pasajeros, COLUMNAS_PASAJEROS), (consumos, COLUMNAS_CONSUMOS)):
            for columna in columnas:
                if columna not in tabla.columns:
                    tabla[columna] = ''
        ahora = datetime.now()
        datos = generar_control_cuentas(pasajeros, consumos, ahora.date())
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError, ValueError) as error:
        app.logger.warning('No se pudo generar el control de cuentas: %s', error)
        return render_template('control_cuentas.html', error=str(error)), 503

    return render_template('control_cuentas.html', datos=datos, fecha_emision=ahora)


@app.route('/habitacion/<int:num_habitacion>')
def ficha_habitacion(num_habitacion):
    """Muestra la ficha individual de una habitación"""
    from core.dashboard import es_checkout_hoy

    # Obtener datos del pasajero
    habitaciones_ocupadas = obtener_habitaciones_ocupadas()

    # Verificar que la habitación esté ocupada
    if num_habitacion not in habitaciones_ocupadas:
        flash(f'La habitación {num_habitacion} no está ocupada actualmente', 'warning')
        return redirect('/dashboard')

    # Obtener resumen completo de la habitación
    datos_pasajero = habitaciones_ocupadas[num_habitacion]
    resumen = obtener_resumen_habitacion(num_habitacion, datos_pasajero)

    # Verificar si es checkout hoy
    resumen['es_checkout_hoy'] = es_checkout_hoy(datos_pasajero['egreso'])
    resumen['catalogo_bebidas'] = obtener_catalogo_bebidas()
    resumen['cantidades_rapidas'] = CANTIDADES_RAPIDAS

    return render_template('ficha_habitacion.html', habitacion=resumen)

@app.route('/habitacion/<int:num_habitacion>/agregar', methods=['POST'])
def agregar_consumo_habitacion(num_habitacion):
    """Agrega un consumo asociado a una estadía validada."""

    id_estadia = request.form.get('id_estadia', '').strip()
    categoria = request.form.get('categoria')
    monto = request.form.get('monto')

    if not categoria or not monto:
        flash('Todos los campos son obligatorios', 'danger')
        return redirect(f'/habitacion/{num_habitacion}')

    habitaciones_ocupadas = obtener_habitaciones_ocupadas()

    if num_habitacion not in habitaciones_ocupadas:
        flash('Habitación no encontrada', 'danger')
        return redirect('/dashboard')

    datos_estadia = validar_estadia_para_consumo(
        id_estadia,
        num_habitacion
    )

    if not datos_estadia:
        flash('No se pudo validar la estadía seleccionada.', 'danger')
        return redirect(f'/habitacion/{num_habitacion}')

    pasajero = datos_estadia['pasajero']

    if agregar_consumo(
        num_habitacion,
        categoria,
        monto,
        pasajero,
        id_estadia=datos_estadia['id_estadia']
    ):
        flash(f'Consumo de ${monto} agregado a {pasajero}', 'success')
    else:
        flash('Error al agregar el consumo', 'danger')

    return redirect(f'/habitacion/{num_habitacion}')


@app.route('/habitacion/<int:num_habitacion>/agregar-bebida', methods=['POST'])
def agregar_bebida_rapida_habitacion(num_habitacion):
    """Agrega una bebida asociada a una estadía validada."""

    producto = request.form.get('producto')
    cantidad = request.form.get('cantidad', 1)
    id_estadia = request.form.get('id_estadia', '').strip()

    habitaciones_ocupadas = obtener_habitaciones_ocupadas()

    if num_habitacion not in habitaciones_ocupadas:
        flash('Habitación no encontrada', 'danger')
        return redirect('/dashboard')

    datos_estadia = validar_estadia_para_consumo(
        id_estadia,
        num_habitacion
    )

    if not datos_estadia:
        flash('No se pudo validar la estadía seleccionada.', 'danger')
        return redirect(f'/habitacion/{num_habitacion}')

    exito, mensaje = agregar_consumo_bebida_rapida(
        num_habitacion,
        producto,
        cantidad,
        datos_estadia['pasajero'],
        id_estadia=datos_estadia['id_estadia']
    )

    flash(
        mensaje if exito else mensaje,
        'success' if exito else 'danger'
    )

    return redirect(f'/habitacion/{num_habitacion}')

@app.route('/habitacion/<int:num_habitacion>/anular/<string:id_consumo>', methods=['POST'])
def anular_consumo_habitacion(num_habitacion, id_consumo):
    """Anula un consumo por ID, conservando el historial."""
    motivo = request.form.get('motivo_anulacion', '').strip()
    if not motivo:
        flash('Debe indicar un motivo para anular el consumo.', 'danger')
    elif anular_consumo_por_id(num_habitacion, id_consumo, motivo, DB_CONSUMOS):
        flash('Consumo anulado. El registro original se conserva en el historial.', 'success')
    else:
        flash('No se pudo anular el consumo. Verifique que exista, pertenezca a la habitación y no esté ya anulado.', 'danger')
    return redirect(f'/habitacion/{num_habitacion}')


@app.route('/checkout/<int:num_habitacion>')
def checkout(num_habitacion):
    """Muestra la pantalla de check-out con resumen final"""
    from core.dashboard import es_checkout_hoy

    # Obtener datos del pasajero
    habitaciones_ocupadas = obtener_habitaciones_ocupadas()

    if num_habitacion not in habitaciones_ocupadas:
        flash('Habitación no encontrada o no ocupada', 'danger')
        return redirect('/dashboard')

    # Obtener resumen completo
    datos_pasajero = habitaciones_ocupadas[num_habitacion]
    resumen = obtener_resumen_habitacion(num_habitacion, datos_pasajero)

    # Verificar si es checkout hoy o anticipado
    resumen['es_checkout_hoy'] = es_checkout_hoy(datos_pasajero['egreso'])

    return render_template('checkout.html', checkout=resumen)

@app.route('/checkout/<int:num_habitacion>/confirmar', methods=['POST'])
def confirmar_checkout(num_habitacion):
    """Procesa el check-out individual: elimina al pasajero y sus consumos pagados"""
    habitaciones_ocupadas = obtener_habitaciones_ocupadas()

    if num_habitacion not in habitaciones_ocupadas:
        flash('Habitación no encontrada', 'danger')
        return redirect('/dashboard')

    try:
        # Los consumos no se eliminan: forman parte del historial permanente.

        # 2. Eliminar pasajero del registro
        if os.path.exists(DB_PASAJEROS):
            df_pasajeros = pd.read_csv(DB_PASAJEROS)
            df_pasajeros = df_pasajeros[
                df_pasajeros['Nro. habitación'].apply(extraer_num_hab) != num_habitacion
            ]
            df_pasajeros.to_csv(DB_PASAJEROS, index=False)

        flash(f'✅ Check-out realizado exitosamente. Habitación {num_habitacion} ahora disponible.', 'success')
        return redirect('/dashboard')

    except Exception as e:
        flash(f'❌ Error al procesar check-out: {str(e)}', 'danger')
        return redirect(f'/checkout/{num_habitacion}')


@app.route('/checkout-masivo')
def vista_checkout_masivo():
    """Vista previa del checkout masivo con resumen de habitaciones y consumos"""
    from core.dashboard import obtener_habitaciones_checkout_pendientes
    from core.consumos import obtener_total_consumos

    # Obtener todas las habitaciones con checkout pendiente (hoy + vencidas)
    habitaciones_checkout = obtener_habitaciones_checkout_pendientes()

    if not habitaciones_checkout:
        flash('No hay habitaciones con checkout pendiente para procesar', 'info')
        return redirect('/dashboard')

    # Preparar resumen detallado
    resumen_checkouts = []
    total_consumos_general = 0

    for num_hab in sorted(habitaciones_checkout.keys()):
        datos = habitaciones_checkout[num_hab]
        totales_consumos = obtener_total_consumos(
            num_hab,
            id_estadia=datos.get('ids_estadia', datos.get('id_estadia', ''))
        )

        resumen_checkouts.append({
            'habitacion': num_hab,
            'pasajero': datos['pasajero'],
            'plazas': datos['plazas'],
            'ingreso': datos['ingreso'],
            'egreso': datos['egreso'],
            'voucher': datos.get('voucher', 'N/A'),
            'total_consumos': totales_consumos['total'],
            'detalle_consumos': totales_consumos
        })
        total_consumos_general += totales_consumos['total']

    return render_template('checkout_masivo.html',
                         checkouts=resumen_checkouts,
                         total_habitaciones=len(resumen_checkouts),
                         total_consumos=total_consumos_general)




@app.route('/checkout-masivo/confirmar', methods=['POST'])
def confirmar_checkout_masivo():
    """Procesa el checkout masivo conservando todos los consumos históricos."""
    try:
        if not os.path.exists(DB_PASAJEROS):
            flash('No hay archivo de pasajeros para procesar', 'warning')
            return redirect('/dashboard')

        df_pasajeros = pd.read_csv(DB_PASAJEROS)
        hoy_dt = datetime.now().date()

        ingreso_dt = pd.to_datetime(
            df_pasajeros['Fecha de ingreso'],
            format='%d/%m/%Y',
            errors='coerce'
        )
        egreso_dt = pd.to_datetime(
            df_pasajeros['Fecha de egreso'],
            format='%d/%m/%Y',
            errors='coerce'
        )

        mask_checkout_pendiente = (
            (ingreso_dt.dt.date <= hoy_dt)
            & (egreso_dt.dt.date <= hoy_dt)
        )

        df_checkout = df_pasajeros[mask_checkout_pendiente].copy()

        habitaciones_checkout = set(
            df_checkout['Nro. habitación']
            .apply(extraer_num_hab)
            .dropna()
            .astype(int)
            .tolist()
        )

        if not habitaciones_checkout:
            flash('No hay habitaciones para procesar', 'info')
            return redirect('/dashboard')

        cantidad_procesada = len(habitaciones_checkout)

        # No modificar DB_CONSUMOS.
        # Los consumos se conservan como historial permanente.

        # Retirar únicamente los pasajeros con checkout pendiente.
        df_pasajeros = df_pasajeros[~mask_checkout_pendiente]
        df_pasajeros.to_csv(DB_PASAJEROS, index=False)

        flash(
            f'✅ Checkout masivo completado: {cantidad_procesada} '
            f'habitaciones liberadas. Los consumos históricos se conservaron.',
            'success'
        )

        return redirect('/dashboard')

    except Exception as e:
        flash(f'❌ Error al procesar checkout masivo: {str(e)}', 'danger')
        return redirect('/checkout-masivo')



@app.route('/cargar', methods=['POST'])
def cargar_consumo():
    """Procesar el registro de un consumo"""
    habitacion = request.form.get('habitacion')
    categoria = request.form.get('categoria')
    monto = request.form.get('monto')

    # Validación básica
    if not habitacion or not categoria or not monto:
        flash('Todos los campos son obligatorios', 'danger')
        return redirect('/')

    # Validar que el pasajero exista
    nombre_pasajero = validar_pasajero(habitacion)
    if not nombre_pasajero:
        flash(f'❌ La habitación {habitacion} no está registrada en el sistema', 'danger')
        return redirect('/')

    # Registrar el consumo
    nuevo_registro = {
        'fecha': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'habitacion': habitacion,
        'pasajero': nombre_pasajero,
        'categoria': categoria,
        'monto': float(monto)
    }

    # Guardar en el CSV
    df_nuevo = pd.DataFrame([nuevo_registro])

    if os.path.exists(DB_CONSUMOS):
        df_nuevo.to_csv(DB_CONSUMOS, mode='a', header=False, index=False)
    else:
        df_nuevo.to_csv(DB_CONSUMOS, mode='w', header=True, index=False)

    flash(f'✅ Consumo registrado: {categoria} - ${monto} para {nombre_pasajero} (Hab. {habitacion})', 'success')
    return redirect('/')

@app.route('/cierre-dia')
def cierre_dia():
    """Generar archivo de consulta de consumos agrupados por categoría (CSV)"""
    if not os.path.exists(DB_CONSUMOS):
        flash("No hay consumos registrados para realizar el cierre.", "warning")
        return redirect('/')

    # 1. Leer los consumos registrados
    df = obtener_historial_consumos(DB_CONSUMOS)
    df = df[df['estado'].fillna('vigente').astype(str).str.lower() != 'anulado']

    # 2. Pivotear datos: Habitaciones como filas, solo 3 categorías como columnas
    tabla_cierre = df.pivot_table(
        index=['habitacion', 'pasajero'],
        columns='categoria',
        values='monto',
        aggfunc='sum',
        fill_value=0
    )

    # 3. Asegurar que existan las 3 columnas principales
    for col in ['Bebidas', 'Estadía', 'Map']:
        if col not in tabla_cierre.columns:
            tabla_cierre[col] = 0

    # 4. Seleccionar solo las columnas que nos interesan
    columnas_orden = ['Bebidas', 'Estadía', 'Map']
    tabla_cierre = tabla_cierre[columnas_orden]

    # 5. Calcular el total acumulado por habitación
    tabla_cierre['TOTAL_GENERAL'] = tabla_cierre.sum(axis=1)

    # 6. Guardar temporalmente para la descarga
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as tmp:
        archivo_salida = tmp.name
        tabla_cierre.to_csv(archivo_salida)

    return send_file(archivo_salida, as_attachment=True, download_name=f"consulta_consumos_{datetime.now().strftime('%d-%m-%Y')}.csv")

@app.route('/cierre-xlsx')
def cierre_xlsx():
    """Generar archivo de salidas en formato XLSX (Excel) - Cada categoría en su columna"""
    if not os.path.exists(DB_CONSUMOS):
        flash("No hay consumos registrados para generar el archivo de salidas.", "warning")
        return redirect('/')

    try:
        # Leer consumos
        df_consumos = obtener_historial_consumos(DB_CONSUMOS)
        df_consumos = df_consumos[df_consumos['estado'].fillna('vigente').astype(str).str.lower() != 'anulado']

        # Crear tabla pivote: habitaciones en filas, categorías en columnas
        tabla_pivot = df_consumos.pivot_table(
            index=['habitacion', 'pasajero'],
            columns='categoria',
            values='monto',
            aggfunc='sum',
            fill_value=0
        ).reset_index()

        # Asegurar que existan todas las columnas (aunque estén vacías)
        for col in ['Estadía', 'Map', 'Bebidas']:
            if col not in tabla_pivot.columns:
                tabla_pivot[col] = 0

        # Calcular total por habitación
        tabla_pivot['Total'] = tabla_pivot['Estadía'] + tabla_pivot['Map'] + tabla_pivot['Bebidas']

        # Crear estructura del archivo (replica salidas.xlsx)
        max_filas = 30
        data = [[None] * 6 for _ in range(max_filas)]

        # Fila 0: Título
        data[0] = ['Pase de caja e información a turno mañana', None, None, None, None, None]
        data[2] = [None, None, 'Turno:   00 A 08 HS', None, None, None]
        data[3] = [None, None, None, None, f'Fecha: {datetime.now().strftime("%Y-%m-%d")}', None]
        data[4] = ['Detalle a cobrar de habitaciones con salida', None, None, None, None, None]
        data[5] = ['HAB', 'Estadía', 'Map', 'Bebidas', 'Forma de pago', 'Total']
        data[6] = [None, None, None, None, None, None]

        # Datos de habitaciones - Cada categoría en su columna
        fila_actual = 7
        for idx, row in tabla_pivot.iterrows():
            habitacion = row['habitacion']
            estadia = row['Estadía'] if row['Estadía'] > 0 else None
            map_val = row['Map'] if row['Map'] > 0 else None
            bebidas = row['Bebidas'] if row['Bebidas'] > 0 else None
            total = row['Total']

            # Distribuir valores en sus respectivas columnas
            data[fila_actual] = [
                int(habitacion),  # HAB (col 0)
                estadia,          # Estadía (col 1)
                map_val,          # Map (col 2)
                bebidas,          # Bebidas (col 3)
                None,             # Forma de pago (col 4)
                total             # Total (col 5)
            ]
            fila_actual += 1

        # Rellenar filas vacías
        for i in range(fila_actual, max_filas):
            data[i] = [None, None, None, None, None, 0.0]

        # Guardar como XLSX in archivo temporal
        df_salidas = pd.DataFrame(data)
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.xlsx', delete=False) as tmp:
            archivo_salida = tmp.name
            df_salidas.to_excel(archivo_salida, engine='openpyxl', index=False, header=False)

        return send_file(os.path.abspath(archivo_salida), as_attachment=True, download_name=f'salidas_{datetime.now().strftime("%d-%m-%Y")}.xlsx')

    except Exception as e:
        flash(f"Error al generar archivo Excel: {str(e)}", "danger")
        return redirect('/')

@app.route('/generar-salidas-checkouts')
def generar_salidas_checkouts():
    """Generar archivo consolidado de checkouts del día (XLSX) - Descarga automática"""
    from core.dashboard import obtener_habitaciones_checkout, obtener_habitaciones_ocupadas

    try:
        # Obtener habitaciones con checkout hoy
        checkouts_hoy = obtener_habitaciones_checkout()

        if not checkouts_hoy:
            flash("No hay habitaciones con check-out programado para hoy.", "warning")
            return redirect('/dashboard')

        # Obtener datos de las habitaciones ocupadas
        habitaciones_ocupadas = obtener_habitaciones_ocupadas()

        # Crear lista de habitaciones con checkout y sus consumos
        datos_checkouts = []
        for num_hab in checkouts_hoy:
            if num_hab in habitaciones_ocupadas:
                from core.consumos import obtener_resumen_habitacion
                resumen = obtener_resumen_habitacion(num_hab, habitaciones_ocupadas[num_hab])
                datos_checkouts.append({
                    'habitacion': num_hab,
                    'pasajero': habitaciones_ocupadas[num_hab]['pasajero'],
                    'Estadía': resumen['totales']['Estadía'],
                    'Map': resumen['totales']['Map'],
                    'Bebidas': resumen['totales']['Bebidas'],
                    'Total': resumen['totales']['total']
                })

        # Si no hay datos, generar archivo vacío indicando que no hay consumos
        if not datos_checkouts:
            # Aún así crear estructura para las habitaciones con checkout
            for num_hab in checkouts_hoy:
                datos_checkouts.append({
                    'habitacion': num_hab,
                    'pasajero': 'Sin datos',
                    'Estadía': 0,
                    'Map': 0,
                    'Bebidas': 0,
                    'Total': 0
                })

        # Crear estructura del archivo (replica salidas.xlsx)
        max_filas = 30
        data = [[None] * 6 for _ in range(max_filas)]

        # Encabezados
        data[0] = ['Pase de caja e información a turno mañana', None, None, None, None, None]
        data[2] = [None, None, 'Turno:   00 A 08 HS', None, None, None]
        data[3] = [None, None, None, None, f'Fecha: {datetime.now().strftime("%d/%m/%Y")}', None]
        data[4] = ['Detalle a cobrar de habitaciones con salida HOY', None, None, None, None, None]
        data[5] = ['HAB', 'Estadía', 'Map', 'Bebidas', 'Forma de pago', 'Total']
        data[6] = [None, None, None, None, None, None]

        # Datos de habitaciones con checkout - Cada categoría en su columna
        fila_actual = 7
        for item in sorted(datos_checkouts, key=lambda x: x['habitacion']):
            estadia = item['Estadía'] if item['Estadía'] > 0 else None
            map_val = item['Map'] if item['Map'] > 0 else None
            bebidas = item['Bebidas'] if item['Bebidas'] > 0 else None
            total = item['Total']

            data[fila_actual] = [
                int(item['habitacion']),  # HAB (col 0)
                estadia,                   # Estadía (col 1)
                map_val,                   # Map (col 2)
                bebidas,                   # Bebidas (col 3)
                None,                      # Forma de pago (col 4)
                total                      # Total (col 5)
            ]
            fila_actual += 1

        # Rellenar filas vacías
        for i in range(fila_actual, max_filas):
            data[i] = [None, None, None, None, None, None]

        # Guardar como XLSX en archivo temporal
        df_salidas = pd.DataFrame(data)
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.xlsx', delete=False) as tmp:
            archivo_salida = tmp.name
            df_salidas.to_excel(archivo_salida, engine='openpyxl', index=False, header=False)

        # Descargar automáticamente (usar ruta absoluta)
        return send_file(os.path.abspath(archivo_salida), as_attachment=True, download_name=f'checkouts_{datetime.now().strftime("%d-%m-%Y")}.xlsx')

    except Exception as e:
        flash(f"Error al generar archivo de checkouts: {str(e)}", "danger")
        return redirect('/dashboard')

@app.route('/ver-consumos')
def ver_consumos():
    """Historial permanente de consumos, incluidos los anulados."""
    from markupsafe import escape
    df = obtener_historial_consumos(DB_CONSUMOS)
    filas = []
    for idx, row in df.iterrows():
        estado = str(row.get('estado', 'vigente')).strip().lower()
        anulado = estado == 'anulado'
        clase_fila = 'table-secondary text-muted' if anulado else ''
        badge = '<span class="badge bg-danger">ANULADO</span>' if anulado else '<span class="badge bg-success">VIGENTE</span>'
        fecha_anulacion = escape(str(row.get('fecha_anulacion', '') or ''))
        motivo = escape(str(row.get('motivo_anulacion', '') or ''))
        detalle = f'<div class="small mt-1"><strong>Anulado:</strong> {fecha_anulacion}<br><strong>Motivo:</strong> {motivo}</div>' if anulado else ''
        accion = ''
        if not anulado:
            accion = f"""
                <form method="POST" action="/historial/anular/{escape(str(row.get('id_consumo', '')))}" class="d-grid gap-1">
                    <input class="form-control form-control-sm" name="motivo_anulacion" maxlength="500" required placeholder="Motivo obligatorio">
                    <button type="submit" class="btn btn-warning btn-sm" onclick="return confirm('¿Confirmás la anulación? El registro se conservará en el historial.')">Anular</button>
                </form>"""
        try:
            monto = float(row.get('monto', 0) or 0)
        except (TypeError, ValueError):
            monto = 0.0
        filas.append(f"""
            <tr class="{clase_fila}">
                <td>{idx + 1}</td><td>{escape(str(row.get('fecha', '')))}</td>
                <td>{escape(str(row.get('habitacion', '')))}</td><td>{escape(str(row.get('pasajero', '')))}</td>
                <td>{escape(str(row.get('categoria', '')))}<div class="small">{escape(str(row.get('item', '') or ''))}</div></td>
                <td>${monto:.2f}</td><td>{badge}{detalle}</td><td>{accion}</td>
            </tr>""")
    filas_html = ''.join(filas) or '<tr><td colspan="8" class="text-center">No hay consumos registrados.</td></tr>'
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <title>Historial de Consumos</title></head><body><main class="container mt-4">
    <h2>Historial permanente de consumos</h2>
    <p class="text-muted">Registros conservados: {len(df)}. Los anulados se muestran, pero no integran los totales operativos.</p>
    <div class="table-responsive"><table class="table table-striped table-hover align-middle">
    <thead class="table-dark"><tr><th>#</th><th>Fecha</th><th>Hab.</th><th>Pasajero</th><th>Categoría / artículo</th><th>Monto original</th><th>Estado / auditoría</th><th>Acción</th></tr></thead>
    <tbody>{filas_html}</tbody></table></div>
        <a href="/dashboard" class="btn btn-primary">
        Volver al Dashboard
    </a>
    </main></body></html>"""


@app.route('/historial/anular/<string:id_consumo>', methods=['POST'])
def anular_consumo_historial(id_consumo):
    """Anula un registro desde el historial general usando su ID estable."""
    motivo = request.form.get('motivo_anulacion', '').strip()
    if not motivo:
        flash('Debe indicar un motivo para anular el consumo.', 'danger')
        return redirect('/ver-consumos')
    df = obtener_historial_consumos(DB_CONSUMOS)
    coincidencias = df[df['id_consumo'].astype(str).str.strip() == id_consumo]
    if len(coincidencias) != 1:
        flash('No se encontró un consumo único con ese identificador.', 'danger')
        return redirect('/ver-consumos')
    try:
        habitacion = int(float(coincidencias.iloc[0]['habitacion']))
    except (TypeError, ValueError):
        flash('La habitación del consumo no es válida.', 'danger')
        return redirect('/ver-consumos')
    if anular_consumo_por_id(habitacion, id_consumo, motivo, DB_CONSUMOS):
        flash('Consumo anulado. Se conservó el registro original.', 'success')
    else:
        flash('No se pudo anular el consumo: puede estar ya anulado.', 'danger')
    return redirect('/ver-consumos')


@app.route('/reiniciar-temporada', methods=['GET', 'POST'])
def reiniciar_temporada():
    """La limpieza de consumos por temporada está deshabilitada para proteger el historial."""
    mensaje = (
        "El reinicio que vaciaba consumos está deshabilitado. "
        "El historial es permanente y no debe borrarse al comenzar otra temporada."
    )
    if request.method == 'POST':
        flash(mensaje, 'warning')
        return redirect('/gestionar-pasajeros')
    return f"""
    <!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <title>Temporada e historial</title></head><body>
    <main class="container mt-5"><div class="alert alert-warning">
    <h3>Reinicio de temporada deshabilitado</h3><p>{mensaje}</p>
    <p>Los consumos deben conservarse. La nueva temporada debe cambiar la ocupación activa, no vaciar el historial.</p>
    </div><a href="/dashboard" class="btn btn-primary">Volver al Dashboard</a></main>
    </body></html>"""


@app.route('/gestionar-pasajeros')
def gestionar_pasajeros():
    """Página para gestionar archivos de pasajeros (cambiar entre temporada alta/baja)"""
    from core.dashboard import es_checkout_hoy

    # Obtener información del archivo actual
    info_actual = {
        'total': 0,
        'habitaciones': [],
        'checkouts_hoy': 0,
        'fecha_ingreso_min': 'N/A',
        'fecha_ingreso_max': 'N/A',
        'fecha_egreso_min': 'N/A',
        'fecha_egreso_max': 'N/A'
    }

    if os.path.exists(DB_PASAJEROS):
        df = pd.read_csv(DB_PASAJEROS)
        info_actual['total'] = len(df)
        info_actual['habitaciones'] = df['Nro. habitación'].tolist()

        # Contar checkouts hoy
        checkouts_hoy = 0
        for _, row in df.iterrows():
            if es_checkout_hoy(row['Fecha de egreso']):
                checkouts_hoy += 1
        info_actual['checkouts_hoy'] = checkouts_hoy

        # Rango de fechas
        info_actual['fecha_ingreso_min'] = df['Fecha de ingreso'].min()
        info_actual['fecha_ingreso_max'] = df['Fecha de ingreso'].max()
        info_actual['fecha_egreso_min'] = df['Fecha de egreso'].min()
        info_actual['fecha_egreso_max'] = df['Fecha de egreso'].max()

    return render_template('gestionar_pasajeros.html', info_actual=info_actual)

@app.route('/subir-pasajeros', methods=['POST'])
def subir_pasajeros():
    """
    Importa el padrón de pasajeros conservando la identidad
    individual de cada estadía.
    """
    import shutil

    archivo_temporal = None

    try:
        # 1. Verificar que se haya seleccionado un archivo.
        if 'archivo' not in request.files:
            flash('No se seleccionó ningún archivo.', 'danger')
            return redirect('/gestionar-pasajeros')

        archivo = request.files['archivo']

        if not archivo.filename:
            flash('No se seleccionó ningún archivo.', 'danger')
            return redirect('/gestionar-pasajeros')

        if not archivo.filename.lower().endswith('.csv'):
            flash('El archivo debe tener formato CSV.', 'danger')
            return redirect('/gestionar-pasajeros')

        # 2. Validar el modo de importación.
        modo = request.form.get('modo_carga', 'agregar').strip()

        if modo not in ('agregar', 'reemplazar'):
            flash('El modo de importación seleccionado no es válido.', 'danger')
            return redirect('/gestionar-pasajeros')

        # 3. Leer el CSV nuevo.
        try:
            df_nuevo = pd.read_csv(archivo)
        except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as exc:
            flash(f'No se pudo leer el archivo CSV: {exc}', 'danger')
            return redirect('/gestionar-pasajeros')

        if df_nuevo.empty:
            flash('El archivo CSV no contiene registros.', 'warning')
            return redirect('/gestionar-pasajeros')

        # 4. Validar las columnas necesarias.
        columnas_requeridas = [
            'Nro. habitación',
            'Fecha de ingreso',
            'Fecha de egreso',
            'Apellido y nombre',
            'Nro. doc.',
            'Voucher',
            'Servicios'
        ]

        faltantes = [
            columna for columna in columnas_requeridas
            if columna not in df_nuevo.columns
        ]

        if faltantes:
            flash(
                'Faltan columnas requeridas: '
                + ', '.join(faltantes),
                'danger'
            )
            return redirect('/gestionar-pasajeros')

        # 5. Leer el padrón actual.
        if os.path.exists(DB_PASAJEROS):
            df_existente = pd.read_csv(
                DB_PASAJEROS,
                dtype={'id_estadia': str}
            )
        else:
            df_existente = pd.DataFrame()

        # 6. Procesar las identidades.
        df_final, resumen = procesar_identidades(
            df_existente,
            df_nuevo,
            modo=modo
        )

        # 7. Preparar directorios.
        directorio_datos = os.path.dirname(DB_PASAJEROS) or '.'
        os.makedirs(directorio_datos, exist_ok=True)

              # 8. Crear copia de seguridad antes de modificar el padrón.
        backup_path = None

        if os.path.exists(DB_PASAJEROS):
            directorio_backups = os.path.join(
                directorio_datos,
                'backups'
            )

            os.makedirs(directorio_backups, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')

            backup_path = os.path.join(
                directorio_backups,
                f'pasajeros_backup_{timestamp}.csv'
            )

            shutil.copy2(DB_PASAJEROS, backup_path)


        # 9. Guardar primero en un archivo temporal.
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.csv',
            prefix='pasajeros_',
            dir=directorio_datos,
            delete=False,
            newline='',
            encoding='utf-8'
        ) as tmp:
            archivo_temporal = tmp.name

            df_final.to_csv(
                archivo_temporal,
                index=False
            )

        # 10. Reemplazar el padrón solamente cuando
        # el archivo temporal se haya escrito correctamente.
        os.replace(archivo_temporal, DB_PASAJEROS)
        archivo_temporal = None

        # 11. Preparar el resumen de la operación.
        mensaje = (
            f"Importación completada. "
            f"Coincidencias reconocidas: {resumen['coincidencias']}. "
            f"Nuevas estadías: {resumen['nuevas_estadias']}. "
            f"Coincidencias ambiguas: "
            f"{resumen['coincidencias_ambiguas']}. "
            f"Total de registros activos: {len(df_final)}."
        )

        if modo == 'reemplazar':
            mensaje = 'Padrón completo reemplazado. ' + mensaje
        else:
            mensaje = 'Reservas agregadas/actualizadas. ' + mensaje

        if backup_path:
            mensaje += ' Se creó una copia de seguridad.'

        flash(mensaje, 'success')

        return redirect('/gestionar-pasajeros')

    except Exception as e:
        flash(
            f'Error al importar el padrón de pasajeros: {str(e)}',
            'danger'
        )
        return redirect('/gestionar-pasajeros')

    finally:
        # Si hubo un error antes de completar la escritura,
        # retirar el archivo temporal sin tocar el padrón original.
        if archivo_temporal and os.path.exists(archivo_temporal):
            os.remove(archivo_temporal)


@app.route('/reserva-express', methods=['GET', 'POST'])
def reserva_express():
    """Página de registro rápido para walk-ins (huéspedes sin reserva)"""

    if request.method == 'GET':
        from core.dashboard import obtener_habitaciones_reservadas_futuras
        from core.reserva_express import calcular_noches_maximas

        # Mostrar formulario con habitaciones disponibles
        habitaciones_disponibles = obtener_habitaciones_disponibles()
        habitacion_preseleccionada = request.args.get('habitacion', type=int)
        tiene_reserva_futura = request.args.get('reserva_futura', type=int) == 1

        # Calcular límites de noches por habitación
        limites_habitaciones = {}
        for hab in habitaciones_disponibles:
            limite = calcular_noches_maximas(hab)
            if limite > 0:
                limites_habitaciones[hab] = limite

        # Si tiene reserva futura, obtener la información
        fecha_reserva_futura = None
        if tiene_reserva_futura and habitacion_preseleccionada:
            reservas_futuras = obtener_habitaciones_reservadas_futuras()
            if habitacion_preseleccionada in reservas_futuras:
                fecha_reserva_futura = reservas_futuras[habitacion_preseleccionada]['ingreso']

        return render_template('reserva_express.html',
                             habitaciones=habitaciones_disponibles,
                             total_disponibles=len(habitaciones_disponibles),
                             habitacion_preseleccionada=habitacion_preseleccionada,
                             tiene_reserva_futura=tiene_reserva_futura,
                             fecha_reserva_futura=fecha_reserva_futura,
                             limites_habitaciones=limites_habitaciones)

    # POST: Procesar reserva
    habitacion = request.form.get('habitacion')
    nombre = request.form.get('nombre', 'Huésped sin reserva').strip()
    pax = request.form.get('pax', 1)
    servicios = request.form.get('servicios', 'DESAYUNO')
    noches = request.form.get('noches', 1)

    # Validar datos
    valido, error = validar_datos_reserva(habitacion, nombre, pax)
    if not valido:
        flash(f'❌ {error}', 'danger')
        return redirect('/reserva-express')

    # Crear reserva con las noches solicitadas
    reserva, mensaje = crear_reserva_express(habitacion, nombre, pax, servicios, noches)

    if reserva:
        flash(f'✅ {mensaje}. Habitación {habitacion} reservada para {nombre} por {noches} noche(s).', 'success')
        return redirect('/dashboard')
    else:
        flash(f'❌ {mensaje}', 'danger')
        return redirect('/reserva-express')

@app.route('/cambiar-habitacion/<int:num_habitacion>', methods=['GET', 'POST'])
def cambiar_habitacion_route(num_habitacion):
    """Interfaz para cambiar un huésped de habitación por desperfectos"""
    from core.cambio_habitacion import (
        obtener_habitaciones_disponibles_para_cambio,
        cambiar_habitacion,
        validar_cambio_habitacion
    )

    if request.method == 'GET':
        # Verificar que la habitación esté ocupada
        habitaciones_ocupadas = obtener_habitaciones_ocupadas()

        if num_habitacion not in habitaciones_ocupadas:
            flash('La habitación no está ocupada actualmente', 'danger')
            return redirect('/dashboard')

        # Obtener datos del pasajero
        datos_pasajero = habitaciones_ocupadas[num_habitacion]

        # Contar solo consumos identificados con la estadía actual.
        ids_estadia = datos_pasajero.get(
            'ids_estadia',
            [datos_pasajero.get('id_estadia', '')]
        )
        cantidad_consumos = 0
        if os.path.exists(DB_CONSUMOS):
            df_consumos = pd.read_csv(DB_CONSUMOS)
            if 'habitacion' in df_consumos.columns and 'id_estadia' in df_consumos.columns:
                ids_actuales = {
                    str(identificador).strip()
                    for identificador in ids_estadia
                    if (
                        identificador is not None
                        and pd.notna(identificador)
                        and str(identificador).strip()
                    )
                }
                ids_consumos = (
                    df_consumos['id_estadia']
                    .fillna('')
                    .astype(str)
                    .str.strip()
                )
                habitaciones = pd.to_numeric(
                    df_consumos['habitacion'],
                    errors='coerce'
                )
                cantidad_consumos = int(
                    (
                        (habitaciones == num_habitacion)
                        & ids_consumos.isin(ids_actuales)
                    ).sum()
                )

        # Obtener habitaciones disponibles
        habitaciones_disponibles = obtener_habitaciones_disponibles_para_cambio(num_habitacion)

        return render_template('cambiar_habitacion.html',
                             habitacion_origen=num_habitacion,
                             datos_pasajero=datos_pasajero,
                             cantidad_consumos=cantidad_consumos,
                             habitaciones_disponibles=habitaciones_disponibles,
                             total_disponibles=len(habitaciones_disponibles))

    # POST: Procesar cambio
    habitacion_destino = request.form.get('habitacion_destino')
    motivo = request.form.get('motivo', '')
    observaciones = request.form.get('observaciones', '')

    # Combinar motivo con observaciones
    motivo_completo = f"{motivo}"
    if observaciones:
        motivo_completo += f" - {observaciones}"

    # Validar
    valido, error = validar_cambio_habitacion(num_habitacion, habitacion_destino)
    if not valido:
        flash(f'❌ {error}', 'danger')
        return redirect(f'/cambiar-habitacion/{num_habitacion}')

    # Realizar cambio
    exito, mensaje = cambiar_habitacion(num_habitacion, habitacion_destino, motivo_completo)

    if exito:
        flash(f'✅ {mensaje}', 'success')
        return redirect(f'/habitacion/{habitacion_destino}')
    else:
        flash(f'❌ {mensaje}', 'danger')
        return redirect(f'/cambiar-habitacion/{num_habitacion}')


@app.route('/cambiar-habitacion-parcial/<int:num_habitacion>', methods=['GET', 'POST'])
def cambiar_habitacion_parcial_route(num_habitacion):
    """Interfaz para mover un solo pasajero a una habitación vacía u ocupada con cupo."""
    from core.cambio_habitacion import (
        obtener_habitaciones_destino_para_cambio_parcial,
        cambiar_pasajero_individual,
        validar_cambio_parcial
    )
    from core.dashboard import obtener_todos_pasajeros_habitacion

    if request.method == 'GET':
        habitaciones_ocupadas = obtener_habitaciones_ocupadas()

        if num_habitacion not in habitaciones_ocupadas:
            flash('La habitación no está ocupada actualmente', 'danger')
            return redirect('/dashboard')

        datos_pasajero = habitaciones_ocupadas[num_habitacion]
        pasajeros_habitacion = obtener_todos_pasajeros_habitacion(num_habitacion)
        destinos = obtener_habitaciones_destino_para_cambio_parcial(num_habitacion)

        if len(pasajeros_habitacion) <= 1:
            flash('Esta habitación tiene un solo pasajero. Use cambio total.', 'info')
            return redirect(f'/cambiar-habitacion/{num_habitacion}')

        return render_template(
            'cambiar_habitacion_parcial.html',
            habitacion_origen=num_habitacion,
            datos_pasajero=datos_pasajero,
            pasajeros_habitacion=pasajeros_habitacion,
            habitaciones_destino=destinos,
            total_destinos=len(destinos)
        )

    habitacion_destino = request.form.get('habitacion_destino')
    nombre_pasajero = request.form.get('pasajero')
    motivo = request.form.get('motivo', '')
    observaciones = request.form.get('observaciones', '')

    motivo_completo = f"{motivo}" if motivo else ""
    if observaciones:
        motivo_completo = f"{motivo_completo} - {observaciones}" if motivo_completo else observaciones

    valido, error = validar_cambio_parcial(num_habitacion, habitacion_destino, nombre_pasajero)
    if not valido:
        flash(f'❌ {error}', 'danger')
        return redirect(f'/cambiar-habitacion-parcial/{num_habitacion}')

    exito, mensaje = cambiar_pasajero_individual(num_habitacion, habitacion_destino, nombre_pasajero, motivo_completo)
    if exito:
        flash(f'✅ {mensaje}', 'success')
        return redirect(f'/habitacion/{habitacion_destino}')

    flash(f'❌ {mensaje}', 'danger')
    return redirect(f'/cambiar-habitacion-parcial/{num_habitacion}')


@app.route('/bebidas-rapidas', methods=['GET', 'POST'])
def bebidas_rapidas():
    """Pantalla de carga masiva de bebidas asociadas a una estadía."""
    from core.dashboard import obtener_todos_pasajeros_habitacion

    if request.method == 'POST':
        habitacion = request.form.get('habitacion')
        id_estadia = request.form.get('id_estadia', '').strip()
        producto = request.form.get('producto')
        cantidad = request.form.get('cantidad', 1)

        try:
            habitacion = int(habitacion)
        except (TypeError, ValueError):
            flash('Habitación inválida', 'danger')
            return redirect('/bebidas-rapidas')

        habitaciones_ocupadas = obtener_habitaciones_ocupadas()

        if habitacion not in habitaciones_ocupadas:
            flash('La habitación no está ocupada', 'danger')
            return redirect('/bebidas-rapidas')

        datos_estadia = validar_estadia_para_consumo(
            id_estadia,
            habitacion
        )

        if not datos_estadia:
            flash('No se pudo validar la estadía seleccionada.', 'danger')
            return redirect('/bebidas-rapidas')

        exito, mensaje = agregar_consumo_bebida_rapida(
            habitacion,
            producto,
            cantidad,
            datos_estadia['pasajero'],
            id_estadia=datos_estadia['id_estadia']
        )

        flash(mensaje, 'success' if exito else 'danger')
        return redirect('/bebidas-rapidas')

    habitaciones_ocupadas = obtener_habitaciones_ocupadas()
    habitaciones = []

    for num_habitacion in sorted(habitaciones_ocupadas.keys()):
        pasajeros = obtener_todos_pasajeros_habitacion(num_habitacion)

        habitaciones.append({
            'numero': num_habitacion,
            'pasajeros': pasajeros,
            'titular': habitaciones_ocupadas[num_habitacion]['pasajero']
        })

    return render_template(
        'bebidas_rapidas.html',
        habitaciones=habitaciones,
        catalogo_bebidas=obtener_catalogo_bebidas(),
        cantidades_rapidas=CANTIDADES_RAPIDAS
    )


def formatear_periodo_consumos(desde, hasta):
    inicio = desde.strftime('%d/%m/%Y')
    return inicio if desde.date() == hasta.date() else f"{inicio} al {hasta.strftime('%d/%m/%Y')}"


@app.route('/informe-consumos', methods=['GET', 'POST'])
def informe_consumos():
    """Consulta el consolidado de productos consumidos por período."""

    hoy = datetime.now().strftime('%Y-%m-%d')
    fecha_desde = request.form.get('fecha_desde', hoy)
    fecha_hasta = request.form.get('fecha_hasta', hoy)

    resultado = None
    error = None
    periodo = None

    if request.method == 'POST':
        try:
            # El calendario HTML entrega las fechas como AAAA-MM-DD.
            desde = datetime.strptime(fecha_desde, '%Y-%m-%d')
            hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d')

            # La función de consolidación espera DD/MM/AAAA.
            resultado = generar_consolidado_productos(
                desde.strftime('%d/%m/%Y'),
                hasta.strftime('%d/%m/%Y'),
                DB_CONSUMOS,
            )
            periodo = formatear_periodo_consumos(desde, hasta)

        except (ValueError, TypeError) as exc:
            error = str(exc)

    return render_template(
        'informe_consumos.html',
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        resultado=resultado,
        error=error,
        periodo=periodo,
    )

@app.route('/informe-consumos-xlsx', methods=['POST'])
def exportar_informe_consumos_xlsx():
    """Exporta a Excel el consolidado de productos del período seleccionado."""

    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    fecha_desde = request.form.get('fecha_desde', '').strip()
    fecha_hasta = request.form.get('fecha_hasta', '').strip()

    try:
        desde = datetime.strptime(fecha_desde, '%Y-%m-%d')
        hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d')

        resultado = generar_consolidado_productos(
            desde.strftime('%d/%m/%Y'),
            hasta.strftime('%d/%m/%Y'),
            DB_CONSUMOS,
        )

        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            archivo_salida = tmp.name

        with pd.ExcelWriter(archivo_salida, engine='openpyxl') as writer:
            detalle = resultado['detalle'][['Producto', 'Unidades']].copy()
            detalle.to_excel(writer, sheet_name='Informe de consumos', index=False, startrow=4)

            hoja = writer.sheets['Informe de consumos']
            hoja['A1'] = 'INFORME CONSOLIDADO DE CONSUMOS'
            hoja['A2'] = f"Período: {formatear_periodo_consumos(desde, hasta)}"
            hoja['A3'] = f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"

            fila_encabezado = 5
            fila_total = fila_encabezado + len(detalle) + 1

            hoja.cell(row=fila_total, column=1, value='TOTAL GENERAL')
            hoja.cell(row=fila_total, column=2, value=resultado['total_unidades'])

            hoja.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
            hoja['A1'].font = Font(bold=True, size=16, color='FFFFFF')
            hoja['A1'].fill = PatternFill('solid', fgColor='245B78')
            hoja['A1'].alignment = Alignment(horizontal='center')

            for celda in hoja[fila_encabezado]:
                celda.font = Font(bold=True, color='FFFFFF')
                celda.fill = PatternFill('solid', fgColor='245B78')
                celda.alignment = Alignment(horizontal='center')

            for fila in range(fila_encabezado + 1, fila_total + 1):
                hoja.cell(row=fila, column=2).number_format = '#,##0.##'

            for celda in hoja[fila_total]:
                celda.font = Font(bold=True)
                celda.border = Border(top=Side(style='thin', color='245B78'))

            hoja.column_dimensions['A'].width = 38
            hoja.column_dimensions['B'].width = 16
            hoja.freeze_panes = 'A6'
            hoja.auto_filter.ref = f'A5:B{fila_encabezado + len(detalle)}'

        nombre_archivo = (
            f"informe_consumos_{desde.strftime('%d-%m-%Y')}_"
            f"{hasta.strftime('%d-%m-%Y')}.xlsx"
        )

        return send_file(
            os.path.abspath(archivo_salida),
            as_attachment=True,
            download_name=nombre_archivo,
        )

    except (ValueError, TypeError) as exc:
        flash(f'No se pudo generar el informe: {exc}', 'danger')
        return redirect('/informe-consumos')

    except Exception as exc:
        flash(f'Error al exportar el informe a Excel: {exc}', 'danger')
        return redirect('/informe-consumos')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)