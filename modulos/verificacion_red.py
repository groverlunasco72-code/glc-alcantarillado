# -*- coding: utf-8 -*-
from qgis.core import QgsWkbTypes, QgsField
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QCheckBox, QGroupBox, QButtonGroup, QRadioButton
)
from .utils import obtener_vertices_linea


# ============================================================
# COMPATIBILIDAD: QMetaType (QGIS 3.38+ / 4.x) vs QVariant (antiguo)
# ============================================================
try:
    from qgis.PyQt.QtCore import QMetaType
    _USE_QMETATYPE = True
except ImportError:
    _USE_QMETATYPE = False


def _campo(nombre, tipo='int', longitud=0, precision=0):
    """
    Crea un QgsField evitando DeprecationWarning.

    tipo: 'string' | 'double' | 'int' | 'bool'
    """
    if _USE_QMETATYPE:
        mapa = {
            'string': QMetaType.QString,
            'double': QMetaType.Double,
            'int':    QMetaType.Int,
            'bool':   QMetaType.Bool,
        }
        qtipo = mapa.get(tipo, QMetaType.QString)
        return QgsField(nombre, qtipo, '', longitud, precision)
    else:
        mapa = {
            'string': QVariant.String,
            'double': QVariant.Double,
            'int':    QVariant.Int,
            'bool':   QVariant.Bool,
        }
        qvtipo = mapa.get(tipo, QVariant.String)
        return QgsField(nombre, qvtipo, tipo, longitud, precision)


