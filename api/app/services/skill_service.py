"""技能（Skill）业务服务：CRUD + 内置模板 + zip 导入(含脚本) + 市场 + fork。

技能归属于 Persona（角色），每个角色有独立的技能库。
导入时 SKILL.md 声明工具及脚本，解压到 storage/skills/{skill_id}/，
Agent 运行时通过 skill_tool_executor 动态调用脚本。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import uuid
import zipfile

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.models.skill_model import Skill
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.skill_repository import SkillRepository
from app.schemas.skill_schema import SkillConfig, SkillCreate, SkillUpdate
from app.services.skill_builtins import BUILTIN_SKILLS, get_builtin_skill

logger = get_logger(__name__)

MAX_SKILLS_PER_PERSONA = 50

# 技能脚本存储根目录
SKILL_STORAGE_ROOT = os.path.join(settings.storage_dir, "skills")


# ── SKILL.md 解析（模块级辅助函数）──

def _parse_frontmatter_yaml(raw: str) -> dict:
    """解析精简 YAML frontmatter。兼容 Claude Code / Cursor / Continue 等主流 SKILL.md 格式。

    字段映射：
      name / description / icon
      tool_keys / allowed-tools → tool_keys（工具白名单）
      tools → 脚本工具声明列表
      triggers → config.triggers（快捷触发词，自动转 quick_prompts）
      model → config.model（可选）
    """
    meta: dict = {}
    current_key: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and not stripped.startswith(" ") and not stripped.startswith("-"):
            kv = stripped.split(":", 1)
            key = kv[0].strip()
            val = kv[1].strip()
            if val == "":
                meta[key] = []
                current_key = key
            else:
                meta[key] = val
                current_key = None
        elif stripped.startswith("- ") and current_key:
            item = stripped[2:].strip().strip('"').strip("'")
            if isinstance(meta.get(current_key), list):
                meta[current_key].append(item)
        else:
            current_key = None

    # 别名兼容
    if "allowed-tools" in meta:
        raw_val = meta.pop("allowed-tools")
        meta.setdefault("tool_keys", raw_val if isinstance(raw_val, list) else [raw_val])

    if "tool_keys" in meta and not isinstance(meta["tool_keys"], list):
        meta["tool_keys"] = [meta["tool_keys"]]
    meta.setdefault("tool_keys", [])
    meta.setdefault("icon", "🧩")
    meta.setdefault("description", "")
    return meta


def _split_skill_body(body: str) -> tuple[str, dict]:
    """从 SKILL.md 正文分离 prompt 和配置块。返回 (prompt_text, config_dict)。"""
    import re

    prompt_text = body
    config: dict = {"quick_prompts": [], "few_shots": []}

    qp_match = re.search(r"\n##\s*快捷提问\s*\n", body)
    if qp_match:
        prompt_text = body[: qp_match.start()]
        qp_section = body[qp_match.end():]
        fs_match = re.search(r"\n##\s*Few-shot\s*示例\s*\n", qp_section)
        if fs_match:
            qp_text = qp_section[: fs_match.start()]
            fs_section = qp_section[fs_match.end():]
        else:
            qp_text = qp_section
            fs_section = ""
        for line in qp_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                config["quick_prompts"].append(stripped[2:].strip())
    else:
        fs_match = re.search(r"\n##\s*Few-shot\s*示例\s*\n", body)
        if fs_match:
            prompt_text = body[: fs_match.start()]
            fs_section = body[fs_match.end():]
        else:
            fs_section = ""

    if fs_section:
        fs_blocks = re.split(r"\n###\s*输入\s*\n", fs_section)
        for block in fs_blocks[1:]:
            io_parts = re.split(r"\n###\s*输出\s*\n", block, maxsplit=1)
            inp = io_parts[0].strip() if len(io_parts) > 0 else ""
            out = io_parts[1].strip() if len(io_parts) > 1 else ""
            if inp or out:
                config["few_shots"].append({"input": inp, "output": out})

    return prompt_text.strip(), config


def _parse_frontmatter(md_text: str) -> tuple[dict, str]:
    """解析 SKILL.md frontmatter。"""
    text = md_text.strip()
    if not text.startswith("---"):
        raise BizError("SKILL.md 必须以 YAML frontmatter（---）开头", code=4070)
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise BizError("SKILL.md frontmatter 不完整", code=4070)
    meta = _parse_frontmatter_yaml(parts[1].strip())
    if "name" not in meta:
        raise BizError("SKILL.md frontmatter 缺少必填字段 name", code=4070)
    return meta, parts[2].strip()


# ── 技能脚本文件系统操作 ──

def _skill_dir(skill_id: uuid.UUID) -> str:
    return os.path.join(SKILL_STORAGE_ROOT, str(skill_id))


def _extract_scripts(zf: zipfile.ZipFile, skill_id: uuid.UUID) -> str:
    """将 zip 中 scripts/ 目录解压到 storage/skills/{skill_id}/。

    兼容多种目录结构：
      scripts/analyze.py              ← 扁平
      my-skill/scripts/analyze.py     ← 嵌套
    """
    dst = _skill_dir(skill_id)
    os.makedirs(dst, exist_ok=True)

    # 找到 SKILL.md 并写入
    skill_md_names = [n for n in zf.namelist() if n.endswith("SKILL.md")]
    for name in skill_md_names:
        # 提取到 dst 根，去掉前缀目录
        target = os.path.join(dst, "SKILL.md")
        with zf.open(name) as src:
            with open(target, "wb") as out:
                out.write(src.read())

    # 解压 scripts/ 目录（去掉可能的前缀目录）
    script_names = [n for n in zf.namelist() if "scripts/" in n and not n.endswith("/")]
    for name in script_names:
        # 取 scripts/ 之后的部分作为目标路径
        idx = name.index("scripts/")
        rel = name[idx:]  # scripts/analyze.py
        target = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(name) as src:
            with open(target, "wb") as out:
                out.write(src.read())

    return dst


def _remove_scripts(skill_id: uuid.UUID) -> None:
    """删除技能对应的脚本目录。"""
    dst = _skill_dir(skill_id)
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)


# ── SkillService ──

class SkillService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SkillRepository(session)

    # ── CRUD ──

    async def list(self, persona_id: uuid.UUID) -> list[Skill]:
        return await self.repo.list_by_persona(persona_id)

    async def _get_or_404(self, persona_id: uuid.UUID, skill_id: uuid.UUID) -> Skill:
        skill = await self.repo.get(persona_id, skill_id)
        if skill is None:
            raise BizError("技能不存在", code=4050, status_code=404)
        return skill

    async def _validate_kb(self, user_id: uuid.UUID, kb_id: str | None) -> uuid.UUID | None:
        if not kb_id:
            return None
        try:
            kb_uuid = uuid.UUID(str(kb_id))
        except (ValueError, TypeError) as e:
            raise BizError("知识库 id 非法", code=4051) from e
        kb = await KnowledgeBaseRepository(self.session).get(user_id, kb_uuid)
        if kb is None:
            raise BizError("绑定的知识库不存在", code=4052, status_code=404)
        return kb_uuid

    async def create(self, persona_id: uuid.UUID, user_id: uuid.UUID, body: SkillCreate) -> Skill:
        if await self.repo.count(persona_id) >= MAX_SKILLS_PER_PERSONA:
            raise BizError(f"技能数量已达上限（{MAX_SKILLS_PER_PERSONA}）", code=4053)
        kb_uuid = await self._validate_kb(user_id, body.kb_id)
        skill = Skill(
            persona_id=persona_id,
            name=body.name.strip(),
            description=body.description or "",
            icon=body.icon or "🧩",
            prompt=body.prompt or "",
            tool_keys=body.tool_keys or [],
            kb_id=kb_uuid,
            enabled=body.enabled,
            config=body.config.model_dump(),
            source="custom",
        )
        created = await self.repo.add(skill)
        logger.info("创建技能: persona=%s skill=%s name=%s", persona_id, created.id, created.name)
        return created

    async def update(
        self, persona_id: uuid.UUID, user_id: uuid.UUID,
        skill_id: uuid.UUID, body: SkillUpdate,
    ) -> Skill:
        skill = await self._get_or_404(persona_id, skill_id)
        fields = body.model_dump(exclude_unset=True)
        if "name" in fields and fields["name"] is not None:
            skill.name = fields["name"].strip()
        if "description" in fields and fields["description"] is not None:
            skill.description = fields["description"]
        if "icon" in fields and fields["icon"] is not None:
            skill.icon = fields["icon"]
        if "prompt" in fields and fields["prompt"] is not None:
            skill.prompt = fields["prompt"]
        if "tool_keys" in fields and fields["tool_keys"] is not None:
            skill.tool_keys = fields["tool_keys"]
        if "kb_id" in fields:
            skill.kb_id = await self._validate_kb(user_id, fields["kb_id"])
        if "enabled" in fields and fields["enabled"] is not None:
            skill.enabled = fields["enabled"]
        if "config" in fields and fields["config"] is not None:
            cfg = body.config
            skill.config = cfg.model_dump() if isinstance(cfg, SkillConfig) else cfg
        if "is_public" in fields and fields["is_public"] is not None:
            skill.is_public = fields["is_public"]
        return await self.repo.save(skill)

    async def delete(self, persona_id: uuid.UUID, skill_id: uuid.UUID) -> None:
        skill = await self._get_or_404(persona_id, skill_id)
        _remove_scripts(skill_id)
        await self.repo.delete(skill)
        logger.info("删除技能: persona=%s skill=%s", persona_id, skill_id)

    # ── 内置模板 ──

    async def add_builtin(self, persona_id: uuid.UUID, key: str) -> Skill:
        tpl = get_builtin_skill(key)
        if tpl is None:
            raise BizError("内置技能模板不存在", code=4054, status_code=404)
        if await self.repo.count(persona_id) >= MAX_SKILLS_PER_PERSONA:
            raise BizError(f"技能数量已达上限（{MAX_SKILLS_PER_PERSONA}）", code=4053)
        skill = Skill(
            persona_id=persona_id,
            name=tpl["name"],
            description=tpl.get("description", ""),
            icon=tpl.get("icon", "🧩"),
            prompt=tpl.get("prompt", ""),
            tool_keys=list(tpl.get("tool_keys", [])),
            kb_id=None,
            config=dict(tpl.get("config", {})),
            is_builtin=True,
            source="builtin",
        )
        return await self.repo.add(skill)

    @staticmethod
    def list_builtins() -> list[dict]:
        return [
            {
                "key": s["key"], "name": s["name"],
                "description": s.get("description", ""), "icon": s.get("icon", "🧩"),
                "prompt": s.get("prompt", ""),
                "tool_keys": list(s.get("tool_keys", [])),
                "config": dict(s.get("config", {})),
            }
            for s in BUILTIN_SKILLS
        ]

    # ── zip 导入（含脚本解压）──

    @staticmethod
    def _parse_skill_zip(data: bytes) -> tuple[dict, str, str]:
        """解析 .zip 技能包，兼容多种目录结构和主流 SKILL.md 格式。

        支持：
          SKILL.md                    ← 扁平
          my-skill/SKILL.md           ← 单层目录
          **/SKILL.md                 ← 任意嵌套，取第一个
        兼容 Claude Code / Cursor / Continue 的 frontmatter。
        """
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                all_names = [n for n in zf.namelist() if n.endswith("SKILL.md")]
                if not all_names:
                    raise BizError("压缩包缺少 SKILL.md", code=4070)
                # 优先扁平结构
                md_name = "SKILL.md" if "SKILL.md" in all_names else all_names[0]
                md_text = zf.read(md_name).decode("utf-8")
                meta, body = _parse_frontmatter(md_text)
                prompt_text, config = _split_skill_body(body)

                # triggers -> quick_prompts（Claude Code 兼容）
                triggers = meta.get("triggers", [])
                if isinstance(triggers, list) and triggers:
                    qp = config.get("quick_prompts", [])
                    config["quick_prompts"] = qp + [str(t) for t in triggers if t]
                if "model" in meta:
                    config["model"] = meta["model"]

                # tools（脚本声明）
                tools_def = meta.get("tools", [])
                if isinstance(tools_def, list):
                    config["tools"] = tools_def
                elif isinstance(tools_def, dict):
                    config["tools"] = [tools_def]

                manifest = {
                    "name": str(meta.get("name", ""))[:64],
                    "description": str(meta.get("description", ""))[:256],
                    "icon": str(meta.get("icon", ""))[:16],
                    "tool_keys": list(meta.get("tool_keys", [])),
                    "config": config,
                }

                fingerprint = json.dumps(
                    {k: manifest.get(k) for k in ("name", "description")},
                    sort_keys=True, ensure_ascii=False,
                ) + prompt_text
                import_hash = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
                return manifest, prompt_text, import_hash
        except BizError:
            raise
        except zipfile.BadZipFile as e:
            raise BizError("不是有效的 zip 文件", code=4070) from e
        except Exception as e:
            logger.warning("技能 zip 解压失败: %s", e)
            raise BizError(f"解压失败：{e}", code=4070) from e

    async def import_zip(
        self, persona_id: uuid.UUID, user_id: uuid.UUID, data: bytes
    ) -> tuple[Skill, bool]:
        """导入 .soulskill.zip：解析 SKILL.md + 解压 scripts/ → 返回 (skill, existing)。"""
        manifest, prompt_text, import_hash = self._parse_skill_zip(data)

        existing = await self.repo.get_by_import_hash(persona_id, import_hash)
        if existing is not None:
            logger.info("技能 zip 去重命中: persona=%s hash=%s", persona_id, import_hash[:12])
            return existing, True

        if await self.repo.count(persona_id) >= MAX_SKILLS_PER_PERSONA:
            raise BizError(f"技能数量已达上限（{MAX_SKILLS_PER_PERSONA}）", code=4053)

        config = manifest.get("config", {})
        kb_uuid = None
        if manifest.get("kb_id"):
            kb_uuid = await self._validate_kb(user_id, manifest["kb_id"])

        skill = Skill(
            persona_id=persona_id,
            name=manifest.get("name", "未命名技能")[:64],
            description=manifest.get("description", "")[:256],
            icon=manifest.get("icon", "🧩")[:16],
            prompt=prompt_text,
            tool_keys=list(manifest.get("tool_keys", [])),
            kb_id=kb_uuid,
            config=config if isinstance(config, dict) else {},
            source="imported",
            import_hash=import_hash,
        )
        created = await self.repo.add(skill)

        # 解压脚本到磁盘
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                script_path = _extract_scripts(zf, created.id)
            created.storage_path = script_path
            await self.repo.save(created)
        except Exception as e:
            logger.warning("技能脚本解压失败: skill=%s err=%s", created.id, e)

        logger.info("导入技能: persona=%s name=%s hash=%s", persona_id, created.name, import_hash[:12])
        return created, False

    # ── 技能市场 ──

    async def list_marketplace(self, limit: int = 50, offset: int = 0) -> list[Skill]:
        """技能市场：所有 is_public=true 的技能。"""
        return await self.repo.list_public(limit=limit, offset=offset)

    async def fork(self, persona_id: uuid.UUID, user_id: uuid.UUID, skill_id: uuid.UUID) -> Skill:
        """从市场复制技能到指定角色（含脚本目录）。"""
        if await self.repo.count(persona_id) >= MAX_SKILLS_PER_PERSONA:
            raise BizError(f"技能数量已达上限（{MAX_SKILLS_PER_PERSONA}）", code=4053)

        src = await self.repo.get_any(skill_id)
        if src is None:
            raise BizError("技能不存在", code=4050, status_code=404)
        if not src.is_public:
            raise BizError("该技能未公开", code=4073)

        new_skill = Skill(
            persona_id=persona_id,
            name=src.name,
            description=src.description,
            icon=src.icon,
            prompt=src.prompt,
            tool_keys=list(src.tool_keys or []),
            kb_id=src.kb_id,
            config=dict(src.config or {}),
            source="marketplace",
            import_hash=src.import_hash,
        )
        created = await self.repo.add(new_skill)

        # 复制脚本目录
        if src.storage_path and os.path.isdir(src.storage_path):
            try:
                dst = _skill_dir(created.id)
                shutil.copytree(src.storage_path, dst)
                created.storage_path = dst
                await self.repo.save(created)
            except Exception as e:
                logger.warning("技能脚本复制失败: skill=%s err=%s", created.id, e)

        logger.info("fork 技能: src=%s dst=%s persona=%s", skill_id, created.id, persona_id)
        return created

    # ── 调用计数 ──

    async def record_call(self, skill_id: uuid.UUID) -> None:
        """技能被 Agent 调用时 +1。"""
        await self.repo.bump_call_count(skill_id)

    # ── 出参 ──

    @staticmethod
    def to_out_dict(skill: Skill) -> dict:
        return {
            "id": str(skill.id),
            "persona_id": str(skill.persona_id),
            "name": skill.name,
            "description": skill.description,
            "icon": skill.icon,
            "prompt": skill.prompt,
            "tool_keys": skill.tool_keys or [],
            "kb_id": str(skill.kb_id) if skill.kb_id else None,
            "enabled": skill.enabled,
            "config": skill.config or {},
            "source": skill.source,
            "is_builtin": skill.is_builtin,
            "is_public": skill.is_public,
            "call_count": skill.call_count,
        }
