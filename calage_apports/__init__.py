# -*- coding: utf-8 -*-
"""Plugin QGIS « Calage des apports »."""


def classFactory(iface):  # noqa: N802  (nom impose par QGIS)
    from .plugin import PluginCalage
    return PluginCalage(iface)
