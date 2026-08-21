import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class AlecaAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class AlecaPaths:
    data_dir: Path
    last_data: Path
    deltas: Path
    cached_data: Path
    overwolf_logs: Path


class AlecaAdapter:
    """Read-only boundary around AlecaFrame local files."""

    def __init__(self, explicit_data_dir: Path | None = None):
        self.explicit_data_dir = explicit_data_dir

    def locate_installation(self) -> Path:
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        extension_root = local / "Overwolf" / "Extensions"
        candidates = sorted(extension_root.glob("afmcagbpgggkpdkokjhjkllpegnadmkignlonpjm/*/manifest.json"))
        if not candidates:
            raise AlecaAdapterError("AlecaFrame Overwolf extension was not found.")
        return candidates[-1].parent

    def locate_user_data(self) -> AlecaPaths:
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        data_dir = self.explicit_data_dir or local / "AlecaFrame"
        paths = AlecaPaths(
            data_dir=data_dir,
            last_data=data_dir / "lastData.dat",
            deltas=data_dir / "deltas.dat",
            cached_data=data_dir / "cachedData",
            overwolf_logs=local / "Overwolf" / "Log" / "Apps" / "AlecaFrame",
        )
        if not paths.last_data.exists():
            raise AlecaAdapterError(f"AlecaFrame inventory file was not found at {paths.last_data}")
        return paths

    def decrypt_last_data(self) -> str:
        paths = self.locate_user_data()
        return self._read_encrypted_text(paths.last_data)

    def read_inventory(self) -> dict[str, Any]:
        payload = json.loads(self.decrypt_last_data())
        if isinstance(payload, dict) and isinstance(payload.get("InventoryJson"), str):
            return json.loads(payload["InventoryJson"])
        return payload

    def read_mastery(self) -> dict[str, Any]:
        return self.read_inventory()

    def read_relics(self) -> dict[str, Any]:
        inventory = self.read_inventory()
        return {k: v for k, v in inventory.items() if "relic" in k.lower()}

    def read_platinum_balance(self) -> int:
        inventory = self.read_inventory()
        if not isinstance(inventory, dict):
            return 0
        paid = inventory.get("PremiumCredits", 0)
        free = inventory.get("PremiumCreditsFree", 0)
        return (paid if isinstance(paid, int) else 0) + (free if isinstance(free, int) else 0)

    def read_settings(self) -> dict[str, str]:
        paths = self.locate_user_data()
        settings: dict[str, str] = {}
        for file_name in ("lastLang.tmp", "lastUsername.txt", "version.txt"):
            path = paths.data_dir / file_name
            if path.exists():
                settings[file_name] = path.read_text(encoding="utf-8", errors="replace")
        return settings

    def read_trades(self) -> list[dict[str, Any]]:
        paths = self.locate_user_data()
        if not paths.overwolf_logs.exists():
            return []
        trades: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        pending: dict[str, Any] | None = None
        for log_file in sorted(paths.overwolf_logs.glob("BackGround.html*.log")):
            for line_no, line in enumerate(log_file.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                if "Processing trade log:" in line:
                    pending = None
                    current = {"source": str(log_file), "source_line": line_no, "given_text": "", "received_text": "", "_side": None}
                elif current is not None and "Trade log processed:" in line:
                    current.update(self._parse_trade_processed(line))
                    current.pop("_side", None)
                    pending = current
                    current = None
                elif pending is not None and "Trade log submitted" in line:
                    trades.append(pending)
                    pending = None
                elif current is not None:
                    if "You are offering:" in line:
                        current["_side"] = "given"
                        offered = self._clean_trade_line(line.split("You are offering:", 1)[-1])
                        if offered:
                            current["given_text"] = self._append_trade_text(current.get("given_text") or "", offered)
                    elif "and will receive from" in line:
                        current["_side"] = "received"
                    else:
                        cleaned = self._clean_trade_line(line)
                        if cleaned and current.get("_side") == "given":
                            current["given_text"] = self._append_trade_text(current.get("given_text") or "", cleaned)
                        elif cleaned and current.get("_side") == "received":
                            current["received_text"] = self._append_trade_text(current.get("received_text") or "", cleaned)
        return trades

    def refresh(self) -> dict[str, Any]:
        return {
            "installation": str(self.locate_installation()),
            "paths": self.locate_user_data(),
            "inventory": self.read_inventory(),
            "settings": self.read_settings(),
            "trades": self.read_trades(),
        }

    @staticmethod
    def _append_trade_text(existing: str, value: str) -> str:
        return f"{existing}\n{value}".strip() if existing else value

    @staticmethod
    def _clean_trade_line(line: str) -> str:
        value = "".join(ch for ch in line.strip() if ord(ch) < 57344 or ord(ch) > 63743)
        value = re.sub(r",?\s*title=.*$", "", value).strip()
        return value

    def read_reference_items(self) -> list[dict[str, Any]]:
        paths = self.locate_user_data()
        basic_items = self._basic_items(paths.cached_data / "custom" / "basic.json")
        crafting_items = self._extract_crafting_reference_items(paths.cached_data / "custom" / "crafting.json", basic_items)
        vault_state = self._vault_state_by_reward_name(paths.cached_data / "json" / "Relics.json")
        market_names = self._market_url_names_by_reward_name(paths.cached_data / "json" / "Relics.json")
        items = self._merge_crafting_parents_with_relic_rewards(crafting_items, basic_items, market_names, vault_state)
        return items

    def read_market_url_names(self) -> dict[str, str]:
        paths = self.locate_user_data()
        return self._market_url_names_by_reward_name(paths.cached_data / "json" / "Relics.json")

    def _read_encrypted_text(self, path: Path) -> str:
        try:
            from cryptography.hazmat.primitives import hashes, padding
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        except ImportError as exc:
            raise AlecaAdapterError("Install backend requirements before decrypting AlecaFrame data.") from exc

        data = path.read_bytes()
        key_materials = [b"12FGB36-LE3-q=9", b"LEO-ALEC", b"12FGB36-LE3-q=9LEO-ALEC"]
        iv_materials = [b"LEO-ALEC", b"12FGB36-LE3-q=9", b"0000000000000000"]
        for key_material in key_materials:
            for iv_material in iv_materials:
                key = self._derive_bytes(PBKDF2HMAC, hashes, key_material, 32)
                iv = self._derive_bytes(PBKDF2HMAC, hashes, iv_material, 16)
                try:
                    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
                    padded = decryptor.update(data) + decryptor.finalize()
                    unpadder = padding.PKCS7(128).unpadder()
                    plain = unpadder.update(padded) + unpadder.finalize()
                    text = plain.decode("utf-8")
                    if text.lstrip().startswith("{"):
                        return text
                except Exception:
                    continue
        return self._read_with_aleca_dll(path)

    @staticmethod
    def _derive_bytes(kdf_cls: Any, hashes: Any, material: bytes, length: int) -> bytes:
        if len(material) in (16, 24, 32) and length in (16, 24, 32):
            return material[:length].ljust(length, b"\0")
        kdf = kdf_cls(algorithm=hashes.SHA256(), length=length, salt=b"AlecaFrame", iterations=1000)
        return kdf.derive(material)

    def _read_with_aleca_dll(self, path: Path) -> str:
        net_dir = self.locate_installation() / "NET"
        command = (
            "$ErrorActionPreference='Stop';"
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
            f"$net={self._ps_quote(str(net_dir))};"
            "Add-Type -Path (Join-Path $net 'Newtonsoft.Json.dll');"
            "Add-Type -Path (Join-Path $net 'AlecaFramePublicLib.dll');"
            "Add-Type -Path (Join-Path $net 'AlecaFrameClientLib.dll');"
            f"[AlecaFrameClientLib.Utils.Misc]::ReadAllTextEncrypted({self._ps_quote(str(path))})"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise AlecaAdapterError(result.stderr.strip() or "AlecaFrame DLL decryption failed.")
        text = result.stdout.strip()
        if not text.lstrip().startswith("{"):
            raise AlecaAdapterError("AlecaFrame DLL returned data that was not JSON.")
        return text

    @staticmethod
    def _ps_quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def read_full_material_build_counts(self) -> dict[str, int]:
        paths = self.locate_user_data()
        basic_items = self._basic_items(paths.cached_data / "custom" / "basic.json")
        try:
            crafting_payload = json.loads((paths.cached_data / "custom" / "crafting.json").read_text(encoding="utf-8", errors="replace"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        crafts = crafting_payload.get("craftsByUUID", {}) if isinstance(crafting_payload, dict) else {}
        counts = self._inventory_counts(self.read_inventory())
        result: dict[str, int] = {}
        for craft in crafts.values():
            if not isinstance(craft, dict):
                continue
            parent_name = craft.get("name")
            if not isinstance(parent_name, str) or "Prime" not in parent_name:
                continue
            requirements: dict[str, int] = {}
            for component in craft.get("components", []) or []:
                for unique_name, needed in self._full_material_requirements(component).items():
                    requirements[unique_name] = requirements.get(unique_name, 0) + needed
            if requirements:
                result[parent_name] = min(
                    counts.get(unique_name, counts.get(self._name_for_unique_name(unique_name, basic_items), 0)) // needed
                    for unique_name, needed in requirements.items()
                )
        return result

    @staticmethod
    def _inventory_counts(payload: Any) -> dict[str, int]:
        counts: dict[str, int] = {}

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                name = next((value.get(key) for key in ("ItemType", "ItemId", "itemType", "itemId", "uniqueName", "name", "Type") if isinstance(value.get(key), str)), None)
                count = next((value.get(key) for key in ("ItemCount", "Count", "count", "amount", "Amount", "quantity") if isinstance(value.get(key), int)), None)
                if name and count is not None:
                    counts[name] = max(counts.get(name, 0), count)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(payload)
        return counts

    @staticmethod
    def _full_material_requirements(component: dict[str, Any], multiplier: int = 1) -> dict[str, int]:
        if not isinstance(component, dict):
            return {}
        unique_name = component.get("uniqueName")
        if not isinstance(unique_name, str):
            return {}
        needed = int(component.get("neededCount", 1) or 1) * multiplier
        children = component.get("components", []) or []
        tradeable = bool(component.get("tradeable", component.get("tradable", False)))
        component_type = component.get("componentType")
        if tradeable or not children or component_type == 2:
            return {unique_name: needed}
        requirements: dict[str, int] = {}
        for child in children:
            for child_unique_name, child_needed in AlecaAdapter._full_material_requirements(child, needed).items():
                requirements[child_unique_name] = requirements.get(child_unique_name, 0) + child_needed
        return requirements

    @staticmethod
    def _name_for_unique_name(unique_name: str, basic_items: dict[str, dict[str, Any]]) -> str:
        value = basic_items.get(unique_name, {})
        name = value.get("name") if isinstance(value, dict) else None
        return name if isinstance(name, str) else unique_name

    @staticmethod
    def _merge_crafting_parents_with_relic_rewards(
        crafting_items: list[dict[str, Any]],
        basic_items: dict[str, dict[str, Any]],
        market_names: dict[str, str],
        vault_state: dict[str, bool],
    ) -> list[dict[str, Any]]:
        parents = [item for item in crafting_items if item["component_type"] == "parent"]
        parent_names = {item["name"] for item in parents}
        crafting_by_name = {item["name"]: item for item in crafting_items if item["component_type"] != "parent"}
        basic_by_name = {
            value.get("name"): (unique_name, value)
            for unique_name, value in basic_items.items()
            if isinstance(value, dict) and isinstance(value.get("name"), str)
        }
        rows: dict[str, dict[str, Any]] = {item["unique_name"]: item for item in parents}
        for item in crafting_items:
            if item.get("component_type") == "nested_prime_requirement":
                rows[item["unique_name"]] = item
        for reward_name in sorted(market_names):
            parent_name = AlecaAdapter._parent_name_from_name(reward_name)
            if parent_name not in parent_names:
                continue
            existing = crafting_by_name.get(reward_name)
            if existing is None and reward_name.endswith(" Blueprint"):
                existing = crafting_by_name.get(reward_name[: -len(" Blueprint")])
            if existing:
                row = dict(existing)
                row["name"] = reward_name
            else:
                basic_match = basic_by_name.get(reward_name)
                if basic_match is None and reward_name.endswith(" Blueprint"):
                    basic_match = basic_by_name.get(reward_name[: -len(" Blueprint")])
                if not basic_match:
                    continue
                unique_name, basic = basic_match
                row = {
                    "unique_name": unique_name,
                    "name": reward_name,
                    "category": "prime_craft",
                    "parent_name": parent_name,
                    "component_type": "relic_reward",
                    "vaulted": False,
                    "tradable": True,
                    "required_count": 1,
                    "image": basic.get("pic") or basic.get("image"),
                }
            row["parent_name"] = parent_name
            row["vaulted"] = vault_state.get(reward_name, False)
            rows[row["unique_name"]] = row
        return list(rows.values())

    @staticmethod
    def _parent_name_from_name(name: str) -> str:
        match = re.match(r"^(.*? Prime)(?:\s|$)", name)
        return match.group(1) if match else name

    @staticmethod
    def _basic_items(path: Path) -> dict[str, dict[str, Any]]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {}
        items = payload.get("items", {}) if isinstance(payload, dict) else {}
        return items if isinstance(items, dict) else {}

    @staticmethod
    def _extract_crafting_reference_items(path: Path, basic_items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return []
        crafts = payload.get("craftsByUUID", {}) if isinstance(payload, dict) else {}
        if not isinstance(crafts, dict):
            return []

        rows: dict[str, dict[str, Any]] = {}
        for craft in crafts.values():
            if not isinstance(craft, dict):
                continue
            parent_name = craft.get("name")
            parent_unique = craft.get("uniqueName")
            if not isinstance(parent_name, str) or "Prime" not in parent_name or not isinstance(parent_unique, str):
                continue
            parent_basic = basic_items.get(parent_unique, {})
            rows[parent_unique] = {
                "unique_name": parent_unique,
                "name": parent_name,
                "category": "prime_craft",
                "parent_name": parent_name,
                "component_type": "parent",
                "vaulted": False,
                "tradable": True,
                "required_count": 1,
                "image": parent_basic.get("pic") or parent_basic.get("image"),
            }
            for component in craft.get("components", []) or []:
                AlecaAdapter._collect_tradeable_components(rows, component, parent_name, basic_items, None)
            AlecaAdapter._collect_nested_prime_requirements(rows, craft, parent_name, parent_unique, basic_items, crafts)
        return list(rows.values())

    @staticmethod
    def _collect_nested_prime_requirements(
        rows: dict[str, dict[str, Any]],
        craft: dict[str, Any],
        parent_name: str,
        parent_unique: str,
        basic_items: dict[str, dict[str, Any]],
        crafts: dict[str, Any],
    ) -> None:
        required: dict[str, dict[str, Any]] = {}
        for component in craft.get("components", []) or []:
            if not isinstance(component, dict):
                continue
            unique_name = component.get("uniqueName")
            if not isinstance(unique_name, str):
                continue
            basic = basic_items.get(unique_name, {})
            display_name = basic.get("name")
            if (
                isinstance(display_name, str)
                and "Prime" in display_name
                and display_name != parent_name
                and unique_name in crafts
                and not bool(component.get("tradeable", component.get("tradable", False)))
            ):
                row = required.setdefault(
                    unique_name,
                    {
                        "unique_name": f"{parent_unique}#requires#{unique_name}",
                        "name": display_name,
                        "category": "prime_craft",
                        "parent_name": parent_name,
                        "component_type": "nested_prime_requirement",
                        "vaulted": False,
                        "tradable": True,
                        "required_count": 0,
                        "image": basic.get("pic") or basic.get("image"),
                    },
                )
                row["required_count"] += int(component.get("neededCount", 1) or 1)
        rows.update({row["unique_name"]: row for row in required.values()})

    @staticmethod
    def _collect_tradeable_components(
        rows: dict[str, dict[str, Any]],
        component: dict[str, Any],
        parent_name: str,
        basic_items: dict[str, dict[str, Any]],
        display_from_parent: dict[str, Any] | None,
    ) -> None:
        if not isinstance(component, dict):
            return
        unique_name = component.get("uniqueName")
        is_tradeable = bool(component.get("tradeable", component.get("tradable", False)))
        basic = basic_items.get(unique_name, {}) if isinstance(unique_name, str) else {}
        display_basic = display_from_parent or basic
        display_name = display_basic.get("name")
        if is_tradeable and isinstance(unique_name, str) and isinstance(display_name, str) and "Prime" in display_name:
            rows[unique_name] = {
                "unique_name": unique_name,
                "name": display_name,
                "category": "prime_craft",
                "parent_name": parent_name,
                "component_type": component.get("componentType"),
                "vaulted": False,
                "tradable": True,
                "required_count": int(component.get("neededCount", 1) or 1),
                "image": display_basic.get("pic") or display_basic.get("image"),
            }
        child_display = display_basic if not is_tradeable and isinstance(display_name, str) and "Prime" in display_name else None
        for child in component.get("components", []) or []:
            AlecaAdapter._collect_tradeable_components(rows, child, parent_name, basic_items, child_display)

    @staticmethod
    def _market_url_names_by_reward_name(path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        try:
            relics = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {}
        names: dict[str, str] = {}
        if not isinstance(relics, list):
            return names
        for relic in relics:
            if not isinstance(relic, dict):
                continue
            for reward in relic.get("rewards", []) or []:
                if not isinstance(reward, dict):
                    continue
                reward_item = reward.get("item") or {}
                if not isinstance(reward_item, dict):
                    continue
                name = reward_item.get("name")
                market = reward_item.get("warframeMarket") or {}
                url_name = market.get("urlName") if isinstance(market, dict) else None
                if isinstance(name, str) and isinstance(url_name, str) and name and url_name:
                    names.setdefault(name, url_name)
        return names

    @staticmethod
    def _vault_state_by_reward_name(path: Path) -> dict[str, bool]:
        if not path.exists():
            return {}
        try:
            relics = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {}
        seen: dict[str, dict[str, bool]] = {}
        if not isinstance(relics, list):
            return {}
        for relic in relics:
            if not isinstance(relic, dict):
                continue
            has_drop_locations = bool(relic.get("locations"))
            for reward in relic.get("rewards", []) or []:
                if not isinstance(reward, dict):
                    continue
                reward_item = reward.get("item") or {}
                if not isinstance(reward_item, dict):
                    continue
                name = reward_item.get("name")
                if not isinstance(name, str) or "Prime" not in name:
                    continue
                state = seen.setdefault(name, {"active": False, "relic": False})
                state["relic"] = True
                state["active"] = state["active"] or has_drop_locations
        return {name: not state["active"] for name, state in seen.items() if state["relic"]}

    @staticmethod
    def _extract_reference_items(payload: Any, category: str) -> list[dict[str, Any]]:
        source = payload.get("items", payload) if isinstance(payload, dict) else payload
        if not isinstance(source, dict):
            return []
        rows = []
        for unique_name, value in source.items():
            if not isinstance(value, dict):
                continue
            name = value.get("name") or value.get("item_name")
            if not name or "Prime" not in name:
                continue
            rows.append(
                {
                    "unique_name": str(unique_name),
                    "name": str(name),
                    "category": category,
                    "parent_name": value.get("parentName") or value.get("setName"),
                    "component_type": value.get("componentType") or value.get("type"),
                    "vaulted": bool(value.get("vaulted", False)),
                    "tradable": bool(value.get("tradeable", value.get("tradable", True))),
                    "required_count": int(value.get("neededCount", value.get("requiredCount", 1)) or 1),
                    "image": value.get("pic") or value.get("image"),
                }
            )
        return rows

    @staticmethod
    def _parse_trade_processed(line: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        match = re.search(r"ts:\s*([^,]+), tx:\s*(\d+), rx:\s*(\d+), user:\s*([^,\s]+)", line)
        if match:
            try:
                result["traded_at"] = datetime.strptime(match.group(1), "%m/%d/%Y %H:%M:%S")
            except ValueError:
                result["traded_at"] = None
            result["partner"] = match.group(4).strip("\ue000\ue005")
        class_match = re.search(r"Classification:\s*(\w+)", line)
        if class_match:
            result["classification"] = class_match.group(1)
        return result

