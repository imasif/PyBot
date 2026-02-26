import importlib
import inspect
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
SKILLS_DIR = Path(__file__).parent / "skills"


@dataclass
class PluginSkill:
    slug: str
    name: str
    module: str
    class_name: str
    description: str = ""
    commands: List[str] = field(default_factory=list)
    exported_methods: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    enabled: bool = True
    instructions: str = ""
    init_args: List[Any] = field(default_factory=list)
    init_kwargs: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


def _resolve_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _infer_service_class_name(slug: str) -> str:
    normalized = (slug or "").replace("-", "_")
    parts = [part for part in normalized.split("_") if part]
    return f"{''.join(part.capitalize() for part in parts)}Service" if parts else "Service"


def _resolve_module_and_class(entry: Path, raw: Dict[str, Any], slug: str) -> tuple[Optional[str], Optional[str]]:
    module_path = raw.get("module")
    class_name = raw.get("class")

    if module_path and class_name:
        return str(module_path), str(class_name)

    service_file = entry / "service.py"
    if not service_file.exists():
        return (str(module_path), str(class_name)) if module_path and class_name else (None, None)

    inferred_module = f"skills.{entry.name}.service"
    inferred_class = _infer_service_class_name(slug)

    resolved_module = str(module_path) if module_path else inferred_module
    resolved_class = str(class_name) if class_name else inferred_class
    logger.info(
        "Skill %s missing explicit module/class; using %s.%s",
        slug,
        resolved_module,
        resolved_class,
    )
    return resolved_module, resolved_class


def load_skill_definitions(skills_dir: Optional[Path] = None) -> Dict[str, PluginSkill]:
    root = Path(skills_dir or SKILLS_DIR)
    definitions: Dict[str, PluginSkill] = {}

    if not root.exists():
        logger.debug("Skill directory missing: %s", root)
        return definitions

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue

        metadata_path = entry / "metadata.json"
        if not metadata_path.exists():
            logger.debug("Skipping %s because metadata.json is absent", entry)
            continue

        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not parse metadata for %s: %s", entry.name, exc)
            continue

        slug = (raw.get("slug") or entry.name).strip()
        module_path, class_name = _resolve_module_and_class(entry, raw, slug)
        if not module_path or not class_name:
            logger.warning("Skill %s missing module/class definition, skipping", slug)
            continue

        name = raw.get("name") or slug.replace("_", " ").title()
        description = (raw.get("description") or "").strip()
        commands = _resolve_list(raw.get("commands"))
        exported_methods = _resolve_list(raw.get("exports"))
        keywords = _resolve_list(raw.get("keywords"))
        init_args = _resolve_list(raw.get("init_args"))
        init_kwargs_raw = raw.get("init_kwargs") or {}
        init_kwargs = init_kwargs_raw if isinstance(init_kwargs_raw, dict) else {}
        enabled = bool(raw.get("enabled", True))

        instructions_file = raw.get("instructions_file", "instructions.md")
        instructions_path = entry / instructions_file
        instructions = ""
        if instructions_path.exists():
            instructions = instructions_path.read_text(encoding="utf-8").strip()

        definitions[slug] = PluginSkill(
            slug=slug,
            name=name,
            module=module_path,
            class_name=class_name,
            description=description,
            commands=[str(item) for item in commands if item],
            exported_methods=[str(item) for item in exported_methods if item],
            keywords=[str(item) for item in keywords if item],
            enabled=enabled,
            instructions=instructions,
            init_args=init_args,
            init_kwargs=init_kwargs,
            metadata=raw,
        )

    return definitions


def instantiate_service(skill: PluginSkill) -> Optional[Any]:
    try:
        module = importlib.import_module(skill.module)
        klass = getattr(module, skill.class_name)
        return klass(*skill.init_args, **skill.init_kwargs)
    except Exception as exc:
        logger.error("Failed to instantiate skill %s (%s): %s", skill.slug, skill.name, exc)
        return None


