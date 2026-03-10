import pandas as pd
import numpy as np
from pandas.tseries.offsets import MonthEnd
from datetime import datetime


def calcular_avance_constructivo(csv_path: str, output_excel: str = "reporte_avance.xlsx") -> pd.DataFrame:
    """Lee el CSV de edificios, filtra por zona, calcula avances y genera un reporte.

    Args:
        csv_path: ruta al archivo CSV de edificios FTTH (separador ';').
        output_excel: nombre/ruta del archivo Excel de salida que contendr\u00e1 dos hojas:
            - "resumen": estad\u00edsticas por PD
            - "detalles": listado de activos filtrados con su estado.

    Retorna:
        Un DataFrame con el resumen por PD (igual al de la hoja "resumen").
    """

    # lectura
    df = pd.read_csv(csv_path, sep=";", encoding="latin1")

    # filtros por region/subregion
    zonas = ["CAPITAL NORTE", "CAPITAL SUR"]
    df = df.loc[
        (df["REGION_OORR"] == "AMBA") & df["SUBREGION_OORR"].isin(zonas)
    ].copy()

    # extraer PD de NAP (primeros cuatro caracteres)
    df["PD"] = df["NAP"].astype(str).str[:4]

    # estados que se consideran "pendiente"
    pendientes_estado = [
        "A CONSTRUIR",
        "A RELEVAR",
        "ACCESO",
        "DISEÑADO",
        "EN CONSTRUCCION",
        "OT ASIGNADA",
    ]

    # agrupar y calcular
    grupos = []
    for pd_code, grupo in df.groupby("PD"):
        total = len(grupo)
        no_es = (grupo["ESTADO_CONSTRUCTIVO_EDIFICIO"] == "NO ES EDIFICIO").sum()
        imposible = (grupo["ESTADO_CONSTRUCTIVO_EDIFICIO"] == "IMPOSIBLE CONSTRUIR").sum()
        relevado = (grupo["ESTADO_CONSTRUCTIVO_EDIFICIO"] == "RELEVADO").sum()
        visitado = (grupo["ESTADO_CONSTRUCTIVO_EDIFICIO"] == "VISITADO").sum()
        construido = (grupo["ESTADO_CONSTRUCTIVO_EDIFICIO"] == "CONSTRUIDO").sum()
        pendiente = grupo["ESTADO_CONSTRUCTIVO_EDIFICIO"].isin(pendientes_estado).sum()

        denom = total - no_es - imposible - relevado - visitado
        pct_pendiente = pendiente / denom if denom > 0 else pd.NA  # decimal fraction
        pct_construido = construido / denom if denom > 0 else pd.NA  # decimal fraction

        grupos.append(
            {
                "PD": pd_code,
                "total": total,
                "construidos": construido,
                "pendientes": pendiente,
                "% construidos": pct_construido,
                "% pendientes": pct_pendiente,
                "no_es_edificio": no_es,
                "imposible_construir": imposible,
                "relevado": relevado,
                "visitado": visitado,
            }
        )

    resumen = pd.DataFrame(grupos).sort_values("PD").reset_index(drop=True)

    # --- Preparar línea de tiempo mensual por PD usando FINALIZACION_REAL ---
    # parsear fecha de finalización
    df["FINALIZACION_REAL_DT"] = pd.to_datetime(df["FINALIZACION_REAL"], dayfirst=True, errors="coerce")

    # mapa de denominadores por PD (usado para %)
    denom_map = (
        resumen.set_index("PD")["total"]
        - resumen.set_index("PD")["no_es_edificio"]
        - resumen.set_index("PD")["imposible_construir"]
        - resumen.set_index("PD")["relevado"]
        - resumen.set_index("PD")["visitado"]
    )

    # DataFrame con solo construidos con fecha
    df_constr = df.loc[df["ESTADO_CONSTRUCTIVO_EDIFICIO"] == "CONSTRUIDO", ["PD", "FINALIZACION_REAL_DT"]].copy()
    min_date = df_constr["FINALIZACION_REAL_DT"].min()
    max_date = pd.Timestamp(datetime.today().date())

    timeline_rows = []
    if pd.notna(min_date):
        start = min_date.replace(day=1)
        months = pd.date_range(start=start, end=max_date, freq="MS")
        for m in months:
            month_end = m + MonthEnd(0)
            month_label = m.strftime("%Y-%m")
            # acumulado construido hasta month_end por PD
            df_up_to = df_constr.loc[df_constr["FINALIZACION_REAL_DT"] <= month_end]
            counts = df_up_to.groupby("PD").size()
            for pd_code, cnt in counts.items():
                denom = denom_map.get(pd_code, np.nan)
                pct = (cnt / denom) if (denom and denom > 0) else pd.NA
                timeline_rows.append({"PD": pd_code, "month": month_label, "construido_cum": int(cnt), "% construido": pct})

    timeline_df = pd.DataFrame(timeline_rows)
    # Pivot a formato ancho: PD x meses con % construido
    if not timeline_df.empty:
        timeline_pivot = timeline_df.pivot(index="PD", columns="month", values="% construido").fillna(0).reset_index()
    else:
        timeline_pivot = pd.DataFrame(columns=["PD"])

    # --- Preparar pivot por FACTIBILIDAD_RED (conteos de pendientes y construidos) ---
    df["FACTIBILIDAD_RED"] = df["FACTIBILIDAD_RED"].fillna("<<VACIO>>")
    # pendientes según conjuntos usados
    pendientes_estado = [
        "A CONSTRUIR",
        "A RELEVAR",
        "ACCESO",
        "DISEÑADO",
        "EN CONSTRUCCION",
        "OT ASIGNADA",
    ]

    df["is_pendiente"] = df["ESTADO_CONSTRUCTIVO_EDIFICIO"].isin(pendientes_estado)
    df["is_construido"] = df["ESTADO_CONSTRUCTIVO_EDIFICIO"] == "CONSTRUIDO"

    pivot_pend = (
        df.loc[df["is_pendiente"]]
        .pivot_table(index="PD", columns="FACTIBILIDAD_RED", values="NAP", aggfunc="count", fill_value=0)
        .add_prefix("pend_")
    )
    pivot_const = (
        df.loc[df["is_construido"]]
        .pivot_table(index="PD", columns="FACTIBILIDAD_RED", values="NAP", aggfunc="count", fill_value=0)
        .add_prefix("const_")
    )

    pivot_fact = pd.concat([pivot_const, pivot_pend], axis=1).fillna(0).reset_index()

    # escribir el Excel con varias hojas y aplicar formato + gráfico
    with pd.ExcelWriter(output_excel, engine="xlsxwriter") as writer:
        resumen.to_excel(writer, sheet_name="resumen", index=False)
        # hoja de detalles: todos los activos filtrados
        df.to_excel(writer, sheet_name="detalles", index=False)
        # timeline pivot (PD x meses) con % construido
        timeline_pivot.to_excel(writer, sheet_name="timeline_monthly", index=False)
        # timeline detalle (filas PD, mes, construido_cum, %)
        timeline_df.to_excel(writer, sheet_name="timeline_details", index=False)
        # pivot por factibilidad
        pivot_fact.to_excel(writer, sheet_name="factibilidad_pivot", index=False)

        # obtener workbook y worksheets
        workbook = writer.book
        ws_res = writer.sheets["resumen"]
        ws_timeline = writer.sheets["timeline_monthly"]

        # formato porcentaje con 1 decimal
        pct_fmt = workbook.add_format({"num_format": "0.0%"})

        # helper: índice a letra Excel (0 -> A)
        def col_letter(idx: int) -> str:
            letters = ""
            while idx >= 0:
                letters = chr(ord("A") + (idx % 26)) + letters
                idx = idx // 26 - 1
            return letters

        # aplicar formato en sheet 'resumen' a columnas % construidos y % pendientes
        for col_name in ["% construidos", "% pendientes"]:
            if col_name in resumen.columns:
                col_idx = resumen.columns.get_loc(col_name)
                letter = col_letter(col_idx)
                ws_res.set_column(f"{letter}:{letter}", 12, pct_fmt)

        # aplicar formato en timeline_monthly a todas las columnas excepto PD
        if not timeline_pivot.empty:
            for i, col in enumerate(timeline_pivot.columns):
                if col != "PD":
                    letter = col_letter(i)
                    ws_timeline.set_column(f"{letter}:{letter}", 12, pct_fmt)

        # Crear gráfico de líneas para top N PDs por 'total'
        try:
            top_n = 6
            top_pds = resumen.sort_values("total", ascending=False).head(top_n)["PD"].tolist()
            # meses en columnas (timeline_pivot columns excluding PD)
            months = [c for c in timeline_pivot.columns if c != "PD"]
            if months and len(top_pds) > 0:
                chart = workbook.add_chart({"type": "line"})
                # categorías para el eje x: header row (row 0), cols 1..n
                first_col = 1
                last_col = first_col + len(months) - 1
                for pd_row_idx, pd_code in enumerate(top_pds):
                    # find row in timeline_pivot
                    try:
                        row_in_df = timeline_pivot.index[timeline_pivot["PD"] == pd_code].tolist()[0]
                    except Exception:
                        continue
                    excel_row = row_in_df + 1  # header is row 0
                    chart.add_series({
                        "name":       ["timeline_monthly", excel_row, 0],
                        "categories": ["timeline_monthly", 0, first_col, 0, last_col],
                        "values":     ["timeline_monthly", excel_row, first_col, excel_row, last_col],
                    })
                chart.set_title({"name": f"% Construido acumulado - Top {top_n} PDs"})
                chart.set_y_axis({"num_format": "0%"})
                chart.set_x_axis({"name": "Mes"})
                # insertar en hoja nueva
                ws_chart = workbook.add_worksheet("timeline_chart")
                ws_chart.insert_chart("B2", chart, {"x_scale": 1.5, "y_scale": 1.2})
        except Exception:
            # no crítico: si falla el gráfico, seguimos sin interrumpir
            pass

    return resumen


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Genera avance constructivo por PD.")
    parser.add_argument(
        "csv",
        help="Ruta al CSV de edificios FTTH (separador ';').",
    )
    parser.add_argument(
        "--out",
        default="reporte_avance.xlsx",
        help="Archivo Excel de salida (por defecto reporte_avance.xlsx).",
    )
    args = parser.parse_args()

    resumen = calcular_avance_constructivo(args.csv, args.out)
    print("Resumen por PD:")
    print(resumen.to_string(index=False))
    print(f"Reporte escrito en {args.out}")
