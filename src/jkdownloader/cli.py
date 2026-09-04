"""Interfaz de linha de comandos y orquestacion principal."""

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from .extraction import procesar_episodio
from .jkanime import (
    buscar_ultimo_episodio,
    descubrir_familia,
    existe_episodio,
    normalizar_serie,
    validar_serie,
)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        description="Extrae los enlaces de descarga de una serie completa de "
                    "jkanime.net y los guarda en un .txt para JDownloader.")
    parser.add_argument("serie", help="URL de la serie o slug. Ej: "
                        "https://jkanime.net/tensei-shitara-slime-datta-ken/")
    parser.add_argument("--temporadas", action="store_true",
                        help="descubrir y procesar TODAS las temporadas/OVAs "
                             "relacionadas de la franquicia")
    parser.add_argument("-o", "--output", metavar="ARCHIVO",
                        help="archivo .txt de salida "
                             "(por defecto: mediafire_<serie>.txt)")
    parser.add_argument("--inicio", type=int, default=1,
                        help="primer capitulo a procesar (defecto: 1)")
    parser.add_argument("--fin", type=int, default=0,
                        help="ultimo capitulo a procesar (defecto: autodetectar "
                             "el total buscando el primer 404)")
    parser.add_argument("--servidor", default="mediafire",
                        help="servidor principal: mediafire (defecto), mega, "
                             "... o 'todos'")
    parser.add_argument("--fallback", default="mega",
                        help="servidores de respaldo por orden, separados por "
                             "comas (defecto: mega). Ej: --fallback mega,1ficher")
    parser.add_argument("--no-verificar", dest="verificar",
                        action="store_false", default=True,
                        help="no comprobar si los enlaces de Mediafire siguen "
                             "vivos (mas rapido, sin respaldo automatico)")
    parser.add_argument("--workers", type=int, default=6,
                        help="peticiones simultaneas (defecto: 6)")
    parser.add_argument("--detalle", action="store_true",
                        help="crear ademas un .csv con temporada, capitulo, "
                             "servidor, idioma, tamano y estado de cada enlace")
    parser.add_argument("--crawljobs", action="store_true",
                        help="crear archivos .crawljob (Folder Watch de "
                             "JDownloader): UN paquete por temporada, sin "
                             "desorden en el LinkGrabber")
    parser.add_argument("--destino", metavar="RUTA", default="",
                        help="con --crawljobs: carpeta base de descargas "
                             "(se crea una subcarpeta por temporada)")
    parser.add_argument("--outdir", metavar="CARPETA", default="links",
                        help="carpeta donde guardar los archivos generados "
                             "(.txt, .csv, .crawljob). Por defecto: links/")
    args = parser.parse_args()

    slug = normalizar_serie(args.serie)
    primario = args.servidor.strip().lower()
    todos = primario == "todos"
    fallbacks = [f.strip().lower() for f in args.fallback.split(",")
                 if f.strip() and f.strip().lower() != primario]

    if args.temporadas:
        print("[*] Descubriendo temporadas/OVAs de la franquicia...")
        print("[*] Comprobando serie base: {}".format(slug))
        datos_base = validar_serie(slug)
        if datos_base is None:
            raise SystemExit("[x] La serie no existe en jkanime: " + slug)
        familia = descubrir_familia(slug)
        print("[+] Miembros encontrados ({}): {}".format(
            len(familia), ", ".join(familia)))
    else:
        familia = [slug]

    nombre_base = "{}_{}".format(primario, slug)
    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        salida = os.path.join(args.outdir,
                              args.output or "{}.txt".format(nombre_base))
    else:
        salida = args.output or "{}.txt".format(nombre_base)
    total_enlaces = 0
    resumen_servidores = Counter()
    lineas_txt = []
    filas_csv = []
    miembros_urls = []
    sin_enlace_global = []
    errores_global = []
    otro_idioma_global = []
    inicio_t = time.time()

    for idx_temp, slug_temp in enumerate(familia, 1):
        print()
        print("=" * 60)
        print("[{}/{}] TEMPORADA/MIEMBRO: {}".format(idx_temp, len(familia),
                                                     slug_temp))
        datos = validar_serie(slug_temp)
        if datos is None:
            print("    [!] No existe o no responde; se salta.")
            continue
        titulo, _ = datos
        print("[+] {}".format(titulo))

        cache = {}
        if args.fin > 0:
            ultimo = args.fin
            if not existe_episodio(slug_temp, args.inicio, cache):
                print("    [!] El capitulo {} no existe; se salta esta entrega."
                      .format(args.inicio))
                continue
            print("[*] Rango forzado: capitulos {} a {}".format(args.inicio,
                                                                ultimo))
        else:
            print("[*] Detectando total de episodios (busqueda binaria)...")
            ultimo = buscar_ultimo_episodio(slug_temp, cache)
            if ultimo == 0:
                print("    [!] Sin capitulos; se salta esta entrega.")
                continue
            print("[+] Ultimo episodio: {}".format(ultimo))

        inicio = max(1, args.inicio)
        if inicio > ultimo:
            print("    [!] Esta entrega solo llega hasta el capitulo {}; "
                  "se salta.".format(ultimo))
            continue
        capitulos = list(range(inicio, ultimo + 1))
        print("[*] Procesando {} capitulos...".format(len(capitulos)))

        resultado, notas, servidores_usados = {}, {}, {}
        otro_idioma_cap = {}
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futuros = {pool.submit(procesar_episodio, slug_temp, n, primario,
                                   fallbacks, args.verificar,
                                   todos): n for n in capitulos}
            hecho = 0
            for futuro in as_completed(futuros):
                n, enlaces, servidor_usado, nota, otro_id = futuro.result()
                if enlaces:
                    resultado[n] = enlaces
                    servidores_usados[n] = servidor_usado
                    otro_idioma_cap[n] = otro_id
                else:
                    notas[n] = nota or "sin datos"
                hecho += 1
                print("    [{:3d}/{}] capitulo {}".format(hecho, len(capitulos),
                                                          n))

        for n in capitulos:
            enlaces = resultado.get(n)
            if enlaces:
                usado = servidores_usados.get(n) or enlaces[0][1]
                es_fallback = (usado.lower() != primario and not todos)
                marca = "{}*".format(usado) if es_fallback else usado
                otro = otro_idioma_cap.get(n, False)
                for url, servidor, tamano in enlaces:
                    lineas_txt.append(url)
                    filas_csv.append((slug_temp, titulo, n, servidor,
                                      "OTRO IDIOMA" if otro else "JP-sub",
                                      tamano, "OK", url))
                    total_enlaces += 1
                resumen_servidores[usado] += 1
                avisos = []
                if es_fallback:
                    avisos.append("RESPALDO por {} no disponible".format(primario))
                if otro:
                    avisos.append("solo existe en otro idioma")
                    otro_idioma_global.append("{}/{}".format(slug_temp, n))
                aviso = "  <- {}".format(" + ".join(avisos)) if avisos else ""
                print("  Cap {:>3}: [{}] {} ({}){}".format(
                    n, marca, enlaces[0][0], enlaces[0][2], aviso))
            else:
                nota = notas.get(n, "?")
                filas_csv.append((slug_temp, titulo, n, "--", "--", "",
                                  "sin enlace ({})".format(nota), ""))
                print("  Cap {:>3}: SIN enlace ({})".format(n, nota))
                if nota == "404":
                    continue
                if nota and nota.startswith(("error", "HTTP")):
                    errores_global.append("{}/{}".format(slug_temp, n))
                else:
                    sin_enlace_global.append("{}/{}".format(slug_temp, n))

        urls_miembro = []
        for n in capitulos:
            for url, _, _ in resultado.get(n, []):
                urls_miembro.append(url)
        if urls_miembro:
            miembros_urls.append({"titulo": titulo, "slug": slug_temp,
                                  "urls": urls_miembro})

    print()
    print("=" * 60)
    print("[=] Enlaces totales: {}".format(total_enlaces))
    for servidor, cuenta in resumen_servidores.most_common():
        etiqueta = "capitulos" if not todos else "capitulos (todos los servidores)"
        print("[=] Via {} : {} {}".format(servidor, cuenta, etiqueta))
    if sin_enlace_global:
        print("[!] Sin enlace: {}".format(", ".join(sin_enlace_global)))
    if errores_global:
        print("[!] Errores temporales (reintentalos): {}".format(
            ", ".join(errores_global)))
    if otro_idioma_global:
        print("[!] Sin version JP-sub (descargada otra version): {}".format(
            ", ".join(otro_idioma_global)))

    with open(salida, "w", encoding="utf-8", newline="\n") as f:
        for linea in lineas_txt:
            f.write(linea + "\n")
    print("[+] Enlaces guardados en: {}".format(salida))

    if args.detalle:
        detalle_path = salida.rsplit(".", 1)[0] + ".detalle.csv"
        with open(detalle_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(("temporada", "titulo", "capitulo", "servidor",
                        "idioma", "tamano", "estado", "url"))
            w.writerows(filas_csv)
        print("[+] Detalle guardado en: {}".format(detalle_path))

    if args.crawljobs and miembros_urls:
        if args.outdir:
            carpeta_cj = os.path.join(args.outdir,
                                      nombre_base + "_jdcrawljobs")
        else:
            carpeta_cj = os.path.splitext(salida)[0] + "_jdcrawljobs"
        os.makedirs(carpeta_cj, exist_ok=True)
        paquetes_creados = {}
        for i, miembro in enumerate(miembros_urls, 1):
            titulo_m = miembro["titulo"]
            if titulo_m in paquetes_creados.values():
                paquete = "{} [{}]".format(titulo_m, miembro["slug"])
            else:
                paquete = titulo_m
            job = {
                "text": "\n ".join(miembro["urls"]),
                "packageName": paquete,
                "enabled": "TRUE",
                "autoStart": "FALSE",
            }
            if args.destino:
                job["downloadFolder"] = args.destino.rstrip("\\/") + os.sep + \
                    miembro["slug"]
            nombre = "{:02d}_{}.crawljob".format(i, miembro["slug"])
            with open(os.path.join(carpeta_cj, nombre), "w",
                      encoding="utf-8") as f:
                f.write(json.dumps([job], ensure_ascii=False, indent=2) + "\n")
            paquetes_creados[nombre] = paquete
        print("[+] {} archivo(s) .crawljob creados en: {}".format(
            len(paquetes_creados), carpeta_cj))
        print("    Para que JDownloader los agrupe por temporada (solo la "
              "primera vez):")
        print("      1. Ajustes -> Extensiones -> activa 'Folder Watch'.")
        print("      2. Forma facil: arrastra los .crawljob a la ventana de")
        print("         LinkGrabber (los trata igual que contenedores .DLC).")
        print("         Forma automatijobs you also get ONE package per season, "
                  "no mess.)")
    print("[i] Total time: {:.1f} s".format(time.time() - start_time))
