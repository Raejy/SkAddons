# Rae's Skript Addon Downloader

A setup using Python to automatically fetch and update Skript addons directly from GitHub and the Modrinth API.

---

## Requirements

* **Python 3.8+**
* `requests` library

To install the required dependency:

```bash
pip install requests

```

---

## Configuration (`addons.json`)

```json
{
  "defaults": {
    "minecraft_version": "26.1",
    "loaders": ["paper"],
    "version_types": ["release"],
    "asset_pattern": "*.jar"
  },
  "addons": {
    "Skript": { "source": "github", "repository": "SkriptLang/Skript" },
    "SkBee": { "source": "modrinth", "project": "skbee" },
    "skript-particle": { "source": "modrinth", "project": "skript-particle" },
    "Lusk": { "source": "modrinth", "project": "lusk" },
    "skript-yaml": { "source": "github", "repository": "Sashie/skript-yaml" },
    "skript-placeholders": { "source": "github", "repository": "APickledWalrus/skript-placeholders" },
    "skript-reflect": { "source": "github", "repository": "SkriptLang/skript-reflect" },
    "skJson": { "source": "github", "repository": "cooffeeRequired/skJson" }
  }
}

```

---

## Setup & Instructions

1. **Clone the repository:**
```bash
git clone https://github.com/Raejy/SkAddons.git
cd SkAddons

```


2. **Install dependencies:**
```bash
pip install requests

```


3. **Run the script:**
```bash
python updater.py

```