class VerificadorRed:
    def __init__(self, iface):
        self.iface = iface
        self.capa_verificar = None
        self.red_verificada = None
        self.resultados = {}
        self.opcion_numeracion = None

    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC')
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(450)

        layout = QVBoxLayout()

        # Título
        label_titulo = QLabel('🔍 VERIFICACIÓN DE CONEXION')
        label_titulo.setStyleSheet('font-size: 14pt; font-weight: bold;')
        layout.addWidget(label_titulo)

        label_info = QLabel('Verifica todos los aspectos críticos de la red:\n'
                           '• Conexiones entre vértices de tuberías\n'
                           '• Tuberías duplicadas o superpuestas\n'
                           '• Tuberías con longitud cero\n'
                           '• Puntos finales desconectados\n'
                           '• Tuberías aisladas')
        label_info.setWordWrap(True)
        layout.addWidget(label_info)

        layout.addWidget(QLabel('─' * 50))

        # Capa actual
        layer_actual = self.iface.activeLayer()
        if layer_actual and layer_actual.geometryType() == QgsWkbTypes.LineGeometry:
            label_capa = QLabel(f'📌 Capa activa: <b>{layer_actual.name()}</b>')
        else:
            label_capa = QLabel('⚠️ No hay capa de línea activa')
        layout.addWidget(label_capa)

        btn_seleccionar = QPushButton('🔄 Usar Capa Activa')
        btn_seleccionar.clicked.connect(lambda: self.seleccionar_capa(dialog))
        layout.addWidget(btn_seleccionar)

        layout.addWidget(QLabel('─' * 50))

        # Opciones de numeración ID_O
        group_numeracion = QGroupBox('🔢 Opciones de Numeración ID_O')
        numeracion_layout = QVBoxLayout()

        label_numeracion = QLabel('¿Cómo deseas manejar el campo ID_O?')
        numeracion_layout.addWidget(label_numeracion)

        # Grupo de botones para seleccionar opción
        self.opcion_numeracion = QButtonGroup(dialog)

        rb_renumerar = QRadioButton('🔄 Renumerar completamente (1, 2, 3, ...)')
        rb_renumerar.setChecked(True)
        numeracion_layout.addWidget(rb_renumerar)
        self.opcion_numeracion.addButton(rb_renumerar, 1)

        rb_mantener = QRadioButton('📋 Mantener numeración actual (usar existente)')
        numeracion_layout.addWidget(rb_mantener)
        self.opcion_numeracion.addButton(rb_mantener, 2)

        # Información adicional
        label_info_id = QLabel('💡 Nota: Si no existe ID_O, se creará automáticamente')
        label_info_id.setStyleSheet('color: #666; font-size: 9pt;')
        numeracion_layout.addWidget(label_info_id)

        group_numeracion.setLayout(numeracion_layout)
        layout.addWidget(group_numeracion)

        layout.addWidget(QLabel('─' * 50))

        # Parámetros de tolerancia
        group_tolerancia = QGroupBox('⚙️ Parámetros de Verificación')
        tolerancia_layout = QVBoxLayout()

        label_tolerancia = QLabel('Tolerancia para considerar puntos "cercanos" (metros):')
        tolerancia_layout.addWidget(label_tolerancia)

        spin_tolerancia = QDoubleSpinBox()
        spin_tolerancia.setRange(0.001, 10.0)
        spin_tolerancia.setSingleStep(0.01)
        spin_tolerancia.setValue(0.01)
        spin_tolerancia.setSuffix(' m')
        spin_tolerancia.setDecimals(3)
        tolerancia_layout.addWidget(spin_tolerancia)

        # Opciones de verificación
        label_opciones = QLabel('Verificar:')
        tolerancia_layout.addWidget(label_opciones)

        check_conexiones = QCheckBox('🔗 Conexiones entre vértices')
        check_conexiones.setChecked(True)
        tolerancia_layout.addWidget(check_conexiones)

        check_duplicados = QCheckBox('📋 Tuberías duplicadas/superpuestas')
        check_duplicados.setChecked(True)
        tolerancia_layout.addWidget(check_duplicados)

        check_longitud = QCheckBox('📏 Longitud cero')
        check_longitud.setChecked(True)
        tolerancia_layout.addWidget(check_longitud)

        check_aisladas = QCheckBox('🏠 Tuberías aisladas (menos de 2 conexiones)')
        check_aisladas.setChecked(True)
        tolerancia_layout.addWidget(check_aisladas)

        group_tolerancia.setLayout(tolerancia_layout)
        layout.addWidget(group_tolerancia)

        # Botón de verificar
        btn_verificar = QPushButton('🔍 VERIFICAR RED COMPLETA')
        btn_verificar.setStyleSheet(
            'background-color: #4CAF50; color: white; font-weight: bold; '
            'font-size: 12pt; padding: 10px;'
        )
        btn_verificar.clicked.connect(lambda: self.verificar_completo(
            dialog, spin_tolerancia.value(),
            check_conexiones.isChecked(),
            check_duplicados.isChecked(),
            check_longitud.isChecked(),
            check_aisladas.isChecked()
        ))
        layout.addWidget(btn_verificar)

        dialog.setLayout(layout)
        dialog.exec_()

    def seleccionar_capa(self, dialog):
        layer = self.iface.activeLayer()
        if not layer:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No hay capa activa')
            return

        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'La capa debe ser de línea')
            return

        self.capa_verificar = layer
        QMessageBox.information(self.iface.mainWindow(), 'OK',
                                f'✅ Capa seleccionada: {layer.name()}')

    def manejar_id_o(self, layer):
        """
        Manejar el campo ID_O según la opción seleccionada por el usuario.

        IMPORTANTE: se hacen commits intermedios entre deleteAttributes,
        addAttributes y la asignación de valores, porque de lo contrario
        QGIS puede no refrescar los fields() y lanzar KeyError.
        """
        opcion = self.opcion_numeracion.checkedId() if self.opcion_numeracion else 1

        # Verificar si existe el campo ID_O
        idx_id_o = layer.fields().indexFromName('ID_O')

        if opcion == 1:  # Renumerar completamente
            # ---- Paso 1: Eliminar el campo existente (si hay) ----
            if idx_id_o != -1:
                layer.startEditing()
                layer.dataProvider().deleteAttributes([idx_id_o])
                layer.commitChanges()
                layer.updateFields()

            # ---- Paso 2: Crear el campo nuevo ----
            layer.startEditing()
            layer.dataProvider().addAttributes([_campo('ID_O', 'int')])
            layer.commitChanges()
            layer.updateFields()

            # ---- Paso 3: Renumerar features ----
            idx_id_o = layer.fields().indexFromName('ID_O')
            if idx_id_o == -1:
                QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                    'No se pudo crear el campo ID_O')
                return

            layer.startEditing()
            contador = 1
            for feature in layer.getFeatures():
                layer.changeAttributeValue(feature.id(), idx_id_o, contador)
                contador += 1
            layer.commitChanges()

            QMessageBox.information(self.iface.mainWindow(), 'OK',
                                    '✅ ID_O renumerado completamente')

        else:  # Mantener numeración actual
            if idx_id_o == -1:
                # Si no existe, crear el campo
                layer.startEditing()
                layer.dataProvider().addAttributes([_campo('ID_O', 'int')])
                layer.commitChanges()
                layer.updateFields()

                # Asignar valores basados en ID de feature
                idx_id_o = layer.fields().indexFromName('ID_O')
                if idx_id_o == -1:
                    QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                        'No se pudo crear el campo ID_O')
                    return

                layer.startEditing()
                for feature in layer.getFeatures():
                    layer.changeAttributeValue(feature.id(), idx_id_o, feature.id())
                layer.commitChanges()

                QMessageBox.information(self.iface.mainWindow(), 'OK',
                                        '✅ ID_O creado con valores existentes')
            else:
                QMessageBox.information(self.iface.mainWindow(), 'OK',
                                        '📋 Manteniendo numeración actual de ID_O')

    def verificar_completo(self, dialog, tolerancia, verif_conexiones,
                           verif_duplicados, verif_longitud, verif_aisladas):
        """Verificación completa de la red"""
        if not self.capa_verificar:
            layer = self.iface.activeLayer()
            if layer and layer.geometryType() == QgsWkbTypes.LineGeometry:
                self.capa_verificar = layer
            else:
                QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                    'Selecciona una capa de línea válida')
                return

        layer = self.capa_verificar

        # Manejar ID_O según opción seleccionada
        self.manejar_id_o(layer)

        # ⭐ Verificar que el campo ID_O existe antes de continuar
        idx_id_o = layer.fields().indexFromName('ID_O')
        if idx_id_o == -1:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se pudo crear/leer el campo ID_O.\n'
                                'Abortando verificación.')
            return

        self.resultados = {
            'conexiones': [],
            'duplicados': [],
            'longitud_cero': [],
            'aisladas': [],
            'estadisticas': {}
        }

        # Obtener todas las geometrías y sus puntos
        features_info = []
        for feature in layer.getFeatures():
            geom = feature.geometry()
            if not geom or geom.isEmpty():
                continue

            vertices = obtener_vertices_linea(geom)
            if not vertices or len(vertices) < 2:
                continue

            # ⭐ Usar índice del campo en lugar de nombre
            id_o = feature.attribute(idx_id_o)
            if id_o is None:
                id_o = feature.id()

            # Calcular longitud
            longitud = geom.length()

            features_info.append({
                'id': feature.id(),
                'id_o': id_o,
                'geom': geom,
                'vertices': vertices,
                'inicio': vertices[0],
                'fin': vertices[-1],
                'longitud': longitud,
                'feature': feature
            })

        if not features_info:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontraron líneas válidas')
            return

        # 1. Verificar longitud cero
        if verif_longitud:
            self.verificar_longitud_cero(features_info)

        # 2. Verificar duplicados
        if verif_duplicados:
            self.verificar_duplicados(features_info, tolerancia)

        # 3. Verificar conexiones entre vértices
        if verif_conexiones:
            self.verificar_conexiones(features_info, tolerancia)

        # 4. Verificar tuberías aisladas
        if verif_aisladas:
            self.verificar_aisladas(features_info, tolerancia)

        # Mostrar resultados detallados
        self.mostrar_resultados_completos(features_info, tolerancia)

    def verificar_longitud_cero(self, features_info):
        """Verificar líneas con longitud cero"""
        for info in features_info:
            if info['longitud'] <= 0.001:  # Menos de 1mm
                self.resultados['longitud_cero'].append({
                    'id': info['id'],
                    'id_o': info['id_o'],
                    'longitud': info['longitud']
                })

    def verificar_duplicados(self, features_info, tolerancia):
        """Verificar líneas duplicadas o superpuestas"""
        for i in range(len(features_info)):
            for j in range(i + 1, len(features_info)):
                info1 = features_info[i]
                info2 = features_info[j]

                geom1 = info1['geom']
                geom2 = info2['geom']

                # Verificar si las líneas son duplicadas (mismos puntos extremos)
                dist_inicio_inicio = info1['inicio'].distance(info2['inicio'])
                dist_fin_fin = info1['fin'].distance(info2['fin'])
                dist_inicio_fin = info1['inicio'].distance(info2['fin'])
                dist_fin_inicio = info1['fin'].distance(info2['inicio'])

                # Son duplicadas si los puntos extremos coinciden (en cualquier orden)
                if (dist_inicio_inicio <= tolerancia and dist_fin_fin <= tolerancia) or \
                   (dist_inicio_fin <= tolerancia and dist_fin_inicio <= tolerancia):
                    self.resultados['duplicados'].append({
                        'linea1_id': info1['id_o'],
                        'linea2_id': info2['id_o'],
                        'distancia_max': max(dist_inicio_inicio, dist_fin_fin,
                                             dist_inicio_fin, dist_fin_inicio)
                    })
                    continue

                # Verificar superposición parcial (intersección)
                try:
                    if geom1.intersects(geom2):
                        interseccion = geom1.intersection(geom2)
                        if not interseccion.isEmpty():
                            # Verificar que no sea solo un punto (intersección válida)
                            if interseccion.length() > tolerancia:
                                self.resultados['duplicados'].append({
                                    'linea1_id': info1['id_o'],
                                    'linea2_id': info2['id_o'],
                                    'distancia_max': 0,
                                    'tipo': 'superposicion_parcial'
                                })
                except Exception:
                    pass

    def verificar_conexiones(self, features_info, tolerancia):
        """Verificar conexiones entre vértices"""
        # Crear diccionario de puntos extremos
        puntos_extremos = []
        for info in features_info:
            puntos_extremos.append({
                'id_o': info['id_o'],
                'punto': info['inicio'],
                'tipo': 'inicio',
                'info': info
            })
            puntos_extremos.append({
                'id_o': info['id_o'],
                'punto': info['fin'],
                'tipo': 'fin',
                'info': info
            })

        # Verificar cada punto extremo
        for i, p1 in enumerate(puntos_extremos):
            encontro_conexion = False
            for j, p2 in enumerate(puntos_extremos):
                if i == j or p1['id_o'] == p2['id_o']:
                    continue

                dist = p1['punto'].distance(p2['punto'])
                if dist <= tolerancia:
                    encontro_conexion = True
                    # Registrar conexión exitosa
                    break

            if not encontro_conexion:
                # Punto extremo sin conexión
                self.resultados['conexiones'].append({
                    'id_o': p1['id_o'],
                    'tipo': p1['tipo'],
                    'punto': p1['punto']
                })

    def verificar_aisladas(self, features_info, tolerancia):
        """Verificar tuberías aisladas (menos de 2 conexiones)"""
        # Contar conexiones por tubería
        conteo_conexiones = {info['id_o']: 0 for info in features_info}

        for info in features_info:
            for otro_info in features_info:
                if info['id_o'] == otro_info['id_o']:
                    continue

                # Verificar si algún extremo conecta con el otro
                dist_ini_ini = info['inicio'].distance(otro_info['inicio'])
                dist_ini_fin = info['inicio'].distance(otro_info['fin'])
                dist_fin_ini = info['fin'].distance(otro_info['inicio'])
                dist_fin_fin = info['fin'].distance(otro_info['fin'])

                if min(dist_ini_ini, dist_ini_fin, dist_fin_ini, dist_fin_fin) <= tolerancia:
                    conteo_conexiones[info['id_o']] += 1

        # Identificar aisladas
        for id_o, conexiones in conteo_conexiones.items():
            if conexiones < 2:
                # Encontrar la información de la tubería
                for info in features_info:
                    if info['id_o'] == id_o:
                        self.resultados['aisladas'].append({
                            'id_o': id_o,
                            'conexiones': conexiones,
                            'longitud': info['longitud']
                        })
                        break

    def mostrar_resultados_completos(self, features_info, tolerancia):
        """Mostrar resultados completos de la verificación"""
        mensaje = "=" * 60 + "\n"
        mensaje += "🔍 GLC - VERIFICACIÓN COMPLETA DE RED DE ALCANTARILLADO\n"
        mensaje += "=" * 60 + "\n\n"

        # Estadísticas generales
        total_tuberias = len(features_info)
        mensaje += f"📊 ESTADÍSTICAS GENERALES:\n"
        mensaje += f"• Total de tuberías analizadas: {total_tuberias}\n"
        mensaje += f"• Tolerancia utilizada: {tolerancia} m\n\n"

        # 1. Longitud cero
        if self.resultados['longitud_cero']:
            mensaje += "❌ TUBERÍAS CON LONGITUD CERO:\n"
            mensaje += f"• Total: {len(self.resultados['longitud_cero'])}\n"
            for item in self.resultados['longitud_cero']:
                mensaje += (f"  - ID_O: {item['id_o']} (ID: {item['id']}) - "
                            f"Longitud: {item['longitud']:.6f} m\n")
            mensaje += "\n"
        else:
            mensaje += "✅ No se encontraron tuberías con longitud cero\n\n"

        # 2. Tuberías duplicadas
        if self.resultados['duplicados']:
            mensaje += "⚠️ TUBERÍAS DUPLICADAS O SUPUERPESTAS:\n"
            mensaje += f"• Total: {len(self.resultados['duplicados'])}\n"
            for item in self.resultados['duplicados']:
                tipo = "DUPLICADA" if 'tipo' not in item else "SUPERPUESTA PARCIAL"
                mensaje += (f"  - {tipo}: ID_O {item['linea1_id']} ↔ "
                            f"ID_O {item['linea2_id']}")
                if 'distancia_max' in item and item['distancia_max'] > 0:
                    mensaje += f" (dist: {item['distancia_max']:.3f} m)"
                mensaje += "\n"
            mensaje += "\n"
        else:
            mensaje += "✅ No se encontraron tuberías duplicadas o superpuestas\n\n"

        # 3. Conexiones faltantes
        if self.resultados['conexiones']:
            mensaje += "🔗 PUNTOS EXTREMOS SIN CONEXIÓN:\n"
            mensaje += f"• Total: {len(self.resultados['conexiones'])}\n"
            for item in self.resultados['conexiones']:
                punto = item['punto']
                mensaje += (f"  - Tubería ID_O: {item['id_o']} - "
                            f"{item['tipo'].upper()} - "
                            f"Coord: ({punto.x():.3f}, {punto.y():.3f})\n")
            mensaje += "\n"
        else:
            mensaje += "✅ Todos los puntos extremos están correctamente conectados\n\n"

        # 4. Tuberías aisladas
        if self.resultados['aisladas']:
            mensaje += "🏠 TUBERÍAS AISLADAS (menos de 2 conexiones):\n"
            mensaje += f"• Total: {len(self.resultados['aisladas'])}\n"
            for item in self.resultados['aisladas']:
                mensaje += (f"  - ID_O: {item['id_o']} - "
                            f"Conexiones: {item['conexiones']} - "
                            f"Longitud: {item['longitud']:.3f} m\n")
            mensaje += "\n"
        else:
            mensaje += "✅ No se encontraron tuberías aisladas\n\n"

        # Resumen final
        total_problemas = (len(self.resultados['longitud_cero']) +
                          len(self.resultados['duplicados']) +
                          len(self.resultados['conexiones']) +
                          len(self.resultados['aisladas']))

        mensaje += "=" * 60 + "\n"
        mensaje += f"📋 RESUMEN FINAL:\n"
        if total_problemas == 0:
            mensaje += "🎉 ¡EXCELENTE! La red está perfectamente verificada sin problemas\n"
        else:
            mensaje += f"⚠️ Se encontraron {total_problemas} problemas que requieren atención\n"
            mensaje += "   • Tuberías con longitud cero: " + ("✅" if not self.resultados['longitud_cero'] else "❌") + "\n"
            mensaje += "   • Tuberías duplicadas: " + ("✅" if not self.resultados['duplicados'] else "❌") + "\n"
            mensaje += "   • Puntos sin conexión: " + ("✅" if not self.resultados['conexiones'] else "❌") + "\n"
            mensaje += "   • Tuberías aisladas: " + ("✅" if not self.resultados['aisladas'] else "❌") + "\n"

        # Mostrar mensaje
        QMessageBox.information(self.iface.mainWindow(),
                                'Resultados de Verificación', mensaje)