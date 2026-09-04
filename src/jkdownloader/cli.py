"""Command-line interface and main orchestration."""

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from .extraction import process_episode
from .jkanime import (
    discover_family,
    episode_exists,
    find_last_episode,
    normalize_series,
    validate_series,
)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # ty: ignore[call-non-callable]

    parser = argparse.ArgumentParser(
        description="Extract download links from a full series on "
        "jkanime.net and save them to a .txt for JDownloader."
    )
    parser.add_argument(
        "series",
        help="Series URL or slug. e.g. "
        "https://jkanime.net/tensei-shitara-slime-datta-ken/",
    )
    parser.add_argument(
        "--seasons",
        action="store_true",
        help="discover and process ALL related seasons/OVAs of the franchise",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="output .txt file (default: mediafire_<series>.txt)",
    )
    parser.add_argument(
        "--start", type=int, default=1, help="first episode to process (default: 1)"
    )
    parser.add_argument(
        "--end",
        type=int,
        default=0,
        help="last episode to process (default: auto-detect "
        "total by finding the first 404)",
    )
    parser.add_argument(
        "--server",
        default="mediafire",
        help="primary server: mediafire (default), mega, ... or 'all'",
    )
    parser.add_argument(
        "--fallback",
        default="mega",
        help="fallback servers in order, comma-separated "
        "(default: mega). e.g. --fallback mega,1fichier",
    )
    parser.add_argument(
        "--no-verify",
        dest="verify",
        action="store_false",
        default=True,
        help="skip checking if Mediafire links are still alive "
        "(faster, no automatic fallback)",
    )
    parser.add_argument(
        "--workers", type=int, default=6, help="concurrent requests (default: 6)"
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="also create a .csv with season, episode, "
        "server, language, size and status for each link",
    )
    parser.add_argument(
        "--crawljobs",
        action="store_true",
        help="create .crawljob files (JDownloader Folder Watch): "
        "ONE package per season, no mess in LinkGrabber",
    )
    parser.add_argument(
        "--dest",
        metavar="PATH",
        default="",
        help="with --crawljobs: base download folder "
        "(a subfolder is created per season)",
    )
    parser.add_argument(
        "--outdir",
        metavar="DIR",
        default="links",
        help="directory to save generated files "
        "(.txt, .csv, .crawljob). Default: links/",
    )
    args = parser.parse_args()

    slug = normalize_series(args.series)
    primary = args.server.strip().lower()
    all_servers = primary == "all"
    fallbacks = [
        f.strip().lower()
        for f in args.fallback.split(",")
        if f.strip() and f.strip().lower() != primary
    ]

    if args.seasons:
        print("[*] Discovering franchise seasons/OVAs...")
        print(f"[*] Checking base series: {slug}")
        base_data = validate_series(slug)
        if base_data is None:
            raise SystemExit("[x] Series does not exist on jkanime: " + slug)
        family = discover_family(slug)
        print("[+] Members found ({}): {}".format(len(family), ", ".join(family)))
    else:
        family = [slug]

    base_name = f"{primary}_{slug}"
    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        output = os.path.join(args.outdir, args.output or f"{base_name}.txt")
    else:
        output = args.output or f"{base_name}.txt"
    total_links = 0
    server_summary = Counter()
    txt_lines = []
    csv_rows = []
    member_urls = []
    no_link_global = []
    errors_global = []
    other_lang_global = []
    start_t = time.time()

    for idx_season, slug_season in enumerate(family, 1):
        print()
        print("=" * 60)
        print(f"[{idx_season}/{len(family)}] SEASON/MEMBER: {slug_season}")
        data = validate_series(slug_season)
        if data is None:
            print("    [!] Does not exist or not responding; skipping.")
            continue
        title, _ = data
        print(f"[+] {title}")

        cache = {}
        if args.end > 0:
            last = args.end
            if not episode_exists(slug_season, args.start, cache):
                print(
                    f"    [!] Episode {args.start} does not exist; skipping this entry."
                )
                continue
            print(f"[*] Forced range: episodes {args.start} to {last}")
        else:
            print("[*] Detecting total episodes (binary search)...")
            last = find_last_episode(slug_season, cache)
            if last == 0:
                print("    [!] No episodes; skipping this entry.")
                continue
            print(f"[+] Last episode: {last}")

        start_ep = max(1, args.start)
        if start_ep > last:
            print(f"    [!] This entry only goes up to episode {last}; skipping.")
            continue
        episodes = list(range(start_ep, last + 1))
        print(f"[*] Processing {len(episodes)} episodes...")

        results, notes, servers_used = {}, {}, {}
        other_lang_ep = {}
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {
                pool.submit(
                    process_episode,
                    slug_season,
                    n,
                    primary,
                    fallbacks,
                    args.verify,
                    all_servers,
                ): n
                for n in episodes
            }
            done = 0
            for future in as_completed(futures):
                n, links, server_used, note, other_id = future.result()
                if links:
                    results[n] = links
                    servers_used[n] = server_used
                    other_lang_ep[n] = other_id
                else:
                    notes[n] = note or "no data"
                done += 1
                print(f"    [{done:3d}/{len(episodes)}] episode {n}")

        for n in episodes:
            links = results.get(n)
            if links:
                used = servers_used.get(n) or links[0][1]
                is_fallback = used.lower() != primary and not all_servers
                tag = f"{used}*" if is_fallback else used
                other = other_lang_ep.get(n, False)
                for url, server, size in links:
                    txt_lines.append(url)
                    csv_rows.append(
                        (
                            slug_season,
                            title,
                            n,
                            server,
                            "OTHER LANG" if other else "JP-sub",
                            size,
                            "OK",
                            url,
                        )
                    )
                    total_links += 1
                server_summary[used] += 1
                warnings = []
                if is_fallback:
                    warnings.append(f"FALLBACK because {primary} unavailable")
                if other:
                    warnings.append("only available in another language")
                    other_lang_global.append(f"{slug_season}/{n}")
                warning = "  <- {}".format(" + ".join(warnings)) if warnings else ""
                print(f"  Ep  {n:>3}: [{tag}] {links[0][0]} ({links[0][2]}){warning}")
            else:
                note = notes.get(n, "?")
                csv_rows.append(
                    (
                        slug_season,
                        title,
                        n,
                        "--",
                        "--",
                        "",
                        f"no link ({note})",
                        "",
                    )
                )
                print(f"  Ep  {n:>3}: NO LINK ({note})")
                if note == "404":
                    continue
                if note and note.startswith(("error", "HTTP")):
                    errors_global.append(f"{slug_season}/{n}")
                else:
                    no_link_global.append(f"{slug_season}/{n}")

        urls_member = []
        for n in episodes:
            for url, _, _ in results.get(n, []):
                urls_member.append(url)
        if urls_member:
            member_urls.append(
                {"title": title, "slug": slug_season, "urls": urls_member}
            )

    print()
    print("=" * 60)
    print(f"[=] Total links: {total_links}")
    for server, count in server_summary.most_common():
        label = "episodes" if not all_servers else "episodes (all servers)"
        print(f"[=] Via {server} : {count} {label}")
    if no_link_global:
        print("[!] No link: {}".format(", ".join(no_link_global)))
    if errors_global:
        print("[!] Temporary errors (retry them): {}".format(", ".join(errors_global)))
    if other_lang_global:
        print(
            "[!] No JP-sub version (downloaded another version): {}".format(
                ", ".join(other_lang_global)
            )
        )

    with open(output, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(line + "\n" for line in txt_lines)
    print(f"[+] Links saved to: {output}")

    if args.detail:
        detail_path = output.rsplit(".", 1)[0] + ".detail.csv"
        with open(detail_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                (
                    "season",
                    "title",
                    "episode",
                    "server",
                    "language",
                    "size",
                    "status",
                    "url",
                )
            )
            w.writerows(csv_rows)
        print(f"[+] Detail saved to: {detail_path}")

    if args.crawljobs and member_urls:
        if args.outdir:
            cj_dir = os.path.join(args.outdir, base_name + "_jdcrawljobs")
        else:
            cj_dir = os.path.splitext(output)[0] + "_jdcrawljobs"
        os.makedirs(cj_dir, exist_ok=True)
        packages_created = {}
        for i, member in enumerate(member_urls, 1):
            title_m = member["title"]
            if title_m in packages_created.values():
                package = "{} [{}]".format(title_m, member["slug"])
            else:
                package = title_m
            job = {
                "text": "\n ".join(member["urls"]),
                "packageName": package,
                "enabled": "TRUE",
                "autoStart": "FALSE",
            }
            if args.dest:
                job["downloadFolder"] = (
                    args.dest.rstrip("\\/") + os.sep + member["slug"]
                )
            name = "{:02d}_{}.crawljob".format(i, member["slug"])
            with open(os.path.join(cj_dir, name), "w", encoding="utf-8") as f:
                f.write(json.dumps([job], ensure_ascii=False, indent=2) + "\n")
            packages_created[name] = package
        print(f"[+] {len(packages_created)} .crawljob file(s) created in: {cj_dir}")
        print("    To group by season in JDownloader (first time only):")
        print("      1. Settings -> Extensions -> enable 'Folder Watch'.")
        print("      2. Easy way: drag the .crawljob files to the")
        print("         LinkGrabber window (treated like .DLC containers).")
        print("         Automated way: point Folder Watch to the .crawljob dir.")
    print(f"[i] Total time: {time.time() - start_t:.1f} s")
