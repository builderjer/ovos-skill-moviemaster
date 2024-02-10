import unittest
from typing import Optional
from os import environ
from os.path import isdir
from shutil import rmtree
from pathlib import Path

from ovos_utils.log import LOG
from ovos_utils.messagebus import FakeBus
from ovos_config.config import update_mycroft_config, Configuration
from ovos_workshop.skills.base import BaseSkill
from ovos_workshop.skill_launcher import PluginSkillLoader, SkillLoader
from ovos_plugin_manager.skills import find_skill_plugins


def get_skill_object(bus: FakeBus, path: str = "", 
                     skill_id: str = "", config_patch: Optional[dict] = None) -> BaseSkill:
    """
    Get an initialized skill object laoded from path or using the plugin manager.
    @param bus: FakeBus instance to bind to skill for testing
    @param path: directory path the skill should be loaded from
    @param skill_id: skill_id to initialize skill with
    @param config_patch: Configuration update to apply
    @returns: Initialized skill object
    """
    if config_patch:
        user_config = update_mycroft_config(config_patch)
        if user_config not in Configuration.xdg_configs:
            Configuration.xdg_configs.append(user_config)
    if path:
        if not isdir(path):
            raise FileNotFoundError(path)
        LOG.info(f"Loading local skill from: {path}")
        loader = SkillLoader(bus, path, skill_id)
        if loader.load():
            return loader.instance
    plugins = find_skill_plugins()
    if skill_id not in plugins:
        raise ValueError(f"Requested skill not found: {skill_id}; available skills: {list(plugins.keys())}")
    else:
        LOG.info(f"Loading skill from plugin: {skill_id}")
    plugin = plugins[skill_id]
    skill = plugin(bus=bus, skill_id=skill_id)
    return skill


class TestSkillLoading(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.skill_id = environ.get("TEST_SKILL_ENTRYPOINT_NAME")
        self.path = str(Path(environ.get("TEST_SKILL_PATH")))

    def test_from_plugin(self):
        bus = FakeBus()
        skill = get_skill_object(bus, skill_id=self.skill_id)
        self.assertEqual(skill.bus, bus)
        self.assertEqual(skill.root_dir, self.path)

    def test_from_loader(self):
        bus = FakeBus()
        skill = get_skill_object(bus, path=self.path)
        self.assertEqual(skill.bus, bus)
        self.assertEqual(skill.root_dir, self.path)

    def test_from_plugin_loader(self):
        bus = FakeBus()
        loader = PluginSkillLoader(bus, self.skill_id)
        for skill_id, plug in find_skill_plugins().items():
            if skill_id == self.skill_id:
                loader.load(plug)
                break
        else:
            raise RuntimeError("plugin not found")

        self.assertEqual(loader.skill_id, self.skill_id)
        self.assertEqual(loader.instance.bus, bus)
        self.assertEqual(loader.instance.skill_id, self.skill_id)

if __name__ == "__main__":
    unittest.main()