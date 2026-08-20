import argparse
import colorsys
import ctypes
import hashlib
import json
import re
import sys
from pathlib import Path

import requests


BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "addons.json"
DEFAULT_ADDONS_DIR = BASE_DIR / "plugins"

session = requests.Session()
session.headers["User-Agent"] = "Rae-SkAddons/1.0"


# Windows ANSI support
VT_ENABLED = sys.platform != "win32"

if sys.platform == "win32":
    try:
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_uint32()

        if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            VT_ENABLED = bool(kernel.SetConsoleMode(handle, mode.value | 4))
    except OSError:
        pass


def rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def gradient(c1, c2, steps=64):
    h1, s1, v1 = colorsys.rgb_to_hsv(*(x / 255 for x in rgb(c1)))
    h2, s2, v2 = colorsys.rgb_to_hsv(*(x / 255 for x in rgb(c2)))

    result = []

    for i in range(steps):
        t = i / max(steps - 1, 1)
        color = colorsys.hsv_to_rgb(
            h1 + (h2 - h1) * t,
            s1 + (s2 - s1) * t,
            v1 + (v2 - v1) * t
        )
        result.append(tuple(round(x * 255) for x in color))

    return result


MAIN_GRADIENT = gradient("#60A5FA", "#4F46E5")

COLORS = {
    "INFO": "#60A5FA",
    "CHECK": "#38BDF8",
    "UPDATED": "#4ADE80",
    "UPDATE": "#818CF8",
    "NEW": "#A78BFA",
    "DOWNLOAD": "#22D3EE",
    "WARNING": "#FACC15",
    "ERROR": "#F87171",
    "OK": "#4ADE80",
}


def color(text, value):
    if not VT_ENABLED:
        return text

    r, g, b = rgb(value)
    return f"\033[38;2;{r};{g};{b}m{text}\033[0m"


def grad(text):
    if not text or not VT_ENABLED:
        return text

    output = []

    for i, char in enumerate(text):
        pos = round(i / max(len(text) - 1, 1) * (len(MAIN_GRADIENT) - 1))
        r, g, b = MAIN_GRADIENT[pos]
        output.append(f"\033[38;2;{r};{g};{b}m{char}\033[0m")

    return "".join(output)


def log(message, level="INFO", addon=None):
    tag = color(f"[{level}]", COLORS.get(level, "#94A3B8"))

    if addon:
        print(f"{tag} {grad(addon)} {message}")
    else:
        print(f"{tag} {message}")


def ver(value):
    return tuple(int(x) for x in re.findall(r"\d+", str(value or "")))


def find_jar(addon, folder):
    filename = addon.get("filename")

    if filename:
        path = folder / filename
        if path.exists():
            return path

    pattern = addon.get("file_pattern")

    if pattern:
        matches = list(folder.glob(pattern))
        if matches:
            return matches[0]

    names = addon.get("names") or [addon["name"]]

    for path in folder.glob("*.jar"):
        if any(name.lower() in path.stem.lower() for name in names):
            return path

    return None


def modrinth(addon):
    project = addon["project"]

    response = session.get(
        f"https://api.modrinth.com/v2/project/{project}/version",
        params={"limit": 50}
    )
    response.raise_for_status()

    versions = response.json()
    allowed = addon.get("version_types", ["release"])

    versions = [
        version for version in versions
        if version["version_type"] in allowed
    ]

    minecraft = addon.get("minecraft_version")

    if minecraft:
        versions = [
            version for version in versions
            if minecraft in version.get("game_versions", [])
        ]

    if not versions:
        raise RuntimeError("No matching versions found on Modrinth.")

    latest = max(
        versions,
        key=lambda version: ver(version["version_number"])
    )

    jars = [
        file for file in latest["files"]
        if file["filename"].endswith(".jar")
    ]

    if not jars:
        raise RuntimeError("No JAR found in the latest Modrinth version.")

    target = next(
        (file for file in jars if file.get("primary")),
        jars[0]
    )

    return {
        "version": latest["version_number"],
        "url": target["url"],
        "filename": target["filename"],
        "sha1": target.get("hashes", {}).get("sha1")
    }


def github(addon):
    repo = addon["repository"]

    response = session.get(
        f"https://api.github.com/repos/{repo}/releases"
    )
    response.raise_for_status()

    releases = [
        release for release in response.json()
        if not release["draft"] and not release["prerelease"]
    ]

    pattern = addon.get("asset_pattern", ".jar").lower().strip("*")

    releases.sort(
        key=lambda release: ver(release.get("tag_name")),
        reverse=True
    )

    for release in releases:
        for asset in release["assets"]:
            name = asset["name"].lower()

            if not name.endswith(".jar"):
                continue

            if pattern != ".jar" and pattern not in name:
                continue

            return {
                "version": release.get("tag_name") or release["name"],
                "url": asset["browser_download_url"],
                "filename": asset["name"],
                "sha1": None
            }

    raise RuntimeError("No matching JAR found in GitHub releases.")


