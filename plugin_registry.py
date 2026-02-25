import importlib
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


__all__ = [
    "PluginSkill",
    "get_skill_definitions",
    "get_skill",
    "get_service_instances",
]