_skill_cache: Optional[Dict[str, PluginSkill]] = None
_instance_cache: Optional[Dict[str, Any]] = None


def get_skill_definitions() -> Dict[str, PluginSkill]:
    global _skill_cache
    if _skill_cache is None:
        _skill_cache = load_skill_definitions()
    return _skill_cache


def get_skill(slug: str) -> Optional[PluginSkill]:
    return get_skill_definitions().get(slug)


def get_service_instances() -> Dict[str, Any]:
    global _instance_cache
    if _instance_cache is None:
        _instance_cache = {}
        for slug, skill in get_skill_definitions().items():
            if not skill.enabled:
                continue
            instance = instantiate_service(skill)
            if instance is not None:
                _instance_cache[slug] = instance
    return _instance_cache


def get_service_method_exports(slug: Optional[str] = None, include_private: bool = False) -> Dict[str, Dict[str, Any]]:
    exports: Dict[str, Dict[str, Any]] = {}
    services = get_service_instances()
    skills = get_skill_definitions()

    for service_slug, instance in services.items():
        if slug and service_slug != slug:
            continue

        skill = skills.get(service_slug)
        method_names = list(((skill.exported_methods if skill else []) or []))

        if not method_names and skill:
            method_names = discover_service_commands(skill.module, skill.class_name)

        if not method_names:
            method_names = list((skill.commands if skill else []) or [])

        if not method_names:
            method_names = [
                name for name in dir(instance)
                if callable(getattr(instance, name, None))
                and (include_private or not name.startswith('_'))
            ]

        method_map: Dict[str, Any] = {}
        for name in method_names:
            method = getattr(instance, name, None)
            if callable(method) and (include_private or not name.startswith('_')):
                method_map[name] = method

        exports[service_slug] = method_map

    return exports


def invoke_service_method(
    service_name: str,
    method_name: str,
    *args,
    default: Any = None,
    include_private: bool = False,
    **kwargs,
) -> Any:
    exports = get_service_method_exports(slug=service_name, include_private=include_private)
    methods = exports.get(service_name, {})
    method = methods.get(method_name)

    if not callable(method):
        instance = get_service_instances().get(service_name)
        method = getattr(instance, method_name, None) if instance is not None else None
        if callable(method) and not include_private and method_name.startswith('_'):
            method = None

    if not callable(method):
        return default

    try:
        return method(*args, **kwargs)
    except Exception as exc:
        logger.error("Failed to invoke %s.%s: %s", service_name, method_name, exc)
        return default


def invoke_first_available_method(
    method_name: str,
    *args,
    default: Any = None,
    include_private: bool = False,
    **kwargs,
) -> Any:
    exports = get_service_method_exports(include_private=include_private)
    instances = get_service_instances()
    for service_name, instance in instances.items():
        methods = exports.get(service_name, {})
        method = methods.get(method_name)
        if not callable(method):
            method = getattr(instance, method_name, None)
            if callable(method) and not include_private and method_name.startswith('_'):
                method = None
        if not callable(method):
            continue
        try:
            result = method(*args, **kwargs)
        except Exception as exc:
            logger.error("Failed to invoke %s.%s: %s", service_name, method_name, exc)
            continue
        if result is not None:
            return result
    return default


def discover_service_commands(module_path: str, class_name: str) -> List[str]:
    try:
        module = importlib.import_module(module_path)
        klass = getattr(module, class_name)
    except Exception as exc:
        logger.warning("Could not import %s.%s for command discovery: %s", module_path, class_name, exc)
        return []

    module_registered = _resolve_list(getattr(module, 'SERVICE_SKILL_COMMANDS', None))
    if module_registered:
        return sorted({str(item) for item in module_registered if item and not str(item).startswith('_')})

    class_registered = _resolve_list(getattr(klass, 'SKILL_COMMANDS', None))
    if class_registered:
        return sorted({str(item) for item in class_registered if item and not str(item).startswith('_')})

    commands: List[str] = []
    for name, attr in klass.__dict__.items():
        if name.startswith("_"):
            continue
        if isinstance(attr, (staticmethod, classmethod)):
            commands.append(name)
            continue
        if inspect.isfunction(attr):
            commands.append(name)

    return sorted(set(commands))


