# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import QAction
import os


class GLCAlcantarilladoPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = '&GLC Alcantarillado'
        self.toolbar = self.iface.addToolBar('GLC Alcantarillado')
        self.toolbar.setObjectName('GLCAlcantarilladoToolbar')

        # ============================================================
        # IMPORTAR MÓDULOS
        # ============================================================
        from .modulos.verificacion_red import VerificadorRed
        from .modulos.generar_camaras import GeneradorCamaras
        from .modulos.copiar_red import CopiarRed
        from .modulos.direccion_flujo import DireccionFlujo
        from .modulos.cabezas_atarjea import CabezasAtarjea
        from .modulos.dividir_tuberia import DividirTuberia
        from .modulos.añadir_tuberia import AnadirTuberia
        from .modulos.eliminar_tuberia import EliminarTuberia
        from .modulos.eliminar_camara import EliminarCamara
        from .modulos.acumulados import Acumulados
        from .modulos.calcular_areas import CalcularAreas
        from .modulos.calcular_areas_acumuladas import CalcularAreasAcumuladas
        from .modulos.calcular_caudales import CalcularCaudales
        from .modulos.calcular_caudales_tramo import CalcularCaudalesTramo
        from .modulos.calcular_caudales_acumulados import CalcularCaudalesAcumulados
        from .modulos.planilla_diametros import PlanillaDiametros
        from .modulos.diseno_pendiente_minima import DisenoPendienteMinima
        from .modulos.diseno_pendiente_minima_adicional import DisenoPendienteMinimaAdicional
        from .modulos.revisar_direccion_flujo import RevisarDireccionFlujo
        from .modulos.asignar_camara_final import AsignarCamaraFinal
        from .modulos.verificar_continuidad import VerificarContinuidad
        from .modulos.verificar_angulos_camaras import VerificarAngulosCamaras
        from .modulos.ruta_critica import RutaCritica
        from .modulos.exportar_swmm import ExportarSWMM
        from .modulos.interaccion_epaswmm import InteraccionEPASWMM
        from .modulos.exportar_completo_dxf import ExportarCompletoDXF
        from .modulos.exportar_civil3d import ExportarCivil3D

        # ============================================================
        # INICIALIZAR MÓDULOS
        # ============================================================
        self.verificador                       = VerificadorRed(iface)
        self.generador                         = GeneradorCamaras(iface)
        self.copiador                          = CopiarRed(iface)
        self.direccion                         = DireccionFlujo(iface)
        self.cabezas                           = CabezasAtarjea(iface)
        self.dividir                           = DividirTuberia(iface)
        self.anadir                            = AnadirTuberia(iface)
        self.eliminar                          = EliminarTuberia(iface)
        self.eliminar_camara                   = EliminarCamara(iface)
        self.acumulados                        = Acumulados(iface)
        self.calcular_areas                    = CalcularAreas(iface)
        self.calcular_areas_acumuladas         = CalcularAreasAcumuladas(iface)
        self.calcular_caudales                 = CalcularCaudales(iface)
        self.calcular_caudales_tramo           = CalcularCaudalesTramo(iface)
        self.calcular_caudales_acumulados      = CalcularCaudalesAcumulados(iface)
        self.planilla_diametros                = PlanillaDiametros(iface)
        self.diseno_pendiente_minima           = DisenoPendienteMinima(iface)
        self.diseno_pendiente_minima_adicional = DisenoPendienteMinimaAdicional(iface)
        self.revisar_direccion                 = RevisarDireccionFlujo(iface)
        self.asignar_final                     = AsignarCamaraFinal(iface)
        self.verificar_continuidad             = VerificarContinuidad(iface)
        self.verificar_angulos                 = VerificarAngulosCamaras(iface)
        self.ruta_critica                      = RutaCritica(iface)
        self.exportar_swmm                     = ExportarSWMM(iface)
        self.interaccion_epaswmm               = InteraccionEPASWMM(iface)
        self.exportar_completo_dxf             = ExportarCompletoDXF(iface)
        self.exportar_civil3d                  = ExportarCivil3D(iface)

    # ============================================================
    # DEFINICIÓN CENTRAL DEL MENÚ
    # Cada entrada: (texto, atributo_del_módulo, separador_antes)
    # ============================================================
    MENU = [
        # ---- 1. VERIFICACIÓN DE RED ----
        ('🛡️ Verificar Red',                              'verificador',                        False),

        # ---- 2. CREAR RED ----
        ('📍 Generar Cámaras',                            'generador',                          True),
        ('🕸️ Generar Red',                                'copiador',                           False),

        # ---- 3. ASIGNAR DIRECCIÓN ----
        ('🔄 Asignar Dirección (Zi > Zf)',             'revisar_direccion',                  True),

        # ---- 4. DIRECCIÓN DE FLUJO ----
        ('➡️ Dirección de Flujo',                      'direccion',                          True),
        ('🌿 Cabezas de Atarjea',                         'cabezas',                            False),

        # ---- 5. ASIGNAR CÁMARA FINAL + VERIFICAR ----
        ('🏁 Asignar Cámara Final',                    'asignar_final',                      True),
        ('🔍 Verificar Continuidad de Red',            'verificar_continuidad',              False),
        ('📐 Verificar Ángulos en Cámaras',            'verificar_angulos',                  False),

        # ---- 6. MODIFICAR RED ----
        ('✂️ Dividir Tubería',                            'dividir',                            True),
        ('➕ Añadir Tubería',                           'anadir',                             False),
        ('🗑️ Eliminar Tubería',                        'eliminar',                           False),
        ('🗑️ Eliminar Cámara',                         'eliminar_camara',                    False),

        # ---- 7. LONGITUD ACUMULADA ----
        ('📏 Calcular Longitud Acumulada',                'acumulados',                         True),

        # ---- 8. TRAZADO DE ÁREAS ----
        ('📐 Calcular Áreas Propias',                     'calcular_areas',                     True),
        ('🗺️ Calcular Áreas Acumuladas',                  'calcular_areas_acumuladas',          False),

        # ---- 9. CÁLCULO DE CAUDALES ----
        ('💧 Calcular Caudales',                          'calcular_caudales',                  True),
        ('🌊 Calcular Caudales por Tramo',                'calcular_caudales_tramo',            False),
        ('📊 Calcular Caudales Acumulados (qacu, qdise)', 'calcular_caudales_acumulados',       False),

        # ---- 10. MÓDULOS DE DISEÑO ----
        ('📋 Planilla de Diámetros',                      'planilla_diametros',                 True),
        ('📉 Diseño por Pendiente Mínima Admisible',      'diseno_pendiente_minima',            False),
        ('📈 Diseño por Pendiente Mínima (con tabla)',    'diseno_pendiente_minima_adicional',  False),

        # ---- 11. HERRAMIENTAS AUXILIARES ----
        ('🧭 Encontrar Ruta Crítica',                  'ruta_critica',                       True),

        # ---- 12. INTERACCIÓN EPA SWMM ----
        ('🔄 Interacción EPA SWMM',                    'interaccion_epaswmm',                True),

        # ---- 13. EXPORTAR A EPA SWMM ----
        ('📤 Exportar a EPA SWMM (.inp)',                 'exportar_swmm',                      False),

        # ---- 14. EXPORTAR A DXF COMPLETO ----
        ('📐 Exportar DXF Completo',                   'exportar_completo_dxf',              True),

        # ---- 15. EXPORTAR A CIVIL 3D ----
        ('🏗️ Exportar a Civil 3D',                     'exportar_civil3d',                   True),
    ]

    # ============================================================
    # CREAR ACCIONES (GUI)
    # ============================================================
    def initGui(self):
        for texto, atributo, separador_antes in self.MENU:
            if separador_antes:
                self.iface.addPluginToMenu(self.menu, None)  # Separador

            modulo = getattr(self, atributo)
            action = QAction(texto, self.iface.mainWindow())
            action.triggered.connect(modulo.mostrar_dialogo)
            self.add_action(action)

    def add_action(self, action):
        self.iface.addPluginToMenu(self.menu, action)
        self.toolbar.addAction(action)
        self.actions.append(action)

    # ============================================================
    # LIMPIEZA AL DESCARGAR EL PLUGIN
    # ============================================================
    def unload(self):
        # Quitar acciones del menú y la barra
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

        # Desactivar herramientas activas (map tools)
        self._desactivar_modulo('direccion', metodo='desactivar_edicion')
        self._desactivar_modulo('cabezas', metodo='desactivar_edicion')
        self._desactivar_modulo('dividir', metodo='tool_seleccion')
        self._desactivar_modulo('anadir', metodo='tool_seleccion')
        self._desactivar_modulo('eliminar', metodo='desactivar')
        self._desactivar_modulo('eliminar_camara', metodo='desactivar')
        self._desactivar_modulo('calcular_caudales_tramo', metodo='desactivar')
        self._desactivar_modulo('asignar_final', metodo='desactivar')
        self._desactivar_modulo('ruta_critica', metodo='desactivar')
        self._desactivar_modulo('exportar_swmm', metodo='desactivar')
        self._desactivar_modulo('interaccion_epaswmm', metodo='desactivar')
        self._desactivar_modulo('verificar_angulos', metodo='desactivar')
        self._desactivar_modulo('exportar_completo_dxf', metodo='desactivar')
        self._desactivar_modulo('exportar_civil3d', metodo='desactivar')

    def _desactivar_modulo(self, atributo, metodo):
        """Desactiva de forma segura un módulo, sea cual sea el método de limpieza."""
        if not hasattr(self, atributo):
            return
        modulo = getattr(self, atributo)

        try:
            # Caso especial: módulos que usan tool_seleccion directamente
            if metodo == 'tool_seleccion':
                if hasattr(modulo, 'tool_seleccion') and modulo.tool_seleccion:
                    self.iface.mapCanvas().unsetMapTool(modulo.tool_seleccion)
                    modulo.tool_seleccion = None
            # Caso normal: llamar al método desactivar/desactivar_edicion
            elif hasattr(modulo, metodo):
                try:
                    getattr(modulo, metodo)(mostrar_mensaje=False)
                except TypeError:
                    getattr(modulo, metodo)()
        except Exception:
            pass