def update(addon, folder, check=False):
    name = addon["name"]
    source = addon.get("source", "").lower()

    try:
        latest = (
            modrinth(addon)
            if source == "modrinth"
            else github(addon)
        )

        local = find_jar(addon, folder)

        if local:
            installed = addon.get("installed_version")

            if not installed and addon.get("version_file"):
                version_file = local.parent / addon["version_file"]

                if version_file.exists():
                    installed = version_file.read_text().strip()

            if installed and ver(latest["version"]) <= ver(installed):
                log(f"{installed} is up to date", "OK", name)
                return "current"

            if local.name == latest["filename"]:
                log(f"{latest['version']} already downloaded", "OK", name)
                return "current"

        if check:
            level = "UPDATE" if local else "NEW"
            log(f"{latest['version']} is available", level, name)
            return "update"

        filename = addon.get("filename") or latest["filename"]
        target = folder / filename

        log(f"Downloading {latest['version']}...", "DOWNLOAD", name)

        response = session.get(latest["url"])
        response.raise_for_status()

        if latest["sha1"]:
            checksum = hashlib.sha1(response.content).hexdigest()

            if checksum.lower() != latest["sha1"].lower():
                raise RuntimeError("SHA1 checksum mismatch.")

        target.write_bytes(response.content)

        log(f"Installed {latest['version']}", "UPDATED", name)
        return "updated"

    except requests.RequestException as e:
        log(f"Request failed: {e}", "ERROR", name)
        return "failed"

    except (KeyError, ValueError) as e:
        log(f"Invalid addon data: {e}", "ERROR", name)
        return "failed"

    except OSError as e:
        log(f"File error: {e}", "ERROR", name)
        return "failed"

    except RuntimeError as e:
        log(str(e), "ERROR", name)
        return "failed"


def main():
    parser = argparse.ArgumentParser(description="Rae's SkAddons")
    parser.add_argument("addon", nargs="?", help="Specific addon to update")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for updates without downloading"
    )
    parser.add_argument(
        "--addons-dir",
        default=DEFAULT_ADDONS_DIR,
        type=Path
    )

    args = parser.parse_args()

    print("\n" + grad(
        "______           _       _____ _     ___      _     _                 "
    ))
    print(grad(
        "| ___ \\         ( )     /  ___| |   / _ \\    | |   | |                "
    ))
    print(grad(
        "| |_/ /__ _  ___|/ ___  \\ `--.| | _/ /_\\ \\ __| | __| | ___  _ __  ___ "
    ))
    print(grad(
        "|    // _` |/ _ \\ / __|  `--. \\ |/ /  _  |/ _` |/ _` |/ _ \\| '_ \\/ __|"
    ))
    print(grad(
        "| |\\ \\ (_| |  __/ \\__ \\ /\\__/ /   <| | | | (_| | (_| | (_) | | | \\__ \\"
    ))
    print(grad(
        "\\_| \\_\\__,_|\\___| |___/ \\____/|_|\\_\\_| |_/_\\__,_|\\__,_|\\___/|_| |_|___/"
    ))
    print(grad(
        "                                                                      "
    ))
    print(grad(
        "                                                                      "
    ))

    if not CONFIG_FILE.exists():
        log(f"{CONFIG_FILE} not found.", "ERROR")
        return

    config = json.loads(CONFIG_FILE.read_text())
    defaults = config.get("defaults", {})
    data = config.get("addons", {})

    addons = []

    for name, settings in data.items():
        if args.addon and name.lower() != args.addon.lower():
            continue

        addons.append({
            **defaults,
            **settings,
            "name": name
        })

    if not addons:
        log("No matching addons found.", "WARNING")
        return

    args.addons_dir.mkdir(parents=True, exist_ok=True)

    log(f"Checking {len(addons)} addon(s)...\n", "CHECK")

    stats = {
        "updated": 0,
        "current": 0,
        "failed": 0
    }

    for addon in addons:
        result = update(addon, args.addons_dir, args.check)

        if result in stats:
            stats[result] += 1

    print("\n" + grad("Finished") + "\n")

    if stats["updated"]:
        log(f"{stats['updated']} addon(s) updated", "UPDATED")

    if stats["current"]:
        log(f"{stats['current']} addon(s) already up to date", "OK")

    if stats["failed"]:
        log(f"{stats['failed']} addon(s) failed", "ERROR")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
    except Exception as e:
        log(f"Fatal error: {e}", "ERROR")

    input("\nPress ENTER to close...")