def sync_skill_metadata_commands(skills_dir: Optional[Path] = None, only_missing: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    root = Path(skills_dir or SKILLS_DIR)
    summary = {
        "updated": [],
        "skipped": [],
        "failed": [],
    }

    if not root.exists():
        logger.warning("Skill directory missing for sync: %s", root)
        return summary

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue

        metadata_path = entry / "metadata.json"
        if not metadata_path.exists():
            summary["skipped"].append(entry.name)
            continue

        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not parse metadata for %s: %s", entry.name, exc)
            summary["failed"].append(entry.name)
            continue

        slug = (raw.get("slug") or entry.name).strip()
        module_path, class_name = _resolve_module_and_class(entry, raw, slug)
        if not module_path or not class_name:
            summary["failed"].append(entry.name)
            continue

        existing = _resolve_list(raw.get("commands"))
        if only_missing and existing:
            summary["skipped"].append(entry.name)
            continue

        discovered = discover_service_commands(module_path, class_name)
        if not discovered:
            summary["skipped"].append(entry.name)
            continue

        if existing == discovered:
            summary["skipped"].append(entry.name)
            continue

        raw["commands"] = discovered
        if not dry_run:
            metadata_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        summary["updated"].append(entry.name)

    return summary


def _is_config_value_set(config_module: Any, key: str) -> bool:
    if not key:
        return False
    value = getattr(config_module, key, None)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def get_plugin_api_status(config_module: Any, include_disabled: bool = False) -> List[str]:
    statuses: List[str] = []

    for slug, skill in get_skill_definitions().items():
        if not include_disabled and not skill.enabled:
            continue

        metadata = skill.metadata or {}
        required_config = [str(item) for item in _resolve_list(metadata.get("required_config")) if item]
        if not required_config:
            continue

        status_label = str(metadata.get("status_label") or skill.name or slug).strip()
        service_ready = all(_is_config_value_set(config_module, key) for key in required_config)
        statuses.append(f"{status_label} {'✅' if service_ready else '❌'}")

    return statuses


def get_required_config_keys(include_disabled: bool = False) -> List[str]:
    keys: List[str] = []

    for _, skill in get_skill_definitions().items():
        if not include_disabled and not skill.enabled:
            continue

        metadata = skill.metadata or {}
        required_config = [str(item) for item in _resolve_list(metadata.get("required_config")) if item]
        keys.extend(required_config)

    seen = set()
    ordered = []
    for key in keys:
        upper_key = key.strip().upper()
        if not upper_key or upper_key in seen:
            continue
        seen.add(upper_key)
        ordered.append(upper_key)

    return ordered


def get_optional_config_keys(include_disabled: bool = False) -> List[str]:
    keys: List[str] = []

    for _, skill in get_skill_definitions().items():
        if not include_disabled and not skill.enabled:
            continue

        metadata = skill.metadata or {}
        optional_config = [str(item) for item in _resolve_list(metadata.get("optional_config")) if item]
        keys.extend(optional_config)

    seen = set()
    ordered = []
    for key in keys:
        upper_key = key.strip().upper()
        if not upper_key or upper_key in seen:
            continue
        seen.add(upper_key)
        ordered.append(upper_key)

    return ordered


__all__ = [
    "PluginSkill",
    "get_skill_definitions",
    "get_skill",
    "get_service_instances",
    "get_service_method_exports",
    "invoke_service_method",
    "invoke_first_available_method",
    "discover_service_commands",
    "sync_skill_metadata_commands",
    "get_plugin_api_status",
    "get_required_config_keys",
    "get_optional_config_keys",
]
